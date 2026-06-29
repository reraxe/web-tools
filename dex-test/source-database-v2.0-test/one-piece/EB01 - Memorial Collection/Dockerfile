FROM python:3.12-slim

LABEL org.opencontainers.image.title="Dex" \
      org.opencontainers.image.description="Digital Encyclopedia Xchange TCG inventory" \
      org.opencontainers.image.version="v2.0-test"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEX_DATA_DIR=/data \
    DEX_INBOUND_DIR=/scanner-inbox \
    DEX_SOURCE_DB_DIR=/source-database \
    DEX_TIMEZONE=America/New_York \
    DEX_TCG_CAPACITY=500 \
    DEX_HOST=0.0.0.0 \
    DEX_PORT=8080

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./
COPY static ./static

RUN useradd --uid 10001 --create-home dex \
    && mkdir -p /data /scanner-inbox /source-database \
    && chown -R dex:dex /app /data /scanner-inbox /source-database

USER dex
EXPOSE 8080
VOLUME ["/data", "/scanner-inbox", "/source-database"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3)" || exit 1

CMD ["python", "app.py"]
