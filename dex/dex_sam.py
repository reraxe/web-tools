"""Conservative One Piece recognition and human-review services for DEX.

Recognition proposes identity.  It never calculates or writes acquisition cost,
card basis, rip economics, sale economics, or listing facts.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol

from dex_sam_identity import (
    ensure_family,
    ensure_reference_identity,
    evaluate_printing_candidates,
    family_printing_candidates,
    identity_history,
    identity_payload,
    printing_evidence_observations,
    record_assertion,
    record_event,
    record_printing_evidence_observations,
    reference_identity,
)


ENGINE_VERSION = "dex-sam-one-piece-v1"
RULES_VERSION = "sam-conservative-2026-08-15-v1"
INDEX_VERSION = "sam-reference-index-v1"
PROVIDER_NAME = "OPTCG_API"
PROVIDER_VERSION = "optcgapi-v1"
AUTO_MATCH_THRESHOLD = 0.90
AUTO_VISUAL_THRESHOLD = 0.86
REVIEW_THRESHOLD = 0.60
AUTO_MARGIN_THRESHOLD = 0.035
MAX_VISUAL_CANDIDATES = 300
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
CARD_NUMBER_RE = re.compile(
    r"\b(?:(?P<set>(?:OP|EB|ST|PRB)\d{1,3})[-_ ]?(?P<number>\d{3}[A-Z]?)|"
    r"(?P<promo>P)[-_ ]?(?P<promo_number>\d{3}[A-Z]?))\b",
    re.I,
)
OCR_METHOD_VERSION = "dex-one-piece-card-number-ocr-v2-staged"
OCR_CARD_NUMBER_MIN_CONFIDENCE = 0.67
OCR_TIMEOUT_SECONDS = 8.0
_OCR_VERSION_CACHE: dict[str, str] = {}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean(value: object, limit: int = 240) -> str:
    return str(value or "").strip()[:limit]


def normalize_card_number(value: object) -> str:
    text = clean(value, 200).upper().replace("_", "-")
    match = CARD_NUMBER_RE.search(text)
    if not match:
        return ""
    if match.group("promo"):
        return f"P-{match.group('promo_number').upper()}"
    return f"{match.group('set').upper()}-{match.group('number').upper()}"


def normalize_ocr_card_number(value: object) -> tuple[str, bool, list[str]]:
    """Conservatively normalize position-bounded OCR confusions.

    Only exact One Piece identifier shapes are accepted.  O/0 and I/1 are
    corrected in numeric positions; arbitrary text is never fuzzy-matched to
    the nearest reference.
    """

    raw = clean(value, 500).upper()
    direct = normalize_card_number(raw)
    if direct:
        return direct, False, []
    text = raw.translate(str.maketrans({"–": "-", "—": "-", "−": "-"}))
    explicit = re.search(
        r"(?<![A-Z0-9])(?P<family>(?:[O0]P|EB|ST|PRB))"
        r"(?P<set>[0-9OIL]{1,3})[-_](?P<number>[0-9OIL]{3})(?P<trailing>[A-Z0-9]?)",
        text,
    )
    if explicit:
        family = "OP" if explicit.group("family") == "0P" else explicit.group("family")
        set_part = explicit.group("set").translate(str.maketrans({"O": "0", "I": "1", "L": "1"}))
        number_part = explicit.group("number").translate(str.maketrans({"O": "0", "I": "1", "L": "1"}))
        corrections: list[str] = []
        if explicit.group("family") == "0P":
            corrections.append("0_TO_O_IN_OP_PREFIX")
        if set_part != explicit.group("set") or number_part != explicit.group("number"):
            corrections.append("O_I_L_TO_DIGITS_IN_NUMERIC_POSITION")
        if explicit.group("trailing"):
            corrections.append("TRAILING_OCR_ARTIFACT_IGNORED")
        return f"{family}{set_part}-{number_part}", bool(corrections), corrections
    promo = re.search(
        r"(?<![A-Z0-9])P[-_](?P<number>[0-9OIL]{3})(?P<trailing>[A-Z0-9]?)", text,
    )
    if promo:
        number_part = promo.group("number").translate(str.maketrans({"O": "0", "I": "1", "L": "1"}))
        corrections = []
        if number_part != promo.group("number"):
            corrections.append("O_I_L_TO_DIGITS_IN_NUMERIC_POSITION")
        if promo.group("trailing"):
            corrections.append("TRAILING_OCR_ARTIFACT_IGNORED")
        return f"P-{number_part}", bool(corrections), corrections
    tokens = re.findall(r"[A-Z0-9_-]{4,14}", text)
    compact_full = re.sub(r"[\s_-]", "", text)
    if re.fullmatch(r"[A-Z0-9]{4,14}", compact_full or "") and compact_full not in tokens:
        tokens.append(compact_full)
    for token in tokens:
        compact = re.sub(r"[^A-Z0-9]", "", token)
        if compact.startswith("0P"):
            compact = "OP" + compact[2:]
            family_correction = "0_TO_O_IN_OP_PREFIX"
        else:
            family_correction = ""
        family = next((item for item in ("PRB", "OP", "EB", "ST") if compact.startswith(item)), "")
        corrections = [family_correction] if family_correction else []
        if family:
            body = compact[len(family):]
            suffix = body[-1] if body and body[-1].isalpha() and body[-1] not in "OIL" else ""
            digits = body[:-1] if suffix else body
            if not (4 <= len(digits) <= 6):
                continue
            set_part, number_part = digits[:-3], digits[-3:]
            if not (1 <= len(set_part) <= 3):
                continue
            translated_set = set_part.translate(str.maketrans({"O": "0", "I": "1", "L": "1"}))
            translated_number = number_part.translate(str.maketrans({"O": "0", "I": "1", "L": "1"}))
            if not (translated_set.isdigit() and translated_number.isdigit()):
                continue
            if translated_set != set_part or translated_number != number_part:
                corrections.append("O_I_L_TO_DIGITS_IN_NUMERIC_POSITION")
            corrections.append("MISSING_OR_NONSTANDARD_HYPHEN")
            return f"{family}{translated_set}-{translated_number}{suffix}", True, sorted(set(corrections))
        if compact.startswith("P"):
            body = compact[1:]
            suffix = body[-1] if body and body[-1].isalpha() and body[-1] not in "OIL" else ""
            digits = body[:-1] if suffix else body
            translated = digits.translate(str.maketrans({"O": "0", "I": "1", "L": "1"}))
            if len(translated) == 3 and translated.isdigit():
                if translated != digits:
                    corrections.append("O_I_L_TO_DIGITS_IN_NUMERIC_POSITION")
                corrections.append("MISSING_OR_NONSTANDARD_HYPHEN")
                return f"P-{translated}{suffix}", True, sorted(set(corrections))
    return "", False, []


def _json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _loads(value: object, fallback: object) -> object:
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hamming_similarity(left: str, right: str) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    try:
        distance = (int(left, 16) ^ int(right, 16)).bit_count()
    except ValueError:
        return 0.0
    return max(0.0, 1.0 - distance / (len(left) * 4))


def _hash_image(image: Any) -> str:
    image = image.convert("L").resize((17, 16))
    pixels = list(image.tobytes())
    bits: list[str] = []
    for y in range(16):
        row = y * 17
        for x in range(16):
            bits.append("1" if pixels[row + x] > pixels[row + x + 1] else "0")
    return f"{int(''.join(bits), 2):064x}"


def _image_features(path: Path, *, scan: bool = False) -> tuple[dict, dict]:
    """Return tolerant visual features and non-grading scan observations."""

    from PIL import Image, ImageEnhance, ImageOps, ImageStat  # type: ignore

    with Image.open(path) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        width, height = image.size
        gray = ImageOps.autocontrast(image.convert("L"))
        stat = ImageStat.Stat(gray)
        mean = float(stat.mean[0])
        contrast = float(stat.stddev[0])
        warnings: list[str] = []
        if width < 200 or height < 280:
            warnings.append("INSUFFICIENT_CARD_AREA")
        aspect = width / max(1, height)
        if aspect < 0.58 or aspect > 0.82:
            warnings.append("CARD_PARTIALLY_CROPPED")
        if mean < 35:
            warnings.append("IMAGE_UNUSUALLY_DARK")
        elif mean > 225:
            warnings.append("IMAGE_UNUSUALLY_BRIGHT")
        if contrast < 18:
            warnings.append("LOW_CONTRAST_OR_GLARE")

        variants = [gray]
        if scan:
            variants.extend(
                [
                    gray.rotate(-2, resample=Image.Resampling.BICUBIC, fillcolor=255),
                    gray.rotate(2, resample=Image.Resampling.BICUBIC, fillcolor=255),
                    ImageEnhance.Contrast(gray).enhance(1.15),
                ]
            )
        hashes: list[dict[str, str]] = []
        for variant in variants:
            normalized = ImageOps.fit(variant, (256, 356), method=Image.Resampling.LANCZOS)
            full = _hash_image(normalized)
            # Mask the artwork center before hashing the frame.  This makes the
            # evidence intentionally insensitive to SAMPLE watermark placement.
            frame = normalized.copy()
            frame.paste(128, (46, 54, 210, 250))
            hashes.append({"full": full, "frame": _hash_image(frame)})
        return (
            {"hashes": hashes, "bucket": hashes[0]["frame"][:4]},
            {
                "width": width,
                "height": height,
                "brightness": round(mean, 2),
                "contrast": round(contrast, 2),
                "warnings": warnings,
            },
        )


def _visual_similarity(scan_features: dict, reference_features: dict) -> float:
    best = 0.0
    for scan_hash in scan_features.get("hashes", []):
        for ref_hash in reference_features.get("hashes", []):
            full = _hamming_similarity(scan_hash.get("full", ""), ref_hash.get("full", ""))
            frame = _hamming_similarity(scan_hash.get("frame", ""), ref_hash.get("frame", ""))
            # Frame evidence dominates so a reference-only SAMPLE watermark does
            # not turn an otherwise correct physical scan into a false negative.
            best = max(best, 0.35 * full + 0.65 * frame, frame * 0.97)
    return round(best, 4)


class OnePieceMetadataProvider(Protocol):
    name: str
    version: str

    def lookup(self, card_number: str) -> dict | None: ...

    def health(self, *, probe: bool = False) -> dict: ...


@dataclass
class OptcgMetadataProvider:
    base_url: str = "https://optcgapi.com"
    timeout_seconds: float = 5.0
    name: str = PROVIDER_NAME
    version: str = PROVIDER_VERSION

    def _url(self, card_number: str) -> str:
        prefix = card_number.split("-", 1)[0]
        family = "decks" if prefix.startswith("ST") else "sets"
        return f"{self.base_url.rstrip('/')}/api/{family}/card/{urllib.parse.quote(card_number)}/"

    def health(self, *, probe: bool = False) -> dict:
        result = {
            "provider": self.name,
            "provider_version": self.version,
            "base_url": self.base_url,
            "configured": bool(self.base_url),
            "live_probe_performed": bool(probe),
            "available": None,
            "structured_metadata_only": True,
            "physical_images_transmitted": False,
        }
        if not probe:
            return result
        started = time.perf_counter()
        try:
            request = urllib.request.Request(
                f"{self.base_url.rstrip('/')}/api/allSets/",
                headers={"Accept": "application/json", "User-Agent": "DEX-v2.2-SAM/1"},
            )
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                result["available"] = 200 <= response.status < 300
                response.read(256)
        except Exception as exc:  # Provider failure is an expected fallback state.
            result["available"] = False
            result["error"] = type(exc).__name__
        result["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        return result

    def lookup(self, card_number: str) -> dict | None:
        normalized = normalize_card_number(card_number)
        if not normalized:
            return None
        request = urllib.request.Request(
            self._url(normalized),
            headers={"Accept": "application/json", "User-Agent": "DEX-v2.2-SAM/1"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        candidate = raw[0] if isinstance(raw, list) and raw else raw
        if not isinstance(candidate, dict):
            return None
        return normalize_optcg_metadata(candidate, normalized)


def normalize_optcg_metadata(raw: dict, fallback_number: str = "") -> dict:
    """Normalize current and older OPTCG response field names without prices."""

    def pick(*keys: str) -> str:
        for key in keys:
            if raw.get(key) not in (None, ""):
                return clean(raw[key], 200)
        return ""

    number = normalize_card_number(
        pick("card_id", "card_number", "id", "cardId") or fallback_number
    )
    set_code = clean(pick("set_id", "set_code", "set") or number.split("-", 1)[0], 40).upper()
    return {
        "game": "One Piece",
        "card_number": number,
        "name": pick("card_name", "name"),
        "set_code": set_code,
        "set_name": pick("set_name", "set_title"),
        "rarity": pick("rarity"),
        "card_type": pick("card_type", "type"),
        "color": pick("card_color", "color"),
        "traits": pick("card_family", "traits", "attribute"),
        "effects": pick("card_text", "effect", "effects"),
        "image_source_id": pick("card_image_id", "image_id"),
        "language": "English",
    }


def metadata_provider_status(db: sqlite3.Connection, provider: OnePieceMetadataProvider, *, probe: bool = False) -> dict:
    health = provider.health(probe=probe)
    row = db.execute(
        """SELECT COUNT(*) AS total,
                  SUM(CASE WHEN cache_state='ACTIVE' THEN 1 ELSE 0 END) AS active,
                  SUM(CASE WHEN cache_state='STALE' THEN 1 ELSE 0 END) AS stale,
                  SUM(CASE WHEN cache_state='MISSING' THEN 1 ELSE 0 END) AS missing,
                  MAX(refreshed_at) AS last_refresh
           FROM sam_metadata_cache WHERE provider=?""",
        (provider.name,),
    ).fetchone()
    health["cache"] = {
        "total": int(row["total"] or 0),
        "active": int(row["active"] or 0),
        "stale": int(row["stale"] or 0),
        "missing": int(row["missing"] or 0),
        "last_refresh": row["last_refresh"],
    }
    return health


def refresh_metadata(
    db: sqlite3.Connection,
    provider: OnePieceMetadataProvider,
    card_numbers: Iterable[str],
    *,
    request_id: str,
) -> dict:
    request_id = clean(request_id, 120)
    if not request_id:
        raise ValueError("request_id is required")
    prior = db.execute(
        "SELECT * FROM sam_metadata_refresh_runs WHERE request_id=?", (request_id,)
    ).fetchone()
    if prior:
        return {**dict(prior), "replayed": True}
    keys = list(dict.fromkeys(filter(None, (normalize_card_number(value) for value in card_numbers))))
    started = time.perf_counter()
    started_at = utcnow()
    refreshed = missing = failures = 0
    for key in keys:
        now = utcnow()
        try:
            metadata = provider.lookup(key)
            state = "ACTIVE" if metadata else "MISSING"
            db.execute(
                """INSERT INTO sam_metadata_cache
                       (provider,source_key,card_number,normalized_metadata,provider_version,
                        fetched_at,refreshed_at,cache_state,error_code)
                   VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(provider,source_key) DO UPDATE SET
                     card_number=excluded.card_number,
                     normalized_metadata=excluded.normalized_metadata,
                     provider_version=excluded.provider_version,
                     fetched_at=excluded.fetched_at,
                     refreshed_at=excluded.refreshed_at,
                     cache_state=excluded.cache_state,
                     error_code=excluded.error_code""",
                (
                    provider.name, key, key, _json(metadata or {}), provider.version,
                    now if metadata else None, now, state, "",
                ),
            )
            refreshed += 1 if metadata else 0
            missing += 0 if metadata else 1
        except Exception as exc:
            failures += 1
            existing = db.execute(
                "SELECT id FROM sam_metadata_cache WHERE provider=? AND source_key=?",
                (provider.name, key),
            ).fetchone()
            if existing:
                db.execute(
                    "UPDATE sam_metadata_cache SET cache_state='STALE',refreshed_at=?,error_code=? WHERE id=?",
                    (now, type(exc).__name__, existing["id"]),
                )
            else:
                db.execute(
                    """INSERT INTO sam_metadata_cache
                           (provider,source_key,card_number,normalized_metadata,provider_version,
                            refreshed_at,cache_state,error_code)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (provider.name, key, key, "{}", provider.version, now, "MISSING", type(exc).__name__),
                )
                missing += 1
    status = "FAILED" if failures and not refreshed else "PARTIAL" if failures else "COMPLETED"
    completed = utcnow()
    duration = round((time.perf_counter() - started) * 1000, 2)
    run_uuid = str(uuid.uuid4())
    db.execute(
        """INSERT INTO sam_metadata_refresh_runs
               (run_uuid,request_id,provider,status,requested_keys,refreshed_keys,
                missing_keys,duration_ms,started_at,completed_at,error_code,payload)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            run_uuid, request_id, provider.name, status, len(keys), refreshed, missing,
            duration, started_at, completed, "PROVIDER_UNAVAILABLE" if failures else "",
            _json({"failure_count": failures}),
        ),
    )
    return {
        "run_uuid": run_uuid, "request_id": request_id, "provider": provider.name,
        "status": status, "requested_keys": len(keys), "refreshed_keys": refreshed,
        "missing_keys": missing, "failure_count": failures, "duration_ms": duration,
        "replayed": False,
    }


def _cached_metadata(db: sqlite3.Connection, card_number: str) -> tuple[dict, dict]:
    row = db.execute(
        """SELECT * FROM sam_metadata_cache
           WHERE card_number=? AND cache_state IN ('ACTIVE','STALE')
           ORDER BY CASE cache_state WHEN 'ACTIVE' THEN 0 ELSE 1 END, refreshed_at DESC LIMIT 1""",
        (card_number,),
    ).fetchone()
    if not row:
        return {}, {}
    return dict(_loads(row["normalized_metadata"], {})), {
        "provider": row["provider"], "source_key": row["source_key"],
        "provider_version": row["provider_version"], "cache_state": row["cache_state"],
        "fetched_at": row["fetched_at"], "refreshed_at": row["refreshed_at"],
    }


def _variant_from_filename(path: Path, card_number: str) -> tuple[str, str]:
    stem = path.stem.lower()
    parallel = re.search(r"(?:^|[_-])(p\d+)(?:$|[_-])", stem)
    if parallel:
        return "Alternate Art", parallel.group(1).upper()
    reprint = re.search(r"(?:^|[_-])(r\d+)(?:$|[_-])", stem)
    if reprint or "reprint" in stem:
        return "Reprint", reprint.group(1).upper() if reprint else "Reprint"
    if "parallel" in stem or "alternate" in stem or "alt" in stem:
        return "Alternate Art", "Unknown"
    return "Standard", "Original"


def index_reference_library(
    db: sqlite3.Connection,
    root: Path,
    *,
    request_id: str,
) -> dict:
    request_id = clean(request_id, 120)
    if not request_id:
        raise ValueError("request_id is required")
    prior = db.execute(
        "SELECT * FROM sam_reference_index_runs WHERE request_id=?", (request_id,)
    ).fetchone()
    if prior:
        return {**dict(prior), "replayed": True}
    root = root.resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError("Configured One Piece reference-library path is unavailable")
    started = time.perf_counter()
    started_at = utcnow()
    seen: set[str] = set()
    indexed = unchanged = changed = duplicates = near_duplicates = 0
    files = sorted(
        (path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES),
        key=lambda path: str(path.relative_to(root)).lower(),
    )
    for path in files:
        relative = str(path.relative_to(root)).replace("\\", "/")
        seen.add(relative)
        stat = path.stat()
        existing = db.execute(
            "SELECT * FROM sam_reference_records WHERE game='One Piece' AND source_reference=?",
            (relative,),
        ).fetchone()
        digest = _sha256(path)
        if existing and existing["sha256"] == digest:
            unchanged += 1
            if not existing["active"]:
                db.execute("UPDATE sam_reference_records SET active=1 WHERE id=?", (existing["id"],))
            ensure_reference_identity(db, existing)
            continue
        duplicate = db.execute(
            "SELECT id FROM sam_reference_records WHERE sha256=? AND active=1 AND source_reference!=? ORDER BY id LIMIT 1",
            (digest, relative),
        ).fetchone()
        features, quality = _image_features(path)
        card_number = normalize_card_number(path.stem)
        set_code = card_number.split("-", 1)[0] if card_number else ""
        metadata, provenance = _cached_metadata(db, card_number) if card_number else ({}, {})
        variant, printing = _variant_from_filename(path, card_number)
        nearby = db.execute(
            """SELECT perceptual_hash FROM sam_reference_records
               WHERE game='One Piece' AND visual_bucket=? AND active=1 LIMIT 20""",
            (features["bucket"],),
        ).fetchall()
        if any(_visual_similarity(features, dict(_loads(row["perceptual_hash"], {}))) >= 0.965 for row in nearby):
            near_duplicates += 1
        now = utcnow()
        values = (
            card_number, set_code, clean(metadata.get("name"), 200), clean(metadata.get("rarity"), 60),
            clean(metadata.get("card_type"), 60), clean(metadata.get("color"), 60),
            clean(metadata.get("language"), 40) or "Unknown", variant, printing,
            path.name, relative, quality["width"], quality["height"], stat.st_size,
            stat.st_mtime_ns, digest, _json(features), features["bucket"],
            clean(provenance.get("provider"), 80), clean(provenance.get("source_key"), 120),
            INDEX_VERSION, now, duplicate["id"] if duplicate else None,
        )
        if existing:
            db.execute(
                """UPDATE sam_reference_records SET
                     card_number=?,set_code=?,card_name=?,rarity=?,card_type=?,color=?,language=?,
                     variant=?,printing=?,source_filename=?,source_reference=?,width=?,height=?,
                     file_size=?,mtime_ns=?,sha256=?,perceptual_hash=?,visual_bucket=?,
                     metadata_provider=?,metadata_source_key=?,index_version=?,indexed_at=?,active=1,
                     duplicate_of_reference_id=? WHERE id=?""",
                (*values, existing["id"]),
            )
            changed += 1
        else:
            cursor = db.execute(
                """INSERT INTO sam_reference_records
                     (reference_uuid,game,card_number,set_code,card_name,rarity,card_type,color,
                      language,variant,printing,source_filename,source_reference,width,height,
                      file_size,mtime_ns,sha256,perceptual_hash,visual_bucket,metadata_provider,
                      metadata_source_key,index_version,indexed_at,duplicate_of_reference_id)
                   VALUES (?,'One Piece',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), *values),
            )
            indexed += 1
            existing = db.execute(
                "SELECT * FROM sam_reference_records WHERE id=?", (int(cursor.lastrowid),)
            ).fetchone()
        refreshed_reference = db.execute(
            "SELECT * FROM sam_reference_records WHERE id=?", (existing["id"],)
        ).fetchone()
        ensure_reference_identity(db, refreshed_reference)
        duplicates += 1 if duplicate else 0
    active_rows = db.execute(
        "SELECT id,source_reference FROM sam_reference_records WHERE game='One Piece' AND active=1"
    ).fetchall()
    missing_ids = [row["id"] for row in active_rows if row["source_reference"] not in seen]
    if missing_ids:
        db.executemany("UPDATE sam_reference_records SET active=0 WHERE id=?", ((item,) for item in missing_ids))
    duration = round((time.perf_counter() - started) * 1000, 2)
    completed = utcnow()
    run_uuid = str(uuid.uuid4())
    db.execute(
        """INSERT INTO sam_reference_index_runs
             (run_uuid,request_id,library_root,index_version,status,files_seen,indexed,
              unchanged,changed,duplicate_hashes,near_duplicates,missing_marked,
              duration_ms,started_at,completed_at,payload)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            run_uuid, request_id, str(root), INDEX_VERSION, "COMPLETED", len(files), indexed,
            unchanged, changed, duplicates, near_duplicates, len(missing_ids), duration,
            started_at, completed, _json({"original_assets_modified": False}),
        ),
    )
    return {
        "run_uuid": run_uuid, "request_id": request_id, "status": "COMPLETED",
        "files_seen": len(files), "indexed": indexed, "unchanged": unchanged,
        "changed": changed, "duplicate_hashes": duplicates,
        "near_duplicates": near_duplicates, "missing_marked": len(missing_ids),
        "duration_ms": duration, "index_version": INDEX_VERSION,
        "library_root": str(root), "original_assets_modified": False, "replayed": False,
    }


def reference_index_status(db: sqlite3.Connection, root: Path) -> dict:
    row = db.execute(
        """SELECT COUNT(*) AS total,
                  SUM(CASE WHEN active=1 THEN 1 ELSE 0 END) AS active,
                  SUM(CASE WHEN duplicate_of_reference_id IS NOT NULL THEN 1 ELSE 0 END) AS duplicates,
                  COUNT(DISTINCT set_code) AS sets,
                  MAX(indexed_at) AS last_indexed
           FROM sam_reference_records WHERE game='One Piece'"""
    ).fetchone()
    last = db.execute(
        "SELECT * FROM sam_reference_index_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return {
        "game": "One Piece", "configured_path": str(root.resolve()),
        "path_available": root.exists() and root.is_dir(), "index_version": INDEX_VERSION,
        "total": int(row["total"] or 0), "active": int(row["active"] or 0),
        "duplicate_hashes": int(row["duplicates"] or 0), "sets": int(row["sets"] or 0),
        "last_indexed": row["last_indexed"], "last_run": dict(last) if last else None,
    }


def _reference_dict(row: sqlite3.Row | None) -> dict | None:
    if not row:
        return None
    result = dict(row)
    result.pop("perceptual_hash", None)
    result["image_url"] = f"/api/sam/references/{row['id']}/image"
    return result


def _reference_with_identity(db: sqlite3.Connection, row: sqlite3.Row | None) -> dict | None:
    result = _reference_dict(row)
    if not result:
        return result
    identity = reference_identity(db, int(result["id"])) or {}
    result.update(identity)
    return result


def reference_path(db: sqlite3.Connection, reference_id: int, root: Path) -> tuple[dict, Path]:
    row = db.execute("SELECT * FROM sam_reference_records WHERE id=? AND active=1", (reference_id,)).fetchone()
    if not row:
        raise ValueError("Reference not found")
    resolved_root = root.resolve()
    path = (resolved_root / row["source_reference"]).resolve()
    if not path.is_relative_to(resolved_root) or not path.is_file():
        raise ValueError("Reference image is unavailable")
    return dict(row), path


def search_references(db: sqlite3.Connection, filters: dict) -> dict:
    if clean(filters.get("game"), 60) not in ("", "One Piece"):
        return {"game": "One Piece", "references": [], "one_piece_only": True}
    where = ["game='One Piece'", "active=1"]
    params: list[object] = []
    exact_fields = {
        "card_number": "card_number", "set_code": "set_code", "rarity": "rarity",
        "color": "color", "card_type": "card_type", "language": "language", "variant": "variant",
    }
    for key, column in exact_fields.items():
        value = clean(filters.get(key), 100)
        if value:
            value = normalize_card_number(value) if key == "card_number" else value
            where.append(f"UPPER({column})=UPPER(?)")
            params.append(value)
    query = clean(filters.get("q"), 120)
    if query:
        normalized_query = normalize_card_number(query)
        if normalized_query:
            where.append("UPPER(card_number)=UPPER(?)")
            params.append(normalized_query)
        else:
            where.append("(card_number LIKE ? OR card_name LIKE ? OR set_code LIKE ?)")
            wildcard = f"%{query}%"
            params.extend([wildcard, wildcard, wildcard])
    limit = min(100, max(1, int(filters.get("limit") or 30)))
    started = time.perf_counter()
    rows = db.execute(
        f"SELECT * FROM sam_reference_records WHERE {' AND '.join(where)} "
        "ORDER BY card_number,variant,printing,id LIMIT ?",
        (*params, limit),
    ).fetchall()
    return {
        "game": "One Piece", "references": [_reference_with_identity(db, row) for row in rows],
        "query_duration_ms": round((time.perf_counter() - started) * 1000, 2),
        "one_piece_only": True,
    }


def _scan_path(card: sqlite3.Row, data_dir: Path) -> Path | None:
    relative = clean(card["front_image"], 500)
    if not relative:
        return None
    root = data_dir.resolve()
    path = (root / relative).resolve()
    return path if path.is_relative_to(root) and path.is_file() else None


def _find_tesseract_command() -> str:
    if clean(os.environ.get("DEX_SAM_OCR_ENABLED"), 20).lower() in ("0", "false", "no", "off"):
        return ""
    configured = clean(os.environ.get("DEX_TESSERACT_CMD"), 500)
    candidates = [configured, shutil.which("tesseract") or ""]
    if os.name == "nt":
        candidates.extend(
            [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            ]
        )
    for candidate in candidates:
        if not candidate:
            continue
        resolved = shutil.which(candidate) or candidate
        if Path(resolved).is_file():
            return str(Path(resolved).resolve())
    return ""


def _tesseract_version(command: str) -> str:
    if command in _OCR_VERSION_CACHE:
        return _OCR_VERSION_CACHE[command]
    try:
        completed = subprocess.run(
            [command, "--version"], capture_output=True, text=True,
            timeout=OCR_TIMEOUT_SECONDS, check=False,
        )
        version = clean((completed.stdout or completed.stderr).splitlines()[0], 120)
    except (OSError, subprocess.SubprocessError, IndexError):
        version = "Unknown"
    _OCR_VERSION_CACHE[command] = version or "Unknown"
    return _OCR_VERSION_CACHE[command]


def _tesseract_tsv(command: str, image_path: Path, psm: int) -> dict:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [
                command, str(image_path), "stdout", "-l", "eng", "--oem", "1",
                "--psm", str(psm), "-c",
                "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_",
                "tsv",
            ],
            capture_output=True, text=True, timeout=OCR_TIMEOUT_SECONDS, check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return {
            "raw": "", "confidence": 0.0, "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "error": clean(type(error).__name__, 80),
        }
    words: list[str] = []
    word_evidence: list[dict] = []
    confidences: list[float] = []
    if completed.returncode == 0:
        for line in completed.stdout.splitlines()[1:]:
            fields = line.split("\t", 11)
            if len(fields) != 12:
                continue
            word = clean(fields[11], 120)
            if not word:
                continue
            words.append(word)
            try:
                confidence = float(fields[10])
            except ValueError:
                confidence = -1.0
            if confidence >= 0:
                confidences.append(confidence)
                word_evidence.append({"text": word, "confidence": round(confidence / 100, 4)})
    return {
        "raw": clean(" ".join(words), 500),
        "confidence": round((sum(confidences) / len(confidences)) / 100, 4) if confidences else 0.0,
        "words": word_evidence,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        "error": "" if completed.returncode == 0 else f"TESSERACT_EXIT_{completed.returncode}",
    }


def _ocr_card_number(scan_path: Path, command: str) -> dict:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps  # type: ignore

    with Image.open(scan_path) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    orientation_normalized = False
    if image.width > image.height:
        image = image.rotate(90, expand=True)
        orientation_normalized = True
    width, height = image.size
    regions = {
        "LOWER_RIGHT_PRIMARY": (0.58, 0.80, 0.99, 0.985),
        "LOWER_RIGHT_TIGHT": (0.69, 0.865, 0.99, 0.975),
        "BOTTOM_BAND_FALLBACK": (0.43, 0.75, 0.99, 0.995),
    }
    # Pass 2 instrumentation showed these two primary PSM 11 variants were the
    # highest-yield pair.  The complete twelve-attempt set remains available,
    # but only disagreement/unreadability pays its process-start cost.
    attempt_plan = (
        ("FAST_PRIMARY", "LOWER_RIGHT_PRIMARY", "GRAY_AUTOCONTRAST_SHARPEN", 11),
        ("FAST_CONFIRMATION", "LOWER_RIGHT_PRIMARY", "BINARY_155", 11),
        ("ESCALATION", "BOTTOM_BAND_FALLBACK", "GRAY_AUTOCONTRAST_SHARPEN", 11),
        ("ESCALATION", "BOTTOM_BAND_FALLBACK", "GRAY_AUTOCONTRAST_SHARPEN", 7),
        ("ESCALATION", "LOWER_RIGHT_PRIMARY", "GRAY_AUTOCONTRAST_SHARPEN", 7),
        ("ESCALATION", "LOWER_RIGHT_PRIMARY", "BINARY_155", 7),
        ("ESCALATION", "LOWER_RIGHT_TIGHT", "GRAY_AUTOCONTRAST_SHARPEN", 11),
        ("ESCALATION", "LOWER_RIGHT_TIGHT", "BINARY_155", 11),
        ("ESCALATION", "LOWER_RIGHT_TIGHT", "GRAY_AUTOCONTRAST_SHARPEN", 7),
        ("ESCALATION", "LOWER_RIGHT_TIGHT", "BINARY_155", 7),
        ("ESCALATION", "BOTTOM_BAND_FALLBACK", "BINARY_155", 11),
        ("ESCALATION", "BOTTOM_BAND_FALLBACK", "BINARY_155", 7),
    )
    attempts: list[dict] = []
    candidate_counts: dict[str, int] = {}
    preprocessing_ms = 0.0
    execution_ms = 0.0
    early_exit_reason = ""
    prepared_cache: dict[tuple[str, str], tuple[list[int], Any]] = {}
    path_cache: dict[tuple[str, str], Path] = {}
    with tempfile.TemporaryDirectory(prefix="dex-sam-ocr-") as temporary:
        temporary_root = Path(temporary)
        for index, (stage, region_name, variant, psm) in enumerate(attempt_plan, start=1):
            key = (region_name, variant)
            attempt_preprocessing_started = time.perf_counter()
            if key not in prepared_cache:
                relative = regions[region_name]
                box = [
                    int(width * relative[0]), int(height * relative[1]),
                    int(width * relative[2]), int(height * relative[3]),
                ]
                crop = image.crop(tuple(box)).convert("L")
                scale = max(2, min(4, round(1400 / max(1, crop.width))))
                enlarged = crop.resize((crop.width * scale, crop.height * scale), Image.Resampling.LANCZOS)
                normalized_image = ImageOps.autocontrast(ImageEnhance.Contrast(enlarged).enhance(1.35))
                sharpened = normalized_image.filter(ImageFilter.SHARPEN)
                if variant == "BINARY_155":
                    prepared_image = sharpened.point(lambda value: 255 if value >= 155 else 0)
                    if sum(prepared_image.getextrema()) / 2 < 128:
                        prepared_image = ImageOps.invert(prepared_image)
                else:
                    prepared_image = sharpened
                prepared_cache[key] = (box, prepared_image)
            box, prepared_image = prepared_cache[key]
            if key not in path_cache:
                image_path = temporary_root / f"ocr-{len(path_cache):02d}.png"
                prepared_image.save(image_path, format="PNG")
                path_cache[key] = image_path
            attempt_preprocessing_ms = round(
                (time.perf_counter() - attempt_preprocessing_started) * 1000, 2
            )
            preprocessing_ms += attempt_preprocessing_ms
            result = _tesseract_tsv(command, path_cache[key], psm)
            execution_ms += float(result["duration_ms"])
            normalized = ""
            bounded = False
            corrections: list[str] = []
            selected_confidence = float(result["confidence"])
            for word in result.get("words", []):
                word_normalized, word_bounded, word_corrections = normalize_ocr_card_number(word["text"])
                if word_normalized and (not normalized or float(word["confidence"]) > selected_confidence):
                    normalized = word_normalized
                    bounded = word_bounded
                    corrections = word_corrections
                    selected_confidence = float(word["confidence"])
            if not normalized:
                normalized, bounded, corrections = normalize_ocr_card_number(result["raw"])
            previous_leader = sorted(candidate_counts.items(), key=lambda item: (-item[1], item[0]))[:1]
            previous_leader_number = previous_leader[0][0] if previous_leader else ""
            if normalized:
                candidate_counts[normalized] = candidate_counts.get(normalized, 0) + 1
            current_leader = sorted(candidate_counts.items(), key=lambda item: (-item[1], item[0]))[:1]
            current_leader_number = current_leader[0][0] if current_leader else ""
            attempt = {
                "sequence": index, "stage": stage,
                "raw": result["raw"], "normalized": normalized,
                "confidence": round(selected_confidence, 4), "region_name": region_name,
                "region": box, "preprocessing": variant, "psm": psm,
                "preprocessing_ms": attempt_preprocessing_ms,
                "execution_ms": round(float(result["duration_ms"]), 2),
                "bounded_normalization_applied": bounded,
                "normalization_corrections": corrections, "error": result["error"],
                "changed_leading_candidate": current_leader_number != previous_leader_number,
                "established_trustworthy_consensus": False,
            }
            attempts.append(attempt)
            valid_attempts_so_far = sum(candidate_counts.values())
            if (
                len(candidate_counts) == 1 and valid_attempts_so_far >= 2
                and next(iter(candidate_counts.values())) >= 2
            ):
                attempt["established_trustworthy_consensus"] = True
                early_exit_reason = "TWO_AGREEING_INDEPENDENT_ATTEMPTS"
                break
    ranked_candidates = sorted(candidate_counts.items(), key=lambda item: (-item[1], item[0]))
    winning_number = ranked_candidates[0][0] if ranked_candidates else ""
    winning_support = ranked_candidates[0][1] if ranked_candidates else 0
    runner_up_support = ranked_candidates[1][1] if len(ranked_candidates) > 1 else 0
    valid_attempts = sum(candidate_counts.values())
    consensus_confidence = round(winning_support / valid_attempts, 4) if valid_attempts else 0.0
    matching_attempts = [item for item in attempts if item["normalized"] == winning_number]
    selected = max(matching_attempts, key=lambda item: item["confidence"]) if matching_attempts else (
        max(attempts, key=lambda item: item["confidence"]) if attempts else None
    )
    trustworthy = bool(
        winning_number and winning_support >= 2 and winning_support > runner_up_support
        and consensus_confidence >= OCR_CARD_NUMBER_MIN_CONFIDENCE
    )
    for attempt in attempts:
        attempt["supports_final_candidate"] = bool(
            winning_number and attempt["normalized"] == winning_number
        )
    execution_path = "FAST_PATH" if len(attempts) <= 2 and early_exit_reason else "ESCALATED_PATH"
    return {
        "raw": selected["raw"] if selected else "",
        "normalized": winning_number if trustworthy else "",
        "candidate_normalized": winning_number,
        "confidence": consensus_confidence if trustworthy else 0.0,
        "candidate_confidence": consensus_confidence,
        "engine_word_confidence": selected["confidence"] if selected else 0.0,
        "consensus_support": winning_support,
        "valid_candidate_attempts": valid_attempts,
        "runner_up_support": runner_up_support,
        "source": "LOCAL_TESSERACT_OCR" if trustworthy else "OCR_NO_VALID_CANDIDATE",
        "region": selected["region"] if selected else None,
        "region_name": selected["region_name"] if selected else "",
        "preprocessing": selected["preprocessing"] if selected else "",
        "psm": selected["psm"] if selected else None,
        "bounded_normalization_applied": bool(selected and selected["bounded_normalization_applied"]),
        "normalization_corrections": selected["normalization_corrections"] if selected else [],
        "method_version": OCR_METHOD_VERSION,
        "runtime": {"available": True, "engine": _tesseract_version(command)},
        "orientation_normalized": orientation_normalized,
        "preprocessing_ms": round(preprocessing_ms, 2),
        "execution_ms": round(execution_ms, 2),
        "attempts": len(attempts),
        "attempts_available": len(attempt_plan),
        "execution_path": execution_path,
        "early_exit_reason": early_exit_reason,
        "debug_attempts": attempts,
    }


def read_card_number_evidence(scan_path: Path | None, existing_value: object) -> dict:
    """Read only a One Piece card number locally; visual matching remains available."""

    existing_raw = clean(existing_value, 100)
    existing = normalize_card_number(existing_raw)
    if existing:
        return {
            "raw": existing_raw, "normalized": existing, "confidence": 0.98,
            "source": "EXISTING_OPERATOR_OR_INTAKE_FIELD", "region": None,
            "method_version": OCR_METHOD_VERSION, "runtime": {"available": None, "engine": "Not used"},
            "preprocessing_ms": 0.0, "execution_ms": 0.0,
        }
    if scan_path:
        filename_number = normalize_card_number(scan_path.stem)
        if filename_number:
            return {
                "raw": scan_path.stem, "normalized": filename_number, "confidence": 0.92,
                "source": "SCAN_FILENAME", "region": None,
                "method_version": OCR_METHOD_VERSION, "runtime": {"available": None, "engine": "Not used"},
                "preprocessing_ms": 0.0, "execution_ms": 0.0,
            }
        command = _find_tesseract_command()
        if command:
            try:
                return _ocr_card_number(scan_path, command)
            except Exception as error:
                return {
                    "raw": "", "normalized": "", "confidence": 0.0,
                    "source": "OCR_FAILED", "region": None,
                    "method_version": OCR_METHOD_VERSION,
                    "runtime": {"available": True, "engine": _tesseract_version(command)},
                    "preprocessing_ms": 0.0, "execution_ms": 0.0,
                    "error": clean(type(error).__name__, 80),
                }
    return {
        "raw": "", "normalized": "", "confidence": 0.0,
        "source": "OCR_UNAVAILABLE", "region": None,
        "method_version": OCR_METHOD_VERSION,
        "runtime": {"available": False, "engine": "Tesseract executable not found"},
        "preprocessing_ms": 0.0, "execution_ms": 0.0,
    }


def _latest_index_token(db: sqlite3.Connection) -> str:
    row = db.execute("SELECT run_uuid FROM sam_reference_index_runs ORDER BY id DESC LIMIT 1").fetchone()
    return row["run_uuid"] if row else INDEX_VERSION


def _candidate_rows(
    db: sqlite3.Connection, *, card_number: str, set_code: str, bucket: str
) -> tuple[list[sqlite3.Row], str]:
    if card_number:
        return db.execute(
            "SELECT * FROM sam_reference_records WHERE game='One Piece' AND active=1 AND card_number=? ORDER BY id",
            (card_number,),
        ).fetchall(), "CARD_NUMBER"
    if set_code:
        return db.execute(
            "SELECT * FROM sam_reference_records WHERE game='One Piece' AND active=1 AND set_code=? ORDER BY id LIMIT ?",
            (set_code, MAX_VISUAL_CANDIDATES),
        ).fetchall(), "BATCH_SET"
    if bucket:
        rows = db.execute(
            "SELECT * FROM sam_reference_records WHERE game='One Piece' AND active=1 AND visual_bucket=? ORDER BY id LIMIT ?",
            (bucket, MAX_VISUAL_CANDIDATES),
        ).fetchall()
        if rows:
            return rows, "VISUAL_BUCKET"
    return db.execute(
        "SELECT * FROM sam_reference_records WHERE game='One Piece' AND active=1 ORDER BY id LIMIT ?",
        (MAX_VISUAL_CANDIDATES,),
    ).fetchall(), "BOUNDED_FALLBACK"


def _source_card_for_reference(db: sqlite3.Connection, reference: sqlite3.Row) -> int:
    now = utcnow()
    db.execute(
        """INSERT INTO source_cards
             (game,card_number,set_code,set_name,name,rarity,color,card_type,
              full_image,small_image,image_hash,updated_at)
           VALUES ('One Piece',?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(game,card_number) DO UPDATE SET
             set_code=excluded.set_code,
             name=CASE WHEN excluded.name!='' THEN excluded.name ELSE source_cards.name END,
             rarity=CASE WHEN excluded.rarity!='' THEN excluded.rarity ELSE source_cards.rarity END,
             color=CASE WHEN excluded.color!='' THEN excluded.color ELSE source_cards.color END,
             card_type=CASE WHEN excluded.card_type!='' THEN excluded.card_type ELSE source_cards.card_type END,
             updated_at=excluded.updated_at""",
        (
            reference["card_number"], reference["set_code"], reference["set_code"],
            reference["card_name"], reference["rarity"], reference["color"],
            reference["card_type"], reference["source_reference"], None,
            clean(dict(_loads(reference["perceptual_hash"], {})).get("hashes", [{}])[0].get("full", ""), 256), now,
        ),
    )
    return int(db.execute(
        "SELECT id FROM source_cards WHERE game='One Piece' AND card_number=?", (reference["card_number"],)
    ).fetchone()["id"])


def _apply_identity(
    db: sqlite3.Connection,
    card: sqlite3.Row,
    reference: sqlite3.Row,
    *,
    state: str,
    confidence: float,
    job_id: int,
    request_id: str = "",
    legacy_decision_id: int | None = None,
) -> None:
    """Apply family identity only; exact printing remains independent."""

    linked = ensure_reference_identity(db, reference)
    if not linked:
        raise ValueError("Selected reference does not establish a card family")
    family_id = int(linked["family"]["id"])
    source_card_id = _source_card_for_reference(db, reference)
    name = reference["card_name"] or ("" if card["name"] == "Needs identification" else card["name"])
    certainty = "AUTHORITATIVE" if state == "AUTO_MATCHED" else "OPERATOR_CONFIRMED"
    db.execute(
        """UPDATE cards SET card_number=?,name=?,set_name=?,color=?,
                   status=?,source_card_id=?,match_confidence=?,match_source=?,match_reviewed=1,
                   matched_at=?,sam_recognition_state=?,sam_recognition_job_id=?,
                   sam_family_id=?,sam_family_certainty=?,updated_at=?
           WHERE id=?""",
        (
            reference["card_number"], name or "Needs identification",
            reference["set_code"] or card["set_name"], reference["color"] or card["color"],
            "IN_STOCK" if reference["card_number"] and name else card["status"],
            source_card_id, confidence, "SAM Auto" if state == "AUTO_MATCHED" else "SAM Operator",
            utcnow(), state, job_id, family_id, certainty, utcnow(), card["id"],
        ),
    )
    event_type = (
        "FAMILY_AUTO_APPLIED" if state == "AUTO_MATCHED" else
        "FAMILY_CORRECTED" if state == "OPERATOR_CORRECTED" else "FAMILY_CONFIRMED"
    )
    event_request = request_id or f"SAM-FAMILY-{event_type}-{job_id}"
    supersedes_assertion_id = None
    if state == "OPERATOR_CORRECTED":
        prior_assertion = db.execute(
            """SELECT id FROM sam_identity_assertions
               WHERE card_id=? AND field_scope='FAMILY' AND authority_granted=1
               ORDER BY id DESC LIMIT 1""",
            (card["id"],),
        ).fetchone()
        supersedes_assertion_id = int(prior_assertion["id"]) if prior_assertion else None
    record_event(
        db, request_id=event_request, job_id=job_id, card_id=int(card["id"]),
        event_type=event_type, family_id=family_id, reference_id=int(reference["id"]),
        prior_family_id=card["sam_family_id"], prior_printing_id=card["sam_printing_id"],
        certainty=certainty, actor="SYSTEM" if state == "AUTO_MATCHED" else "OPERATOR",
        reason_code="ESTABLISHED_SAM_FAMILY_AUTHORITY",
        evidence={"engine_version": ENGINE_VERSION, "rules_version": RULES_VERSION,
                  "printing_authority_granted": False},
    )
    record_assertion(
        db, card_id=int(card["id"]), job_id=job_id, legacy_decision_id=legacy_decision_id,
        field_scope="FAMILY", family_id=family_id, reference_id=int(reference["id"]),
        proposed_value=reference["card_number"], certainty=certainty,
        confidence=confidence, authority_granted=True,
        actor="SYSTEM" if state == "AUTO_MATCHED" else "OPERATOR",
        reason_code="FAMILY_IDENTITY_APPLIED",
        evidence={"variant_unchanged": True, "printing_id": None},
        supersedes_assertion_id=supersedes_assertion_id,
    )


def _operator_identity_exists(db: sqlite3.Connection, card_id: int) -> bool:
    return bool(db.execute(
        """SELECT 1 FROM sam_recognition_decisions
           WHERE card_id=? AND decision_type IN ('OPERATOR_CONFIRMED','OPERATOR_CORRECTED') LIMIT 1""",
        (card_id,),
    ).fetchone())


def _apply_catalog_family_identity(
    db: sqlite3.Connection,
    card: sqlite3.Row,
    family_data: dict,
    *,
    state: str,
    confidence: float,
    job_id: int,
    request_id: str,
    legacy_decision_id: int,
) -> None:
    """Apply an operator-confirmed catalog family without inventing a reference image."""

    number = normalize_card_number(family_data.get("card_number"))
    name = clean(family_data.get("canonical_name"), 240)
    set_code = clean(family_data.get("set_code"), 80).upper() or number.split("-", 1)[0]
    family = ensure_family(
        db, game="One Piece", set_code=set_code, card_number=number, name=name,
        external_descriptors={"source": "FROZEN_LOCAL_ONE_PIECE_CATALOG", "reference_image_required": False},
    )
    if not family:
        raise ValueError("Selected catalog family is unavailable")
    now = utcnow()
    db.execute(
        """UPDATE cards SET card_number=?,name=?,set_name=?,status='IN_STOCK',
                  match_confidence=?,match_source='SAM Operator Catalog',match_reviewed=1,
                  matched_at=?,sam_recognition_state=?,sam_recognition_job_id=?,
                  sam_family_id=?,sam_family_certainty='OPERATOR_CONFIRMED',updated_at=?
           WHERE id=?""",
        (number, name or "Needs identification", set_code, confidence, now, state, job_id,
         int(family["id"]), now, card["id"]),
    )
    event_type = "FAMILY_CORRECTED" if state == "OPERATOR_CORRECTED" else "FAMILY_CONFIRMED"
    record_event(
        db, request_id=request_id, job_id=job_id, card_id=int(card["id"]),
        event_type=event_type, family_id=int(family["id"]), reference_id=None,
        prior_family_id=card["sam_family_id"], prior_printing_id=card["sam_printing_id"],
        certainty="OPERATOR_CONFIRMED", actor="OPERATOR",
        reason_code="OPERATOR_CONFIRMED_CATALOG_FAMILY",
        evidence={"reference_image_available": False, "printing_authority_granted": False},
    )
    record_assertion(
        db, card_id=int(card["id"]), job_id=job_id, legacy_decision_id=legacy_decision_id,
        field_scope="FAMILY", family_id=int(family["id"]), reference_id=None,
        proposed_value=number, certainty="OPERATOR_CONFIRMED", confidence=confidence,
        authority_granted=True, actor="OPERATOR", reason_code="OPERATOR_CONFIRMED_CATALOG_FAMILY",
        evidence={"reference_image_available": False, "exact_printing_unchanged": True},
    )


def recognition_result(db: sqlite3.Connection, job_id_or_uuid: int | str) -> dict:
    if isinstance(job_id_or_uuid, int) or str(job_id_or_uuid).isdigit():
        job = db.execute("SELECT * FROM sam_recognition_jobs WHERE id=?", (int(job_id_or_uuid),)).fetchone()
    else:
        job = db.execute("SELECT * FROM sam_recognition_jobs WHERE job_uuid=?", (str(job_id_or_uuid),)).fetchone()
    if not job:
        raise ValueError("Recognition job not found")
    candidates = db.execute(
        """SELECT r.*,c.rank,c.confidence,c.card_number_score,c.visual_score,
                  c.context_score,c.evidence AS candidate_evidence
           FROM sam_recognition_candidates c
           JOIN sam_reference_records r ON r.id=c.reference_id
           WHERE c.job_id=? ORDER BY c.rank""",
        (job["id"],),
    ).fetchall()
    candidate_payloads = []
    for row in candidates:
        item = _reference_dict(row) or {}
        item.update(reference_identity(db, int(row["id"])) or {})
        item.update({
            "rank": row["rank"], "confidence": row["confidence"],
            "card_number_score": row["card_number_score"], "visual_score": row["visual_score"],
            "context_score": row["context_score"],
            "candidate_evidence": _loads(row["candidate_evidence"], {}),
        })
        candidate_payloads.append(item)
    decisions = [dict(row) for row in db.execute(
        "SELECT * FROM sam_recognition_decisions WHERE job_id=? ORDER BY id", (job["id"],)
    ).fetchall()]
    identity_decisions = []
    for row in db.execute(
        "SELECT * FROM sam_identity_decision_events WHERE job_id=? ORDER BY id", (job["id"],)
    ).fetchall():
        item = dict(row)
        item["evidence"] = _loads(item.get("evidence"), {})
        identity_decisions.append(item)
    card = db.execute("SELECT * FROM cards WHERE id=?", (job["card_id"],)).fetchone()
    result = {
        "job": {**dict(job), "scan_quality": _loads(job["scan_quality"], {}),
                 "exception_codes": _loads(job["exception_codes"], []),
                 "evidence": _loads(job["evidence"], {}),
                 "printing_evidence": _loads(job["printing_evidence"], {})},
        "sku": card["sku"],
        "scan_image_url": f"/media/{card['front_image']}" if card["front_image"] else "",
        "effective_state": card["sam_recognition_state"] or job["recognition_state"],
        "top_candidate": candidate_payloads[0] if candidate_payloads else None,
        "alternate_candidates": candidate_payloads[1:4], "candidates": candidate_payloads,
        "decisions": decisions, "identity_decisions": identity_decisions,
        "current_revision": int(job["revision"]) + len(decisions) + len(identity_decisions),
        "authoritative": (card["sam_recognition_state"] or job["recognition_state"]) in
                         ("AUTO_MATCHED", "OPERATOR_CONFIRMED", "OPERATOR_CORRECTED"),
        "calculation_boundary": "IDENTITY_ONLY_NO_ECONOMICS",
        "printing_evidence_observations": printing_evidence_observations(db, int(job["id"])),
    }
    separated = identity_payload(db, int(job["id"]), candidate_payloads)
    result.update(separated)
    result["authoritative"] = separated["family"]["authoritative"]
    return result


def submit_recognition(
    db: sqlite3.Connection,
    card_id: int,
    *,
    data_dir: Path,
    request_id: str,
) -> dict:
    card = db.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
    if not card:
        raise ValueError("Card not found")
    batch = db.execute("SELECT * FROM batches WHERE id=?", (card["batch_id"],)).fetchone()
    if not batch or batch["game"] != "One Piece":
        raise ValueError("Phase 7 recognition supports One Piece only")
    request_id = clean(request_id, 120)
    if not request_id:
        raise ValueError("request_id is required")
    replay = db.execute("SELECT id FROM sam_recognition_jobs WHERE request_id=?", (request_id,)).fetchone()
    if replay:
        result = recognition_result(db, replay["id"])
        result["replayed"] = True
        return result
    scan_path = _scan_path(card, data_dir)
    scan_sha = _sha256(scan_path) if scan_path else clean(card["source_hash"], 128)
    recognition_key = hashlib.sha256(
        f"{card_id}|{scan_sha}|{ENGINE_VERSION}|{RULES_VERSION}|{OCR_METHOD_VERSION}|{_latest_index_token(db)}".encode()
    ).hexdigest()
    existing = db.execute(
        "SELECT id FROM sam_recognition_jobs WHERE recognition_key=?", (recognition_key,)
    ).fetchone()
    if existing:
        result = recognition_result(db, existing["id"])
        result["replayed"] = True
        return result
    started = time.perf_counter()
    number_evidence = read_card_number_evidence(scan_path, card["card_number"])
    raw_number = number_evidence["raw"]
    normalized_number = number_evidence["normalized"]
    number_confidence = number_evidence["confidence"]
    scan_features: dict = {"hashes": [], "bucket": ""}
    quality = {"warnings": ["NO_FRONT_SCAN"] if not scan_path else []}
    if scan_path:
        try:
            scan_features, quality = _image_features(scan_path, scan=True)
        except Exception:
            quality = {"warnings": ["SCAN_IMAGE_UNREADABLE"]}
    set_code = clean(batch["set_code"], 40).upper()
    scan_ocr_evidence = number_evidence.get("source") == "LOCAL_TESSERACT_OCR"
    rows, narrowing = _candidate_rows(
        db, card_number="" if scan_ocr_evidence else normalized_number,
        set_code=set_code, bucket=scan_features.get("bucket", "")
    )
    exact_reference_rows = db.execute(
        """SELECT * FROM sam_reference_records
           WHERE game='One Piece' AND active=1 AND UPPER(card_number)=UPPER(?)
           ORDER BY id""",
        (normalized_number,),
    ).fetchall() if normalized_number else []
    catalog_family = None
    if normalized_number:
        from dex_sam_audited import catalog_search

        catalog_result = catalog_search(normalized_number, db=db, limit=5)
        exact_families = [
            item for item in catalog_result.get("families", [])
            if normalize_card_number(item.get("card_number")) == normalized_number
        ]
        catalog_family = exact_families[0] if exact_families else None
    scored: list[tuple[float, float, float, float, sqlite3.Row]] = []
    visual_ranked: list[tuple[float, sqlite3.Row]] = []
    for reference in rows:
        number_score = 1.0 if normalized_number and reference["card_number"] == normalized_number else 0.0
        visual_score = _visual_similarity(
            scan_features, dict(_loads(reference["perceptual_hash"], {}))
        ) if scan_features.get("hashes") else 0.0
        visual_ranked.append((visual_score, reference))
        context_score = 1.0 if set_code and reference["set_code"] == set_code else 0.0
        confidence = (
            0.55 * number_score + 0.40 * visual_score + 0.05 * context_score
            if normalized_number else 0.82 * visual_score + 0.18 * context_score
        )
        scored.append((round(confidence, 4), number_score, visual_score, context_score, reference))
    scored.sort(key=lambda item: (-item[0], -item[2], item[4]["id"]))
    visual_ranked.sort(key=lambda item: (-item[0], item[1]["id"]))
    best = scored[0] if scored else None
    second = scored[1] if len(scored) > 1 else None
    visual_best = visual_ranked[0] if visual_ranked else None
    margin = round(best[0] - second[0], 4) if best and second else 1.0
    exceptions: list[str] = []
    warnings = quality.get("warnings", [])
    if warnings:
        exceptions.append("POOR_SCAN_QUALITY")
    ocr_visual_conflict = bool(
        scan_ocr_evidence and normalized_number and visual_best
        and visual_best[1]["card_number"] != normalized_number
    )
    ocr_reference_missing = bool(
        scan_ocr_evidence and normalized_number
        and not exact_reference_rows
    )
    if ocr_visual_conflict:
        exceptions.append("CARD_NUMBER_OCR_CONFLICT")
    if ocr_reference_missing:
        exceptions.append("CARD_NUMBER_REFERENCE_MISSING")
    ambiguous_variant = bool(
        best and second and best[4]["card_number"] == second[4]["card_number"]
        and abs(best[2] - second[2]) < AUTO_MARGIN_THRESHOLD
    )
    if ambiguous_variant:
        exceptions.append("MULTIPLE_PLAUSIBLE_VARIANTS")
    provider_meta, provider_provenance = _cached_metadata(db, normalized_number) if normalized_number else ({}, {})
    if normalized_number and not provider_meta:
        exceptions.append("METADATA_PROVIDER_MISSING")
    severe_quality = any(code in warnings for code in ("INSUFFICIENT_CARD_AREA", "SCAN_IMAGE_UNREADABLE"))
    if (
        best and best[0] >= AUTO_MATCH_THRESHOLD and best[1] >= 0.99
        and best[2] >= AUTO_VISUAL_THRESHOLD and margin >= AUTO_MARGIN_THRESHOLD
        and not ambiguous_variant and not severe_quality
        and not ocr_visual_conflict and not ocr_reference_missing
    ):
        state = "AUTO_MATCHED"
    elif best and best[0] >= REVIEW_THRESHOLD and not (severe_quality and not normalized_number):
        state = "NEEDS_REVIEW"
        if not exceptions:
            exceptions.append("LOW_RECOGNITION_CONFIDENCE")
    elif catalog_family and scan_ocr_evidence and normalized_number and not ocr_visual_conflict:
        # A trusted printed-number read may nominate an exact catalog family for
        # operator review. It does not create a reference candidate, automatic
        # authority, or an exact-printing decision.
        state = "NEEDS_REVIEW"
    else:
        state = "UNIDENTIFIED"
        exceptions.append("NO_REFERENCE_MATCH")
    identity_candidates: list[dict] = []
    for item in scored[:5]:
        linked = ensure_reference_identity(db, item[4]) or {}
        reference_item = _reference_dict(item[4]) or {}
        reference_item.update(reference_identity(db, int(item[4]["id"])) or {})
        reference_item.update({
            "confidence": item[0], "card_number_score": item[1],
            "visual_score": item[2], "context_score": item[3],
        })
        identity_candidates.append(reference_item)
    best_identity = identity_candidates[0] if identity_candidates else {}
    family_id = int(best_identity.get("family_id") or 0) or None
    if not family_id and catalog_family:
        catalog_record = ensure_family(
            db,
            game="One Piece",
            set_code=clean(catalog_family.get("set_code"), 80).upper(),
            card_number=normalized_number,
            name=clean(catalog_family.get("canonical_name"), 240),
            external_descriptors={
                "source": "FROZEN_LOCAL_ONE_PIECE_CATALOG",
                "reference_image_available": bool(exact_reference_rows),
            },
        )
        family_id = int(catalog_record["id"]) if catalog_record else None
    family_certainty = (
        "CONFLICTING" if ocr_visual_conflict else
        "AUTHORITATIVE" if state == "AUTO_MATCHED" else
        "HIGH_CONFIDENCE_SUGGESTION" if best or catalog_family else "UNRESOLVED"
    )
    # Printing evidence may use every visually scored reference from the
    # recognized family.  The five-item identity list remains a presentation
    # concern and must not flatten or truncate the printing candidate pool.
    printing_visual_candidates = [
        {"id": int(item[4]["id"]), "visual_score": item[2]}
        for item in scored
    ]
    printing_candidates = family_printing_candidates(
        db, family_id, printing_visual_candidates, quality
    )
    printing_evaluation = evaluate_printing_candidates(
        printing_candidates or identity_candidates, family_id, {}
    )
    printing_candidate = printing_evaluation.get("candidate") or {}
    printing_id = int(printing_candidate.get("printing_id") or 0) or None
    now = utcnow()
    job_uuid = f"SAM-JOB-{uuid.uuid4()}"
    evidence = {
        "candidate_narrowing": f"{narrowing}_OCR_CROSSCHECK" if scan_ocr_evidence else narrowing,
        "candidate_universe": len(rows),
        "candidates_scored": len(scored), "margin": margin,
        "card_number": {
            **number_evidence,
            "agreement": (
                "REFERENCE_MISSING" if ocr_reference_missing else
                "CONFLICT" if ocr_visual_conflict else
                "AGREES_WITH_VISUAL_TOP" if scan_ocr_evidence and normalized_number else
                "NOT_APPLICABLE"
            ),
        },
        "visual_top_candidate": {
            "card_number": visual_best[1]["card_number"],
            "card_name": visual_best[1]["card_name"],
            "visual_score": visual_best[0],
        } if visual_best else None,
        "provider_cache": provider_provenance,
        "provider_metadata_available": bool(provider_meta),
        "catalog_family": catalog_family,
        "exact_reference_available": bool(exact_reference_rows),
        "exact_reference_in_candidate_pool": any(
            row["card_number"] == normalized_number for row in rows
        ) if normalized_number else False,
        "family_reference_separation": "CATALOG_FAMILY_DOES_NOT_REQUIRE_REFERENCE_IMAGE",
        "sample_watermark_policy": "IGNORED_AS_REFERENCE_ARTIFACT",
        "family_printing_separation": "FAMILY_AUTHORITY_NEVER_IMPLIES_PRINTING_AUTHORITY",
        "recognition_duration_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    cursor = db.execute(
        """INSERT INTO sam_recognition_jobs
             (job_uuid,request_id,recognition_key,card_id,batch_id,rip_session_id,
              acquisition_line_id,game,status,engine_version,rules_version,scan_sha256,
               raw_ocr_candidate,normalized_card_number,card_number_confidence,confidence,
               recognition_state,scan_quality,exception_codes,evidence,submitted_at,completed_at,
               family_id,family_confidence,family_certainty,printing_id,printing_confidence,
               printing_certainty,printing_unresolved_reason,printing_evidence)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            job_uuid, request_id, recognition_key, card_id, batch["id"], card["rip_session_id"],
            batch["acquisition_line_id"], "One Piece", "COMPLETED", ENGINE_VERSION,
            RULES_VERSION, scan_sha, raw_number, normalized_number, number_confidence,
            best[0] if best else number_confidence if catalog_family else 0.0,
            state, _json(quality), _json(sorted(set(exceptions))),
            _json(evidence), now, now, family_id,
            best[0] if best else number_confidence if catalog_family else 0.0,
            family_certainty, printing_id, float(printing_evaluation.get("confidence") or 0),
            printing_evaluation["certainty"], printing_evaluation["unresolved_reason"],
            _json(printing_evaluation),
        ),
    )
    job_id = int(cursor.lastrowid)
    for rank, item in enumerate(scored[:5], start=1):
        db.execute(
            """INSERT INTO sam_recognition_candidates
                 (job_id,rank,reference_id,confidence,card_number_score,visual_score,
                  context_score,evidence) VALUES (?,?,?,?,?,?,?,?)""",
            (job_id, rank, item[4]["id"], item[0], item[1], item[2], item[3],
             _json({"narrowing": narrowing, "sample_watermark_ignored": True})),
        )
    record_printing_evidence_observations(
        db, job_id=job_id, family_id=family_id, candidates=printing_candidates
    )
    if best:
        db.execute("UPDATE sam_recognition_jobs SET top_reference_id=? WHERE id=?", (best[4]["id"], job_id))
    identity_applied = False
    if state == "AUTO_MATCHED" and best and not _operator_identity_exists(db, card_id):
        _apply_identity(db, card, best[4], state=state, confidence=best[0], job_id=job_id)
        db.execute("UPDATE sam_recognition_jobs SET identity_applied=1 WHERE id=?", (job_id,))
        identity_applied = True
    elif not _operator_identity_exists(db, card_id):
        db.execute(
            "UPDATE cards SET sam_recognition_state=?,sam_recognition_job_id=?,updated_at=? WHERE id=?",
            (state, job_id, now, card_id),
        )
        if family_id:
            record_assertion(
                db, card_id=card_id, job_id=job_id, field_scope="FAMILY",
                family_id=family_id, reference_id=int(best[4]["id"]) if best else None,
                proposed_value=(
                    best[4]["card_number"] if best else
                    catalog_family.get("card_number", "") if catalog_family else ""
                ),
                certainty=family_certainty,
                confidence=best[0] if best else number_confidence if catalog_family else 0,
                authority_granted=False, actor="SYSTEM",
                reason_code=(
                    "SAM_OCR_CATALOG_FAMILY_SUGGESTION" if catalog_family and not best
                    else "SAM_FAMILY_SUGGESTION"
                ),
                evidence={
                    "printing_authority_granted": False,
                    "reference_image_available": bool(exact_reference_rows),
                },
            )
    record_assertion(
        db, card_id=card_id, job_id=job_id, field_scope="PRINTING",
        family_id=family_id, printing_id=printing_id,
        reference_id=int(best[4]["id"]) if best else None,
        proposed_value=printing_candidate.get("variant_label", ""),
        certainty=printing_evaluation["certainty"],
        confidence=float(printing_evaluation.get("confidence") or 0),
        authority_granted=False, actor="SYSTEM",
        reason_code=printing_evaluation["unresolved_reason"] or "PRINTING_SUGGESTION_ONLY",
        evidence=printing_evaluation,
    )
    result = recognition_result(db, job_id)
    result["replayed"] = False
    result["identity_applied"] = identity_applied
    return result


