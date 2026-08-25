import importlib.util
import json
import os
import sqlite3
import tempfile
import time
import unittest
import urllib.request
import uuid
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageEnhance

from dex_migrations import DEFAULT_MIGRATIONS, MigrationError, apply_migrations
from dex_sam import (
    AUTO_MATCH_THRESHOLD,
    ENGINE_VERSION,
    INDEX_VERSION,
    RULES_VERSION,
    _ocr_card_number,
    OptcgMetadataProvider,
    decide_recognition,
    index_reference_library,
    metadata_provider_status,
    normalize_card_number,
    normalize_ocr_card_number,
    normalize_optcg_metadata,
    recognition_history,
    reference_index_status,
    refresh_metadata,
    read_card_number_evidence,
    review_queue,
    search_references,
    submit_recognition,
)


class FakeProvider:
    name = "OPTCG_API"
    version = "fixture-v1"

    def __init__(self, rows=None, failing=False):
        self.rows = rows or {}
        self.failing = failing

    def lookup(self, card_number):
        if self.failing:
            raise OSError("provider unavailable")
        return self.rows.get(card_number)

    def health(self, *, probe=False):
        return {
            "provider": self.name,
            "provider_version": self.version,
            "configured": True,
            "available": False if self.failing and probe else None,
            "live_probe_performed": probe,
            "structured_metadata_only": True,
            "physical_images_transmitted": False,
        }


def make_card_art(path, *, color=(195, 32, 45), accent=(25, 70, 145), sample=False, rotate=0):
    image = Image.new("RGB", (500, 700), (242, 238, 220))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((18, 18, 482, 682), radius=24, outline=(20, 20, 20), width=12)
    draw.rectangle((42, 55, 458, 410), fill=color)
    draw.ellipse((125, 105, 375, 355), fill=accent, outline=(255, 255, 255), width=12)
    draw.rectangle((55, 445, 445, 635), outline=accent, width=8)
    draw.text((65, 660), "OP16-032", fill=(10, 10, 10))
    if sample:
        draw.text((160, 300), "SAMPLE", fill=(255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0))
    if rotate:
        image = image.rotate(rotate, resample=Image.Resampling.BICUBIC, fillcolor=(255, 255, 255))
    image.save(path)


