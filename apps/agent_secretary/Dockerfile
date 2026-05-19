# Secretary agent. Built on iic-base (P1.2). Build context: repo root.

FROM iic-base:latest

COPY apps/agent_secretary/requirements.txt /app/agent_secretary/requirements.txt
RUN pip install --no-cache-dir -r /app/agent_secretary/requirements.txt

COPY apps/agent_secretary/secretary/ /app/secretary/

EXPOSE 8086

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8086/health || exit 1

CMD ["uvicorn", "secretary.main:app", "--host", "0.0.0.0", "--port", "8086"]