def submit_recognition_for_sku(
    db: sqlite3.Connection, sku: str, *, data_dir: Path, request_id: str
) -> dict:
    card = db.execute("SELECT id FROM cards WHERE sku=?", (clean(sku, 80).upper(),)).fetchone()
    if not card:
        raise ValueError("Card not found")
    return submit_recognition(db, card["id"], data_dir=data_dir, request_id=request_id)


def review_queue(db: sqlite3.Connection, *, batch_id: int | None = None) -> dict:
    params: list[object] = []
    where = ""
    if batch_id is not None:
        where = "WHERE j.batch_id=?"
        params.append(batch_id)
    rows = db.execute(
        f"""SELECT j.*,c.sku,c.front_image,c.sam_recognition_state,c.variant,
                   c.market_average,b.batch_code
            FROM sam_recognition_jobs j
            JOIN cards c ON c.id=j.card_id
            JOIN batches b ON b.id=j.batch_id
            JOIN (SELECT card_id,MAX(id) AS latest_id FROM sam_recognition_jobs GROUP BY card_id) latest
              ON latest.latest_id=j.id
            {where}
            ORDER BY j.submitted_at,j.id""",
        params,
    ).fetchall()
    lanes = {key: [] for key in ("MATCHED", "NEEDS_REVIEW", "UNIDENTIFIED")}
    for row in rows:
        state = row["sam_recognition_state"] or row["recognition_state"]
        lane = "MATCHED" if state in ("AUTO_MATCHED", "OPERATOR_CONFIRMED", "OPERATOR_CORRECTED") else state
        printing_evidence = _loads(row["printing_evidence"], {})
        competing = printing_evidence.get("competing_printings") or []
        priority_reasons = []
        priority_score = 0
        if row["printing_certainty"] == "CONFLICTING":
            priority_score += 40
            priority_reasons.append("CONFLICTING_PRINTING_EVIDENCE")
        if row["printing_certainty"] == "HIGH_CONFIDENCE_SUGGESTION":
            priority_score += 30
            priority_reasons.append("PRINTING_SUGGESTION_AWAITS_OPERATOR")
        if len(competing) > 1:
            priority_score += 20
            priority_reasons.append("MULTIPLE_SAME_FAMILY_PRINTINGS")
        legacy_variant = clean(row["variant"], 120).upper()
        suggested_variant = clean((printing_evidence.get("candidate") or {}).get("variant_label"), 120).upper()
        if legacy_variant not in ("", "STANDARD", "UNKNOWN") and suggested_variant and legacy_variant != suggested_variant:
            priority_score += 15
            priority_reasons.append("LEGACY_VARIANT_EVIDENCE_MISMATCH")
        if row["market_average"] is not None and float(row["market_average"]) >= 20:
            priority_score += 10
            priority_reasons.append("VALUE_REVIEW_PRIORITY_ONLY")
        lanes[lane].append({
            "job_uuid": row["job_uuid"], "sku": row["sku"], "batch_code": row["batch_code"],
            "state": state, "confidence": row["confidence"],
            "scan_image_url": f"/media/{row['front_image']}" if row["front_image"] else "",
            "exception_codes": _loads(row["exception_codes"], []),
            "printing_certainty": row["printing_certainty"],
            "printing_confidence": row["printing_confidence"],
            "printing_candidate_count": len(competing),
            "review_priority_score": priority_score,
            "review_priority_reasons": priority_reasons,
            "economics_value_used_for_identity": False,
        })
    for items in lanes.values():
        items.sort(key=lambda item: (-item["review_priority_score"], item["job_uuid"]))
    return {
        "counts": {key: len(value) for key, value in lanes.items()},
        "lanes": lanes, "scanning_blocked": False, "game": "One Piece",
    }