class Phase7SamTest(unittest.TestCase):
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
        })
        spec = importlib.util.spec_from_file_location("dex_phase7_sam_app", Path(__file__).parents[1] / "app.py")
        cls.app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.app)
        cls.app.init_db()
        cls.server = cls.app.ThreadingHTTPServer(("127.0.0.1", 0), cls.app.DexHandler)
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        import threading
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.temp.cleanup()

    def setUp(self):
        with self.app.connect() as db:
            db.execute("PRAGMA foreign_keys=OFF")
            for table in (
                "sam_recognition_decisions", "sam_recognition_candidates", "sam_recognition_jobs",
                "sam_reference_records", "sam_reference_index_runs", "sam_metadata_refresh_runs",
                "sam_metadata_cache", "cards", "rip_sessions", "batches",
                "acquisition_lines", "acquisitions",
            ):
                db.execute(f"DELETE FROM {table}")
            db.execute("PRAGMA foreign_keys=ON")
        for path in self.references.glob("*"):
            if path.is_file():
                path.unlink()
        if self.app.IMAGE_DIR.exists():
            for path in self.app.IMAGE_DIR.rglob("*.png"):
                path.unlink()

    def request(self, path, method="GET", body=None):
        payload = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            self.base + path, data=payload, method=method,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())

    def batch_and_card(self, *, game="One Piece", number="", image=None, cost=123.45):
        now = self.app.utcnow()
        with self.app.connect() as db:
            batch_id = db.execute(
                """INSERT INTO batches
                   (batch_code,created_at,status,game,set_code,set_name,acquisition_type,total_cost)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (f"SAM-B-{uuid.uuid4().hex[:8]}", now, "OPEN", game, "OP16", "Time of Battle", "Singles", cost),
            ).lastrowid
            sku = f"SAM-{uuid.uuid4().hex[:10].upper()}"
            relative = None
            if image:
                destination = self.app.IMAGE_DIR / sku / "front.png"
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(Path(image).read_bytes())
                relative = str(destination.relative_to(self.data)).replace("\\", "/")
            card_id = db.execute(
                """INSERT INTO cards
                   (sku,batch_id,created_at,updated_at,card_number,name,status,front_image,source_hash)
                   VALUES (?,?,?,?,?,'Needs identification','REVIEW',?,?)""",
                (sku, batch_id, now, now, number, relative, uuid.uuid4().hex),
            ).lastrowid
        return batch_id, card_id, sku

    def seed_metadata_and_index(self, names=None):
        names = names or {"OP16-032": "Nami"}
        provider = FakeProvider({
            number: {"game": "One Piece", "card_number": number, "name": name,
                     "set_code": "OP16", "set_name": "Time of Battle", "rarity": "R",
                     "card_type": "Character", "color": "Blue", "language": "English"}
            for number, name in names.items()
        })
        with self.app.connect() as db:
            refresh_metadata(db, provider, names, request_id=f"META-{uuid.uuid4()}")
            return index_reference_library(db, self.references, request_id=f"INDEX-{uuid.uuid4()}")

    def test_provider_normalization_cache_provenance_and_outage_fallback(self):
        normalized = normalize_optcg_metadata({
            "card_id": "op16_032", "card_name": "Nami", "set_id": "OP16",
            "set_name": "Time of Battle", "rarity": "R", "card_color": "Blue",
            "card_type": "Character", "card_text": "Effect", "market_price": "999.99",
        })
        self.assertEqual(normalized["card_number"], "OP16-032")
        self.assertNotIn("market_price", normalized)
        provider = FakeProvider({"OP16-032": normalized})
        with self.app.connect() as db:
            result = refresh_metadata(db, provider, ["op16_032"], request_id="META-OK")
            self.assertEqual(result["refreshed_keys"], 1)
            cached = db.execute("SELECT * FROM sam_metadata_cache").fetchone()
            self.assertEqual(cached["cache_state"], "ACTIVE")
            self.assertEqual(cached["provider_version"], "fixture-v1")
            fallback = refresh_metadata(db, FakeProvider(failing=True), ["OP16-032"], request_id="META-DOWN")
            self.assertEqual(fallback["status"], "FAILED")
            self.assertEqual(db.execute("SELECT cache_state FROM sam_metadata_cache").fetchone()[0], "STALE")
            health = metadata_provider_status(db, FakeProvider(failing=True), probe=True)
            self.assertFalse(health["available"])
            self.assertEqual(health["cache"]["stale"], 1)

    def test_card_number_ocr_normalization_is_strict_bounded_and_extensible(self):
        cases = {
            "OP16-017": "OP16-017",
            "0P16-0I7": "OP16-017",
            "OPI6-0I7": "OP16-017",
            "OP16017": "OP16-017",
            "OP16-0178": "OP16-017",
            "EB01-006": "EB01-006",
            "ST27-001": "ST27-001",
            "PRB02-018": "PRB02-018",
            "P-105": "P-105",
            "P1O5": "P-105",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_ocr_card_number(raw)[0], expected)
        for raw in ("", "16-017", "OP16-0?7", "ORDER-017", "OP16", "blurred garbage"):
            with self.subTest(invalid=raw):
                self.assertEqual(normalize_ocr_card_number(raw)[0], "")

    def test_valid_readable_card_number_uses_bounded_deterministic_consensus(self):
        scan = self.root / "readable-card-number.png"
        make_card_art(scan)
        tsv = {
            "raw": "OP16-017",
            "confidence": 0.96,
            "words": [{"text": "OP16-017", "confidence": 0.96}],
            "duration_ms": 1.0,
            "error": "",
        }
        with patch("dex_sam._tesseract_tsv", return_value=tsv) as run_ocr, patch(
            "dex_sam._tesseract_version", return_value="fixture-tesseract-5"
        ):
            evidence = _ocr_card_number(scan, "fixture-tesseract")
        self.assertEqual(evidence["normalized"], "OP16-017")
        self.assertEqual(evidence["source"], "LOCAL_TESSERACT_OCR")
        self.assertEqual(evidence["confidence"], 1.0)
        self.assertEqual(evidence["consensus_support"], 2)
        self.assertEqual(evidence["valid_candidate_attempts"], 2)
        self.assertEqual(evidence["execution_path"], "FAST_PATH")
        self.assertEqual(evidence["early_exit_reason"], "TWO_AGREEING_INDEPENDENT_ATTEMPTS")
        self.assertEqual(run_ocr.call_count, 2)
        self.assertEqual(
            {item["region_name"] for item in evidence["debug_attempts"]},
            {"LOWER_RIGHT_PRIMARY"},
        )

    def test_ocr_disagreement_escalates_through_bounded_fallback_before_consensus(self):
        scan = self.root / "conflicting-card-number-reads.png"
        make_card_art(scan)
        responses = [
            {"raw": "OP16-033", "confidence": 0.9, "words": [], "duration_ms": 1.0, "error": ""},
            {"raw": "OP16-032", "confidence": 0.9, "words": [], "duration_ms": 1.0, "error": ""},
        ] + [
            {"raw": "OP16-032", "confidence": 0.9, "words": [], "duration_ms": 1.0, "error": ""}
            for _ in range(10)
        ]
        with patch("dex_sam._tesseract_tsv", side_effect=responses) as run_ocr, patch(
            "dex_sam._tesseract_version", return_value="fixture-tesseract-5"
        ):
            evidence = _ocr_card_number(scan, "fixture-tesseract")
        self.assertEqual(evidence["normalized"], "OP16-032")
        self.assertEqual(evidence["execution_path"], "ESCALATED_PATH")
        self.assertEqual(evidence["attempts"], 12)
        self.assertEqual(run_ocr.call_count, 12)
        self.assertEqual(evidence["runner_up_support"], 1)
        self.assertFalse(any(item["established_trustworthy_consensus"] for item in evidence["debug_attempts"]))

    def test_ocr_unavailable_and_unreadable_fall_back_without_guessing(self):
        scan = self.root / "neutral-scan.png"
        make_card_art(scan)
        with patch("dex_sam._find_tesseract_command", return_value=""):
            unavailable = read_card_number_evidence(scan, "")
        self.assertEqual(unavailable["source"], "OCR_UNAVAILABLE")
        self.assertEqual(unavailable["normalized"], "")
        unreadable = {
            "raw": "", "normalized": "", "confidence": 0.0,
            "source": "OCR_NO_VALID_CANDIDATE", "region": [300, 500, 500, 700],
            "method_version": "fixture-ocr", "runtime": {"available": True},
            "preprocessing_ms": 1.0, "execution_ms": 2.0,
        }
        with patch("dex_sam._find_tesseract_command", return_value="fixture"), patch(
            "dex_sam._ocr_card_number", return_value=unreadable
        ):
            failed = read_card_number_evidence(scan, "")
        self.assertEqual(failed["normalized"], "")
        self.assertEqual(failed["source"], "OCR_NO_VALID_CANDIDATE")

    def test_blurred_cropped_and_low_contrast_ocr_failures_preserve_visual_candidate(self):
        scan = self.root / "ocr-visual-fallback.png"
        make_card_art(scan)
        make_card_art(self.references / "OP16-032.png")
        self.seed_metadata_and_index()
        for index, failure in enumerate(("BLURRED_IDENTIFIER", "CROPPED_IDENTIFIER", "LOW_CONTRAST_IDENTIFIER")):
            _, card_id, _ = self.batch_and_card(image=scan)
            evidence = {
                "raw": "", "normalized": "", "confidence": 0.0,
                "source": "OCR_NO_VALID_CANDIDATE", "region": [300, 500, 500, 700],
                "region_name": "LOWER_RIGHT_PRIMARY", "method_version": "fixture-ocr",
                "runtime": {"available": True, "engine": "fixture"},
                "preprocessing_ms": 1.0, "execution_ms": 2.0, "error": failure,
            }
            with self.subTest(failure=failure), patch("dex_sam.read_card_number_evidence", return_value=evidence):
                with self.app.connect() as db:
                    result = submit_recognition(
                        db, card_id, data_dir=self.data, request_id=f"OCR-FALLBACK-{index}"
                    )
            self.assertEqual(result["top_candidate"]["card_number"], "OP16-032")
            self.assertEqual(result["effective_state"], "NEEDS_REVIEW")
            self.assertFalse(result["authoritative"])

    def test_ocr_visual_conflict_never_creates_authority(self):
        scan = self.root / "ocr-conflict.png"
        make_card_art(scan, color=(195, 32, 45), accent=(25, 70, 145))
        make_card_art(self.references / "OP16-032.png", color=(195, 32, 45), accent=(25, 70, 145))
        make_card_art(self.references / "OP16-033.png", color=(20, 140, 75), accent=(130, 50, 160))
        self.seed_metadata_and_index({"OP16-032": "Visual Answer", "OP16-033": "Wrong OCR Number"})
        _, card_id, _ = self.batch_and_card(image=scan)
        evidence = {
            "raw": "OP16-033", "normalized": "OP16-033", "confidence": 0.95,
            "source": "LOCAL_TESSERACT_OCR", "region": [300, 500, 500, 700],
            "region_name": "LOWER_RIGHT_PRIMARY", "method_version": "fixture-ocr",
            "runtime": {"available": True, "engine": "fixture"},
            "preprocessing_ms": 1.0, "execution_ms": 2.0,
        }
        with patch("dex_sam.read_card_number_evidence", return_value=evidence):
            with self.app.connect() as db:
                result = submit_recognition(db, card_id, data_dir=self.data, request_id="OCR-CONFLICT")
                card = db.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        self.assertEqual(result["effective_state"], "NEEDS_REVIEW")
        self.assertIn("CARD_NUMBER_OCR_CONFLICT", result["job"]["exception_codes"])
        self.assertEqual(result["job"]["evidence"]["card_number"]["agreement"], "CONFLICT")
        self.assertEqual(result["job"]["evidence"]["visual_top_candidate"]["card_number"], "OP16-032")
        self.assertFalse(result["authoritative"])
        self.assertEqual(card["card_number"], "")

    def test_valid_ocr_without_reference_preserves_evidence_and_invents_no_identity(self):
        scan = self.root / "ocr-missing-reference.png"
        make_card_art(scan)
        make_card_art(self.references / "OP16-032.png")
        self.seed_metadata_and_index({"OP16-032": "Only Indexed Reference"})
        _, card_id, _ = self.batch_and_card(image=scan)
        evidence = {
            "raw": "EB01-006", "normalized": "EB01-006", "confidence": 0.95,
            "source": "LOCAL_TESSERACT_OCR", "region": [300, 500, 500, 700],
            "region_name": "LOWER_RIGHT_PRIMARY", "method_version": "fixture-ocr",
            "runtime": {"available": True, "engine": "fixture"},
            "preprocessing_ms": 1.0, "execution_ms": 2.0,
        }
        with patch("dex_sam.read_card_number_evidence", return_value=evidence):
            with self.app.connect() as db:
                result = submit_recognition(db, card_id, data_dir=self.data, request_id="OCR-MISSING-REFERENCE")
                card = db.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        self.assertIn("CARD_NUMBER_REFERENCE_MISSING", result["job"]["exception_codes"])
        self.assertEqual(result["job"]["evidence"]["card_number"]["agreement"], "REFERENCE_MISSING")
        self.assertFalse(result["authoritative"])
        self.assertEqual(card["card_number"], "")

    def test_ocr_agreement_cannot_bypass_same_number_variant_ambiguity(self):
        scan = self.root / "ocr-variant.png"
        make_card_art(scan)
        make_card_art(self.references / "OP16-032.png")
        make_card_art(self.references / "OP16-032_p1.png")
        self.seed_metadata_and_index()
        _, card_id, _ = self.batch_and_card(image=scan)
        evidence = {
            "raw": "OP16-032", "normalized": "OP16-032", "confidence": 1.0,
            "source": "LOCAL_TESSERACT_OCR", "region": [300, 500, 500, 700],
            "region_name": "LOWER_RIGHT_PRIMARY", "method_version": "fixture-ocr",
            "runtime": {"available": True, "engine": "fixture"},
            "preprocessing_ms": 1.0, "execution_ms": 2.0,
        }
        with patch("dex_sam.read_card_number_evidence", return_value=evidence):
            with self.app.connect() as db:
                result = submit_recognition(db, card_id, data_dir=self.data, request_id="OCR-VARIANT")
        self.assertEqual(result["effective_state"], "NEEDS_REVIEW")
        self.assertIn("MULTIPLE_PLAUSIBLE_VARIANTS", result["job"]["exception_codes"])
        self.assertFalse(result["authoritative"])

    def test_incremental_index_changed_skip_duplicates_and_no_asset_mutation(self):
        first = self.references / "OP16-032.png"
        duplicate = self.references / "OP16-032-copy.png"
        make_card_art(first)
        duplicate.write_bytes(first.read_bytes())
        before = first.read_bytes()
        initial = self.seed_metadata_and_index()
        self.assertEqual(initial["files_seen"], 2)
        self.assertEqual(initial["duplicate_hashes"], 1)
        with self.app.connect() as db:
            second = index_reference_library(db, self.references, request_id="INDEX-SKIP")
        self.assertEqual(second["unchanged"], 2)
        image = Image.open(first)
        ImageEnhance.Brightness(image).enhance(0.8).save(first)
        with self.app.connect() as db:
            third = index_reference_library(db, self.references, request_id="INDEX-CHANGE")
            status = reference_index_status(db, self.references)
        self.assertEqual(third["changed"], 1)
        self.assertEqual(status["active"], 2)
        self.assertNotEqual(first.read_bytes(), before)
        self.assertEqual(duplicate.read_bytes(), before)
        self.assertTrue(third["original_assets_modified"] is False)

    def test_high_confidence_auto_match_with_rotation_and_sample_watermark_tolerance(self):
        reference = self.references / "OP16-032.png"
        scan = self.root / "scan-rotated.png"
        make_card_art(reference, sample=True)
        make_card_art(scan, rotate=2)
        self.seed_metadata_and_index()
        _, card_id, _ = self.batch_and_card(number="OP16-032", image=scan)
        with self.app.connect() as db:
            result = submit_recognition(db, card_id, data_dir=self.data, request_id="RECOG-HIGH")
            card = db.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        self.assertEqual(result["effective_state"], "AUTO_MATCHED")
        self.assertGreaterEqual(result["job"]["confidence"], AUTO_MATCH_THRESHOLD)
        self.assertEqual(card["card_number"], "OP16-032")
        self.assertEqual(card["name"], "Nami")
        self.assertEqual(result["job"]["evidence"]["sample_watermark_policy"], "IGNORED_AS_REFERENCE_ARTIFACT")

    def test_variant_ambiguity_and_medium_confidence_route_to_review(self):
        scan = self.root / "ambiguous-scan.png"
        make_card_art(scan)
        make_card_art(self.references / "OP16-032.png")
        make_card_art(self.references / "OP16-032_p1.png")
        self.seed_metadata_and_index()
        _, card_id, _ = self.batch_and_card(number="OP16-032", image=scan)
        with self.app.connect() as db:
            result = submit_recognition(db, card_id, data_dir=self.data, request_id="RECOG-AMB")
        self.assertEqual(result["effective_state"], "NEEDS_REVIEW")
        self.assertIn("MULTIPLE_PLAUSIBLE_VARIANTS", result["job"]["exception_codes"])
        self.assertFalse(result["authoritative"])
        self.assertTrue(result["alternate_candidates"])
        self.assertEqual(result["alternate_candidates"][0]["printing"], "P1")
        with self.app.connect() as db:
            confirmed = decide_recognition(db, result["job"]["job_uuid"], {
                "request_id": "DEC-CONFIRM", "action": "CONFIRM",
                "expected_revision": result["current_revision"],
            })
        self.assertEqual(confirmed["effective_state"], "OPERATOR_CONFIRMED")
        self.assertTrue(confirmed["authoritative"])

    def test_poor_unknown_scan_never_forces_identity(self):
        make_card_art(self.references / "OP16-032.png")
        self.seed_metadata_and_index()
        poor = self.root / "poor.png"
        Image.new("RGB", (40, 40), (255, 255, 255)).save(poor)
        _, card_id, _ = self.batch_and_card(image=poor)
        with self.app.connect() as db:
            result = submit_recognition(db, card_id, data_dir=self.data, request_id="RECOG-POOR")
            card = db.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        self.assertEqual(result["effective_state"], "UNIDENTIFIED")
        self.assertIn("POOR_SCAN_QUALITY", result["job"]["exception_codes"])
        self.assertEqual(card["card_number"], "")
        self.assertEqual(card["status"], "REVIEW")
        with self.app.connect() as db:
            left = decide_recognition(db, result["job"]["job_uuid"], {
                "request_id": "DEC-LEAVE", "action": "LEAVE_UNIDENTIFIED",
                "expected_revision": result["current_revision"],
            })
        self.assertEqual(left["decisions"][-1]["decision_type"], "LEFT_UNIDENTIFIED")
        self.assertFalse(left["authoritative"])

    def test_operator_confirm_correct_and_leave_unidentified_preserve_suggestion_history(self):
        scan = self.root / "operator.png"
        make_card_art(scan)
        make_card_art(self.references / "OP16-032.png")
        make_card_art(self.references / "OP16-033_p1.png", accent=(30, 75, 150))
        self.seed_metadata_and_index({"OP16-032": "Nami", "OP16-033": "Robin"})
        batch_id, card_id, _ = self.batch_and_card(image=scan, cost=123.45)
        with self.app.connect() as db:
            economics_before = tuple(db.execute(
                "SELECT total_cost,final_usd_paid_cents FROM batches WHERE id=?", (batch_id,)
            ).fetchone())
            result = submit_recognition(db, card_id, data_dir=self.data, request_id="RECOG-OP")
            correction_ref = db.execute("SELECT id FROM sam_reference_records WHERE card_number='OP16-033'").fetchone()[0]
            queue_before = review_queue(db, batch_id=batch_id)
            corrected = decide_recognition(db, result["job"]["job_uuid"], {
                "request_id": "DEC-CORRECT", "action": "CORRECT",
                "expected_revision": result["current_revision"], "reference_id": correction_ref,
                "reason_code": "OPERATOR_IDENTIFICATION_CORRECTION", "notes": "Fixture top suggestion intentionally wrong",
            })
            history = recognition_history(db, card_id)
            card = db.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
            queue_after = review_queue(db, batch_id=batch_id)
            economics_after = tuple(db.execute(
                "SELECT total_cost,final_usd_paid_cents FROM batches WHERE id=?", (batch_id,)
            ).fetchone())
        self.assertEqual(corrected["effective_state"], "OPERATOR_CORRECTED")
        self.assertTrue(corrected["authoritative"])
        self.assertEqual(card["card_number"], "OP16-033")
        self.assertEqual(card["sam_recognition_state"], "OPERATOR_CORRECTED")
        self.assertEqual(history["history"][0]["job"]["top_reference_id"], result["job"]["top_reference_id"])
        self.assertEqual(history["history"][0]["decisions"][0]["original_top_reference_id"], result["job"]["top_reference_id"])
        self.assertEqual(history["history"][0]["decisions"][0]["selected_reference_id"], correction_ref)
        self.assertEqual(history["history"][0]["decisions"][0]["decision_type"], "OPERATOR_CORRECTED")
        self.assertEqual(sum(queue_before["counts"].values()), 1)
        self.assertEqual(queue_after["counts"]["MATCHED"], 1)
        self.assertEqual(queue_after["counts"]["NEEDS_REVIEW"], 0)
        self.assertEqual(economics_after, economics_before)
        with self.app.connect() as db:
            refresh_metadata(db, FakeProvider({"OP16-033": {
                "game": "One Piece", "card_number": "OP16-033", "name": "External Replacement Name",
                "set_code": "OP16",
            }}), ["OP16-033"], request_id="META-AFTER-OPERATOR")
            unchanged = db.execute("SELECT card_number,name FROM cards WHERE id=?", (card_id,)).fetchone()
        self.assertEqual(tuple(unchanged), ("OP16-033", "Robin"))
        with self.app.connect() as db:
            replay = decide_recognition(db, result["job"]["job_uuid"], {
                "request_id": "DEC-CORRECT", "action": "CORRECT", "expected_revision": 999,
            })
        self.assertTrue(replay["replayed"])
        with self.app.connect() as db:
            with self.assertRaisesRegex(ValueError, "refresh before recording"):
                decide_recognition(db, result["job"]["job_uuid"], {
                    "request_id": "DEC-CORRECT-STALE", "action": "CORRECT",
                    "expected_revision": result["current_revision"], "reference_id": correction_ref,
                    "reason_code": "OPERATOR_IDENTIFICATION_CORRECTION", "notes": "Stale duplicate decision",
                })

    def test_reasonable_crop_tolerance_remains_conservative_and_correct(self):
        reference = self.references / "OP16-032.png"
        scan = self.root / "cropped.png"
        make_card_art(reference)
        base = Image.open(reference)
        base.crop((8, 10, 492, 692)).resize((500, 700), Image.Resampling.LANCZOS).save(scan)
        self.seed_metadata_and_index()
        _, card_id, _ = self.batch_and_card(number="OP16-032", image=scan)
        with self.app.connect() as db:
            result = submit_recognition(db, card_id, data_dir=self.data, request_id="RECOG-CROP")
        self.assertEqual(result["effective_state"], "AUTO_MATCHED")

    def test_retry_is_idempotent_but_two_physical_copies_remain_distinct(self):
        reference = self.references / "OP16-032.png"
        scan = self.root / "copies.png"
        make_card_art(reference)
        make_card_art(scan)
        self.seed_metadata_and_index()
        _, first_id, _ = self.batch_and_card(number="OP16-032", image=scan)
        _, second_id, _ = self.batch_and_card(number="OP16-032", image=scan)
        with self.app.connect() as db:
            first = submit_recognition(db, first_id, data_dir=self.data, request_id="COPY-1")
            retry = submit_recognition(db, first_id, data_dir=self.data, request_id="COPY-1")
            second = submit_recognition(db, second_id, data_dir=self.data, request_id="COPY-2")
            count = db.execute("SELECT COUNT(*) FROM sam_recognition_jobs").fetchone()[0]
        self.assertTrue(retry["replayed"])
        self.assertNotEqual(first["job"]["job_uuid"], second["job"]["job_uuid"])
        self.assertEqual(count, 2)

    def test_review_queue_does_not_block_scanning_and_recognition_changes_no_economics(self):
        good = self.root / "queue-good.png"
        poor = self.root / "queue-poor.png"
        make_card_art(self.references / "OP16-032.png")
        make_card_art(good)
        Image.new("RGB", (40, 40), "white").save(poor)
        self.seed_metadata_and_index()
        batch_id, first_id, _ = self.batch_and_card(number="OP16-032", image=good, cost=456.78)
        _, second_id, _ = self.batch_and_card(image=poor, cost=987.65)
        with self.app.connect() as db:
            before = tuple(db.execute("SELECT total_cost,final_usd_paid_cents FROM batches WHERE id=?", (batch_id,)).fetchone())
            submit_recognition(db, first_id, data_dir=self.data, request_id="QUEUE-1")
            submit_recognition(db, second_id, data_dir=self.data, request_id="QUEUE-2")
            queue = review_queue(db)
            after = tuple(db.execute("SELECT total_cost,final_usd_paid_cents FROM batches WHERE id=?", (batch_id,)).fetchone())
        self.assertFalse(queue["scanning_blocked"])
        self.assertEqual(sum(queue["counts"].values()), 2)
        self.assertEqual(before, after)
        self.assertEqual(queue["counts"]["UNIDENTIFIED"], 1)

    def test_acquisition_batch_rip_and_scan_provenance_are_retained(self):
        scan = self.root / "provenance.png"
        make_card_art(self.references / "OP16-032.png")
        make_card_art(scan)
        self.seed_metadata_and_index()
        batch_id, card_id, _ = self.batch_and_card(number="OP16-032", image=scan)
        now = self.app.utcnow()
        with self.app.connect() as db:
            acquisition_id = db.execute(
                """INSERT INTO acquisitions
                   (acquisition_uuid,acquisition_code,creation_request_id,state,created_at,updated_at)
                   VALUES (?,?,?,'READY_FOR_INTAKE',?,?)""",
                (str(uuid.uuid4()), f"ACQ-{uuid.uuid4().hex[:8]}", str(uuid.uuid4()), now, now),
            ).lastrowid
            line_id = db.execute(
                """INSERT INTO acquisition_lines
                   (line_uuid,acquisition_id,line_sequence,product_class,game,quantity,
                    quantity_certainty,created_at,updated_at)
                   VALUES (?, ?,1,'SINGLE_CARDS','One Piece',1,'KNOWN',?,?)""",
                (str(uuid.uuid4()), acquisition_id, now, now),
            ).lastrowid
            db.execute("UPDATE batches SET acquisition_line_id=? WHERE id=?", (line_id, batch_id))
            rip_id = db.execute(
                "INSERT INTO rip_sessions (rip_code,batch_id,status,created_at) VALUES (?,?, 'DRAFT',?)",
                (f"RIP-{uuid.uuid4().hex[:8]}", batch_id, now),
            ).lastrowid
            db.execute("UPDATE cards SET rip_session_id=? WHERE id=?", (rip_id, card_id))
            result = submit_recognition(db, card_id, data_dir=self.data, request_id="RECOG-PROVENANCE")
        self.assertEqual(result["job"]["batch_id"], batch_id)
        self.assertEqual(result["job"]["rip_session_id"], rip_id)
        self.assertEqual(result["job"]["acquisition_line_id"], line_id)
        self.assertTrue(result["job"]["scan_sha256"])

    def test_manual_find_match_search_and_one_piece_only_boundary(self):
        make_card_art(self.references / "OP16-032.png")
        self.seed_metadata_and_index()
        with self.app.connect() as db:
            found = search_references(db, {"q": "Nami"})
            blocked = search_references(db, {"game": "Pokemon", "q": "Nami"})
        self.assertEqual(found["references"][0]["card_number"], "OP16-032")
        self.assertEqual(blocked["references"], [])
        _, card_id, _ = self.batch_and_card(game="Pokemon")
        with self.app.connect() as db:
            with self.assertRaisesRegex(ValueError, "One Piece only"):
                submit_recognition(db, card_id, data_dir=self.data, request_id="PKM-BLOCK")

    def test_thousands_of_references_search_and_candidate_narrowing_performance(self):
        now = self.app.utcnow()
        feature = json.dumps({"hashes": [{"full": "0" * 64, "frame": "0" * 64}], "bucket": "0000"})
        batch_id, _, _ = self.batch_and_card()
        started = time.perf_counter()
        with self.app.connect() as db:
            rows = []
            for index in range(5000):
                number = f"OP{(index // 120) + 1:02d}-{(index % 120) + 1:03d}"
                rows.append((
                    str(uuid.uuid4()), number, number.split("-")[0], f"Card {index}",
                    f"ref-{index}.png", f"ref-{index}.png", f"{index:064x}"[-64:],
                    feature, INDEX_VERSION, now,
                ))
            db.executemany(
                """INSERT INTO sam_reference_records
                   (reference_uuid,game,card_number,set_code,card_name,source_filename,
                    source_reference,file_size,mtime_ns,sha256,perceptual_hash,visual_bucket,index_version,indexed_at)
                   VALUES (?,'One Piece',?,?,?,?,?,1,1,?,?, '0000',?,?)""",
                rows,
            )
            bulk_ms = round((time.perf_counter() - started) * 1000, 2)
            query = search_references(db, {"card_number": "OP16-032"})
            cache_started = time.perf_counter()
            db.executemany(
                """INSERT INTO sam_metadata_cache
                     (provider,source_key,card_number,normalized_metadata,provider_version,
                      fetched_at,refreshed_at,cache_state)
                   VALUES ('PERF',?,?,?,?,?,?, 'ACTIVE')""",
                [
                    (
                        f"PERF-{index:05d}", f"OP{(index // 120) + 1:02d}-{(index % 120) + 1:03d}",
                        json.dumps({"name": f"Metadata Card {index}"}), "perf-v1", now, now,
                    )
                    for index in range(5000)
                ],
            )
            cache_ms = round((time.perf_counter() - cache_started) * 1000, 2)
            cache_query_started = time.perf_counter()
            cache_hit = db.execute(
                "SELECT normalized_metadata FROM sam_metadata_cache WHERE provider='PERF' AND card_number='OP16-032' AND cache_state='ACTIVE'"
            ).fetchone()
            cache_query_ms = round((time.perf_counter() - cache_query_started) * 1000, 2)

            db.executemany(
                "INSERT INTO cards (sku,batch_id,created_at,updated_at) VALUES (?,?,?,?)",
                [(f"SAM-PERF-{index:04d}", batch_id, now, now) for index in range(1000)],
            )
            card_ids = [row["id"] for row in db.execute("SELECT id FROM cards WHERE sku LIKE 'SAM-PERF-%' ORDER BY id")]
            db.executemany(
                """INSERT INTO sam_recognition_jobs
                     (job_uuid,request_id,recognition_key,card_id,batch_id,game,status,
                      engine_version,rules_version,scan_sha256,recognition_state,
                      scan_quality,exception_codes,evidence,submitted_at,completed_at)
                   VALUES (?,?,?,?,?,'One Piece','COMPLETED',?,?,?,?,'{}','[]','{}',?,?)""",
                [
                    (
                        f"SAM-PERF-JOB-{index:04d}", f"SAM-PERF-REQ-{index:04d}",
                        f"SAM-PERF-KEY-{index:04d}", card_id, batch_id,
                        ENGINE_VERSION, RULES_VERSION, f"{index:064x}"[-64:],
                        ("AUTO_MATCHED", "NEEDS_REVIEW", "UNIDENTIFIED")[index % 3], now, now,
                    )
                    for index, card_id in enumerate(card_ids)
                ],
            )
            queue_started = time.perf_counter()
            queue = review_queue(db, batch_id=batch_id)
            queue_ms = round((time.perf_counter() - queue_started) * 1000, 2)
        self.assertLess(query["query_duration_ms"], 500)
        self.assertLess(bulk_ms, 5000)
        self.assertLessEqual(len(query["references"]), 1)
        self.assertIsNotNone(cache_hit)
        self.assertLess(cache_ms, 5000)
        self.assertLess(cache_query_ms, 500)
        self.assertEqual(sum(queue["counts"].values()), 1000)
        self.assertLess(queue_ms, 2000)
        print(
            f"Phase 7 performance: 5000 references {bulk_ms:.2f} ms; reference search {query['query_duration_ms']:.2f} ms; "
            f"5000 metadata cache rows {cache_ms:.2f} ms / lookup {cache_query_ms:.2f} ms; "
            f"1000-card review queue {queue_ms:.2f} ms"
        )

    def test_api_status_index_recognition_review_and_history(self):
        scan = self.root / "api-scan.png"
        make_card_art(self.references / "OP16-032.png")
        make_card_art(scan)
        self.seed_metadata_and_index()
        _, _, sku = self.batch_and_card(number="OP16-032", image=scan)
        status, provider = self.request("/api/sam/provider/health")
        self.assertEqual(status, 200)
        self.assertTrue(provider["structured_metadata_only"])
        status, result = self.request(f"/api/cards/{sku}/sam/recognize", "POST", {"request_id": "API-RECOG"})
        self.assertEqual(status, 200)
        self.assertEqual(result["effective_state"], "AUTO_MATCHED")
        _, queues = self.request("/api/sam/review-queues")
        self.assertEqual(queues["counts"]["MATCHED"], 1)
        _, history = self.request(f"/api/cards/{sku}/sam/history")
        self.assertEqual(len(history["history"]), 1)

    def test_migration_is_additive_no_backfill_and_forced_failure_rolls_back(self):
        with self.app.connect() as db:
            sam_migration = next(migration for migration in DEFAULT_MIGRATIONS if migration.migration_id == "0014_v22_phase7_sam_recognition")
            card_id = self.batch_and_card()[1]
            card = db.execute("SELECT sam_recognition_state,sam_recognition_job_id FROM cards WHERE id=?", (card_id,)).fetchone()
            self.assertEqual(tuple(card), (None, None))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "failure.db"
            source = sqlite3.connect(self.app.DB_PATH)
            target = sqlite3.connect(path)
            source.backup(target)
            source.close()
            target.execute("DROP TABLE sam_recognition_decisions")
            target.execute("DELETE FROM schema_migrations WHERE migration_id='0014_v22_phase7_sam_recognition'")
            target.execute("DROP TABLE sam_metadata_cache")
            target.execute("CREATE TABLE sam_metadata_cache (id INTEGER PRIMARY KEY)")
            target.commit()
            with self.assertRaises(MigrationError):
                apply_migrations(target, (sam_migration,))
            self.assertIsNone(target.execute("SELECT 1 FROM schema_migrations WHERE migration_id='0014_v22_phase7_sam_recognition'").fetchone())
            self.assertIsNone(target.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sam_recognition_decisions'").fetchone())
            target.close()


if __name__ == "__main__":
    unittest.main()
