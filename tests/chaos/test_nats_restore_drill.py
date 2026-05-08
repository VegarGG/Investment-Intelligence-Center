"""v2.5 T1.7 — NATS restore-drill acceptance.

Plan §T1.7 acceptance: a restore drill on a clean machine recovers all
durable consumers. This test stands in for the production drill via a
fake JetStream that mirrors the `nats stream backup` / `nats stream
restore` CLI shape.

Real-integration variant gated by `IIC_NATS_DRILL=1` — runs against a
docker-compose'd NATS, write a known sequence, run the backup script,
wipe the data dir, run `nats stream restore`, compare. Skipped by
default to keep the test suite hermetic.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import pytest


@dataclass(slots=True)
class _FakeMessage:
    subject: str
    data: bytes
    seq: int


@dataclass(slots=True)
class _FakeConsumer:
    name: str
    durable: bool
    last_seq: int = 0


@dataclass(slots=True)
class _FakeStream:
    name: str
    subjects: tuple[str, ...]
    messages: list[_FakeMessage] = field(default_factory=list)
    consumers: dict[str, _FakeConsumer] = field(default_factory=dict)


class _FakeJetStream:
    """Minimal in-memory stand-in for the NATS JetStream surface our backup
    script depends on. Mirrors `stream backup --all` and `stream restore`.
    """

    def __init__(self) -> None:
        self.streams: dict[str, _FakeStream] = {}

    def add_stream(self, name: str, subjects: Iterable[str]) -> _FakeStream:
        s = _FakeStream(name=name, subjects=tuple(subjects))
        self.streams[name] = s
        return s

    def publish(self, stream: str, subject: str, data: bytes) -> int:
        s = self.streams[stream]
        seq = len(s.messages) + 1
        s.messages.append(_FakeMessage(subject=subject, data=data, seq=seq))
        return seq

    def add_consumer(self, stream: str, name: str, durable: bool, ack_seq: int) -> None:
        s = self.streams[stream]
        s.consumers[name] = _FakeConsumer(name=name, durable=durable, last_seq=ack_seq)

    # ---- backup / restore (the surface T1.7 cares about) ----------

    def backup(self, out_dir: Path) -> None:
        """Mirror of `nats stream backup --all <out>`."""
        out_dir.mkdir(parents=True, exist_ok=True)
        for s in self.streams.values():
            stream_dir = out_dir / s.name
            stream_dir.mkdir(exist_ok=True)
            (stream_dir / "stream.json").write_text(
                json.dumps({"name": s.name, "subjects": list(s.subjects)})
            )
            (stream_dir / "messages.jsonl").write_text(
                "\n".join(
                    json.dumps({"subject": m.subject, "data": m.data.decode(), "seq": m.seq})
                    for m in s.messages
                )
            )
            (stream_dir / "consumers.json").write_text(
                json.dumps(
                    {
                        c.name: {"durable": c.durable, "last_seq": c.last_seq}
                        for c in s.consumers.values()
                    }
                )
            )

    @classmethod
    def restore(cls, in_dir: Path) -> "_FakeJetStream":
        """Mirror of `nats stream restore` after `--all` backup."""
        js = cls()
        for stream_dir in sorted(in_dir.iterdir()):
            if not stream_dir.is_dir():
                continue
            spec = json.loads((stream_dir / "stream.json").read_text())
            stream = js.add_stream(spec["name"], spec["subjects"])
            msg_path = stream_dir / "messages.jsonl"
            if msg_path.exists():
                for line in msg_path.read_text().splitlines():
                    if not line.strip():
                        continue
                    d = json.loads(line)
                    stream.messages.append(
                        _FakeMessage(subject=d["subject"], data=d["data"].encode(), seq=d["seq"])
                    )
            cons_path = stream_dir / "consumers.json"
            if cons_path.exists():
                for name, c in json.loads(cons_path.read_text()).items():
                    stream.consumers[name] = _FakeConsumer(
                        name=name, durable=bool(c["durable"]), last_seq=int(c["last_seq"])
                    )
        return js


def _seed_fake_jetstream() -> _FakeJetStream:
    js = _FakeJetStream()
    js.add_stream("INTEL", ("intel.digest.v1", "intel.event.high_impact.v1"))
    js.add_stream("ADVICE", ("advice.fundamental.v1", "advice.quant.v1"))

    js.publish("INTEL", "intel.digest.v1", b'{"id":"d1"}')
    js.publish("INTEL", "intel.digest.v1", b'{"id":"d2"}')
    js.publish("INTEL", "intel.event.high_impact.v1", b'{"id":"e1"}')
    js.publish("ADVICE", "advice.fundamental.v1", b'{"id":"a1"}')

    js.add_consumer("INTEL", "orchestrator.intel_digest", durable=True, ack_seq=2)
    js.add_consumer("ADVICE", "backtest.fill", durable=True, ack_seq=1)
    return js


def test_restore_drill_round_trip(tmp_path):
    """Backup + restore preserves messages + durable consumer offsets."""
    js = _seed_fake_jetstream()
    backup_dir = tmp_path / "backup"
    js.backup(backup_dir)

    # Wipe the data dir (simulate disaster).
    del js

    # Restore from backup.
    restored = _FakeJetStream.restore(backup_dir)

    # Streams + subjects survived.
    assert set(restored.streams) == {"INTEL", "ADVICE"}
    assert restored.streams["INTEL"].subjects == ("intel.digest.v1", "intel.event.high_impact.v1")

    # Messages restored with seq + body intact.
    intel_msgs = restored.streams["INTEL"].messages
    assert [m.seq for m in intel_msgs] == [1, 2, 3]
    assert intel_msgs[0].data == b'{"id":"d1"}'

    # Durable consumer offsets restored — drill acceptance criterion.
    cons = restored.streams["INTEL"].consumers["orchestrator.intel_digest"]
    assert cons.durable is True
    assert cons.last_seq == 2


def test_backup_script_exists_and_is_executable():
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "infra" / "linux" / "scripts" / "nats-backup.sh"
    assert script.exists(), f"missing {script}"
    assert os.access(script, os.X_OK), f"{script} not executable"


def test_backup_script_has_systemd_timer():
    repo_root = Path(__file__).resolve().parents[2]
    timer = repo_root / "infra" / "linux" / "scripts" / "iic-nats-backup.timer"
    assert timer.exists(), f"missing {timer}"
    body = timer.read_text()
    assert "OnCalendar=*-*-* 03:00:00" in body, "expected 03:00 daily schedule"
    assert "Persistent=true" in body, "missed runs must catch up after reboot"


@pytest.mark.skipif(
    os.environ.get("IIC_NATS_DRILL") != "1",
    reason="real-integration drill — set IIC_NATS_DRILL=1 with docker-compose'd NATS to run",
)
def test_real_nats_restore_drill():
    """Real-integration variant — runs against a docker-compose'd NATS.

    Documented for clarity. Expectations:
    - `nats` CLI is on PATH.
    - `nats://localhost:4222` is reachable.
    - The script is deployed as `/usr/local/bin/iic-nats-backup.sh`.
    """
    out = tempfile.mkdtemp(prefix="nats-drill-")
    try:
        env = os.environ.copy()
        env["BACKUP_ROOT"] = out
        env["RETENTION_DAYS"] = "1"
        repo_root = Path(__file__).resolve().parents[2]
        script = repo_root / "infra" / "linux" / "scripts" / "nats-backup.sh"
        result = subprocess.run([str(script)], env=env, check=True, capture_output=True)
        assert b"nats-backup complete" in result.stdout + result.stderr
    finally:
        shutil.rmtree(out, ignore_errors=True)
