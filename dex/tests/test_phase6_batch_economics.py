import sqlite3
import time
import unittest
from pathlib import Path

from dex_batch_economics import (
    acquisition_group_economics_payload,
    batch_economics_export_rows,
    batch_economics_payload,
)
from dex_economics import CALCULATION_VERSION
from dex_rip import create_rip_session, finalize_rip
from dex_sealed import create_sealed_sale
from tests.test_phase5_sealed import add_batch, database, sale_payload


ROOT = Path(__file__).parents[1]


def add_phase6_card_columns(db: sqlite3.Connection) -> None:
    columns = {row[1] for row in db.execute("PRAGMA table_info(cards)")}
    for name, declaration in (
        ("market_average", "REAL"),
        ("market_updated_at", "TEXT"),
        ("listing_price", "REAL"),
    ):
        if name not in columns:
            db.execute(f"ALTER TABLE cards ADD COLUMN {name} {declaration}")


def add_rip_card(
    db: sqlite3.Connection,
    batch_id: int,
    rip_id: int,
    card_id: int,
    *,
    market: float | None = None,
    listed: float | None = None,
) -> None:
    db.execute(
        """INSERT INTO cards
           (id, sku, batch_id, name, status, updated_at, recycled_at, rip_session_id,
            market_average, market_updated_at, listing_price)
           VALUES (?, ?, ?, ?, 'IN_STOCK', '2026-08-14T12:00:00+00:00', NULL, ?, ?, ?, ?)""",
        (
            card_id,
            f"PHASE6-{card_id:05d}",
            batch_id,
            f"Phase 6 card {card_id}",
            rip_id,
            market,
            "2026-08-14T11:00:00+00:00" if market is not None else None,
            listed,
        ),
    )


def finalize_equal(db: sqlite3.Connection, rip_id: int, request_id: str) -> None:
    finalize_rip(
        db,
        rip_id,
        {
            "allocation_method": "EQUAL",
            "bulk_mode": "NONE",
            "confirm_all_cards_accounted": True,
            "confirm_finalization": True,
            "request_id": request_id,
        },
    )


