#!/usr/bin/env python3
"""Create disposable Phase 7B operator-QA storage; never overwrites a target."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a disposable Phase 7B DEX demo")
    parser.add_argument("--output", required=True, help="New empty directory for disposable storage")
    args = parser.parse_args()
    target = Path(args.output).resolve()
    if target.exists():
        print(f"REFUSED: target already exists: {target}", file=sys.stderr)
        return 2
    target.mkdir(parents=True)

    project = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project))
    os.environ.update({
        "DEX_DATA_DIR": str(target),
        "DEX_DB_PATH": str(target / "dex.db"),
        "DEX_IMAGE_DIR": str(target / "images"),
        "DEX_INBOUND_DIR": str(target / "inbound"),
        "DEX_SOURCE_DB_DIR": str(target / "source-database"),
        "DEX_WATCH_INBOUND": "0",
        "DEX_SEED_DEMO": "1",
    })

    import app

    app.init_db()
    app.seed_demo()
    with app.connect() as db:
        batch = db.execute("SELECT * FROM batches WHERE product_code='OP16-BOX'").fetchone()
        rip = app.create_rip_session(db, int(batch["id"]), {"units_opened": 1})
        db.execute("UPDATE cards SET rip_session_id=? WHERE batch_id=?", (rip["id"], batch["id"]))
        app.finalize_rip(db, int(rip["id"]), {
            "allocation_method": "EQUAL", "bulk_mode": "NONE",
            "confirm_all_cards_accounted": True, "confirm_finalization": True,
            "request_id": "PHASE7B-DEMO-FINALIZATION",
            "notes": "Disposable Phase 7B operator-QA baseline.",
        })
        cards = db.execute("SELECT id,sku,status FROM cards WHERE batch_id=? ORDER BY id", (batch["id"],)).fetchall()
        order_id = db.execute(
            """INSERT INTO sale_orders
               (platform,order_number,sold_at,subtotal,shipping_collected,platform_fees,
                postage_cost,notes,order_type,merchandise_total_cents,
                shipping_collected_cents,marketplace_fees_cents,actual_postage_cents)
               VALUES ('eBay','P7B-CARD-DEMO','2026-08-14',40,5,6,7,
                       'Disposable Phase 7B card-order scenario','CARD',4000,500,600,700)"""
        ).lastrowid
        for card in cards[:2]:
            db.execute("INSERT INTO sale_items (order_id,card_id,sale_price) VALUES (?,?,20.00)", (order_id, card["id"]))
            db.execute("UPDATE cards SET status='SOLD',updated_at=? WHERE id=?", (app.utcnow(), card["id"]))
        app.log_action(db, "SALE", "Completed disposable Phase 7B card order", {
            "order_id": order_id,
            "cards": [{"id": card["id"], "status": card["status"]} for card in cards[:2]],
        })
        sealed = app.create_sealed_sale(db, {
            "batch_id": int(batch["id"]), "quantity": 1, "platform": "eBay",
            "order_number": "P7B-SEALED-DEMO", "sold_at": "2026-08-14",
            "merchandise_total": "135.00", "shipping_collected": "8.00",
            "marketplace_fees": "18.00", "actual_postage": "10.00",
            "marketplace_tax": "9.00", "request_id": "PHASE7B-DEMO-SEALED-SALE",
            "notes": "Disposable exact sealed-return scenario.",
        }, "2026-08-14")
        print(f"PASS: disposable Phase 7B storage created at {target}")
        print(f"Batch: {batch['batch_code']} / {batch['product_name']}")
        print(f"Card order: P7B-CARD-DEMO / order ID {order_id} / exact cards {cards[0]['sku']}, {cards[1]['sku']}")
        print(f"Sealed order: P7B-SEALED-DEMO / order ID {sealed['id']} / exact unit {sealed['sealed_units'][0]['unit_code']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
