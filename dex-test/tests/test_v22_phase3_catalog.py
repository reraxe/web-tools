import json
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import patch

import app
from dex_catalog import (
    add_identifier_mapping,
    catalog_contract,
    correct_identifier_mapping,
    create_catalog_product,
    identify_unknown_product,
    lookup_identifier,
    normalize_identifier,
    scan_apply_product,
    search_catalog_products,
)
from dex_inbound import add_acquisition_line, create_acquisition
from dex_migrations import DEFAULT_MIGRATIONS, MigrationError, apply_migrations
from tests.test_phase5_sealed import base_schema


UPC_BOX = "012345678905"
EAN_DECK = "4006381333931"
GTIN_PACK = "10012345678902"
UNKNOWN_VALID = "036000291452"


class CatalogFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.db_path = root / "phase3-catalog.db"
        with (
            patch.object(app, "DB_PATH", self.db_path),
            patch.object(app, "DATA_DIR", root),
            patch.object(app, "IMAGE_DIR", root / "images"),
            patch.object(app, "INBOUND_DIR", root / "inbound"),
            patch.object(app, "SOURCE_DB_DIR", root / "source"),
        ):
            app.init_db()
        self.db = sqlite3.connect(self.db_path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def product(self, request, name, product_class="SEALED_PRODUCT", subtype="Booster Box", **fields):
        return create_catalog_product(
            self.db,
            {
                "request_id": request,
                "game": fields.pop("game", "One Piece"),
                "display_name": name,
                "set_code": fields.pop("set_code", "OP16"),
                "set_name": fields.pop("set_name", "Legacy of the Master"),
                "product_class": product_class,
                "product_subtype": subtype,
                "provenance": fields.pop("provenance", "SEED_FIXTURE"),
                "verified": True,
                **fields,
            },
        )

    def map(self, product, raw, request, identifier_type=""):
        return add_identifier_mapping(
            self.db,
            product["id"],
            {
                "request_id": request,
                "raw_identifier": raw,
                "identifier_type": identifier_type,
                "provenance": "SEED_FIXTURE",
                "verified": True,
            },
        )

    def acquisition(self, request="ACQ-CREATE", product_class="SEALED_PRODUCT"):
        result = create_acquisition(
            self.db,
            {
                "request_id": request,
                "source_scope": "DOMESTIC",
                "merchant_name": "Phase 3 QA Shop",
                "purchased_on": "2026-08-15",
                "payment_method": "CASH",
            },
        )
        return add_acquisition_line(
            self.db,
            result["acquisition"]["id"],
            {
                "request_id": f"{request}:LINE",
                "expected_revision": result["acquisition"]["revision"],
                "product_class": product_class,
            },
        )


class CatalogMigrationTest(unittest.TestCase):
    def test_phase3_migration_is_additive_and_does_not_backfill(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        base_schema(db)
        apply_migrations(db, DEFAULT_MIGRATIONS[:8])
        db.execute("INSERT INTO batches (id,batch_code,total_cost) VALUES (1,'P7C-PRESERVED',42.50)")
        db.execute(
            """INSERT INTO acquisitions
               (acquisition_uuid,acquisition_code,creation_request_id,created_at,updated_at)
               VALUES ('ACQ-OLD','ACQ-OLD-1','OLD','2026-08-15','2026-08-15')"""
        )
        before = tuple(db.execute("SELECT id,batch_code,total_cost FROM batches").fetchone())
        self.assertEqual(apply_migrations(db), ("0009_v22_phase3_product_catalog_upc", "0010_v22_phase4_source_documents", "0011_v22_phase5_receipt_intelligence", "0012_v22_prephase_ux_safety_hotfix", "0013_v22_phase6_downstream_intake_bridge", "0014_v22_phase7_sam_recognition", "0015_v22_rc3_hf1_mixed_purchase_reconciliation", "0016_v23_inventory_intelligence_phase1_receipt_semantics", "0017_v24_sam_phase1_family_printing", "0018_v24_jarvis_economics_sam_phase2"))
        self.assertEqual(tuple(db.execute("SELECT id,batch_code,total_cost FROM batches").fetchone()), before)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM catalog_products").fetchone()[0], 0)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM product_identifiers").fetchone()[0], 0)
        self.assertIn("catalog_product_id", {row[1] for row in db.execute("PRAGMA table_info(acquisition_lines)")})
        self.assertEqual(apply_migrations(db), ())
        db.close()

    def test_forced_failure_rolls_back_catalog_tables_linkage_and_marker(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        base_schema(db)
        apply_migrations(db, DEFAULT_MIGRATIONS[:8])
        db.execute("CREATE TABLE migration_index_sentinel (id INTEGER)")
        db.execute("CREATE INDEX idx_catalog_products_search ON migration_index_sentinel(id)")
        db.commit()
        with self.assertRaises(MigrationError):
            apply_migrations(db)
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn("catalog_products", tables)
        self.assertNotIn("product_identifiers", tables)
        self.assertNotIn("product_identifier_events", tables)
        self.assertNotIn("catalog_product_id", {row[1] for row in db.execute("PRAGMA table_info(acquisition_lines)")})
        self.assertIsNone(db.execute("SELECT 1 FROM schema_migrations WHERE migration_id='0009_v22_phase3_product_catalog_upc'").fetchone())
        db.close()


class IdentifierValidationTest(unittest.TestCase):
    def test_supported_codes_validate_and_preserve_leading_zeroes(self):
        upc = normalize_identifier(UPC_BOX)
        self.assertEqual(upc["identifier_type"], "UPC_A")
        self.assertEqual(upc["normalized_identifier"], "00" + UPC_BOX)
        self.assertEqual(normalize_identifier(EAN_DECK)["identifier_type"], "EAN_13")
        self.assertEqual(normalize_identifier(GTIN_PACK)["identifier_type"], "GTIN_14")
        self.assertEqual(normalize_identifier(" dex-op16-box ", "INTERNAL")["normalized_identifier"], "DEX-OP16-BOX")

    def test_invalid_check_digit_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "check digit"):
            normalize_identifier(UPC_BOX[:-1] + "4")