class Phase6BatchEconomicsTest(unittest.TestCase):
    def setUp(self):
        self.db = database()
        add_phase6_card_columns(self.db)

    def tearDown(self):
        self.db.close()

    def test_backend_report_separates_realized_remaining_and_reconciles_exactly(self):
        add_batch(self.db, 1, cents=1000, units=3)
        rip = create_rip_session(self.db, 1, {"units_opened": 1})
        add_rip_card(self.db, 1, rip["id"], 1, market=2.00, listed=2.50)
        add_rip_card(self.db, 1, rip["id"], 2, market=4.00, listed=5.00)
        finalize_equal(self.db, rip["id"], "PHASE6-FINALIZE-1")

        card_order = self.db.execute(
            """INSERT INTO sale_orders
               (platform, order_number, sold_at, subtotal, shipping_collected,
                platform_fees, postage_cost, notes, order_type,
                merchandise_total_cents, shipping_collected_cents,
                marketplace_fees_cents, actual_postage_cents)
               VALUES ('eBay','PHASE6-CARD','2026-08-14',5,1,.5,.25,'','CARD',500,100,50,25)"""
        ).lastrowid
        self.db.execute(
            "INSERT INTO sale_items (order_id, card_id, sale_price) VALUES (?, 1, 5.00)",
            (card_order,),
        )
        self.db.execute("UPDATE cards SET status='SOLD' WHERE id=1")

        sealed_payload = sale_payload(1, "PHASE6-SEALED")
        sealed_payload.update(
            {
                "merchandise_total": "6.00",
                "shipping_collected": "0.00",
                "marketplace_fees": "0.60",
                "actual_postage": "0.40",
            }
        )
        create_sealed_sale(self.db, sealed_payload, "2026-08-14")
        changes_before = self.db.total_changes
        report = batch_economics_payload(self.db, 1)

        self.assertEqual(self.db.total_changes, changes_before)
        self.assertEqual(report["calculation_version"], CALCULATION_VERSION)
        self.assertEqual(report["state"], "AUTHORITATIVE")
        self.assertEqual(report["acquisition"]["authoritative_cost_cents"], 1000)
        self.assertEqual(report["realized"]["gross_merchandise_cents"], 1100)
        self.assertEqual(report["realized"]["net_proceeds_cents"], 1025)
        self.assertEqual(report["realized"]["sold_basis_cents"], 500)
        self.assertEqual(report["realized"]["realized_profit_loss_cents"], 525)
        self.assertEqual(report["realized"]["cost_recovery_percent"], 102.5)
        self.assertEqual(report["remaining"]["market"]["known_value_cents"], 400)
        self.assertEqual(report["remaining"]["listed"]["known_value_cents"], 500)
        self.assertEqual(report["remaining"]["market"]["coverage_label"], "1/2 inventory items valued")
        self.assertEqual(report["remaining"]["market"]["freshness"], "2026-08-14T11:00:00+00:00")
        self.assertEqual(report["remaining"]["listed"]["freshness_label"], "Freshness Unknown")
        self.assertFalse(report["remaining"]["current_position_complete"])
        self.assertEqual(report["remaining"]["current_economic_position_cents"], 425)
        self.assertEqual(report["remaining"]["projected_listed_position_cents"], 525)
        self.assertEqual(report["remaining"]["known_basis_cents"], 500)
        self.assertTrue(report["reconciliation"]["basis"]["reconciled"])
        self.assertEqual(
            report["reconciliation"]["sealed_quantity"],
            {
                "applicable": True,
                "acquired": 3,
                "opened": 1,
                "sold": 1,
                "remaining": 1,
                "corrected_adjusted": 0,
                "difference": 0,
                "reconciled": True,
            },
        )
        self.assertEqual([order["order_type"] for order in report["sales"]["orders"]], ["SEALED", "CARD"])

        self.db.execute(
            "UPDATE cards SET recycled_at='2026-08-14T13:00:00+00:00' WHERE id=2"
        )
        recycled = batch_economics_payload(self.db, 1)
        self.assertEqual(recycled["remaining"]["market"]["known_value_cents"], 0)
        self.assertEqual(recycled["remaining"]["known_basis_cents"], 333)
        self.assertEqual(recycled["excluded"]["recycled_card_count"], 1)
        self.assertEqual(recycled["excluded"]["known_basis_cents"], 167)
        self.assertEqual(recycled["excluded"]["market"]["known_value_cents"], 400)

    def test_cross_batch_order_is_attributed_once_in_receipt_group(self):
        for batch_id, cents, card_id in ((1, 500, 1), (2, 900, 2)):
            add_batch(self.db, batch_id, cents=cents, units=1)
            rip = create_rip_session(self.db, batch_id, {"units_opened": 1})
            add_rip_card(self.db, batch_id, rip["id"], card_id)
            finalize_equal(self.db, rip["id"], f"PHASE6-FINALIZE-GROUP-{batch_id}")

        order_id = self.db.execute(
            """INSERT INTO sale_orders
               (platform, order_number, sold_at, subtotal, shipping_collected,
                platform_fees, postage_cost, notes, order_type,
                merchandise_total_cents, shipping_collected_cents,
                marketplace_fees_cents, actual_postage_cents)
               VALUES ('eBay','PHASE6-CROSS','2026-08-14',10,1,1.10,.90,'','CARD',1000,100,110,90)"""
        ).lastrowid
        self.db.execute(
            "INSERT INTO sale_items (order_id, card_id, sale_price) VALUES (?, 1, 3.00)",
            (order_id,),
        )
        self.db.execute(
            "INSERT INTO sale_items (order_id, card_id, sale_price) VALUES (?, 2, 7.00)",
            (order_id,),
        )
        self.db.execute("UPDATE cards SET status='SOLD' WHERE id IN (1,2)")

        first = batch_economics_payload(self.db, 1)
        second = batch_economics_payload(self.db, 2)
        group = acquisition_group_economics_payload(self.db, "receipt-phase5")

        self.assertEqual(first["realized"]["net_proceeds_cents"], 270)
        self.assertEqual(second["realized"]["net_proceeds_cents"], 630)
        self.assertEqual(group["realized"]["net_proceeds_cents"], 900)
        self.assertEqual(group["realized"]["gross_merchandise_cents"], 1000)
        self.assertEqual(group["realized"]["unique_order_count"], 1)
        self.assertIn("not allocated automatically", group["notice"])
        self.assertIn("allocated once", group["realized"]["allocation_notice"])

    def test_export_serializes_backend_report_and_legacy_stays_separate(self):
        add_batch(self.db, 1, cents=1200, units=3)
        self.db.execute(
            """INSERT INTO batches
               (id, batch_code, created_at, status, acquisition_type, total_cost)
               VALUES (2, 'LEGACY-PHASE6', '2026-08-14', 'OPEN', 'Singles', 12.34)"""
        )
        rows = batch_economics_export_rows(self.db)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["calculation_version"], CALCULATION_VERSION)
        self.assertEqual(rows[0]["authoritative_cost_cents"], 1200)
        self.assertEqual(rows[1]["economics_state"], "LEGACY_ESTIMATE_ONLY")
        self.assertNotIn("authoritative_cost_cents", rows[1])

    def test_large_batch_report_is_read_only_and_completes_promptly(self):
        self.db.execute(
            """INSERT INTO batches
               (id, batch_code, created_at, status, acquisition_type, total_cost,
                economics_mode, economics_status, product_name,
                final_usd_paid_cents, units_acquired, receipt_group_reference)
               VALUES (1, 'PHASE6-LARGE', '2026-08-14', 'OPEN', 'Singles', 2500,
                       'SINGLES_LUMP_SUM', 'DRAFT', 'Large disposable lot',
                       250000, 0, '')"""
        )
        self.db.executemany(
            """INSERT INTO cards
               (id, sku, batch_id, name, status, updated_at, recycled_at,
                market_average, market_updated_at, listing_price)
               VALUES (?, ?, 1, 'Large batch card', 'IN_STOCK', '2026-08-14', NULL,
                       1.25, '2026-08-14T10:00:00+00:00', 1.50)""",
            ((index, f"LARGE-{index:05d}") for index in range(1, 2501)),
        )
        self.db.commit()
        changes_before = self.db.total_changes
        started = time.perf_counter()
        report = batch_economics_payload(self.db, 1)
        elapsed = time.perf_counter() - started
        self.assertEqual(report["remaining"]["market"]["valued_count"], 2500)
        self.assertEqual(report["remaining"]["market"]["known_value_cents"], 312500)
        self.assertEqual(self.db.total_changes, changes_before)
        self.assertLess(elapsed, 2.0)


