# Admin / configuration API (P3.1). Built on iic-base. Build context: repo root.

FROM iic-base:latest

COPY apps/admin_api/requirements.txt /app/admin_api/requirements.txt
RUN pip install --no-cache-dir -r /app/admin_api/requirements.txt

COPY apps/admin_api/admin_api/ /app/admin_api/

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8090/admin/health || exit 1

CMD ["uvicorn", "admin_api.main:app", "--host", "0.0.0.0", "--port", "8090"]