class CatalogServiceTest(CatalogFixture):
    def test_recognized_upc_repeats_increment_one_line_and_request_replay_is_idempotent(self):
        product = self.product("PROD-BOX", "OP16 Booster Box")
        self.map(product, UPC_BOX, "MAP-BOX")
        result = self.acquisition()
        acquisition_id = result["acquisition"]["id"]
        first_payload = {
            "request_id": "SCAN-BOX-1",
            "expected_revision": result["acquisition"]["revision"],
            "raw_identifier": UPC_BOX,
        }
        first = scan_apply_product(self.db, acquisition_id, first_payload)
        self.assertEqual(first["status"], "RECOGNIZED")
        self.assertEqual(first["decision_level"], "AUTOMATIC_VISIBLE")
        self.assertEqual(first["scan"]["quantity"], 1)
        self.assertEqual(len([line for line in first["acquisition"]["lines"] if not line["canceled_at"]]), 1)
        replay = scan_apply_product(self.db, acquisition_id, first_payload)
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(replay["acquisition"]["lines"][0]["quantity"], 1)
        current = first["acquisition"]
        for index in (2, 3):
            response = scan_apply_product(
                self.db,
                acquisition_id,
                {
                    "request_id": f"SCAN-BOX-{index}",
                    "expected_revision": current["acquisition"]["revision"],
                    "raw_identifier": UPC_BOX,
                },
            )
            current = response["acquisition"]
        self.assertEqual(current["lines"][0]["quantity"], 3)
        self.assertEqual(current["lines"][0]["catalog_product"]["display_name"], "OP16 Booster Box")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM acquisition_lines").fetchone()[0], 1)

    def test_ean_gtin_and_different_products_create_separate_lines(self):
        deck = self.product("PROD-DECK", "ST27 Starter Deck", set_code="ST27", subtype="Starter Deck")
        pack = self.product("PROD-PACK", "OP16 Sleeved Booster", "PACK_PRODUCT", "Sleeved Booster")
        self.map(deck, EAN_DECK, "MAP-DECK")
        self.map(pack, GTIN_PACK, "MAP-PACK")
        result = self.acquisition(product_class="PACK_PRODUCT")
        acquisition_id = result["acquisition"]["id"]
        for request, raw in (("SCAN-EAN", EAN_DECK), ("SCAN-GTIN", GTIN_PACK)):
            response = scan_apply_product(
                self.db,
                acquisition_id,
                {
                    "request_id": request,
                    "expected_revision": result["acquisition"]["revision"],
                    "raw_identifier": raw,
                },
            )
            result = response["acquisition"]
        active = [line for line in result["lines"] if not line["canceled_at"]]
        self.assertEqual([(line["product_name"], line["quantity"]) for line in active], [("ST27 Starter Deck", 1), ("OP16 Sleeved Booster", 1)])

    def test_unknown_does_not_guess_or_mutate_and_local_identification_is_not_remembered(self):
        result = self.acquisition()
        acquisition_id = result["acquisition"]["id"]
        unknown = scan_apply_product(
            self.db,
            acquisition_id,
            {
                "request_id": "SCAN-UNKNOWN",
                "expected_revision": result["acquisition"]["revision"],
                "raw_identifier": UNKNOWN_VALID,
            },
        )
        self.assertEqual(unknown["status"], "UNKNOWN")
        self.assertEqual(unknown["decision_level"], "NEEDS_ATTENTION")
        self.assertEqual(unknown["acquisition"]["acquisition"]["revision"], result["acquisition"]["revision"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM catalog_products").fetchone()[0], 0)
        local = identify_unknown_product(
            self.db,
            acquisition_id,
            {
                "request_id": "IDENTIFY-LOCAL",
                "expected_revision": result["acquisition"]["revision"],
                "raw_identifier": UNKNOWN_VALID,
                "remember_mapping": False,
                "game": "Riftbound",
                "display_name": "Local Demo Box",
                "set_code": "SFD",
                "set_name": "Spiritforged",
                "product_class": "SEALED_PRODUCT",
                "product_subtype": "Collection Box",
            },
        )
        self.assertEqual(local["status"], "IDENTIFIED_LOCAL")
        self.assertIsNone(local["acquisition"]["lines"][0]["catalog_product_id"])
        self.assertEqual(local["acquisition"]["lines"][0]["quantity"], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM product_identifiers").fetchone()[0], 0)
        self.assertEqual(lookup_identifier(self.db, UNKNOWN_VALID)["status"], "UNKNOWN")

    def test_remembered_mapping_resolves_in_future_acquisition_and_resume_is_stable(self):
        first = self.acquisition("ACQ-FIRST")
        learned = identify_unknown_product(
            self.db,
            first["acquisition"]["id"],
            {
                "request_id": "IDENTIFY-REMEMBER",
                "expected_revision": first["acquisition"]["revision"],
                "raw_identifier": UNKNOWN_VALID,
                "remember_mapping": True,
                "game": "Pokemon",
                "display_name": "Journey Together ETB",
                "set_code": "JTG",
                "set_name": "Journey Together",
                "product_class": "SEALED_PRODUCT",
                "product_subtype": "ETB",
            },
        )
        self.assertEqual(learned["status"], "IDENTIFIED_AND_REMEMBERED")
        self.assertEqual(learned["acquisition"]["lines"][0]["quantity"], 1)
        reloaded = acquisition_payload = learned["acquisition"]
        self.assertEqual(reloaded["lines"][0]["catalog_product"]["display_name"], "Journey Together ETB")
        second = self.acquisition("ACQ-SECOND")
        automatic = scan_apply_product(
            self.db,
            second["acquisition"]["id"],
            {
                "request_id": "SCAN-LEARNED",
                "expected_revision": second["acquisition"]["revision"],
                "raw_identifier": UNKNOWN_VALID,
            },
        )
        self.assertEqual(automatic["status"], "RECOGNIZED")
        self.assertEqual(automatic["product"]["provenance"], "OPERATOR_DEFINED")
        self.assertEqual(automatic["identifier"]["mapping_provenance"], "OPERATOR_CONFIRMED")

    def test_collision_is_blocked_and_correction_preserves_mapping_history(self):
        first = self.product("PROD-1", "Original Box")
        second = self.product("PROD-2", "Corrected Box", set_code="OP17")
        mapped = self.map(first, UPC_BOX, "MAP-1")
        with self.assertRaisesRegex(ValueError, "already mapped"):
            self.map(second, UPC_BOX, "MAP-COLLISION")
        identifier_id = mapped["identifier"]["mapping_id"]
        with self.assertRaisesRegex(ValueError, "explanatory note"):
            correct_identifier_mapping(
                self.db,
                identifier_id,
                {"request_id": "CORRECT-NO-NOTE", "catalog_product_id": second["id"], "reason_code": "WRONG_PRODUCT"},
            )
        corrected = correct_identifier_mapping(
            self.db,
            identifier_id,
            {
                "request_id": "CORRECT-1",
                "catalog_product_id": second["id"],
                "reason_code": "WRONG_PRODUCT",
                "notes": "Fixture intentionally began with the wrong commercial product.",
            },
        )
        self.assertEqual(corrected["catalog_product_id"], second["id"])
        mapping_events = [event for event in corrected["events"] if event["event_type"].startswith("MAPPING_")]
        self.assertEqual([event["event_type"] for event in mapping_events], ["MAPPING_CREATED", "MAPPING_CORRECTED"])
        self.assertEqual(mapping_events[-1]["from_catalog_product_id"], first["id"])
        self.assertEqual(mapping_events[-1]["to_catalog_product_id"], second["id"])

    def test_catalog_and_upc_never_create_downstream_or_economic_facts(self):
        product = self.product("PROD-SAFE", "Safety Box")
        self.map(product, UPC_BOX, "MAP-SAFE")
        result = self.acquisition()
        scanned = scan_apply_product(
            self.db,
            result["acquisition"]["id"],
            {"request_id": "SCAN-SAFE", "expected_revision": result["acquisition"]["revision"], "raw_identifier": UPC_BOX},
        )
        self.assertEqual(scanned["acquisition"]["acquisition"]["state"], "ACQUISITION_INCOMPLETE")
        for table in ("batches", "cards", "sealed_units", "rip_sessions", "rip_basis_events"):
            self.assertEqual(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
        self.assertIsNone(scanned["acquisition"]["lines"][0]["assigned_landed_cost_cents"])

    def test_manual_pack_sealed_and_single_card_lines_remain_available(self):
        result = self.acquisition(product_class="PACK_PRODUCT")
        result = add_acquisition_line(
            self.db,
            result["acquisition"]["id"],
            {"request_id": "MANUAL-SEALED", "expected_revision": result["acquisition"]["revision"], "product_class": "SEALED_PRODUCT", "game": "Pokemon", "product_name": "Manual ETB", "quantity": 2},
        )
        result = add_acquisition_line(
            self.db,
            result["acquisition"]["id"],
            {"request_id": "MANUAL-SINGLES", "expected_revision": result["acquisition"]["revision"], "product_class": "SINGLE_CARDS", "game": "One Piece", "set_code": "OP16", "quantity": 4},
        )
        self.assertEqual([line["product_class"] for line in result["lines"]], ["PACK_PRODUCT", "SEALED_PRODUCT", "SINGLE_CARDS"])
        self.assertTrue(all(line["catalog_product_id"] is None for line in result["lines"]))


class CatalogPerformanceTest(CatalogFixture):
    def test_thousand_product_catalog_search_and_lookup_are_prompt(self):
        now = "2026-08-15T00:00:00+00:00"
        self.db.executemany(
            """INSERT INTO catalog_products
               (product_uuid,creation_request_id,game,display_name,set_code,set_name,product_class,
                product_subtype,manufacturer_product_code,active,provenance,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,1,'IMPORT',?,?)""",
            [
                (f"CAT-{i}", f"REQ-{i}", f"Game {i % 8}", f"Catalog Product {i}", f"SET{i % 40}", f"Set {i % 40}", "PACK_PRODUCT" if i % 2 else "SEALED_PRODUCT", "Booster Pack", f"MFG-{i}", now, now)
                for i in range(1000)
            ],
        )
        started = time.perf_counter()
        rows = search_catalog_products(self.db, "Catalog Product 99")
        elapsed_ms = (time.perf_counter() - started) * 1000
        self.assertTrue(rows)
        self.assertLess(elapsed_ms, 250)
        print(f"Phase 3 catalog performance: 1,000 products searched in {elapsed_ms:.2f} ms")


class CatalogApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = (
            patch.object(app, "DB_PATH", root / "dex.db"),
            patch.object(app, "DATA_DIR", root),
            patch.object(app, "IMAGE_DIR", root / "images"),
            patch.object(app, "INBOUND_DIR", root / "inbound"),
            patch.object(app, "SOURCE_DB_DIR", root / "source"),
        )
        for item in self.patches:
            item.start()
        app.init_db()
        self.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.DexHandler)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.thread.join(timeout=3); self.server.server_close()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def request(self, path, method="GET", body=None):
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_catalog_lookup_search_scan_and_contract_apis(self):
        status, product = self.request(
            "/api/catalog/products",
            "POST",
            {"request_id": "API-PRODUCT", "game": "One Piece", "display_name": "API OP16 Box", "set_code": "OP16", "product_class": "SEALED_PRODUCT", "product_subtype": "Booster Box"},
        )
        self.assertEqual(status, 201)
        status, mapped = self.request(
            f"/api/catalog/products/{product['id']}/identifiers",
            "POST",
            {"request_id": "API-MAP", "raw_identifier": UPC_BOX, "provenance": "OPERATOR_CONFIRMED"},
        )
        self.assertEqual(status, 201)
        status, lookup = self.request(f"/api/catalog/identifiers/lookup?identifier={UPC_BOX}")
        self.assertEqual((status, lookup["status"]), (200, "RECOGNIZED"))
        status, search = self.request("/api/catalog/products?q=OP16")
        self.assertEqual(search["products"][0]["id"], product["id"])
        status, contract = self.request("/api/catalog/contract")
        self.assertEqual(contract, catalog_contract())
        self.assertFalse(contract["boundaries"]["sealed_unit_identity"])
        status, created = self.request("/api/acquisitions", "POST", {"request_id": "API-ACQ"})
        status, created = self.request(
            f"/api/acquisitions/{created['acquisition']['id']}/lines",
            "POST",
            {"request_id": "API-LINE", "expected_revision": created["acquisition"]["revision"], "product_class": "SEALED_PRODUCT"},
        )
        status, scanned = self.request(
            f"/api/acquisitions/{created['acquisition']['id']}/product-scan",
            "POST",
            {"request_id": "API-SCAN", "expected_revision": created["acquisition"]["revision"], "raw_identifier": UPC_BOX},
        )
        self.assertEqual((status, scanned["status"], scanned["scan"]["quantity"]), (200, "RECOGNIZED", 1))
        status, history = self.request(f"/api/catalog/identifiers/{mapped['identifier']['mapping_id']}/history")
        self.assertEqual(status, 200)
        self.assertTrue(any(event["event_type"] == "SCAN_APPLIED" for event in history["events"]))


if __name__ == "__main__":
    unittest.main()
