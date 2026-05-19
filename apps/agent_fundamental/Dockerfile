# Fundamental agent. Built on iic-base (P1.2). Build context: repo root.

FROM iic-base:latest

COPY apps/agent_fundamental/requirements.txt /app/agent_fundamental/requirements.txt
RUN pip install --no-cache-dir -r /app/agent_fundamental/requirements.txt

COPY apps/agent_fundamental/fund/ /app/fund/
COPY apps/agent_fundamental/watchlist.yaml /app/watchlist.yaml

EXPOSE 8082

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8082/health || exit 1

CMD ["uvicorn", "fund.main:app", "--host", "0.0.0.0", "--port", "8082"]
