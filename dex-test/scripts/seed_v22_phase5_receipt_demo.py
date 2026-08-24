#!/usr/bin/env python3
"""Create disposable v2.2 Phase 5 receipt-intelligence QA storage."""

from __future__ import annotations

import argparse
import base64
import io
import os
import sys
from pathlib import Path

from PIL import Image
from reportlab.pdfgen import canvas


def pdf_bytes(lines: list[str]) -> bytes:
    output = io.BytesIO()
    page = canvas.Canvas(output, pagesize=(612, 792), pageCompression=0)
    y = 760
    for line in lines:
        page.drawString(40, y, line)
        y -= 18
    page.save()
    return output.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a disposable DEX Phase 5 receipt-intelligence demo")
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
        "DEX_WATCH_INBOUND": "0", "DEX_SEED_DEMO": "0", "DEX_AUTO_PURGE": "0",
    })

    import app
    from dex_documents import get_document_store, upload_document
    from dex_inbound import acquisition_payload, add_acquisition_line, autosave_acquisition, autosave_acquisition_line, create_acquisition
    from dex_receipts import get_receipt_extractor, queue_extraction

    app.init_db()
    store = get_document_store(target)
    extractor = get_receipt_extractor()

    def create_scenario(db, key: str, label: str, products: list[tuple[str, int]], receipt: bytes,
                        mime: str = "application/pdf", manual_final: int | None = None) -> str:
        result = create_acquisition(db, {
            "request_id": f"P5-{key}-ACQ", "source_scope": "DOMESTIC", "merchant_name": label,
            "payment_method": "CREDIT_DEBIT_CARD", "wizard_step": "REVIEW",
            **({"final_usd_paid_cents": manual_final} if manual_final is not None else {}),
        })
        acquisition_id = result["acquisition"]["id"]
        for index, (name, quantity) in enumerate(products, 1):
            result = add_acquisition_line(db, acquisition_id, {
                "request_id": f"P5-{key}-LINE-{index}", "expected_revision": result["acquisition"]["revision"],
                "product_class": "SEALED_PRODUCT",
            })
            line = next(item for item in result["lines"] if not item["canceled_at"] and not item["product_name"])
            result = autosave_acquisition_line(db, line["id"], {
                "request_id": f"P5-{key}-LINE-FACTS-{index}", "expected_revision": result["acquisition"]["revision"],
                "game": "One Piece", "set_code": name.split()[0], "product_name": name,
                "quantity": quantity, "quantity_certainty": "KNOWN", "intended_action": "DECIDE_LATER",
            })
        attached = upload_document(db, acquisition_id, {
            "request_id": f"P5-{key}-DOC", "expected_revision": result["acquisition"]["revision"],
            "original_filename": f"phase5-{key.lower()}.{'pdf' if mime == 'application/pdf' else 'png'}",
            "declared_mime_type": mime, "data_base64": base64.b64encode(receipt).decode(),
            "document_role": "RECEIPT", "capture_method": "FILE_UPLOAD",
        }, store)
        result = acquisition_payload(db, acquisition_id)
        queue_extraction(db, attached["document"]["id"], {
            "request_id": f"P5-{key}-EXTRACT", "expected_revision": result["acquisition"]["revision"], "auto_apply": True,
        }, store, extractor)
        result = acquisition_payload(db, acquisition_id)
        if result["acquisition"]["wizard_step"] != "REVIEW":
            autosave_acquisition(db, acquisition_id, {
                "request_id": f"P5-{key}-REVIEW", "expected_revision": result["acquisition"]["revision"], "wizard_step": "REVIEW",
            })
        return result["acquisition"]["acquisition_code"]

    with app.connect() as db:
        happy = create_scenario(db, "HAPPY", "Receipt Intelligence Shop", [("OP16 Booster Box", 2)], pdf_bytes([
            "Merchant: Receipt Intelligence Shop", "Date: 2026-08-15", "Order #: HAPPY-5001", "Currency: USD",
            "ITEM | OP16 Booster Box | QTY 2 | UNIT 50.00 | TOTAL 100.00", "Subtotal: 100.00",
            "Tax: 8.00", "Shipping: 5.00", "Total: 113.00",
        ]))
        multi = create_scenario(db, "MULTI", "Multi Product Shop", [("OP16 Booster Box", 1), ("ST27 Starter Deck", 1)], pdf_bytes([
            "Merchant: Multi Product Shop", "Date: 2026-08-15", "Order #: MULTI-5002", "Currency: USD",
            "ITEM | OP16 Booster Box | QTY 1 | UNIT 100.00 | TOTAL 100.00",
            "ITEM | ST27 Starter Deck | QTY 1 | UNIT 50.00 | TOTAL 50.00",
            "Subtotal: 150.00", "Tax: 10.00", "Shipping: 1.00", "Total: 161.00",
        ]))
        conflict = create_scenario(db, "CONFLICT", "QA Conflict – Manual Value Preserved", [("OP16 Booster Box", 2)], pdf_bytes([
            "Merchant: Conflicting Receipt Shop", "Date: 2026-08-15", "Order #: CONFLICT-5003", "Currency: USD",
            "ITEM | OP16 Booster Box | QTY 2 | UNIT 50.00 | TOTAL 100.00", "Subtotal: 100.00",
            "Tax: 8.00", "Shipping: 5.00", "Total: 113.00",
        ]), manual_final=9000)
        incomplete = create_scenario(db, "INCOMPLETE", "Incomplete Receipt Shop", [("OP16 Booster Box", 2)], pdf_bytes([
            "Merchant: Incomplete Receipt Shop", "Date: 2026-08-15", "Order #: INCOMPLETE-5004", "Currency: USD",
            "ITEM | OP16 Booster Box | QTY 2 | UNIT 50.00 | TOTAL 100.00", "Subtotal: 100.00",
        ]))
        picture = io.BytesIO()
        Image.new("RGB", (640, 360), (242, 238, 225)).save(picture, format="PNG")
        failure = create_scenario(db, "FAILURE", "QA Failure – Manual Path Available", [("OP16 Booster Box", 1)], picture.getvalue(), "image/png")

    print(f"PASS: disposable Phase 5 storage created at {target}")
    print(f"Happy path: {happy}")
    print(f"Multi-line exact allocation: {multi}")
    print(f"Manual conflict: {conflict}")
    print(f"Incomplete / Unknown: {incomplete}")
    print(f"Retryable extraction failure: {failure}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
