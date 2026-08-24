import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from app import undo_last_action
from dex_migrations import DEFAULT_MIGRATIONS, MigrationError, apply_migrations
from dex_rip import create_rip_session
from dex_sealed import (
    adjust_sealed_unit,
    batch_sealed_payload,
    create_sealed_sale,
    sealed_order_payload,
    sealed_sale_preview,
    synchronize_sealed_units,
    undo_specific_sealed_sale,
)


ROOT = Path(__file__).parents[1]


def base_schema(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        CREATE TABLE batches (
            id INTEGER PRIMARY KEY,
            batch_code TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'OPEN',
            acquisition_type TEXT NOT NULL DEFAULT 'Booster Box',
            total_cost REAL NOT NULL DEFAULT 0,
            recycled_at TEXT
        );
        CREATE TABLE cards (
            id INTEGER PRIMARY KEY,
            sku TEXT NOT NULL UNIQUE,
            batch_id INTEGER NOT NULL REFERENCES batches(id),
            name TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'IN_STOCK',
            updated_at TEXT NOT NULL DEFAULT '',
            recycled_at TEXT
        );
        CREATE TABLE processed_scans (
            fingerprint TEXT PRIMARY KEY,
            batch_id INTEGER NOT NULL REFERENCES batches(id),
            processed_at TEXT NOT NULL
        );
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            action_type TEXT NOT NULL,
            description TEXT NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}',
            undone_at TEXT
        );
        CREATE TABLE sale_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            order_number TEXT NOT NULL DEFAULT '',
            sold_at TEXT NOT NULL,
            subtotal REAL NOT NULL DEFAULT 0,
            shipping_collected REAL NOT NULL DEFAULT 0,
            platform_fees REAL NOT NULL DEFAULT 0,
            postage_cost REAL NOT NULL DEFAULT 0,
            notes TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE sale_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES sale_orders(id),
            card_id INTEGER NOT NULL UNIQUE REFERENCES cards(id),
            sale_price REAL NOT NULL DEFAULT 0
        );
        """
    )


def database(path: Path | None = None) -> sqlite3.Connection:
    db = sqlite3.connect(path or ":memory:", timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    base_schema(db)
    apply_migrations(db)
    return db


def add_batch(db: sqlite3.Connection, batch_id: int, *, cents: int = 1000, units: int = 3) -> None:
    db.execute(
        """INSERT INTO batches
           (id, batch_code, created_at, status, acquisition_type, total_cost,
            economics_mode, economics_status, product_name,
            final_usd_paid_cents, units_acquired, receipt_group_reference)
           VALUES (?, ?, '2026-08-14', 'OPEN', 'Booster Box', ?,
                   'SEALED_RIP', 'DRAFT', ?, ?, ?, 'RECEIPT-PHASE5')""",
        (batch_id, f"OP-PHASE5-{batch_id:02d}", cents / 100, f"Product {batch_id}", cents, units),
    )
    synchronize_sealed_units(db, batch_id)


def sale_payload(batch_id: int, request_id: str, quantity: int = 1) -> dict:
    return {
        "batch_id": batch_id,
        "quantity": quantity,
        "platform": "eBay",
        "order_number": request_id,
        "sold_at": "2026-08-14",
        "merchandise_total": "15.00",
        "shipping_collected": "2.00",
        "marketplace_fees": "1.00",
        "actual_postage": "3.00",
        "marketplace_tax": "1.25",
        "request_id": request_id,
    }


class Phase5MigrationTest(unittest.TestCase):
    def test_migration_backfills_card_orders_and_migrates_existing_rip_to_exact_units(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        base_schema(db)
        db.execute("INSERT INTO batches (id,batch_code,total_cost) VALUES (1,'LEGACY-SEALED',10.00)")
        db.execute(
            """INSERT INTO sale_orders
               (platform, order_number, sold_at, subtotal, shipping_collected, platform_fees, postage_cost)
               VALUES ('eBay','OLD-1','2026-08-01',12.34,1.00,2.00,3.00)"""
        )
        apply_migrations(db, DEFAULT_MIGRATIONS[:1])
        db.execute(
            """UPDATE batches SET economics_mode='SEALED_RIP', economics_status='DRAFT',
               product_name='Legacy boxes', final_usd_paid_cents=1000, units_acquired=3 WHERE id=1"""
        )
        apply_migrations(db, DEFAULT_MIGRATIONS[:2])
        db.execute(
            "INSERT INTO rip_sessions (rip_code,batch_id,units_opened,created_at) VALUES ('RIP-OLD',1,1,'2026-08-01')"
        )
        self.assertEqual(apply_migrations(db, DEFAULT_MIGRATIONS[:3]), ("0003_phase5_sealed_inventory",))
        self.assertEqual(
            apply_migrations(db),
            (
                "0004_phase7a_corrections_dispositions",
                "0005_phase7b_post_sale_events",
                "0006_v22_phase1_inbound_acquisitions",
                "0007_v22_phase2_manual_acquisition_wizard",
                "0008_v22_phase2_ux_revision",
                "0009_v22_phase3_product_catalog_upc",
                "0010_v22_phase4_source_documents",
                "0011_v22_phase5_receipt_intelligence",
                "0012_v22_prephase_ux_safety_hotfix",
                "0013_v22_phase6_downstream_intake_bridge",
                "0014_v22_phase7_sam_recognition",
                "0015_v22_rc3_hf1_mixed_purchase_reconciliation",
                "0016_v23_inventory_intelligence_phase1_receipt_semantics",
                "0017_v24_sam_phase1_family_printing",
                "0018_v24_jarvis_economics_sam_phase2",
            ),
        )
        units = db.execute("SELECT unit_sequence,basis_cents,status,rip_session_id FROM sealed_units ORDER BY unit_sequence").fetchall()
        self.assertEqual([(row["basis_cents"], row["status"]) for row in units], [(334, "OPENED"), (333, "REMAINING"), (333, "REMAINING")])
        self.assertEqual(units[0]["rip_session_id"], 1)
        order = db.execute("SELECT * FROM sale_orders WHERE order_number='OLD-1'").fetchone()
        self.assertEqual(order["order_type"], "CARD")
        self.assertEqual(order["merchandise_total_cents"], 1234)
        self.assertEqual(apply_migrations(db), ())
        db.close()

    def test_failed_phase5_migration_rolls_back_columns_tables_and_marker(self):
        db = sqlite3.connect(":memory:")
        base_schema(db)
        apply_migrations(db, DEFAULT_MIGRATIONS[:2])
        db.execute("CREATE TABLE sealed_units (sentinel TEXT)")
        db.commit()
        with self.assertRaises(MigrationError):
            apply_migrations(db)
        self.assertNotIn("order_type", {row[1] for row in db.execute("PRAGMA table_info(sale_orders)")})
        self.assertIsNone(db.execute("SELECT 1 FROM schema_migrations WHERE migration_id='0003_phase5_sealed_inventory'").fetchone())
        self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sealed_sale_items'").fetchone())
        db.close()


class Phase5SealedEconomicsTest(unittest.TestCase):
    def setUp(self):
        self.db = database()
        add_batch(self.db, 1)

    def tearDown(self):
        self.db.close()

    def test_multi_unit_sale_uses_exact_basis_tax_exclusion_idempotency_and_atomic_undo(self):
        payload = sale_payload(1, "SEALED-ORDER-1", 2)
        preview = sealed_sale_preview(self.db, payload)
        original_ids = [row["id"] for row in self.db.execute("SELECT id FROM sealed_units WHERE batch_id=1 ORDER BY unit_sequence")]
        repeated_preview = sealed_sale_preview(self.db, payload)
        self.assertEqual([unit["id"] for unit in repeated_preview["sealed_units"]], original_ids[:2])
        self.assertEqual(
            [row["id"] for row in self.db.execute("SELECT id FROM sealed_units WHERE batch_id=1 ORDER BY unit_sequence")],
            original_ids,
        )
        self.assertEqual([row["unit_sequence"] for row in preview["sealed_units"]], [1, 2])
        self.assertEqual(preview["sold_basis_cents"], 667)
        self.assertEqual(preview["net_proceeds_cents"], 1300)
        self.assertEqual(preview["realized_profit_loss_cents"], 633)
        self.assertEqual(preview["marketplace_tax_cents"], 125)

        order = create_sealed_sale(self.db, payload, "2026-08-14")
        duplicate = create_sealed_sale(self.db, payload, "2026-08-14")
        self.assertEqual(order["id"], duplicate["id"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sale_orders WHERE order_type='SEALED'").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sealed_sale_items").fetchone()[0], 2)
        self.assertEqual(batch_sealed_payload(self.db, 1)["counts"], {"remaining": 1, "opened": 0, "sold": 2, "corrected_adjusted": 0})
        with self.assertRaisesRegex(ValueError, "Not enough sealed units"):
            create_sealed_sale(self.db, sale_payload(1, "SEALED-OVERSELL", 2), "2026-08-14")

        result = undo_last_action(self.db)
        self.assertIn("sealed order", result["undone"])
        restored = batch_sealed_payload(self.db, 1)
        self.assertEqual(restored["counts"]["remaining"], 3)
        history = sealed_order_payload(self.db, order["id"])
        self.assertTrue(history["canceled"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sealed_unit_events WHERE event_type='SALE_UNDONE'").fetchone()[0], 2)

    def test_order_specific_undo_restores_only_that_orders_exact_units_and_retains_history(self):
        order = create_sealed_sale(self.db, sale_payload(1, "SEALED-DETAIL-UNDO", 2), "2026-08-14")
        consumed_ids = [unit["id"] for unit in order["sealed_units"]]
        self.db.execute(
            """INSERT INTO activity_log (created_at, action_type, description, payload)
               VALUES ('2026-08-14T12:00:00+00:00', 'CARD_UPDATE', 'Later unrelated action', '{}')"""
        )

        details = sealed_order_payload(self.db, order["id"])
        self.assertTrue(details["undo_eligible"])
        self.assertEqual([unit["id"] for unit in details["sealed_units"]], consumed_ids)

        undone = undo_specific_sealed_sale(self.db, order["id"])
        self.assertEqual(undone["restored_unit_ids"], consumed_ids)
        retained = sealed_order_payload(self.db, order["id"])
        self.assertTrue(retained["canceled"])
        self.assertFalse(retained["undo_eligible"])
        self.assertEqual([unit["id"] for unit in retained["sealed_units"]], consumed_ids)
        self.assertEqual(
            [row["status"] for row in self.db.execute(
                "SELECT status FROM sealed_units WHERE id IN (?, ?) ORDER BY id", consumed_ids
            ).fetchall()],
            ["REMAINING", "REMAINING"],
        )
        later = self.db.execute("SELECT undone_at FROM activity_log WHERE description='Later unrelated action'").fetchone()
        self.assertIsNone(later["undone_at"])

    def test_card_and_sealed_items_cannot_be_mixed(self):
        payload = sale_payload(1, "MIXED-ORDER")
        payload["skus"] = ["OP-FAKE-CARD"]
        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            create_sealed_sale(self.db, payload, "2026-08-14")

    def test_rip_claims_exact_unit_and_sale_cannot_claim_it_again(self):
        rip = create_rip_session(self.db, 1, {"units_opened": 1})
        self.assertEqual(rip["sealed_units"][0]["unit_sequence"], 1)
        opened_id = rip["sealed_units"][0]["id"]
        selected = sale_payload(1, "SEALED-SELECT-OPENED")
        selected["sealed_unit_ids"] = [opened_id]
        with self.assertRaisesRegex(ValueError, "no longer available"):
            create_sealed_sale(self.db, selected, "2026-08-14")
        order = create_sealed_sale(self.db, sale_payload(1, "SEALED-AFTER-RIP"), "2026-08-14")
        self.assertEqual(order["sealed_units"][0]["unit_sequence"], 2)
        counts = batch_sealed_payload(self.db, 1)["counts"]
        self.assertEqual(counts, {"remaining": 1, "opened": 1, "sold": 1, "corrected_adjusted": 0})

    def test_reason_aware_adjustment_preserves_exact_reconciliation(self):
        unit = self.db.execute("SELECT * FROM sealed_units WHERE batch_id=1 ORDER BY unit_sequence DESC LIMIT 1").fetchone()
        adjusted = adjust_sealed_unit(
            self.db,
            unit["id"],
            {"request_id": "ADJUST-1", "reason_code": "DAMAGED", "notes": "Seal crushed"},
        )
        self.assertEqual(adjusted["status"], "ADJUSTED")
        duplicate = adjust_sealed_unit(
            self.db,
            unit["id"],
            {"request_id": "ADJUST-1", "reason_code": "DAMAGED", "notes": "Seal crushed"},
        )
        self.assertEqual(duplicate["status"], "ADJUSTED")
        reconciliation = batch_sealed_payload(self.db, 1)
        self.assertTrue(reconciliation["reconciliation"]["reconciled"])
        self.assertEqual(reconciliation["counts"]["corrected_adjusted"], 1)


class Phase5ConcurrencyTest(unittest.TestCase):
    def test_two_writers_cannot_sell_the_same_last_unit(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "phase5.db"
            setup = database(path)
            add_batch(setup, 1, cents=500, units=1)
            setup.commit()
            setup.close()
            results: list[str] = []
            lock = threading.Lock()

            def worker(request_id: str) -> None:
                db = sqlite3.connect(path, timeout=10)
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA foreign_keys=ON")
                try:
                    db.execute("BEGIN IMMEDIATE")
                    create_sealed_sale(db, sale_payload(1, request_id), "2026-08-14")
                    db.commit()
                    outcome = "sold"
                except (ValueError, sqlite3.DatabaseError):
                    db.rollback()
                    outcome = "rejected"
                finally:
                    db.close()
                with lock:
                    results.append(outcome)

            threads = [threading.Thread(target=worker, args=(f"RACE-{index}",)) for index in (1, 2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(sorted(results), ["rejected", "sold"])
            verify = sqlite3.connect(path)
            self.assertEqual(verify.execute("SELECT COUNT(*) FROM sale_orders WHERE order_type='SEALED'").fetchone()[0], 1)
            self.assertEqual(verify.execute("SELECT status FROM sealed_units").fetchone()[0], "SOLD")
            verify.close()


class Phase5UiPackagingContractTest(unittest.TestCase):
    def test_sealed_workflow_is_separate_and_backend_calculated(self):
        javascript = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("Card and sealed-product orders are separate workflows", javascript)
        self.assertIn('/api/sealed-sales/preview', javascript)
        self.assertIn('api("/api/sealed-sales"', javascript)
        self.assertIn("Marketplace-collected sales tax", javascript)
        self.assertIn("Corrected / adjusted", javascript)
        self.assertIn("openSealedOrderDetails", javascript)
        self.assertIn("undo-sealed-order", javascript)
        self.assertIn("v2.2-test-inbound-phase6-intake-bridge", html)
        self.assertIn("dex_sealed.py", dockerfile)
        self.assertIn("import dex_migrations, dex_economics, dex_legacy_economics, dex_acquisition, dex_rip, dex_sealed", dockerfile)


if __name__ == "__main__":
    unittest.main()
