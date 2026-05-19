"""GDELT 2.0 GKG crawler (P2.5).

Pulls the GDELT Global Knowledge Graph 15-minute CSV (gzipped) and emits
one ``RawEvent`` per row. Each row has location, theme, tone and document
URLs; the relevant projections for ``RawEvent`` are:

  RawEvent.source_id  = "gdelt"
  RawEvent.url        = first SOURCEURL
  RawEvent.title      = top theme(s)
  RawEvent.body       = "tone={tone:+.2f}; themes={themes[:5]}"
  RawEvent.event_ts   = parsed from CSV column 1 (DATE, yyyymmddhhmmss)
  RawEvent.lang       = "en"
  RawEvent.metadata   = full row keyed by column name; preserves lat/lon
                        so the geo dashboard (P5) can read it.

Cadence: every 15 minutes (matches GDELT's release schedule). The
``LATEST_FILE_URL`` endpoint tells us the most recent CSV name; we then
download, gunzip, parse, and yield. Failures (404 between releases, bad
gzip) are logged and yield nothing — the pipeline runs again in 15 min.
"""

from __future__ import annotations

import csv
import gzip
import io
import logging
import zipfile
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from ..types import RawEvent, SourceCfg

log = logging.getLogger(__name__)

LATEST_FILE_URL = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"
GDELT_GKG_COLUMNS = (
    "GKGRECORDID DATE SourceCollectionIdentifier SourceCommonName DocumentIdentifier "
    "Counts V2Counts Themes V2Themes Locations V2Locations Persons V2Persons "
    "Organizations V2Organizations V2Tone Dates GCAM SharingImage RelatedImages "
    "SocialImageEmbeds SocialVideoEmbeds Quotations AllNames Amounts TranslationInfo Extras"
).split()

UrlFetcher = Callable[[str], Awaitable[bytes]]


async def _httpx_fetch(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


def _parse_gdelt_date(raw: str) -> datetime:
    # GDELT v2 timestamps are 14-char yyyymmddhhmmss.
    return datetime.strptime(raw[:14], "%Y%m%d%H%M%S").replace(tzinfo=UTC)


def _first_location(raw_locations: str) -> tuple[float | None, float | None, str | None]:
    """V2Locations is `#` separated; each entry pipe-separated. Fields:
    Type|FullName|CountryCode|ADM1Code|ADM2Code|Lat|Long|FeatureID|...."""
    if not raw_locations:
        return None, None, None
    first = raw_locations.split("#", 1)[0]
    parts = first.split("|")
    if len(parts) < 7:
        return None, None, None
    try:
        lat = float(parts[5]) if parts[5] else None
        lon = float(parts[6]) if parts[6] else None
    except ValueError:
        lat, lon = None, None
    name = parts[1] or None
    return lat, lon, name


def _tone_from_v2(raw_tone: str) -> float | None:
    if not raw_tone:
        return None
    try:
        return float(raw_tone.split(",", 1)[0])
    except ValueError:
        return None


class GdeltCrawler:
    """Fetches the latest GDELT GKG file once per call. The pipeline calls
    ``fetch(source)`` every 15 min; idempotency comes from the hash gate
    keyed on ``GKGRECORDID``."""

    def __init__(self, fetch_url: UrlFetcher | None = None) -> None:
        self._fetch = fetch_url or _httpx_fetch

    async def _latest_gkg_url(self) -> str | None:
        raw = (await self._fetch(LATEST_FILE_URL)).decode("utf-8", errors="replace")
        for line in raw.splitlines():
            # Each line: "<size> <md5> <url>"; gkg files end in `.gkg.csv.zip`.
            parts = line.split()
            if len(parts) >= 3 and parts[2].endswith(".gkg.csv.zip"):
                return parts[2]
        return None

    async def fetch(self, source: SourceCfg) -> AsyncIterator[RawEvent]:
        url = source.url or await self._latest_gkg_url()
        if not url:
            log.warning("gdelt: no latest gkg file available")
            return

        try:
            blob = await self._fetch(url)
        except httpx.HTTPError as exc:
            log.warning("gdelt: fetch failed %s: %s", url, exc)
            return

        # GDELT files arrive as `.zip` containing one CSV. We support both
        # `.zip` and `.gz` to keep the fixture path simple in tests.
        try:
            if url.endswith(".zip"):
                with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                    name = zf.namelist()[0]
                    csv_bytes = zf.read(name)
            elif url.endswith(".gz"):
                csv_bytes = gzip.decompress(blob)
            else:
                csv_bytes = blob
        except (OSError, zipfile.BadZipFile) as exc:
            log.warning("gdelt: decompress failed %s: %s", url, exc)
            return

        reader = csv.reader(
            io.StringIO(csv_bytes.decode("utf-8", errors="replace")),
            delimiter="\t",
        )
        for row in reader:
            if len(row) < len(GDELT_GKG_COLUMNS):
                continue
            data: dict[str, Any] = dict(zip(GDELT_GKG_COLUMNS, row, strict=False))
            try:
                event_ts = _parse_gdelt_date(data["DATE"])
            except ValueError:
                continue
            lat, lon, place = _first_location(data.get("V2Locations") or "")
            tone = _tone_from_v2(data.get("V2Tone") or "")
            themes = (data.get("V2Themes") or "").split(";")[:5]
            doc_url = (data.get("DocumentIdentifier") or "").split("<")[0]
            yield RawEvent(
                source_id="gdelt",
                title=";".join(t.split(",", 1)[0] for t in themes if t)[:200] or "GDELT event",
                body=(
                    f"tone={tone if tone is not None else 0:+.2f}; "
                    f"place={place or '-'}; "
                    f"themes={','.join(t.split(',', 1)[0] for t in themes if t)[:300]}"
                ),
                url=doc_url or None,
                event_ts=event_ts,
                ingest_ts=datetime.now(UTC),
                lang="en",
                raw={
                    "gkg_record_id": data.get("GKGRECORDID"),
                    "lat": lat,
                    "lon": lon,
                    "tone": tone,
                    "themes": themes,
                    "raw_locations": data.get("V2Locations"),
                },
            )
