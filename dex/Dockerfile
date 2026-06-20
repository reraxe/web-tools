FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEX_DATA_DIR=/data \
    DEX_INBOUND_DIR=/scanner-inbox \
    DEX_HOST=0.0.0.0 \
    DEX_PORT=8080

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

FROM base AS test
COPY app.py ./
COPY static ./static
COPY tests ./tests
RUN DEX_WATCH_INBOUND=0 DEX_SEED_DEMO=0 python -m unittest discover -s tests -v

FROM test AS runtime

RUN rm -rf tests \
    && useradd --uid 10001 --create-home dex \
    && mkdir -p /data /scanner-inbox \
    && chown -R dex:dex /app /data /scanner-inbox

USER dex
EXPOSE 8080
VOLUME ["/data", "/scanner-inbox"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3)" || exit 1

CMD ["python", "app.py"]
