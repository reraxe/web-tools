import csv
import io
import json
import sqlite3
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

import app
from dex_corrections import dispose_card, reverse_event as reverse_economic_event
from dex_economics import CALCULATION_VERSION
from dex_migrations import DEFAULT_MIGRATIONS
from dex_portfolio_economics import portfolio_economics_export_rows, portfolio_economics_payload
from dex_post_sale import (
    create_chargeback,
    create_fee_credit,
    create_postage_refund,
    create_refund,
    create_return,
    create_sale_correction,
    reverse_event as reverse_post_sale_event,
)
from dex_sealed import create_sealed_sale, synchronize_sealed_units, undo_specific_sealed_sale
from tests.test_phase7b_post_sale import Phase7BFixture


ROOT = Path(__file__).parents[1]


class Phase7CPortfolioTest(Phase7BFixture):
    def add_sealed_batch(self, batch_id=3):
        self.db.execute(
            """INSERT INTO batches
               (id,batch_code,created_at,status,game,set_code,acquisition_type,total_cost,
                economics_mode,economics_status,product_name,receipt_group_reference,
                final_usd_paid_cents,units_acquired)
               VALUES (?,?,'2026-08-14','OPEN','One Piece','OP16','Booster Box',12,
                       'SEALED_RIP','FINALIZED','Phase 7C sealed','P7C-SEALED',1200,2)""",
            (batch_id, f"OP-P7C-SEALED-{batch_id}"),
        )
        synchronize_sealed_units(self.db, batch_id)

    @staticmethod
    def sealed_sale_payload(batch_id, number, request_id):
        return {
            "batch_id": batch_id,
            "quantity": 1,
            "platform": "eBay",
            "order_number": number,
            "sold_at": "2026-08-14",
            "merchandise_total": "8.00",
            "shipping_collected": "1.00",
            "marketplace_fees": "1.00",
            "actual_postage": "1.00",
            "marketplace_tax": "5.00",
            "request_id": request_id,
        }

    def build_portfolio(self):
        first = self.add_singles_batch(1, 2, "P7C-SHARED")
        second = self.add_singles_batch(2, 2, "P7C-SHARED")
        self.db.execute(
            "UPDATE cards SET market_average=4.00, market_updated_at='2026-08-14T09:00:00+00:00', listing_price=4.50 WHERE id=?",
            (first[0],),
        )
        self.db.execute(
            "UPDATE cards SET market_average=5.00, market_updated_at='2026-08-14T10:00:00+00:00', listing_price=6.00 WHERE id=?",
            (first[1],),
        )
        self.db.execute("UPDATE cards SET listing_price=8.00 WHERE id=?", (second[1],))
        order_id = self.card_order(
            [first[0], second[0]], merchandise=3000, shipping=300,
            fees=300, postage=200, number="P7C-CROSS-BATCH",
        )
        sale_items = self.db.execute(
            "SELECT id FROM sale_items WHERE order_id=? ORDER BY id", (order_id,)
        ).fetchall()
        self.db.execute("UPDATE sale_items SET sale_price=10.00 WHERE id=?", (sale_items[0][0],))
        self.db.execute("UPDATE sale_items SET sale_price=20.00 WHERE id=?", (sale_items[1][0],))
        create_refund(self.db, order_id, {
            "request_id": "P7C-REFUND", "reason_code": "CUSTOMER_REQUEST",
            "merchandise_amount": "3.00", "shipping_amount": "0",
        })
        chargeback = create_chargeback(self.db, order_id, {
            "request_id": "P7C-CHARGEBACK", "reason_code": "PAYMENT_DISPUTE", "amount": "1.00",
        })
        reverse_post_sale_event(self.db, chargeback["event_id"], {
            "request_id": "P7C-CHARGEBACK-REV", "reason_code": "DATA_ENTRY_ERROR",
            "notes": "Disposable reversal coverage.",
        })
        fee_credit = create_fee_credit(self.db, order_id, {
            "request_id": "P7C-FEE-CREDIT", "reason_code": "MARKETPLACE_CREDIT", "amount": "0.50",
        })
        reverse_post_sale_event(self.db, fee_credit["event_id"], {
            "request_id": "P7C-FEE-CREDIT-REV", "reason_code": "DATA_ENTRY_ERROR",
            "notes": "Disposable fee-credit reversal.",
        })
        postage_refund = create_postage_refund(self.db, order_id, {
            "request_id": "P7C-POSTAGE-REFUND", "reason_code": "CARRIER_REFUND", "amount": "0.25",
        })
        reverse_post_sale_event(self.db, postage_refund["event_id"], {
            "request_id": "P7C-POSTAGE-REFUND-REV", "reason_code": "DATA_ENTRY_ERROR",
            "notes": "Disposable postage-refund reversal.",
        })
        correction = create_sale_correction(self.db, order_id, {
            "request_id": "P7C-SALE-CORRECTION", "reason_code": "DATA_ENTRY_ERROR",
            "notes": "Disposable sale correction.", "shipping_delta": "0.25",
        })
        reverse_post_sale_event(self.db, correction["event_id"], {
            "request_id": "P7C-SALE-CORRECTION-REV", "reason_code": "DATA_ENTRY_ERROR",
            "notes": "Disposable sale-correction reversal.",
        })

        self.add_sealed_batch()
        sealed_order = create_sealed_sale(
            self.db, self.sealed_sale_payload(3, "P7C-SEALED-ACTIVE", "P7C-SEALED-ACTIVE-REQ"),
            "2026-08-14",
        )
        canceled = create_sealed_sale(
            self.db, self.sealed_sale_payload(3, "P7C-SEALED-CANCELED", "P7C-SEALED-CANCELED-REQ"),
            "2026-08-14",
        )
        undo_specific_sealed_sale(self.db, canceled["id"])

        self.db.execute(
            """INSERT INTO batches
               (id,batch_code,created_at,status,game,set_code,acquisition_type,total_cost)
               VALUES (4,'P7C-LEGACY','2026-08-14','OPEN','One Piece','OP16','Singles',25.00)"""
        )
        self.db.execute(
            """INSERT INTO batches
               (id,batch_code,created_at,status,game,set_code,acquisition_type,total_cost,
                economics_mode,economics_status,product_name,final_usd_paid_cents,units_acquired)
               VALUES (5,'P7C-DRAFT','2026-08-14','OPEN','One Piece','OP16','Singles',15.00,
                       'SINGLES_LUMP_SUM','DRAFT','Draft excluded lot',1500,0)"""
        )
        return first, second, order_id, sealed_order["id"]

    def test_portfolio_uses_effective_facts_once_and_labels_incomplete_valuation(self):
        first, second, order_id, _ = self.build_portfolio()
        changes_before = self.db.total_changes
        report = portfolio_economics_payload(self.db)
        self.assertEqual(self.db.total_changes, changes_before)
        self.assertEqual(report["calculation_version"], "acquisition-rip-v3")
        self.assertEqual(report["state"], "FINALIZED_ECONOMICS_ONLY")
        self.assertEqual(report["scope"]["finalized_batch_count"], 3)
        self.assertEqual(report["scope"]["authoritative_unfinalized_batch_count"], 1)
        self.assertEqual(report["scope"]["legacy_estimate_batch_count"], 1)

        self.assertEqual(report["summary"]["authoritative_acquisition_cost_cents"], 3200)
        self.assertEqual(report["realized"]["gross_merchandise_cents"], 3500)
        self.assertEqual(report["realized"]["shipping_collected_cents"], 400)
        self.assertEqual(report["realized"]["marketplace_fees_cents"], 400)
        self.assertEqual(report["realized"]["actual_postage_cents"], 300)
        self.assertEqual(report["realized"]["other_net_cents"], 0)
        self.assertEqual(report["summary"]["effective_realized_net_proceeds_cents"], 3200)
        self.assertEqual(report["summary"]["active_sold_basis_cents"], 1600)
        self.assertEqual(report["summary"]["realized_profit_loss_cents"], 1600)
        self.assertEqual(report["summary"]["cost_recovery_percent"], 100.0)
        self.assertEqual(report["realized"]["unique_order_count"], 2)
        self.assertEqual(report["realized"]["canceled_order_count"], 1)

        self.assertEqual(report["remaining"]["market"]["known_value_cents"], 500)
        self.assertEqual(report["remaining"]["market"]["valued_count"], 1)
        self.assertEqual(report["remaining"]["market"]["total_count"], 3)
        self.assertFalse(report["remaining"]["market"]["complete"])
        self.assertEqual(report["remaining"]["market"]["freshness"], "2026-08-14T10:00:00+00:00")
        self.assertEqual(report["remaining"]["listed"]["known_value_cents"], 1400)
        self.assertFalse(report["remaining"]["listed"]["complete"])
        self.assertEqual(report["remaining"]["listed"]["freshness_label"], "Freshness Unknown")
        self.assertEqual(report["remaining"]["market"]["sealed"]["state"], "UNKNOWN")
        self.assertEqual(report["summary"]["current_economic_position_cents"], 500)
        self.assertFalse(report["summary"]["current_position_complete"])
        self.assertEqual(report["summary"]["projected_listed_position_cents"], 1400)
        self.assertFalse(report["summary"]["projected_listed_position_complete"])

        self.assertEqual(report["reconciliation"]["authoritative_cost"]["difference_cents"], 0)
        self.assertEqual(report["reconciliation"]["realized_net"]["difference_cents"], 0)
        self.assertTrue(report["reconciliation"]["stable_order_attribution"]["reconciled"])
        self.assertEqual(report["reconciliation"]["stable_order_attribution"]["duplicate_attribution_count"], 0)
        self.assertEqual(report["receipt_groups"]["group_count"], 2)
        self.assertIn("not allocated automatically", report["receipt_groups"]["notice"])
        self.assertIn("SEALED_VALUE_UNKNOWN", [warning["code"] for warning in report["warnings"]])

        sale_item = self.db.execute(
            "SELECT id FROM sale_items WHERE order_id=? AND card_id=?", (order_id, first[0])
        ).fetchone()[0]
        returned = create_return(self.db, order_id, {
            "request_id": "P7C-RETURN", "reason_code": "CUSTOMER_RETURN",
            "physical_received_confirmed": True, "condition_confirmed": True,
            "items": [{"item_type": "CARD", "sale_item_id": sale_item, "outcome": "RESTOCKED"}],
        })
        after_return = portfolio_economics_payload(self.db)
        self.assertEqual(after_return["summary"]["effective_realized_net_proceeds_cents"], 3200)
        self.assertEqual(after_return["summary"]["active_sold_basis_cents"], 1100)
        self.assertEqual(after_return["summary"]["realized_profit_loss_cents"], 2100)
        self.assertEqual(after_return["remaining"]["market"]["known_value_cents"], 900)
        reverse_post_sale_event(self.db, returned["event_id"], {
            "request_id": "P7C-RETURN-REV", "reason_code": "DATA_ENTRY_ERROR",
            "notes": "Disposable return reversal.",
        })
        self.assertEqual(portfolio_economics_payload(self.db)["summary"]["active_sold_basis_cents"], 1600)

        loss = dispose_card(self.db, "OP-P7B-01-002", {
            "request_id": "P7C-LOSS", "reason_code": "DAMAGED", "notes": "Disposable damage coverage.",
        })
        after_loss = portfolio_economics_payload(self.db)
        self.assertEqual(after_loss["summary"]["operational_loss_cents"], 500)
        self.assertEqual(after_loss["remaining"]["market"]["known_value_cents"], 0)
        self.assertEqual(after_loss["summary"]["current_economic_position_cents"], 0)
        reverse_economic_event(self.db, loss["event_id"], {
            "request_id": "P7C-LOSS-REV", "notes": "Disposable loss reversal.",
        })
        self.assertEqual(portfolio_economics_payload(self.db)["summary"]["operational_loss_cents"], 0)

    def test_http_and_csv_are_read_only_and_share_backend_values(self):
        self.add_singles_batch(1, 1, "P7C-API")
        self.db.execute(
            "UPDATE cards SET market_average=12.34, market_updated_at='2026-08-14T12:00:00+00:00', listing_price=13.50"
        )
        self.db.commit()
        with patch.object(app, "DB_PATH", self.db_path):
            server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.DexHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with urllib.request.urlopen(base + "/api/portfolio/economics", timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    payload = json.loads(response.read())
                with urllib.request.urlopen(base + "/api/export/portfolio-economics.csv", timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    csv_text = response.read().decode("utf-8-sig")
                row = next(csv.DictReader(io.StringIO(csv_text)))
                self.assertEqual(row["calculation_version"], CALCULATION_VERSION)
                self.assertEqual(int(row["authoritative_acquisition_cost_cents"]), payload["summary"]["authoritative_acquisition_cost_cents"])
                self.assertEqual(int(row["remaining_market_value_cents"]), payload["summary"]["known_remaining_market_value_cents"])
                self.assertEqual(row["economics_state"], "FINALIZED_ECONOMICS_ONLY")
            finally:
                server.shutdown(); thread.join(timeout=3); server.server_close()

    def test_realistically_large_portfolio_is_read_only_and_prompt(self):
        next_batch = 1
        for _ in range(40):
            self.add_singles_batch(next_batch, 100, f"P7C-LARGE-{next_batch:03d}")
            next_batch += 1
        self.db.execute(
            "UPDATE cards SET market_average=1.25, market_updated_at='2026-08-14T08:00:00+00:00', listing_price=1.50"
        )
        self.db.commit()
        changes_before = self.db.total_changes
        started = time.perf_counter()
        report = portfolio_economics_payload(self.db)
        elapsed = time.perf_counter() - started
        self.assertEqual(self.db.total_changes, changes_before)
        self.assertEqual(report["scope"]["finalized_batch_count"], 40)
        self.assertEqual(report["inventory_counts"]["remaining_cards"], 4000)
        self.assertEqual(report["remaining"]["market"]["known_value_cents"], 500000)
        self.assertEqual(report["remaining"]["listed"]["known_value_cents"], 600000)
        self.assertTrue(report["remaining"]["market"]["complete"])
        self.assertLess(elapsed, 5.0)
        print(f"Phase 7C performance: 40 finalized batches / 4,000 cards in {elapsed * 1000:.2f} ms (read-only)")


class Phase7CContractTest(unittest.TestCase):
    def test_no_schema_migration_and_ui_uses_backend_payload_only(self):
        self.assertIn("0005_phase7b_post_sale_events", [migration.migration_id for migration in DEFAULT_MIGRATIONS])
        javascript = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn('data-view="economics"', index)
        self.assertIn("v2.2-test-inbound-phase6-intake-bridge", index)
        self.assertIn("Operational Economics", javascript)
        self.assertIn('/api/portfolio/economics', javascript)
        self.assertIn('/api/export/portfolio-economics.csv', javascript)
        self.assertIn("summary.current_economic_position_cents", javascript)
        self.assertNotIn("realized.net_proceeds_cents +", javascript)
        self.assertNotIn("summary.effective_realized_net_proceeds_cents +", javascript)
        self.assertIn('/api/portfolio/economics', app_source)
        self.assertIn("COPY dex_portfolio_economics.py ./", dockerfile)
        self.assertIn('RUN python -c "import dex_portfolio_economics"', dockerfile)


if __name__ == "__main__":
    unittest.main()
