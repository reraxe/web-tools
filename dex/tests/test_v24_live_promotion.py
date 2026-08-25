import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
import dex_sam_audited
from scripts.verify_v24_live_day_zero import verify_database


ROOT = Path(__file__).parents[1]


class V24LivePromotionTests(unittest.TestCase):
    def test_release_identity_is_live_everywhere(self):
        self.assertEqual(app.APP_VERSION, "v2.4-live")
        self.assertEqual((ROOT / "VERSION").read_text(encoding="utf-8").strip(), "v2.4-live")
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn('class="environment-badge">LIVE</strong>', html)
        self.assertIn('app.js?v=v2.4-live', html)

    def test_frozen_recognizer_and_catalog_knowledge_are_available(self):
        status = dex_sam_audited.frozen_component_status()
        self.assertTrue(status["available"])
        self.assertFalse(status["recognizer_changed"])
        self.assertEqual(status["build_fingerprint"], dex_sam_audited.BUILD_FINGERPRINT)
        catalog = json.loads(
            (ROOT / "sam_multi_evidence_frozen" / "config" / "one_piece_family_catalog_snapshot_v1.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(catalog["family_count"], len(catalog["families"]))
        self.assertGreater(catalog["family_count"], 0)
        self.assertFalse(catalog["recognition_authority"])

    def test_clean_day_zero_database_has_only_schema_and_zero_operational_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "live-data"
            references = root / "references"
            data.mkdir()
            references.mkdir()
            database = data / "dex.db"
            with (
                patch.object(app, "DATA_DIR", data),
                patch.object(app, "DB_PATH", database),
                patch.object(app, "IMAGE_DIR", data / "images"),
                patch.object(app, "INBOUND_DIR", root / "live-scanner-inbox"),
                patch.object(app, "SOURCE_DB_DIR", references),
                patch.object(app, "ONE_PIECE_REFERENCE_DIR", references),
            ):
                app.init_db()
            report = verify_database(database)
            self.assertEqual(report["status"], "PASS", report)
            self.assertEqual(report["integrity"], "ok")
            self.assertEqual(report["foreign_key_violations"], [])
            self.assertEqual(report["migration_prefixes"], [f"{number:04d}" for number in range(1, 20)])

    def test_live_promotion_adds_no_migration_0020(self):
        with sqlite3.connect(":memory:") as connection:
            from dex_migrations import DEFAULT_MIGRATIONS
            self.assertEqual(DEFAULT_MIGRATIONS[-1].migration_id.split("_", 1)[0], "0019")


if __name__ == "__main__":
    unittest.main()
