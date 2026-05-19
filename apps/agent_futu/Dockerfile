# FUTU agent (v2.5 T2.7). Built on iic-base (P1.2). Build context: repo root.
#
# Read-only multi-account FUTU integration; Phase A uses FakeOpenD by
# default, Phase B switches in real OpenD via FUTU_OPEND_BACKEND=real.

FROM iic-base:latest

COPY apps/agent_futu/requirements.txt /app/agent_futu/requirements.txt
RUN pip install --no-cache-dir -r /app/agent_futu/requirements.txt

COPY apps/agent_futu/futu/ /app/futu/

EXPOSE 8087

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8087/health || exit 1

CMD ["uvicorn", "futu.main:app", "--host", "0.0.0.0", "--port", "8087"]
