# IIC base image (P1.1).
#
# Every agent image extends this with FROM iic-base. The base contains:
#   - Python 3.12 + curl (for HEALTHCHECK probes)
#   - Every internal `packages/*` editable-installed at /app/packages
#   - The transitive deps of those packages
#
# This replaces the dev bind-mount workaround that papered over the
# missing per-agent install of shared packages (D6 §1.1 patch #8).
#
# Build context expected: repo root.
#     docker build -f infra/iic-base/Dockerfile -t iic-base:latest .
#
# The base image does not declare a CMD; each agent supplies its own.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    IIC_REPO_ROOT=/app

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Copy every internal package into /app/packages/.
COPY packages/ /app/packages/

# Editable-install each internal package. -e gives every agent image the
# same import paths (`import schema`, `import llm_client`, …) and means
# code edits at runtime do not require a rebuild when the same checkout
# is bind-mounted for local dev.
RUN pip install --upgrade pip \
 && pip install \
        -e /app/packages/schema \
        -e /app/packages/featureflags \
        -e /app/packages/llm-client \
        -e /app/packages/data-bus \
        -e /app/packages/notifier \
        -e /app/packages/prompts \
        -e /app/packages/data-lake

# Sanity import — fail the build if any package is missing or broken.
RUN python -c "import schema, featureflags, llm_client, data_bus, notifier, prompts, data_lake; print('iic-base ok')"
