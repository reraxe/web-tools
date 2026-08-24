import hashlib
import importlib.util
import json
import os
import tempfile
import threading
import unittest
import urllib.request
import uuid
from pathlib import Path

from PIL import Image, ImageDraw

from dex_migrations import DEFAULT_MIGRATIONS
from dex_sam import (
    AUTO_MARGIN_THRESHOLD,
    AUTO_MATCH_THRESHOLD,
    AUTO_VISUAL_THRESHOLD,
    ENGINE_VERSION,
    INDEX_VERSION,
    OCR_CARD_NUMBER_MIN_CONFIDENCE,
    REVIEW_THRESHOLD,
    RULES_VERSION,
    _image_features,
)
from dex_sam_challenger import CHALLENGER_VERSION, shadow_recognition_for_job


def make_art(path: Path, color: tuple[int, int, int], accent: tuple[int, int, int]) -> None:
    image = Image.new("RGB", (500, 700), (245, 242, 230))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((16, 16, 484, 684), radius=25, outline=(10, 10, 10), width=11)
    draw.rectangle((40, 45, 460, 420), fill=color)
    draw.ellipse((105, 95, 395, 385), fill=accent, outline=(255, 255, 255), width=9)
    draw.rectangle((55, 455, 445, 640), outline=accent, width=7)
    image.save(path)


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SamChallengerShadowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.data = cls.root / "data"
        cls.references = cls.root / "references"
        cls.report_path = cls.root / "challenger-report.json"
        cls.report_path.write_text(json.dumps({
            "challenger_version": CHALLENGER_VERSION,
            "baseline": {"correct_top_family": 9},
            "challenger": {"correct_top_family": 49, "false_auto_matches": 0},
            "gates": {"false_auto_matches_zero": True},
        }), encoding="utf-8")
        os.environ.update({
            "DEX_DATA_DIR": str(cls.data),
            "DEX_DB_PATH": str(cls.data / "dex.db"),
            "DEX_IMAGE_DIR": str(cls.data / "images"),
            "DEX_INBOUND_DIR": str(cls.data / "inbound"),
            "DEX_SOURCE_DB_DIR": str(cls.references),
            "DEX_ONE_PIECE_REFERENCE_DIR": str(cls.references),
            "DEX_SAM_CHALLENGER_REPORT_PATH": str(cls.report_path),
            "DEX_WATCH_INBOUND": "0",
            "DEX_SEED_DEMO": "0",
        })
        spec = importlib.util.spec_from_file_location(
            "dex_sam_challenger_test_app", Path(__file__).parents[1] / "app.py"
        )
        cls.app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.app)
        cls.app.init_db()
        cls.server = cls.app.ThreadingHTTPServer(("127.0.0.1", 0), cls.app.DexHandler)
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
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
                "sam_reference_records", "sam_reference_index_runs", "sam_metadata_cache",
                "cards", "batches",
            ):
                db.execute(f"DELETE FROM {table}")
            db.execute("PRAGMA foreign_keys=ON")
        self.scan = self.root / "scan.png"
        make_art(self.scan, (180, 30, 50), (30, 80, 180))

    def request(self, path: str) -> tuple[int, dict]:
        with urllib.request.urlopen(self.base + path, timeout=10) as response:
            return response.status, json.loads(response.read())

    def seed_job(self, *, ocr_number="OP16-032", set_code=""):
        now = self.app.utcnow()
        sku = f"CHALLENGER-{uuid.uuid4().hex[:8].upper()}"
        destination = self.data / "images" / sku / "front.png"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.scan.read_bytes())
        scan_features, quality = _image_features(destination, scan=True)
        evidence = {
            "card_number": {
                "raw": ocr_number,
                "normalized": ocr_number,
                "confidence": 1.0 if ocr_number else 0.0,
                "source": "LOCAL_TESSERACT_OCR" if ocr_number else "OCR_NO_VALID_CANDIDATE",
                "preprocessing_ms": 10.0,
                "execution_ms": 20.0,
            }
        }
        with self.app.connect() as db:
            batch_id = db.execute(
                """INSERT INTO batches
                   (batch_code,created_at,status,game,set_code,set_name,acquisition_type)
                   VALUES (?,?, 'OPEN','One Piece',?,'Fixture','Singles')""",
                (f"SAM-C-{uuid.uuid4().hex[:8]}", now, set_code),
            ).lastrowid
            card_id = db.execute(
                """INSERT INTO cards
                   (sku,batch_id,created_at,updated_at,name,status,front_image,source_hash)
                   VALUES (?,?,?,?, 'Needs identification','REVIEW',?,?)""",
                (sku, batch_id, now, now, str(destination.relative_to(self.data)).replace("\\", "/"), uuid.uuid4().hex),
            ).lastrowid
            job_uuid = f"SAM-JOB-{uuid.uuid4()}"
            db.execute(
                """INSERT INTO sam_recognition_jobs
                   (job_uuid,request_id,recognition_key,card_id,batch_id,game,status,
                    engine_version,rules_version,scan_sha256,normalized_card_number,
                    card_number_confidence,recognition_state,scan_quality,exception_codes,
                    evidence,submitted_at,completed_at)
                   VALUES (?,?,?,?,?,'One Piece','COMPLETED',?,?,?,?,?,'NEEDS_REVIEW',?,'[]',?,?,?)""",
                (
                    job_uuid, f"REQ-{uuid.uuid4()}", f"KEY-{uuid.uuid4()}", card_id, batch_id,
                    ENGINE_VERSION, RULES_VERSION, file_sha(destination), ocr_number,
                    1.0 if ocr_number else 0.0, json.dumps(quality), json.dumps(evidence), now, now,
                ),
            )
        return job_uuid, sku, scan_features

    def add_reference(self, number: str, path: Path, *, set_code="OP16", variant="Unknown") -> int:
        features, _ = _image_features(path)
        now = self.app.utcnow()
        with self.app.connect() as db:
            return db.execute(
                """INSERT INTO sam_reference_records
                   (reference_uuid,game,card_number,set_code,card_name,variant,source_filename,
                    source_reference,file_size,mtime_ns,sha256,perceptual_hash,visual_bucket,
                    index_version,indexed_at)
                   VALUES (?,'One Piece',?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    str(uuid.uuid4()), number, set_code, f"Card {number}", variant, path.name,
                    path.name, path.stat().st_size, path.stat().st_mtime_ns, file_sha(path),
                    json.dumps(features), features["bucket"], INDEX_VERSION, now,
                ),
            ).lastrowid

    def test_challenger_remains_additive_with_phase1_semantic_schema(self):
        self.assertEqual(DEFAULT_MIGRATIONS[-1].migration_id, "0018_v24_jarvis_economics_sam_phase2")
        source = (Path(__file__).parents[1] / "dex_sam.py").read_text(encoding="utf-8")
        self.assertNotIn("dex_sam_challenger", source)
        self.assertEqual(AUTO_MATCH_THRESHOLD, 0.90)
        self.assertEqual(AUTO_VISUAL_THRESHOLD, 0.86)
        self.assertEqual(REVIEW_THRESHOLD, 0.60)
        self.assertEqual(AUTO_MARGIN_THRESHOLD, 0.035)
        self.assertEqual(OCR_CARD_NUMBER_MIN_CONFIDENCE, 0.67)

    def test_trusted_ocr_nominates_family_but_variant_safeguard_blocks_authority(self):
        job_uuid, _sku, _ = self.seed_job(ocr_number="OP16-032")
        first = self.root / "OP16-032-full.png"
        second = self.root / "OP16-032-small.png"
        first.write_bytes(self.scan.read_bytes())
        second.write_bytes(self.scan.read_bytes())
        self.add_reference("OP16-032", first, variant="Full")
        self.add_reference("OP16-032", second, variant="Small")
        with self.app.connect() as db:
            result = shadow_recognition_for_job(db, job_uuid, data_dir=self.data)
        self.assertEqual(result["trusted_ocr_family"], "OP16-032")
        self.assertIn("OP16-032", result["candidate_generation"]["family_numbers"])
        self.assertFalse(result["trusted_ocr_is_authority"])
        self.assertFalse(result["identity_applied"])
        self.assertEqual(result["recognition_state"], "NEEDS_REVIEW")
        self.assertEqual(result["printing_stage"]["status"], "UNRESOLVED_VARIANT_AMBIGUITY")

    def test_global_visual_neighbors_recover_family_without_ocr_or_set_context(self):
        job_uuid, _sku, _ = self.seed_job(ocr_number="", set_code="")
        correct = self.root / "OP16-032.png"
        wrong = self.root / "OP01-001.png"
        correct.write_bytes(self.scan.read_bytes())
        make_art(wrong, (20, 140, 80), (190, 160, 20))
        self.add_reference("OP16-032", correct)
        self.add_reference("OP01-001", wrong, set_code="OP01")
        with self.app.connect() as db:
            result = shadow_recognition_for_job(db, job_uuid, data_dir=self.data)
        self.assertEqual(result["family_stage"]["top_family"]["card_number"], "OP16-032")
        self.assertIn("GLOBAL_VISUAL_NEIGHBOR", result["family_stage"]["top_family"]["candidate_sources"])
        self.assertEqual(result["printing_stage"]["family"], "OP16-032")

    def test_shadow_evaluation_is_logically_and_physically_read_only(self):
        job_uuid, _sku, _ = self.seed_job(ocr_number="OP16-032")
        correct = self.root / "readonly.png"
        correct.write_bytes(self.scan.read_bytes())
        self.add_reference("OP16-032", correct)
        with self.app.connect() as db:
            before = {
                table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("cards", "sam_recognition_jobs", "sam_recognition_candidates", "sam_recognition_decisions")
            }
        before_hash = file_sha(self.app.DB_PATH)
        uri = f"file:{self.app.DB_PATH.as_posix()}?mode=ro"
        import sqlite3
        db = sqlite3.connect(uri, uri=True)
        try:
            db.row_factory = sqlite3.Row
            result = shadow_recognition_for_job(db, job_uuid, data_dir=self.data)
        finally:
            db.close()
        after_hash = file_sha(self.app.DB_PATH)
        with self.app.connect() as db:
            after = {
                table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in before
            }
        self.assertEqual(before, after)
        self.assertEqual(before_hash, after_hash)
        self.assertEqual(result["database_writes"], 0)
        self.assertEqual(result["calculation_boundary"], "IDENTITY_SHADOW_ONLY_NO_WRITES_NO_ECONOMICS")

    def test_comparison_and_per_job_apis_are_read_only(self):
        job_uuid, _sku, _ = self.seed_job(ocr_number="OP16-032")
        correct = self.root / "api-correct.png"
        correct.write_bytes(self.scan.read_bytes())
        self.add_reference("OP16-032", correct)
        status, report = self.request("/api/sam/challenger/comparison")
        self.assertEqual(status, 200)
        self.assertTrue(report["available"])
        self.assertEqual(report["mode"], "SHADOW_ONLY")
        status, result = self.request(f"/api/sam/recognitions/{job_uuid}/challenger")
        self.assertEqual(status, 200)
        self.assertFalse(result["identity_applied"])
        self.assertEqual(result["database_writes"], 0)
        _, source = self.request("/api/sam/source")
        self.assertTrue(source["phase7"]["challenger"]["available"])


if __name__ == "__main__":
    unittest.main()