class Phase6UiAndPackagingContractTest(unittest.TestCase):
    def test_ui_is_backend_only_and_preserves_required_hierarchy(self):
        javascript = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        sections = [
            'data-economics-section="summary"',
            'data-economics-section="acquisition"',
            'data-economics-section="recovery"',
            'data-economics-section="remaining"',
            'data-economics-section="rips"',
            'data-economics-section="sales"',
            'data-economics-section="reconciliation"',
        ]
        positions = [javascript.index(section) for section in sections]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("What did this cost?", javascript)
        self.assertIn("How much have I recovered?", javascript)
        self.assertIn("What remains?", javascript)
        self.assertIn("Am I currently ahead or behind?", javascript)
        self.assertIn("Market value and listed value are not realized profit", javascript)
        self.assertIn("Missing market and listed values are never substituted", javascript)
        self.assertIn("remaining.current_economic_position_cents", javascript)
        self.assertNotIn("realized.net_proceeds_cents +", javascript)
        self.assertIn("@media (max-width: 620px)", styles)
        self.assertIn("dex_batch_economics.py", dockerfile)
        self.assertIn("import dex_migrations, dex_economics, dex_legacy_economics, dex_acquisition, dex_rip, dex_sealed, dex_batch_economics", dockerfile)


if __name__ == "__main__":
    unittest.main()
