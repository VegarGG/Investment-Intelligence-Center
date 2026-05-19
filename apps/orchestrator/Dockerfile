# Orchestrator agent (workflow 32 / v2.5 T1). Built on iic-base which carries
# the internal `packages/*` editable-installs (P1.2).

FROM iic-base:latest

COPY apps/orchestrator/requirements.txt /app/orchestrator/requirements.txt
RUN pip install --no-cache-dir -r /app/orchestrator/requirements.txt

COPY apps/orchestrator/orchestrator/ /app/orchestrator/

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8080/health || exit 1

CMD ["uvicorn", "orchestrator.app:app", "--host", "0.0.0.0", "--port", "8080"]
