import importlib.util
import os
import sqlite3
import tempfile
import time
import unittest
import uuid
from pathlib import Path

from PIL import Image, ImageDraw

from dex_migrations import DEFAULT_MIGRATIONS, MigrationError, apply_migrations
from dex_sam import decide_recognition, index_reference_library, recognition_result, submit_recognition
from dex_sam_identity import evaluate_printing_candidates, identity_history, record_assertion


def make_art(path: Path, *, accent=(20, 80, 170)) -> None:
    image = Image.new("RGB", (500, 700), (246, 242, 226))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((18, 18, 482, 682), radius=24, outline=(20, 20, 20), width=12)
    draw.rectangle((45, 55, 455, 420), fill=accent)
    draw.ellipse((125, 110, 375, 360), fill=(190, 40, 55), outline="white", width=10)
    draw.text((65, 660), "OP16-034", fill=(10, 10, 10))
    image.save(path)


class SamPhase1FamilyPrintingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.data = cls.root / "data"
        cls.references = cls.root / "references"
        os.environ.update({
            "DEX_DATA_DIR": str(cls.data),
            "DEX_DB_PATH": str(cls.data / "dex.db"),
            "DEX_IMAGE_DIR": str(cls.data / "images"),
            "DEX_INBOUND_DIR": str(cls.data / "inbound"),
            "DEX_SOURCE_DB_DIR": str(cls.references),
            "DEX_ONE_PIECE_REFERENCE_DIR": str(cls.references),
            "DEX_WATCH_INBOUND": "0",
            "DEX_SEED_DEMO": "0",
            "DEX_SAM_OCR_ENABLED": "0",
        })
        spec = importlib.util.spec_from_file_location(
            "dex_v24_sam_phase1_app", Path(__file__).parents[1] / "app.py"
        )
        cls.app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.app)
        cls.app.init_db()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        with self.app.connect() as db:
            db.execute("PRAGMA foreign_keys=OFF")
            for trigger in (
                "sam_identity_assertions_no_update", "sam_identity_assertions_no_delete",
                "sam_identity_events_no_update", "sam_identity_events_no_delete",
            ):
                db.execute(f"DROP TRIGGER IF EXISTS {trigger}")
            for table in (
                "sam_identity_decision_events", "sam_identity_assertions",
                "sam_reference_asset_links", "sam_printing_external_ids",
                "sam_commercial_printings", "sam_card_families",
                "sam_recognition_decisions", "sam_recognition_candidates",
                "sam_recognition_jobs", "sam_reference_records",
                "sam_reference_index_runs", "sam_metadata_refresh_runs",
                "sam_metadata_cache", "source_cards", "cards", "rip_sessions",
                "batches", "acquisition_lines", "acquisitions",
            ):
                db.execute(f"DELETE FROM {table}")
            db.execute(
                "CREATE TRIGGER sam_identity_assertions_no_update BEFORE UPDATE ON sam_identity_assertions "
                "BEGIN SELECT RAISE(ABORT, 'SAM identity assertions are append-only'); END"
            )
            db.execute(
                "CREATE TRIGGER sam_identity_assertions_no_delete BEFORE DELETE ON sam_identity_assertions "
                "BEGIN SELECT RAISE(ABORT, 'SAM identity assertions are append-only'); END"
            )
            db.execute(
                "CREATE TRIGGER sam_identity_events_no_update BEFORE UPDATE ON sam_identity_decision_events "
                "BEGIN SELECT RAISE(ABORT, 'SAM identity decisions are append-only'); END"
            )
            db.execute(
                "CREATE TRIGGER sam_identity_events_no_delete BEFORE DELETE ON sam_identity_decision_events "
                "BEGIN SELECT RAISE(ABORT, 'SAM identity decisions are append-only'); END"
            )
            db.execute("PRAGMA foreign_keys=ON")
        self.references.mkdir(parents=True, exist_ok=True)
        for path in self.references.glob("*"):
            if path.is_file():
                path.unlink()

    def _batch_card(self, image: Path, *, variant="Legacy Variant", cost=123.45):
        now = self.app.utcnow()
        with self.app.connect() as db:
            batch_id = db.execute(
                """INSERT INTO batches
                   (batch_code,created_at,status,game,set_code,set_name,acquisition_type,total_cost)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (f"SAM-P1-{uuid.uuid4().hex[:8]}", now, "OPEN", "One Piece", "OP16",
                 "Time of Battle", "Singles", cost),
            ).lastrowid
            sku = f"SAM-P1-{uuid.uuid4().hex[:10].upper()}"
            destination = self.app.IMAGE_DIR / sku / "front.png"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(image.read_bytes())
            relative = str(destination.relative_to(self.data)).replace("\\", "/")
            card_id = db.execute(
                """INSERT INTO cards
                   (sku,batch_id,created_at,updated_at,card_number,name,variant,status,front_image,source_hash)
                   VALUES (?,?,?,?,?,'Needs identification',?,'REVIEW',?,?)""",
                (sku, batch_id, now, now, "OP16-034", variant, relative, uuid.uuid4().hex),
            ).lastrowid
        return card_id, sku

    def _index(self, filenames):
        base = self.root / "base.png"
        make_art(base)
        for filename in filenames:
            (self.references / filename).write_bytes(base.read_bytes())
        with self.app.connect() as db:
            return index_reference_library(db, self.references, request_id=f"INDEX-{uuid.uuid4()}")

    def _recognize(self, filenames=("OP16-034.jpg",), *, variant="Legacy Variant"):
        self._index(filenames)
        image = self.references / filenames[0]
        card_id, sku = self._batch_card(image, variant=variant)
        with self.app.connect() as db:
            result = submit_recognition(
                db, card_id, data_dir=self.data, request_id=f"RECOGNIZE-{uuid.uuid4()}"
            )
            card = dict(db.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone())
        return card_id, sku, result, card

    def test_family_correct_printing_unknown_never_updates_legacy_variant(self):
        _, _, result, card = self._recognize()
        self.assertEqual(result["family"]["card_number"], "OP16-034")
        self.assertTrue(result["family"]["authoritative"])
        self.assertEqual(result["printing"]["certainty"], "UNRESOLVED")
        self.assertFalse(result["printing"]["authoritative"])
        self.assertIsNone(card["sam_printing_id"])
        self.assertEqual(card["variant"], "Legacy Variant")

    def test_same_family_wrong_printing_collision_forces_unresolved(self):
        _, _, result, card = self._recognize(("OP16-034_p1.jpg", "OP16-034_p2.jpg"))
        self.assertEqual(result["family"]["card_number"], "OP16-034")
        self.assertIn(result["printing"]["certainty"], ("UNRESOLVED", "CONFLICTING"))
        self.assertFalse(result["printing"]["authoritative"])
        self.assertGreaterEqual(len(result["printing"]["competing_same_family_printings"]), 2)
        self.assertIsNone(card["sam_printing_id"])
        self.assertEqual(card["variant"], "Legacy Variant")

    def test_positive_marker_can_create_suggestion_but_never_authority(self):
        candidate = {
            "id": 1, "family_id": 10, "commercial_printing_id": 99,
            "printing_uuid": "PRINT-99", "variant_label": "SP",
            "visual_score": 0.98,
            "evidence_requirements": {"required_markers": ["SP_MARKER"]},
        }
        result = evaluate_printing_candidates([candidate], 10, {"SP_MARKER": "PRESENT"})
        self.assertEqual(result["certainty"], "HIGH_CONFIDENCE_SUGGESTION")
        self.assertFalse(result["authority_granted"])
        self.assertEqual(result["candidate"]["printing_id"], 99)

    def test_missing_marker_blocks_special_printing_authority(self):
        candidate = {
            "id": 1, "family_id": 10, "commercial_printing_id": 99,
            "variant_label": "Winner", "visual_score": 0.99,
            "evidence_requirements": {"required_markers": ["WINNER_MARKER"]},
        }
        result = evaluate_printing_candidates(
            [candidate], 10, {"WINNER_MARKER": "ABSENT_CONFIDENT"}
        )
        self.assertEqual(result["certainty"], "UNRESOLVED")
        self.assertEqual(result["unresolved_reason"], "REQUIRED_PRINTING_MARKER_ABSENT")
        self.assertFalse(result["authority_granted"])

    def test_system_caller_cannot_grant_exact_printing_authority(self):
        card_id, _, _, _ = self._recognize(("OP16-034_p1.jpg",))
        with self.app.connect() as db:
            family_id = db.execute(
                "SELECT family_id FROM sam_reference_asset_links LIMIT 1"
            ).fetchone()[0]
            printing_id = db.execute(
                "SELECT printing_id FROM sam_reference_asset_links WHERE printing_id IS NOT NULL LIMIT 1"
            ).fetchone()[0]
            with self.assertRaisesRegex(ValueError, "explicit operator confirmation"):
                record_assertion(
                    db, card_id=card_id, field_scope="PRINTING", family_id=family_id,
                    printing_id=printing_id, certainty="AUTHORITATIVE", authority_granted=True,
                    actor="SYSTEM", reason_code="INVALID_SYSTEM_PRINTING_AUTHORITY",
                )
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(
                    """INSERT INTO sam_identity_assertions
                       (assertion_uuid,card_id,field_scope,family_id,printing_id,certainty,
                        authority_granted,actor,created_at)
                       VALUES (?,?,?,?,?,'AUTHORITATIVE',1,'SYSTEM',?)""",
                    (str(uuid.uuid4()), card_id, "PRINTING", family_id, printing_id,
                     "2026-08-21T00:00:00+00:00"),
                )

    def test_conflicting_reference_assets_do_not_force_winner(self):
        candidates = [
            {"id": 1, "family_id": 10, "commercial_printing_id": 91,
             "variant_label": "SP A", "visual_score": 0.97,
             "evidence_requirements": {"required_markers": ["SP_MARKER"]}},
            {"id": 2, "family_id": 10, "commercial_printing_id": 92,
             "variant_label": "SP B", "visual_score": 0.96,
             "evidence_requirements": {"required_markers": ["SP_MARKER"]}},
        ]
        result = evaluate_printing_candidates(candidates, 10, {"SP_MARKER": "PRESENT"})
        self.assertEqual(result["certainty"], "CONFLICTING")
        self.assertIsNone(result["candidate"])
        self.assertFalse(result["authority_granted"])

    def test_operator_family_only_confirmation_leaves_printing_unresolved(self):
        card_id, _, result, _ = self._recognize(("OP16-034_p1.jpg", "OP16-034_p2.jpg"))
        with self.app.connect() as db:
            decision = decide_recognition(db, result["job"]["job_uuid"], {
                "request_id": "OPERATOR-FAMILY-ONLY", "action": "CONFIRM_FAMILY",
                "expected_revision": result["current_revision"],
                "reference_id": result["top_candidate"]["id"],
            })
            card = db.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        self.assertTrue(decision["family"]["authoritative"])
        self.assertFalse(decision["printing"]["authoritative"])
        self.assertIsNone(card["sam_printing_id"])
        self.assertEqual(card["variant"], "Legacy Variant")

    def test_operator_printing_correction_is_append_only_and_preserves_suggestion(self):
        card_id, _, result, _ = self._recognize(("OP16-034_p1.jpg", "OP16-034_p2.jpg"))
        with self.app.connect() as db:
            family_result = decide_recognition(db, result["job"]["job_uuid"], {
                "request_id": "OPERATOR-FAMILY", "action": "CONFIRM_FAMILY",
                "expected_revision": result["current_revision"],
                "reference_id": result["top_candidate"]["id"],
            })
            first = family_result["candidates"][0]
            second = next(
                item for item in family_result["candidates"]
                if item["commercial_printing_id"] != first["commercial_printing_id"]
            )
            confirmed = decide_recognition(db, result["job"]["job_uuid"], {
                "request_id": "OPERATOR-PRINTING-CONFIRM", "action": "CONFIRM_PRINTING",
                "expected_revision": family_result["current_revision"],
                "reference_id": first["id"], "printing_id": first["commercial_printing_id"],
            })
            corrected = decide_recognition(db, result["job"]["job_uuid"], {
                "request_id": "OPERATOR-PRINTING-CORRECT", "action": "CORRECT_PRINTING",
                "expected_revision": confirmed["current_revision"],
                "reference_id": second["id"], "printing_id": second["commercial_printing_id"],
                "reason_code": "VARIANT_OR_PRINTING_CORRECTION",
                "notes": "The alternate artwork marker matches the second documented printing.",
            })
            card = db.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
            history = identity_history(db, card_id)
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE sam_identity_decision_events SET notes='rewrite' WHERE card_id=?", (card_id,))
        self.assertTrue(corrected["printing"]["authoritative"])
        self.assertEqual(card["sam_printing_id"], second["commercial_printing_id"])
        self.assertEqual(card["variant"], "Legacy Variant")
        printing_events = [event for event in history["events"] if event["event_type"].startswith("PRINTING_")]
        self.assertEqual([event["event_type"] for event in printing_events], ["PRINTING_CONFIRMED", "PRINTING_CORRECTED"])
        self.assertEqual(printing_events[1]["prior_printing_id"], first["commercial_printing_id"])
        authoritative_assertions = [
            item for item in history["assertions"]
            if item["field_scope"] == "PRINTING" and item["authority_granted"]
        ]
        self.assertEqual(
            authoritative_assertions[-1]["supersedes_assertion_id"],
            authoritative_assertions[-2]["id"],
        )

    def test_legacy_values_are_not_backfilled_and_migration_is_transactional(self):
        legacy_root = self.root / f"legacy-{uuid.uuid4().hex}"
        original = {
            "DB_PATH": self.app.DB_PATH, "DATA_DIR": self.app.DATA_DIR,
            "IMAGE_DIR": self.app.IMAGE_DIR, "INBOUND_DIR": self.app.INBOUND_DIR,
            "SOURCE_DB_DIR": self.app.SOURCE_DB_DIR, "apply_migrations": self.app.apply_migrations,
        }
        try:
            self.app.DATA_DIR = legacy_root
            self.app.DB_PATH = legacy_root / "dex.db"
            self.app.IMAGE_DIR = legacy_root / "images"
            self.app.INBOUND_DIR = legacy_root / "inbound"
            self.app.SOURCE_DB_DIR = legacy_root / "source"
            self.app.apply_migrations = lambda db: apply_migrations(db, DEFAULT_MIGRATIONS[:-2])
            self.app.init_db()
            with self.app.connect() as db:
                now = self.app.utcnow()
                batch_id = db.execute(
                    """INSERT INTO batches
                       (batch_code,created_at,status,game,set_code,set_name,acquisition_type,total_cost)
                       VALUES ('LEGACY-SAM',?,'OPEN','One Piece','OP16','Time of Battle','Singles',10)""",
                    (now,),
                ).lastrowid
                card_id = db.execute(
                    """INSERT INTO cards
                       (sku,batch_id,created_at,updated_at,variant,rarity,status)
                       VALUES ('LEGACY-PRINT',?,?,?,'Unverified Parallel','R*','IN_STOCK')""",
                    (batch_id, now, now),
                ).lastrowid
                job_id = db.execute(
                    """INSERT INTO sam_recognition_jobs
                       (job_uuid,request_id,recognition_key,card_id,batch_id,game,status,
                        engine_version,rules_version,recognition_state,submitted_at)
                       VALUES ('LEGACY-JOB','LEGACY-JOB-REQUEST','LEGACY-KEY',?,?,'One Piece',
                               'COMPLETED','dex-sam-one-piece-v1','sam-conservative-2026-08-15-v1',
                               'NEEDS_REVIEW',?)""",
                    (card_id, batch_id, now),
                ).lastrowid
                db.execute(
                    """INSERT INTO sam_recognition_decisions
                       (decision_uuid,request_id,job_id,card_id,decision_type,expected_revision,
                        effective_at,recorded_at,reason_code,notes)
                       VALUES ('LEGACY-DECISION','LEGACY-DECISION-REQUEST',?,?,'LEFT_UNIDENTIFIED',
                               1,?,?, 'LEGACY_REVIEW','Preserve this historical decision')""",
                    (job_id, card_id, now, now),
                )
                self.assertIsNone(db.execute(
                    "SELECT 1 FROM schema_migrations WHERE migration_id=?",
                    (DEFAULT_MIGRATIONS[-2].migration_id,),
                ).fetchone())
                self.assertEqual(apply_migrations(db, DEFAULT_MIGRATIONS[-2:-1]), (DEFAULT_MIGRATIONS[-2].migration_id,))
                card = db.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
                self.assertEqual(card["variant"], "Unverified Parallel")
                self.assertEqual(card["rarity"], "R*")
                self.assertIsNone(card["sam_family_id"])
                self.assertIsNone(card["sam_printing_id"])
                self.assertEqual(card["sam_legacy_identity_provenance"], "LEGACY_RECORDED")
                self.assertEqual(db.execute(
                    "SELECT notes FROM sam_recognition_decisions WHERE id=1"
                ).fetchone()[0], "Preserve this historical decision")
                migrated_job = db.execute(
                    "SELECT family_id,printing_id,family_certainty,printing_certainty FROM sam_recognition_jobs WHERE id=?",
                    (job_id,),
                ).fetchone()
                self.assertEqual(tuple(migrated_job), (None, None, "UNRESOLVED", "UNRESOLVED"))
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

            failed_path = legacy_root / "failed.db"
            source = sqlite3.connect(self.app.DB_PATH)
            failed = sqlite3.connect(failed_path)
            source.backup(failed)
            source.close()
            failed.execute("DELETE FROM schema_migrations WHERE migration_id=?", (DEFAULT_MIGRATIONS[-2].migration_id,))
            failed.execute("DROP TRIGGER sam_identity_assertions_no_update")
            failed.execute("DROP TRIGGER sam_identity_assertions_no_delete")
            failed.execute("DROP TRIGGER sam_identity_events_no_update")
            failed.execute("DROP TRIGGER sam_identity_events_no_delete")
            for table in ("sam_identity_decision_events", "sam_identity_assertions", "sam_reference_asset_links", "sam_printing_external_ids", "sam_commercial_printings", "sam_card_families"):
                failed.execute(f"DROP TABLE {table}")
            failed.execute("CREATE TABLE sam_card_families (id INTEGER PRIMARY KEY)")
            failed.commit()
            with self.assertRaises(MigrationError):
                apply_migrations(failed, DEFAULT_MIGRATIONS[-2:-1])
            self.assertIsNone(failed.execute(
                "SELECT 1 FROM schema_migrations WHERE migration_id=?", (DEFAULT_MIGRATIONS[-2].migration_id,)
            ).fetchone())
            self.assertIsNone(failed.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sam_commercial_printings'"
            ).fetchone())
            failed.close()
        finally:
            for key, value in original.items():
                setattr(self.app, key, value)

    def test_family_printing_lookup_and_review_payload_performance(self):
        self._index(tuple(f"OP16-{index:03d}_p1.jpg" for index in range(1, 301)))
        card_id, _ = self._batch_card(self.references / "OP16-034_p1.jpg")
        with self.app.connect() as db:
            started = time.perf_counter()
            rows = db.execute(
                """SELECT f.id,p.id,l.reference_id
                     FROM sam_card_families f
                     LEFT JOIN sam_commercial_printings p ON p.family_id=f.id
                     JOIN sam_reference_asset_links l ON l.family_id=f.id
                    WHERE f.game='One Piece' AND f.card_number='OP16-034'"""
            ).fetchall()
            elapsed = (time.perf_counter() - started) * 1000
            recognition_started = time.perf_counter()
            result = submit_recognition(
                db, card_id, data_dir=self.data, request_id="PERFORMANCE-RECOGNITION"
            )
            recognition_elapsed = (time.perf_counter() - recognition_started) * 1000
            payload_started = time.perf_counter()
            payload = recognition_result(db, result["job"]["id"])
            payload_elapsed = (time.perf_counter() - payload_started) * 1000
        self.assertTrue(rows)
        self.assertEqual(payload["family"]["card_number"], "OP16-034")
        self.assertLess(elapsed, 250)
        self.assertLess(recognition_elapsed, 1000)
        self.assertLess(payload_elapsed, 250)
        print(
            f"SAM Phase 1 performance: family/printing lookup {elapsed:.2f} ms; "
            f"recognition {recognition_elapsed:.2f} ms; review payload {payload_elapsed:.2f} ms"
        )


if __name__ == "__main__":
    unittest.main()
