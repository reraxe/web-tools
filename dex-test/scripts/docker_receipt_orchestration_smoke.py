"""Build-time, private-local receipt orchestration smoke for the DEX image."""

from __future__ import annotations

import base64
import io
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def receipt_png() -> bytes:
    image = Image.new("RGB", (1400, 950), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=46)
    lines = (
        "Docker Receipt Smoke Shop",
        "Date 08/21/2026",
        "Mastercard",
        "Inventory item $10.00",
        "Subtotal $10.00",
        "Total $10.00",
    )
    for index, line in enumerate(lines):
        draw.text((70, 60 + index * 120), line, fill="black", font=font)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="dex-receipt-orchestration-smoke-") as temporary:
        root = Path(temporary)
        os.environ.update({
            "DEX_DB_PATH": str(root / "dex.db"),
            "DEX_DATA_DIR": str(root),
            "DEX_DOCUMENT_DIR": str(root / "source-documents"),
            "DEX_SEED_DEMO": "0",
            "DEX_AUTO_PURGE": "0",
            "DEX_RECEIPT_OCR_ENABLED": "1",
        })

        import app
        from dex_documents import get_document_store, upload_document
        from dex_inbound import acquisition_payload, create_acquisition
        from dex_receipts import get_receipt_extractor, queue_extraction

        app.init_db()
        db = sqlite3.connect(app.DB_PATH)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            store = get_document_store(root)
            result = create_acquisition(db, {"request_id": "DOCKER-RECEIPT-SMOKE-ACQ"})
            uploaded = upload_document(db, result["acquisition"]["id"], {
                "request_id": "DOCKER-RECEIPT-SMOKE-UPLOAD",
                "expected_revision": result["acquisition"]["revision"],
                "original_filename": "docker-receipt-smoke.png",
                "declared_mime_type": "image/png",
                "data_base64": base64.b64encode(receipt_png()).decode(),
                "document_role": "RECEIPT",
                "capture_method": "FILE_UPLOAD",
            }, store)
            result = acquisition_payload(db, result["acquisition"]["id"])
            job = queue_extraction(db, uploaded["document"]["id"], {
                "request_id": "DOCKER-RECEIPT-SMOKE-EXTRACT",
                "expected_revision": result["acquisition"]["revision"],
                "auto_apply": True,
            }, store, get_receipt_extractor())
            result = acquisition_payload(db, result["acquisition"]["id"])
            assert job["status"] == "COMPLETED", (job.get("error_code"), job.get("error_message"))
            assert result["acquisition"]["payment_method"] == "CREDIT_DEBIT_CARD"
            assert result["receipt_intelligence"]["semantic_review"]["active_assertion_count"] > 0
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            db.close()
    print("Docker receipt OCR + orchestration smoke: PASS")


if __name__ == "__main__":
    main()
