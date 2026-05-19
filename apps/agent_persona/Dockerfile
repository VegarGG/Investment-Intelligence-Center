# Persona agent. Built on iic-base (P1.2). Build context: repo root.
# The persona YAML specs live under docs/prompts/persona; mount or copy
# them under $IIC_REPO_ROOT/docs/prompts/persona at runtime.

FROM iic-base:latest

COPY apps/agent_persona/requirements.txt /app/agent_persona/requirements.txt
RUN pip install --no-cache-dir -r /app/agent_persona/requirements.txt

COPY apps/agent_persona/persona/ /app/persona/
COPY docs/prompts/persona/ /app/docs/prompts/persona/

EXPOSE 8084

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8084/health || exit 1

CMD ["uvicorn", "persona.main:app", "--host", "0.0.0.0", "--port", "8084"]
