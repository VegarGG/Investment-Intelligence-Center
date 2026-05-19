# Backtest agent. Built on iic-base (P1.2). Build context: repo root.

FROM iic-base:latest

COPY apps/agent_backtest/requirements.txt /app/agent_backtest/requirements.txt
RUN pip install --no-cache-dir -r /app/agent_backtest/requirements.txt

COPY apps/agent_backtest/backtest/ /app/backtest/

EXPOSE 8085

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8085/health || exit 1

CMD ["uvicorn", "backtest.main:app", "--host", "0.0.0.0", "--port", "8085"]
