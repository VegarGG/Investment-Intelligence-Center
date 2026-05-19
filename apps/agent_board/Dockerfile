# Investment Board agent. Built on iic-base (P1.2). Build context: repo root.

FROM iic-base:latest

COPY apps/agent_board/requirements.txt /app/agent_board/requirements.txt
RUN pip install --no-cache-dir -r /app/agent_board/requirements.txt

COPY apps/agent_board/board/ /app/board/

EXPOSE 8088

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8088/health || exit 1

CMD ["uvicorn", "board.main:app", "--host", "0.0.0.0", "--port", "8088"]
