FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .
RUN chmod +x /app/entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]

FROM runtime AS test
RUN pip install --no-cache-dir "httpx2>=2,<3" "pytest>=8.3,<9" "ruff>=0.9,<1"
