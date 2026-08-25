import hashlib
import json
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import app
import dex_sam_audited as audited
from dex_migrations import DEFAULT_MIGRATIONS, MigrationError, apply_migrations
from tests.test_phase5_sealed import base_schema


def fake_result(scan_hash):
    return {
        "accepted_build_identifier": audited.BUILD_IDENTIFIER,
        "build_fingerprint": audited.BUILD_FINGERPRINT,
        "source_sha256": scan_hash,
        "suggested_family": "OP16-034",
        "suggested_name": "Monkey.D.Luffy",
        "evidence_state": "SUPPORT",
        "review_state": "SUGGESTION",
        "human_explanation": ["Frozen evidence supports OP16-034."],
        "top_candidate": {"card_number": "OP16-034", "canonical_name": "Monkey.D.Luffy", "visual_score": .91},
        "candidates": [
            {"card_number": "OP16-034", "canonical_name": "Monkey.D.Luffy", "visual_score": .91, "assertions": []},
            {"card_number": "OP16-035", "canonical_name": "Roronoa Zoro", "visual_score": .82, "assertions": []},
        ],
        "candidate_count": 2,
        "dual_ocr": {"state": "CANDIDATE_ONLY", "observations": []},
        "name_observations": [],
        "conflicts": False,
        "candidate_generation": {"strategy": "FROZEN"},
        "latency_ms": {"operator_suggestion_total": 1.0},
        "authority": {"suggestion_only": True, "identity_applied": False, "exact_printing_authority": False},
    }


class AuditedSamIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db_path = self.root / "dex.db"
        self.data = self.root / "data"
        self.refs = self.root / "refs"
        self.data.mkdir()
        self.refs.mkdir()
        with (
            patch.object(app, "DB_PATH", self.db_path),
            patch.object(app, "DATA_DIR", self.data),
            patch.object(app, "IMAGE_DIR", self.data / "images"),
            patch.object(app, "INBOUND_DIR", self.data / "inbound"),
            patch.object(app, "SOURCE_DB_DIR", self.refs),
            patch.object(app, "ONE_PIECE_REFERENCE_DIR", self.refs),
        ):
            app.init_db()
        self.db = sqlite3.connect(self.db_path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute(
            """INSERT INTO batches
                 (batch_code,created_at,status,game,set_code,set_name,acquisition_type,total_cost)
               VALUES ('AUDIT-BATCH','2026-08-24','OPEN','One Piece','OP16','The Time of Battle','Singles',0)"""
        )
        batch_id = self.db.execute("SELECT id FROM batches WHERE batch_code='AUDIT-BATCH'").fetchone()[0]
        scan_dir = self.data / "images"
        scan_dir.mkdir(parents=True, exist_ok=True)
        self.scan = scan_dir / "scan.png"
        Image.new("RGB", (300, 420), (230, 40, 50)).save(self.scan)
        self.db.execute(
            """INSERT INTO cards
                 (sku,batch_id,created_at,updated_at,name,status,front_image,variant)
               VALUES ('OP-AUDIT-0001',?,'2026-08-24','2026-08-24','Needs identification','REVIEW','images/scan.png','Standard')""",
            (batch_id,),
        )
        reference = self.refs / "OP16-034.png"
        Image.new("RGB", (300, 420), (225, 45, 55)).save(reference)
        self.db.execute(
            """INSERT INTO sam_reference_records
                 (reference_uuid,game,card_number,set_code,card_name,source_filename,source_reference,
                  width,height,file_size,mtime_ns,sha256,perceptual_hash,visual_bucket,index_version,indexed_at)
               VALUES (?,'One Piece','OP16-034','OP16','Monkey.D.Luffy','OP16-034.png','OP16-034.png',
                       300,420,?,?,?,?,'abcd','fixture','2026-08-24')""",
            (str(uuid.uuid4()), reference.stat().st_size, reference.stat().st_mtime_ns,
             audited.sha256(reference), json.dumps({"hashes": [{"full": "0" * 64, "frame": "0" * 64}], "bucket": "abcd"})),
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def recognize(self, request_id="SAM-AUDIT-TEST-1"):
        return audited.recognize_card(
            self.db, "OP-AUDIT-0001", data_dir=self.data, reference_root=self.refs,
            request_id=request_id, runner=lambda path, digest, index, data: fake_result(digest),
        )

    def decision(self, result_uuid, action="CONFIRMED_UNCHANGED", **extra):
        payload = {"request_id": f"DEC-{uuid.uuid4()}", "action": action, **extra}
        return audited.record_operator_decision(self.db, result_uuid, payload)

    # 1
    def test_001_migration_is_ordered_after_v24_baseline(self):
        self.assertEqual(DEFAULT_MIGRATIONS[-1].migration_id, "0019_v24_sam_multi_evidence_operator_trial_v1a")

    # 2
    def test_002_scan_is_accepted_and_frozen(self):
        result = self.recognize()
        self.assertEqual(result["original_result"]["suggested_family"], "OP16-034")
        self.assertTrue(result["original_result"]["result_logged_before_operator"])

    # 3
    def test_003_prior_benchmark_scan_is_rejected(self):
        digest = audited.sha256(self.scan)
        with patch.object(audited, "_blocklisted_hashes", return_value={digest}):
            with self.assertRaisesRegex(ValueError, "prior research"):
                self.recognize()

    # 4
    def test_004_result_generated_with_frozen_build_identity(self):
        result = self.recognize()["original_result"]
        self.assertEqual(result["build_fingerprint"], audited.BUILD_FINGERPRINT)
        self.assertFalse(result["recognizer_changed"])

    # 5
    def test_005_no_identity_write_before_confirmation(self):
        self.recognize()
        card = self.db.execute("SELECT * FROM cards WHERE sku='OP-AUDIT-0001'").fetchone()
        self.assertIsNone(card["sam_family_id"])
        self.assertEqual(card["name"], "Needs identification")

    # 6
    def test_006_confirm_applies_operator_family(self):
        result = self.recognize()
        decided = self.decision(result["result_uuid"])
        self.assertTrue(decided["inventory_family_authoritative"])
        self.assertEqual(self.db.execute("SELECT card_number FROM cards").fetchone()[0], "OP16-034")

    # 7
    def test_007_correction_applies_selected_family(self):
        result = self.recognize()
        self.decision(result["result_uuid"], "CORRECTED_FAMILY", selected_family="OP16-035",
                      reason_code="OPERATOR_VISUAL_IDENTIFICATION", notes="Printed number is OP16-035.")
        self.assertEqual(self.db.execute("SELECT card_number FROM cards").fetchone()[0], "OP16-035")

    # 8
    def test_008_mark_unidentified_never_writes_identity(self):
        result = self.recognize()
        self.decision(result["result_uuid"], "MARKED_UNIDENTIFIED",
                      reason_code="INSUFFICIENT_EVIDENCE", notes="Unreadable scan.")
        self.assertIsNone(self.db.execute("SELECT sam_family_id FROM cards").fetchone()[0])

    # 9
    def test_009_needs_review_never_writes_identity(self):
        result = self.recognize()
        self.decision(result["result_uuid"], "ESCALATED_REVIEW",
                      reason_code="INSUFFICIENT_EVIDENCE", notes="Second review required.")
        self.assertIsNone(self.db.execute("SELECT sam_family_id FROM cards").fetchone()[0])

    # 10
    def test_010_original_result_is_immutable_after_decision(self):
        result = self.recognize()
        before = result["original_result_sha256"]
        self.decision(result["result_uuid"])
        after = audited.get_result(self.db, result["result_uuid"])["original_result_sha256"]
        self.assertEqual(before, after)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("UPDATE sam_audited_recognition_results SET suggested_family='X'")

    # 11
    def test_011_operator_decision_is_separate_record(self):
        result = self.recognize()
        self.decision(result["result_uuid"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sam_audited_recognition_results").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sam_audited_operator_decisions").fetchone()[0], 1)

    # 12
    def test_012_unverified_delta_is_recorded(self):
        result = self.recognize()
        self.decision(result["result_uuid"], "CORRECTED_FAMILY", selected_family="OP16-035",
                      reason_code="OCR_FAILURE", notes="Footer OCR was wrong.")
        row = self.db.execute("SELECT * FROM sam_audited_recognition_deltas").fetchone()
        self.assertEqual(row["verification_state"], "UNVERIFIED")
        self.assertFalse(json.loads(row["forensic_json"])["operator_decision_is_verified_truth"])

    # 13
    def test_013_catalog_search_is_descriptive_only(self):
        row = audited.catalog_search("OP16-035")["families"][0]
        self.assertEqual(row["card_number"], "OP16-035")
        self.assertTrue(row["descriptive_only_until_operator_selection"])

    # 14
    def test_014_unknown_catalog_family_is_rejected(self):
        result = self.recognize()
        with self.assertRaisesRegex(ValueError, "frozen local"):
            self.decision(result["result_uuid"], "CORRECTED_FAMILY", selected_family="OP99-999",
                          reason_code="OTHER", notes="Not a real catalog family.")

    # 15
    def test_015_exact_printing_remains_unchanged(self):
        self.db.execute("UPDATE cards SET sam_printing_id=NULL,sam_printing_certainty='UNRESOLVED'")
        result = self.recognize()
        decided = self.decision(result["result_uuid"])
        card = self.db.execute("SELECT sam_printing_id,sam_printing_certainty,variant FROM cards").fetchone()
        self.assertEqual(tuple(card), (None, "UNRESOLVED", "Standard"))
        self.assertTrue(decided["exact_printing_unchanged_by_audited_trial"])

    # 16
    def test_016_recognition_request_is_idempotent(self):
        first = self.recognize("SAME-RESULT-REQUEST")
        second = self.recognize("SAME-RESULT-REQUEST")
        self.assertEqual(first["result_uuid"], second["result_uuid"])
        self.assertTrue(second["replayed"])

    # 17
    def test_017_decision_request_is_idempotent(self):
        result = self.recognize()
        payload = {"request_id": "SAME-DECISION-REQUEST", "action": "CONFIRMED_UNCHANGED"}
        first = audited.record_operator_decision(self.db, result["result_uuid"], payload)
        second = audited.record_operator_decision(self.db, result["result_uuid"], payload)
        self.assertEqual(first["operator_decisions"][0]["id"], second["operator_decisions"][0]["id"])
        self.assertTrue(second["replayed"])

    # 18
    def test_018_verified_truth_is_optional_and_separate(self):
        result = self.recognize()
        self.decision(result["result_uuid"])
        verified = audited.record_verified_truth(self.db, result["result_uuid"], {
            "request_id": "VERIFY-1", "disposition": "SAM_CORRECT", "notes": "Independent review.",
        })
        self.assertEqual(verified["verified_truth"][0]["verified_family"], "OP16-034")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sam_audited_operator_decisions").fetchone()[0], 1)

    # 19
    def test_019_operator_correction_later_reversed_is_supported(self):
        result = self.recognize()
        self.decision(result["result_uuid"], "CORRECTED_FAMILY", selected_family="OP16-035",
                      reason_code="OCR_FAILURE", notes="Initial operator correction.")
        verified = audited.record_verified_truth(self.db, result["result_uuid"], {
            "request_id": "VERIFY-REVERSE", "disposition": "OPERATOR_CORRECTION_LATER_REVERSED",
            "verified_family": "OP16-034", "notes": "Second review reversed the operator correction.",
        })
        self.assertEqual(verified["verified_truth"][0]["disposition"], "OPERATOR_CORRECTION_LATER_REVERSED")

    # 20
    def test_020_frozen_recognizer_components_match_accepted_hashes(self):
        status = audited.frozen_component_status()
        self.assertTrue(status["available"], status)
        self.assertEqual(status["mismatched"], [])

    # 21
    def test_021_migration_is_additive_idempotent_and_integrity_safe(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        base_schema(db)
        apply_migrations(db, DEFAULT_MIGRATIONS[:-1])
        db.execute("INSERT INTO batches (id,batch_code) VALUES (1,'LEGACY-AUDIT')")
        db.execute("INSERT INTO cards (id,sku,batch_id) VALUES (1,'LEGACY-AUDIT-1',1)")
        before = tuple(db.execute("SELECT id,sku,batch_id FROM cards").fetchone())
        self.assertEqual(
            apply_migrations(db, DEFAULT_MIGRATIONS[-1:]),
            ("0019_v24_sam_multi_evidence_operator_trial_v1a",),
        )
        self.assertEqual(tuple(db.execute("SELECT id,sku,batch_id FROM cards").fetchone()), before)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM sam_audited_recognition_results").fetchone()[0], 0)
        self.assertEqual(apply_migrations(db, DEFAULT_MIGRATIONS[-1:]), ())
        self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        db.close()

    # 22
    def test_022_failed_migration_rolls_back_without_ledger_marker(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        base_schema(db)
        apply_migrations(db, DEFAULT_MIGRATIONS[:-1])
        db.execute("CREATE TABLE sam_audited_operator_decisions (sentinel TEXT)")
        db.commit()
        with self.assertRaises(MigrationError):
            apply_migrations(db, DEFAULT_MIGRATIONS[-1:])
        self.assertIsNone(db.execute(
            "SELECT 1 FROM schema_migrations WHERE migration_id='0019_v24_sam_multi_evidence_operator_trial_v1a'"
        ).fetchone())
        self.assertNotIn(
            "sam_audited_recognition_results",
            {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")},
        )
        self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        db.close()

    # 23
    def test_023_database_enforces_one_decision_per_frozen_result(self):
        result = self.recognize()
        self.decision(result["result_uuid"])
        existing = self.db.execute("SELECT * FROM sam_audited_operator_decisions").fetchone()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                """INSERT INTO sam_audited_operator_decisions
                     (decision_uuid,request_id,result_id,card_id,action,identity_applied,
                      recognition_result_sha256,effective_at,recorded_at)
                   VALUES (?,?,?,?,?,0,?,?,?)""",
                (
                    "DUPLICATE-DECISION", "DUPLICATE-DECISION-REQUEST", existing["result_id"],
                    existing["card_id"], "ESCALATED_REVIEW", existing["recognition_result_sha256"],
                    "2026-08-24T00:00:00+00:00", "2026-08-24T00:00:00+00:00",
                ),
            )


if __name__ == "__main__":
    unittest.main()
