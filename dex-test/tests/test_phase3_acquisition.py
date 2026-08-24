import shutil
import importlib.util
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dex_acquisition import acquisition_payload, normalize_acquisition_input
from dex_migrations import DEFAULT_MIGRATIONS, MigrationError, apply_migrations


class AcquisitionValidationTest(unittest.TestCase):
    def test_exact_usd_reconciliation_and_reference_currency(self):
        facts = normalize_acquisition_input(
            {
                "economics_mode": "SEALED_RIP",
                "product_name": "OP16 Booster Box",
                "units_acquired": "6",
                "receipt_group_reference": "receipt-001",
                "original_currency": "cad",
                "original_foreign_amount": "900.00",
                "purchase_subtotal": "600.00",
                "acquisition_tax": "48.00",
                "inbound_shipping": "15.00",
                "acquisition_fees": "2.00",
                "acquisition_discount": "5.00",
                "final_usd_paid": "660.00",
            }
        )
        self.assertEqual(facts["final_usd_paid_cents"], 66000)
        self.assertEqual(facts["component_total_cents"], 66000)
        self.assertEqual(facts["reconciliation_difference_cents"], 0)
        self.assertEqual(facts["receipt_group_reference"], "RECEIPT-001")
        self.assertEqual(facts["original_currency"], "CAD")
        self.assertEqual(facts["original_foreign_amount_minor"], 90000)

    def test_mismatch_requires_explicit_acknowledgement(self):
        payload = {
            "economics_mode": "SEALED_RIP",
            "product_name": "Six boxes",
            "units_acquired": 6,
            "purchase_subtotal": "600.00",
            "final_usd_paid": "605.00",
        }
        with self.assertRaisesRegex(ValueError, r"\$5\.00 above"):
            normalize_acquisition_input(payload)
        payload["cost_reconciliation_acknowledged"] = True
        facts = normalize_acquisition_input(payload)
        self.assertEqual(facts["reconciliation_difference_cents"], 500)
        self.assertEqual(facts["cost_reconciliation_acknowledged"], 1)

    def test_missing_cost_is_null_and_singles_have_no_sealed_units(self):
        facts = normalize_acquisition_input(
            {
                "economics_mode": "SINGLES_LUMP_SUM",
                "product_name": "Convention singles lot",
                "units_acquired": "0",
            }
        )
        self.assertIsNone(facts["final_usd_paid_cents"])
        self.assertIsNone(facts["reconciliation_difference_cents"])
        self.assertEqual(facts["units_acquired"], 0)


