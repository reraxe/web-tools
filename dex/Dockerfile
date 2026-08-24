FROM python:3.12-slim

LABEL org.opencontainers.image.title="Dex" \
      org.opencontainers.image.description="Digital Encyclopedia Xchange TCG inventory" \
      org.opencontainers.image.version="v2.4-live"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEX_DATA_DIR=/data \
    DEX_INBOUND_DIR=/scanner-inbox \
    DEX_SOURCE_DB_DIR=/source-database \
    DEX_ONE_PIECE_REFERENCE_DIR=/source-database \
    DEX_SAM_OCR_ENABLED=1 \
    DEX_TESSERACT_CMD=/usr/bin/tesseract \
    DEX_TIMEZONE=America/New_York \
    DEX_TCG_CAPACITY=500 \
    DEX_HOST=0.0.0.0 \
    DEX_PORT=8080

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && tesseract --version \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./
COPY dex_migrations.py dex_economics.py dex_legacy_economics.py dex_acquisition.py dex_rip.py dex_sealed.py ./
COPY dex_batch_economics.py ./
COPY dex_corrections.py ./
COPY dex_post_sale.py ./
COPY dex_portfolio_economics.py ./
COPY dex_inbound.py ./
COPY dex_catalog.py ./
COPY dex_documents.py ./
COPY dex_receipts.py ./
COPY dex_receipt_ocr.py dex_receipt_parser.py dex_receipt_semantics.py ./
COPY dex_intake_bridge.py ./
COPY dex_sam.py ./
COPY dex_sam_identity.py ./
COPY dex_sam_challenger.py ./
COPY dex_sam_audited.py dex_sam_audited_worker.py ./
COPY sam_multi_evidence_frozen ./sam_multi_evidence_frozen
COPY dex_jarvis_economics.py ./
COPY scripts/docker_receipt_orchestration_smoke.py ./scripts/docker_receipt_orchestration_smoke.py
COPY static ./static

RUN python -c "import dex_migrations, dex_economics, dex_legacy_economics, dex_acquisition, dex_rip, dex_sealed, dex_batch_economics"
RUN python -c "import dex_corrections"
RUN python -c "import dex_post_sale"
RUN python -c "import dex_portfolio_economics"
RUN python -c "import dex_inbound"
RUN python -c "import dex_catalog"
RUN python -c "import dex_documents"
RUN python -c "import dex_receipts"
RUN python -c "import dex_receipt_ocr, dex_receipt_parser; assert dex_receipt_ocr.provider_health()['private_local_processing']"
RUN python -c "import dex_receipt_semantics"
RUN python -c "import dex_intake_bridge"
RUN python -c "import dex_sam"
RUN python -c "import dex_sam_identity"
RUN python -c "import dex_sam_challenger"
RUN python -c "import dex_sam_audited; assert dex_sam_audited.frozen_component_status()['available']"
RUN python -c "import dex_jarvis_economics"
RUN python scripts/docker_receipt_orchestration_smoke.py

RUN useradd --uid 10001 --create-home dex \
    && mkdir -p /data /scanner-inbox /source-database \
    && chown -R dex:dex /app /data /scanner-inbox /source-database

USER dex
EXPOSE 8080
VOLUME ["/data", "/scanner-inbox", "/source-database"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3)" || exit 1

CMD ["python", "app.py"]
