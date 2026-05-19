# IIC v2.5 — extend the timescale/timescaledb-ha image with pg_partman.
#
# The upstream `timescale/timescaledb-ha:pg16` image ships timescaledb,
# pgvector, vectorscale, hypopg, pgaudit and friends — but NOT pg_partman,
# which the alembic migration 0001 needs to set up the monthly-partitioned
# `lake.events` table. The PGDG apt repo on Ubuntu 22.04 ships a matching
# `postgresql-16-partman` package, so we just install it on top.
#
# P1.4 — Pin by build-arg. Ops sets `IIC_PG_BASE_IMAGE=timescale/...@sha256:<digest>`
# in `.env` or via `--build-arg`; the floating tag is only the dev fallback.
# Two prior outages in D6 traced to silent upstream re-tags; never run a
# floating tag in prod.

ARG IIC_PG_BASE_IMAGE=timescale/timescaledb-ha:pg16
FROM ${IIC_PG_BASE_IMAGE}

USER root

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends postgresql-16-partman; \
    rm -rf /var/lib/apt/lists/*

USER postgres