def decide_recognition(db: sqlite3.Connection, job_uuid: str, payload: dict) -> dict:
    request_id = clean(payload.get("request_id"), 120)
    if not request_id:
        raise ValueError("request_id is required")
    prior = db.execute(
        "SELECT job_id FROM sam_recognition_decisions WHERE request_id=?", (request_id,)
    ).fetchone()
    if not prior:
        prior = db.execute(
            "SELECT job_id FROM sam_identity_decision_events WHERE request_id=?", (request_id,)
        ).fetchone()
    if prior:
        result = recognition_result(db, prior["job_id"])
        result["replayed"] = True
        return result
    job = db.execute("SELECT * FROM sam_recognition_jobs WHERE job_uuid=?", (job_uuid,)).fetchone()
    if not job:
        raise ValueError("Recognition job not found")
    current_revision = int(job["revision"]) + int(db.execute(
        "SELECT COUNT(*) FROM sam_recognition_decisions WHERE job_id=?", (job["id"],)
    ).fetchone()[0]) + int(db.execute(
        "SELECT COUNT(*) FROM sam_identity_decision_events WHERE job_id=?", (job["id"],)
    ).fetchone()[0])
    expected = int(payload.get("expected_revision") or 0)
    if expected != current_revision:
        raise ValueError("Recognition changed; refresh before recording this decision")
    action = clean(payload.get("action"), 40).upper()
    selected_id = payload.get("reference_id")
    selected_family_number = normalize_card_number(payload.get("family_card_number"))
    family_actions = {"CONFIRM", "CONFIRM_FAMILY", "CORRECT", "CORRECT_FAMILY", "LEAVE_UNIDENTIFIED"}
    printing_actions = {
        "CONFIRM_PRINTING", "CORRECT_PRINTING", "LEAVE_PRINTING_UNRESOLVED", "MARK_PRINTING_CONFLICT"
    }
    if action in ("CONFIRM", "CONFIRM_FAMILY"):
        decision_type = "OPERATOR_CONFIRMED"
        selected_id = selected_id or job["top_reference_id"]
        if selected_id and int(selected_id) != int(job["top_reference_id"] or 0):
            raise ValueError("Use the correction action when selecting a different identity")
        proposed_family = db.execute(
            "SELECT card_number FROM sam_card_families WHERE id=?",
            (job["family_id"],),
        ).fetchone() if job["family_id"] else None
        if selected_family_number and (
            not proposed_family
            or selected_family_number != normalize_card_number(proposed_family["card_number"])
        ):
            raise ValueError("Use the correction action when selecting a different identity")
    elif action in ("CORRECT", "CORRECT_FAMILY"):
        decision_type = "OPERATOR_CORRECTED"
        if not selected_id and not selected_family_number:
            raise ValueError("Select the correct family or reference")
    elif action == "LEAVE_UNIDENTIFIED":
        decision_type = "LEFT_UNIDENTIFIED"
        selected_id = None
    elif action in printing_actions:
        decision_type = action
    else:
        raise ValueError("Choose a supported family or printing decision")
    reference = None
    if selected_id:
        reference = db.execute(
            "SELECT * FROM sam_reference_records WHERE id=? AND game='One Piece' AND active=1",
            (int(selected_id),),
        ).fetchone()
        if not reference:
            raise ValueError("Selected reference is unavailable")
        selected_family_number = normalize_card_number(reference["card_number"])
    selected_catalog_family = None
    if selected_family_number:
        from dex_sam_audited import catalog_search

        catalog_result = catalog_search(selected_family_number, db=db, limit=5)
        selected_catalog_family = next((
            item for item in catalog_result.get("families", [])
            if normalize_card_number(item.get("card_number")) == selected_family_number
        ), None)
        if not selected_catalog_family:
            raise ValueError("Selected One Piece family is unavailable in the local catalog")
    reason = clean(payload.get("reason_code"), 80)
    notes = clean(payload.get("notes"), 1000)
    if decision_type in ("OPERATOR_CORRECTED", "CORRECT_PRINTING") and (not reason or not notes):
        raise ValueError("A correction reason and note are required")
    now = utcnow()
    card = db.execute("SELECT * FROM cards WHERE id=?", (job["card_id"],)).fetchone()
    if action in family_actions:
        cursor = db.execute(
            """INSERT INTO sam_recognition_decisions
                 (decision_uuid,request_id,job_id,card_id,decision_type,original_top_reference_id,
                  selected_reference_id,expected_revision,effective_at,recorded_at,reason_code,notes,evidence)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                f"SAM-DEC-{uuid.uuid4()}", request_id, job["id"], job["card_id"], decision_type,
                job["top_reference_id"], selected_id, expected, clean(payload.get("effective_at"), 40) or now,
                now, reason, notes,
                _json({
                    "original_suggestion_preserved": True,
                    "printing_authority_granted": False,
                    "selected_family_card_number": selected_family_number or None,
                    "reference_image_available": bool(reference),
                }),
            ),
        )
        if reference:
            _apply_identity(
                db, card, reference, state=decision_type,
                confidence=float(job["confidence"]), job_id=job["id"],
                request_id=request_id, legacy_decision_id=int(cursor.lastrowid),
            )
        elif selected_catalog_family and decision_type in ("OPERATOR_CONFIRMED", "OPERATOR_CORRECTED"):
            _apply_catalog_family_identity(
                db, card, selected_catalog_family, state=decision_type,
                confidence=float(job["family_confidence"] or job["confidence"] or 0),
                job_id=int(job["id"]), request_id=request_id,
                legacy_decision_id=int(cursor.lastrowid),
            )
        else:
            db.execute(
                "UPDATE cards SET sam_recognition_state='UNIDENTIFIED',sam_recognition_job_id=?,updated_at=? WHERE id=?",
                (job["id"], now, job["card_id"]),
            )
    else:
        family_id = int(card["sam_family_id"] or 0) or None
        if not family_id or card["sam_family_certainty"] not in ("AUTHORITATIVE", "OPERATOR_CONFIRMED"):
            raise ValueError("Confirm the card family before deciding an exact printing")
        printing_id = int(payload.get("printing_id") or 0) or None
        if not printing_id and reference:
            linked = ensure_reference_identity(db, reference) or {}
            printing_id = int((linked.get("printing") or {}).get("id") or 0) or None
        printing = None
        if printing_id:
            printing = db.execute(
                "SELECT * FROM sam_commercial_printings WHERE id=? AND family_id=? AND active=1",
                (printing_id, family_id),
            ).fetchone()
            if not printing:
                raise ValueError("Selected printing does not belong to the confirmed card family")
        prior_printing_id = card["sam_printing_id"]
        if action in ("CONFIRM_PRINTING", "CORRECT_PRINTING"):
            if not printing:
                raise ValueError("Select a documented commercial printing")
            db.execute(
                "UPDATE cards SET sam_printing_id=?,sam_printing_certainty='OPERATOR_CONFIRMED',updated_at=? WHERE id=?",
                (printing_id, now, job["card_id"]),
            )
            db.execute(
                "UPDATE sam_commercial_printings SET authority_state='OPERATOR_CONFIRMED',updated_at=? WHERE id=?",
                (now, printing_id),
            )
            event_type = "PRINTING_CORRECTED" if action == "CORRECT_PRINTING" else "PRINTING_CONFIRMED"
            certainty = "OPERATOR_CONFIRMED"
            authority_granted = True
            reason_code = reason or "OPERATOR_CONFIRMED_EXACT_PRINTING"
        else:
            if not prior_printing_id:
                certainty = "CONFLICTING" if action == "MARK_PRINTING_CONFLICT" else "UNRESOLVED"
                db.execute(
                    "UPDATE cards SET sam_printing_id=NULL,sam_printing_certainty=?,updated_at=? WHERE id=?",
                    (certainty, now, job["card_id"]),
                )
            else:
                certainty = card["sam_printing_certainty"]
            event_type = "PRINTING_CONFLICT" if action == "MARK_PRINTING_CONFLICT" else "PRINTING_LEFT_UNRESOLVED"
            authority_granted = False
            reason_code = reason or (
                "OPERATOR_MARKED_PRINTING_CONFLICT" if action == "MARK_PRINTING_CONFLICT"
                else "OPERATOR_LEFT_PRINTING_UNRESOLVED"
            )
        event_id = record_event(
            db, request_id=request_id, job_id=int(job["id"]), card_id=int(job["card_id"]),
            event_type=event_type, family_id=family_id,
            printing_id=printing_id if authority_granted else None,
            reference_id=int(reference["id"]) if reference else None,
            prior_family_id=family_id, prior_printing_id=prior_printing_id,
            certainty=certainty, actor="OPERATOR", reason_code=reason_code, notes=notes,
            evidence={"operator_only_printing_authority": True,
                      "original_suggestion_preserved": True,
                      "legacy_variant_unchanged": True},
            effective_at=clean(payload.get("effective_at"), 40),
        )
        supersedes_assertion_id = None
        if action == "CORRECT_PRINTING":
            prior_assertion = db.execute(
                """SELECT id FROM sam_identity_assertions
                   WHERE card_id=? AND field_scope='PRINTING' AND authority_granted=1
                   ORDER BY id DESC LIMIT 1""",
                (job["card_id"],),
            ).fetchone()
            supersedes_assertion_id = int(prior_assertion["id"]) if prior_assertion else None
        record_assertion(
            db, card_id=int(job["card_id"]), job_id=int(job["id"]), field_scope="PRINTING",
            family_id=family_id, printing_id=printing_id if authority_granted else None,
            reference_id=int(reference["id"]) if reference else None,
            proposed_value=printing["variant_label"] if printing else "",
            certainty=certainty, confidence=float(job["printing_confidence"] or 0),
            authority_granted=authority_granted, actor="OPERATOR", reason_code=reason_code,
            notes=notes, evidence={"decision_event_id": event_id, "legacy_variant_unchanged": True},
            supersedes_assertion_id=supersedes_assertion_id,
        )
    result = recognition_result(db, job["id"])
    result["replayed"] = False
    return result


def recognition_history(db: sqlite3.Connection, card_id: int) -> dict:
    card = db.execute("SELECT sku FROM cards WHERE id=?", (card_id,)).fetchone()
    if not card:
        raise ValueError("Card not found")
    jobs = db.execute(
        "SELECT id FROM sam_recognition_jobs WHERE card_id=? ORDER BY id", (card_id,)
    ).fetchall()
    return {"sku": card["sku"], "history": [recognition_result(db, row["id"]) for row in jobs]}


def default_provider() -> OptcgMetadataProvider:
    return OptcgMetadataProvider(
        base_url=os.environ.get("DEX_OPTCG_API_BASE", "https://optcgapi.com"),
        timeout_seconds=float(os.environ.get("DEX_OPTCG_TIMEOUT", "5")),
    )
