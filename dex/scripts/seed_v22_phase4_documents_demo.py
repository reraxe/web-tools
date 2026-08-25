#!/usr/bin/env python3
"""Create disposable v2.2 Phase 4 document QA storage; never overwrites a target."""

from __future__ import annotations

import argparse
import base64
import io
import os
import sys
from pathlib import Path

from PIL import Image


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a disposable DEX Phase 4 source-document demo")
    parser.add_argument("--output", required=True, help="New, nonexistent directory for disposable storage")
    args = parser.parse_args()
    target = Path(args.output).resolve()
    if target.exists():
        print(f"REFUSED: target already exists: {target}", file=sys.stderr)
        return 2
    target.mkdir(parents=True)

    project = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project))
    os.environ.update({
        "DEX_DATA_DIR": str(target), "DEX_DB_PATH": str(target / "dex.db"),
        "DEX_IMAGE_DIR": str(target / "images"), "DEX_INBOUND_DIR": str(target / "inbound"),
        "DEX_SOURCE_DB_DIR": str(target / "source-database"),
        "DEX_DOCUMENT_DIR": str(target / "source-documents"), "DEX_DOCUMENT_PROVIDER": "LOCAL",
        "DEX_WATCH_INBOUND": "0", "DEX_SEED_DEMO": "0",
    })

    import app
    from dex_documents import get_document_store, upload_document
    from dex_inbound import add_acquisition_line, autosave_acquisition, autosave_acquisition_line, create_acquisition

    app.init_db()
    store = get_document_store(target)
    with app.connect() as db:
        result = create_acquisition(db, {
            "request_id": "PHASE4-DEMO-ACQUISITION", "source_scope": "DOMESTIC",
            "merchant_name": "Phase 4 Receipt QA Shop", "purchased_on": "2026-08-15", "payment_method": "CREDIT_DEBIT_CARD",
        })
        acquisition_id = result["acquisition"]["id"]
        result = add_acquisition_line(db, acquisition_id, {
            "request_id": "PHASE4-DEMO-LINE", "expected_revision": result["acquisition"]["revision"], "product_class": "SEALED_PRODUCT",
        })
        line = next(item for item in result["lines"] if not item["canceled_at"])
        result = autosave_acquisition_line(db, line["id"], {
            "request_id": "PHASE4-DEMO-LINE-FACTS", "expected_revision": result["acquisition"]["revision"],
            "game": "One Piece", "set_code": "OP16", "product_name": "OP16 Booster Box",
            "quantity": 2, "quantity_certainty": "KNOWN", "intended_action": "DECIDE_LATER",
        })
        result = autosave_acquisition(db, acquisition_id, {
            "request_id": "PHASE4-DEMO-PURCHASE", "expected_revision": result["acquisition"]["revision"],
            "wizard_step": "PRODUCTS", "purchase_subtotal_cents": 19000, "acquisition_tax_cents": 1000,
            "inbound_shipping_cents": 500, "final_usd_paid_cents": 20500,
        })

        picture = io.BytesIO()
        Image.new("RGB", (640, 360), (242, 238, 225)).save(picture, format="PNG")
        attached = upload_document(db, acquisition_id, {
            "request_id": "PHASE4-DEMO-DOCUMENT-PNG", "expected_revision": result["acquisition"]["revision"],
            "original_filename": "phase4-receipt-screenshot.png", "declared_mime_type": "image/png",
            "data_base64": base64.b64encode(picture.getvalue()).decode(), "document_role": "RECEIPT", "capture_method": "SCREENSHOT",
        }, store)
        result = attached.get("acquisition_payload") or __import__("dex_inbound").acquisition_payload(db, acquisition_id)
        upload_document(db, acquisition_id, {
            "request_id": "PHASE4-DEMO-DOCUMENT-PDF", "expected_revision": result["acquisition"]["revision"],
            "original_filename": "phase4-order-confirmation.pdf", "declared_mime_type": "application/pdf",
            "data_base64": base64.b64encode(b"%PDF-1.4\n1 0 obj<</Type /Catalog /Pages 2 0 R>>endobj\n2 0 obj<</Type /Pages /Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type /Page /Parent 2 0 R>>endobj\n%%EOF\n").decode(),
            "document_role": "ORDER_CONFIRMATION", "capture_method": "PDF_UPLOAD",
        }, store)

    print(f"PASS: disposable Phase 4 storage created at {target}")
    print("Open Inbound and resume the acquisition for Phase 4 Receipt QA Shop.")
    print("Two private source documents are attached; add/remove/retry tests remain operator-controlled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
