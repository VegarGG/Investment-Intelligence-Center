# Intelligence agent (workflow 10). Built on iic-base (P1.2).
# Build context: repo root.

FROM iic-base:latest

COPY apps/agent_intelligence/requirements.txt /app/agent_intelligence/requirements.txt
RUN pip install --no-cache-dir -r /app/agent_intelligence/requirements.txt

COPY apps/agent_intelligence/intel/ /app/intel/
COPY apps/agent_intelligence/sources.yaml /app/sources.yaml

EXPOSE 8081

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8081/health || exit 1

CMD ["uvicorn", "intel.main:app", "--host", "0.0.0.0", "--port", "8081"]
