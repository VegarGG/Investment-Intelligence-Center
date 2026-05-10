# IIC v2.5 — extend the timescale/timescaledb-ha image with pg_partman.
#
# The upstream `timescale/timescaledb-ha:pg16` image ships timescaledb,
# pgvector, vectorscale, hypopg, pgaudit and friends — but NOT pg_partman,
# which the alembic migration 0001 needs to set up the monthly-partitioned
# `lake.events` table. The PGDG apt repo on Ubuntu 22.04 ships a matching
# `postgresql-16-partman` package, so we just install it on top.
#
# Pinning is by major version (16 + 5) to keep the build reproducible while
# letting security patches roll in.

FROM timescale/timescaledb-ha:pg16

USER root

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends postgresql-16-partman; \
    rm -rf /var/lib/apt/lists/*

USER postgres
