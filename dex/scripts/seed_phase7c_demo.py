#!/usr/bin/env python3
"""Create disposable Phase 7C operator-QA storage; never overwrites a target."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a disposable Phase 7C DEX demo")
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
        sealed_batch = db.execute("SELECT * FROM batches WHERE product_code='OP16-BOX'").fetchone()
        db.execute(
            "UPDATE batches SET receipt_group_reference='P7C-DEMO-RECEIPT' WHERE id=?",
            (sealed_batch["id"],),
        )
        rip = app.create_rip_session(db, int(sealed_batch["id"]), {"units_opened": 1})
        db.execute("UPDATE cards SET rip_session_id=? WHERE batch_id=?", (rip["id"], sealed_batch["id"]))
        app.finalize_rip(db, int(rip["id"]), {
            "allocation_method": "EQUAL", "bulk_mode": "NONE",
            "confirm_all_cards_accounted": True, "confirm_finalization": True,
            "request_id": "PHASE7C-DEMO-SEALED-FINALIZATION",
            "notes": "Disposable Phase 7C finalized sealed/rip baseline.",
        })
        sealed_cards = db.execute(
            "SELECT id,sku,status FROM cards WHERE batch_id=? ORDER BY id", (sealed_batch["id"],)
        ).fetchall()
        db.execute(
            """UPDATE cards SET market_average=12.00, market_updated_at='2026-08-14T18:00:00+00:00',
                                  listing_price=15.00 WHERE batch_id=?""",
            (sealed_batch["id"],),
        )

        card_order = db.execute(
            """INSERT INTO sale_orders
               (platform,order_number,sold_at,subtotal,shipping_collected,platform_fees,
                postage_cost,notes,order_type,merchandise_total_cents,
                shipping_collected_cents,marketplace_fees_cents,actual_postage_cents)
               VALUES ('eBay','P7C-CARD-DEMO','2026-08-14',40,5,6,7,
                       'Disposable Phase 7C effective card order','CARD',4000,500,600,700)"""
        ).lastrowid
        for card in sealed_cards[:2]:
            db.execute("INSERT INTO sale_items (order_id,card_id,sale_price) VALUES (?,?,20.00)", (card_order, card["id"]))
            db.execute("UPDATE cards SET status='SOLD',updated_at=? WHERE id=?", (app.utcnow(), card["id"]))
        app.log_action(db, "SALE", "Completed disposable Phase 7C card order", {
            "order_id": card_order,
            "cards": [{"id": card["id"], "status": card["status"]} for card in sealed_cards[:2]],
        })
        app.create_refund(db, card_order, {
            "request_id": "PHASE7C-DEMO-REFUND", "reason_code": "CUSTOMER_REQUEST",
            "merchandise_amount": "5.00", "shipping_amount": "1.00",
            "notes": "Disposable effective-proceeds demonstration.",
        })
        sealed_order = app.create_sealed_sale(db, {
            "batch_id": int(sealed_batch["id"]), "quantity": 1, "platform": "eBay",
            "order_number": "P7C-SEALED-DEMO", "sold_at": "2026-08-14",
            "merchandise_total": "135.00", "shipping_collected": "8.00",
            "marketplace_fees": "18.00", "actual_postage": "10.00",
            "marketplace_tax": "9.00", "request_id": "PHASE7C-DEMO-SEALED-SALE",
            "notes": "Disposable sealed sale; marketplace tax is excluded from P/L.",
        }, "2026-08-14")

        singles_batch_id = db.execute(
            """INSERT INTO batches
               (batch_code,created_at,status,game,set_code,acquisition_type,total_cost,
                economics_mode,economics_status,product_name,product_code,
                receipt_group_reference,reporting_currency,final_usd_paid_cents,units_acquired)
               VALUES ('OP-P7C-SINGLES','2026-08-14','OPEN','One Piece','OP16','Singles Lot',300,
                       'SINGLES_LUMP_SUM','FINALIZED','Disposable singles lot','P7C-SINGLES',
                       'P7C-DEMO-RECEIPT','USD',30000,0)"""
        ).lastrowid
        singles_rip = app.create_rip_session(db, singles_batch_id, {"units_opened": 0})
        singles_cards = []
        for sequence in range(1, 4):
            card_id = db.execute(
                """INSERT INTO cards
                   (sku,batch_id,created_at,updated_at,name,status,rip_session_id,
                    market_average,market_updated_at,listing_price)
                   VALUES (?,?,? ,? ,? ,'IN_STOCK',?, ?, '2026-08-14T19:00:00+00:00', ?)""",
                (
                    f"OP-P7C-SINGLES-{sequence:03d}", singles_batch_id, app.utcnow(), app.utcnow(),
                    f"Disposable portfolio single {sequence}", singles_rip["id"],
                    None if sequence == 2 else 20.00 + sequence,
                    25.00 + sequence,
                ),
            ).lastrowid
            singles_cards.append(card_id)
        app.finalize_rip(db, int(singles_rip["id"]), {
            "allocation_method": "EQUAL", "bulk_mode": "NONE",
            "confirm_all_cards_accounted": True, "confirm_finalization": True,
            "request_id": "PHASE7C-DEMO-SINGLES-FINALIZATION",
            "notes": "Disposable Phase 7C finalized singles allocation.",
        })

        cross_order = db.execute(
            """INSERT INTO sale_orders
               (platform,order_number,sold_at,subtotal,shipping_collected,platform_fees,
                postage_cost,notes,order_type,merchandise_total_cents,
                shipping_collected_cents,marketplace_fees_cents,actual_postage_cents)
               VALUES ('TCGplayer','P7C-CROSS-BATCH','2026-08-14',30,3,3,2,
                       'Stable cross-batch attribution demonstration','CARD',3000,300,300,200)"""
        ).lastrowid
        db.execute("INSERT INTO sale_items (order_id,card_id,sale_price) VALUES (?,?,10.00)", (cross_order, sealed_cards[2]["id"]))
        db.execute("INSERT INTO sale_items (order_id,card_id,sale_price) VALUES (?,?,20.00)", (cross_order, singles_cards[0]))
        db.execute("UPDATE cards SET status='SOLD',updated_at=? WHERE id IN (?,?)", (app.utcnow(), sealed_cards[2]["id"], singles_cards[0]))
        app.log_action(db, "SALE", "Completed disposable cross-batch order", {
            "order_id": cross_order,
            "cards": [{"id": sealed_cards[2]["id"], "status": "IN_STOCK"}, {"id": singles_cards[0], "status": "IN_STOCK"}],
        })
        app.dispose_card(db, "OP-P7C-SINGLES-003", {
            "request_id": "PHASE7C-DEMO-DISPOSITION", "reason_code": "DAMAGED",
            "notes": "Disposable Operational Loss demonstration.",
        })

        db.execute(
            """INSERT INTO batches
               (batch_code,created_at,status,game,set_code,acquisition_type,total_cost)
               VALUES ('P7C-LEGACY-ESTIMATE','2026-08-14','OPEN','One Piece','OP16','Singles',25.00)"""
        )
        db.execute(
            """INSERT INTO batches
               (batch_code,created_at,status,game,set_code,acquisition_type,total_cost,
                economics_mode,economics_status,product_name,reporting_currency,
                final_usd_paid_cents,units_acquired)
               VALUES ('P7C-AUTHORITATIVE-DRAFT','2026-08-14','OPEN','One Piece','OP16','Singles',15.00,
                       'SINGLES_LUMP_SUM','DRAFT','Unfinalized excluded example','USD',1500,0)"""
        )

        report = app.portfolio_economics_payload(db)
        print(f"PASS: disposable Phase 7C storage created at {target}")
        print(f"Portfolio: {report['scope']['finalized_batch_count']} finalized / {report['scope']['legacy_estimate_batch_count']} legacy estimate / {report['scope']['authoritative_unfinalized_batch_count']} unfinalized")
        print(f"Receipt group: P7C-DEMO-RECEIPT / batches {sealed_batch['batch_code']}, OP-P7C-SINGLES")
        print(f"Cross-batch order: P7C-CROSS-BATCH / order ID {cross_order}")
        print(f"Sealed order: P7C-SEALED-DEMO / order ID {sealed_order['id']}")
        print("Open: #economics")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