class Phase3UiContractTest(unittest.TestCase):
    def test_ui_uses_backend_acquisition_values_and_discloses_group_behavior(self):
        root = Path(__file__).parents[1]
        javascript = (root / "static" / "app.js").read_text(encoding="utf-8")
        html = (root / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn("/economics`", javascript)
        self.assertIn("Phase 3 Acquisition Facts", javascript)
        self.assertIn("Final USD actually paid", javascript)
        self.assertIn("Informational link only", javascript)
        self.assertIn("never allocate shared costs automatically", javascript)
        self.assertIn("Array.isArray(group?.batches) ? group.batches : []", javascript)
        self.assertNotIn("group.batches.map", javascript)
        self.assertIn("v2.1-test-phase4-checkpoint1", html)

    def test_runtime_image_packages_every_imported_phase3_module(self):
        root = Path(__file__).parents[1]
        dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn(
            "COPY dex_migrations.py dex_economics.py dex_legacy_economics.py dex_acquisition.py dex_rip.py dex_sealed.py ./",
            dockerfile,
        )
        self.assertIn(
            "import dex_migrations, dex_economics, dex_legacy_economics, dex_acquisition, dex_rip, dex_sealed",
            dockerfile,
        )


class SeededOperatorBatchOpenRegressionTest(unittest.TestCase):
    def test_seeded_op16_batch_detail_arrays_and_frontend_fallback(self):
        root = Path(__file__).parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary) / "data"
            environment = {
                "DEX_DATA_DIR": str(data),
                "DEX_DB_PATH": str(data / "dex.db"),
                "DEX_IMAGE_DIR": str(data / "images"),
                "DEX_INBOUND_DIR": str(data / "inbound"),
                "DEX_SOURCE_DB_DIR": str(data / "source-database"),
                "DEX_WATCH_INBOUND": "0",
                "DEX_SEED_DEMO": "1",
            }
            with patch.dict(os.environ, environment):
                spec = importlib.util.spec_from_file_location(
                    "dex_phase3_seeded_operator_regression", root / "app.py"
                )
                app = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(app)
                app.init_db()
                app.seed_demo()
                with app.connect() as db:
                    batch = db.execute(
                        "SELECT * FROM batches WHERE batch_code LIKE 'OP-B%-01'"
                    ).fetchone()
                    cards = [dict(row) for row in db.execute(
                        "SELECT * FROM cards WHERE batch_id=? ORDER BY id", (batch["id"],)
                    )]
                    acquisition = app.acquisition_payload(db, batch["id"])
                with app.open_readonly_database(app.DB_PATH) as db:
                    estimate = app.estimate_legacy_batch(db, batch["id"])
        self.assertEqual(batch["product_name"], "OP16 Booster Box")
        self.assertEqual(len(cards), 4)
        self.assertIsInstance(estimate["warnings"], list)
        self.assertIsInstance(acquisition["receipt_group"]["batches"], list)
        javascript = (root / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("const groupBatches = Array.isArray(group?.batches) ? group.batches : [];", javascript)
        self.assertIn("groupBatches.map", javascript)


class Phase3LegacyMigrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.source = Path(self.temp.name) / "legacy-source.db"
        db = sqlite3.connect(self.source)
        try:
            db.execute(
                """CREATE TABLE batches (
                    id INTEGER PRIMARY KEY,
                    batch_code TEXT NOT NULL,
                    total_cost REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'OPEN'
                )"""
            )
            db.execute("INSERT INTO batches VALUES (1, 'OP-LEGACY-01', 114.99, 'COMPLETE')")
            db.commit()
        finally:
            db.close()

    def tearDown(self):
        self.temp.cleanup()

    def test_disposable_v2_copy_migrates_once_without_backfill(self):
        working = Path(self.temp.name) / "legacy-working.db"
        shutil.copy2(self.source, working)
        db = sqlite3.connect(working)
        db.row_factory = sqlite3.Row
        try:
            self.assertEqual(
                apply_migrations(db, DEFAULT_MIGRATIONS[:-2]),
                tuple(migration.migration_id for migration in DEFAULT_MIGRATIONS[:-2]),
            )
            self.assertEqual(apply_migrations(db, DEFAULT_MIGRATIONS[:-2]), ())
            row = db.execute("SELECT * FROM batches WHERE id = 1").fetchone()
            self.assertEqual(row["economics_mode"], "LEGACY")
            self.assertEqual(row["economics_status"], "ESTIMATED")
            self.assertEqual(row["total_cost"], 114.99)
            self.assertIsNone(row["final_usd_paid_cents"])
            marker = db.execute(
                "SELECT migration_id FROM schema_migrations"
            ).fetchall()
            self.assertEqual(
                [tuple(row) for row in marker],
                [(migration.migration_id,) for migration in DEFAULT_MIGRATIONS[:-2]],
            )
            index = db.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_batches_receipt_group'"
            ).fetchone()
            self.assertIsNotNone(index)
        finally:
            db.close()

        untouched = sqlite3.connect(self.source)
        try:
            columns = {row[1] for row in untouched.execute("PRAGMA table_info(batches)")}
        finally:
            untouched.close()
        self.assertNotIn("final_usd_paid_cents", columns)
        source_db = sqlite3.connect(self.source)
        try:
            source_tables = {
                row[0] for row in source_db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        finally:
            source_db.close()
        self.assertNotIn("schema_migrations", source_tables)

    def test_receipt_group_payload_never_allocates_shared_costs(self):
        working = Path(self.temp.name) / "group.db"
        shutil.copy2(self.source, working)
        db = sqlite3.connect(working)
        db.row_factory = sqlite3.Row
        try:
            apply_migrations(db, DEFAULT_MIGRATIONS[:-2])
            db.execute(
                """UPDATE batches SET receipt_group_reference='R-1', product_name='Boxes',
                   economics_mode='SEALED_RIP', economics_status='DRAFT',
                   final_usd_paid_cents=60000, units_acquired=6 WHERE id=1"""
            )
            db.execute(
                """INSERT INTO batches
                   (id, batch_code, total_cost, receipt_group_reference, product_name,
                    economics_mode, economics_status, final_usd_paid_cents, units_acquired)
                   VALUES (2, 'OP-LEGACY-02', 80, 'R-1', 'Decks', 'SEALED_RIP', 'DRAFT', 8000, 2)"""
            )
            payload = acquisition_payload(db, 1)
        finally:
            db.close()
        self.assertEqual(payload["receipt_group"]["known_assigned_cost_cents"], 68000)
        self.assertEqual(len(payload["receipt_group"]["batches"]), 2)
        self.assertIn("not allocated automatically", payload["receipt_group"]["notice"])

    def test_actual_phase3_migration_rolls_back_on_index_conflict(self):
        working = Path(self.temp.name) / "migration-failure.db"
        shutil.copy2(self.source, working)
        db = sqlite3.connect(working)
        try:
            db.execute("CREATE TABLE idx_batches_receipt_group (id INTEGER PRIMARY KEY)")
            db.commit()
            with self.assertRaises(MigrationError):
                apply_migrations(db)
            columns = {row[1] for row in db.execute("PRAGMA table_info(batches)")}
            marker = db.execute(
                "SELECT migration_id FROM schema_migrations WHERE migration_id = ?",
                (DEFAULT_MIGRATIONS[0].migration_id,),
            ).fetchone()
        finally:
            db.close()
        self.assertNotIn("economics_mode", columns)
        self.assertIsNone(marker)


if __name__ == "__main__":
    unittest.main()
