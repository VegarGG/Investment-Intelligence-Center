# Quant agent. Built on iic-base (P1.2). Build context: repo root.

FROM iic-base:latest

COPY apps/agent_quant/requirements.txt /app/agent_quant/requirements.txt
RUN pip install --no-cache-dir -r /app/agent_quant/requirements.txt

COPY apps/agent_quant/quant/ /app/quant/

EXPOSE 8083

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8083/health || exit 1

CMD ["uvicorn", "quant.main:app", "--host", "0.0.0.0", "--port", "8083"]
