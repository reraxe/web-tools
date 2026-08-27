"""DEX integration boundary for the frozen SAM multi-evidence operator trial.

Recognition is immutable and suggestion-only.  Inventory family facts change
only in :func:`record_operator_decision` after an explicit confirm/correct
action.  Exact printing is never applied here.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from functools import lru_cache
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from dex_sam_identity import ensure_family, record_assertion, record_event


BUILD_IDENTIFIER = "SAM-MULTI-EVIDENCE-BLIND-TRIAL-v1a-AUDIT-20260824"
BUILD_FINGERPRINT = "dd899b6f73891252395ae9b8d09b43906ad15c656f0a0c739bd15a916c012493"
INTEGRATION_VERSION = "dex-sam-multi-evidence-operator-trial-v1a"
ALLOWED_DECISIONS = {
    "CONFIRMED_UNCHANGED", "CORRECTED_FAMILY", "CORRECTED_CARD_NUMBER",
    "CORRECTED_NAME", "MARKED_UNIDENTIFIED", "ESCALATED_REVIEW", "RESCAN_REQUESTED",
}
WRITE_DECISIONS = {"CONFIRMED_UNCHANGED", "CORRECTED_FAMILY", "CORRECTED_CARD_NUMBER"}
FROZEN_ROOT = Path(__file__).resolve().parent / "sam_multi_evidence_frozen"
WORKER_PATH = Path(__file__).resolve().parent / "dex_sam_audited_worker.py"
PRINTED_CARD_NUMBER_RE = re.compile(
    r"^(?:(?P<set>(?:OP|EB|ST|PRB)\d{1,3})[-_\s\u2010-\u2015]?(?P<number>\d{3}[A-Z]?)|"
    r"(?P<promo>P)[-_\s\u2010-\u2015]?(?P<promo_number>\d{3}[A-Z]?))$",
    re.I,
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clean(value: Any, limit: int = 500) -> str:
    return str(value or "").strip()[:limit]


def _redact_private_paths(value: Any) -> Any:
    if isinstance(value, list):
        return [_redact_private_paths(item) for item in value]
    if isinstance(value, dict):
        return {
            key: ("PRIVATE_SOURCE_REDACTED" if key in {"source_path", "stored_source_private", "original_filename_private"}
                  else _redact_private_paths(item))
            for key, item in value.items()
        }
    return value


def _frozen_expected_hashes() -> dict[str, str]:
    hashes: dict[str, str] = {}
    for line in (FROZEN_ROOT / "FROZEN_COMPONENT_SHA256SUMS.txt").read_text(encoding="utf-8-sig").splitlines():
        if "  " not in line:
            continue
        digest, relative = line.split("  ", 1)
        hashes[relative.replace("/", os.sep)] = digest
    return hashes


def frozen_component_status() -> dict[str, Any]:
    missing: list[str] = []
    mismatched: list[str] = []
    for relative, expected in _frozen_expected_hashes().items():
        path = FROZEN_ROOT / relative
        if not path.is_file():
            missing.append(relative.replace(os.sep, "/"))
        elif sha256(path) != expected:
            mismatched.append(relative.replace(os.sep, "/"))
    fingerprint = (FROZEN_ROOT / "TRIAL_BUILD_FINGERPRINT.txt").read_text(encoding="utf-8").strip()
    return {
        "available": not missing and not mismatched and fingerprint == BUILD_FINGERPRINT,
        "build_identifier": BUILD_IDENTIFIER,
        "build_fingerprint": fingerprint,
        "expected_fingerprint": BUILD_FINGERPRINT,
        "missing": missing,
        "mismatched": mismatched,
        "recognizer_changed": False,
        "suggestion_only": True,
        "exact_printing_authority": False,
    }


def _blocklisted_hashes() -> set[str]:
    payload = json.loads((FROZEN_ROOT / "config" / "prior_scan_hash_blocklist_v1.json").read_text(encoding="utf-8"))
    values: list[str] = []
    if isinstance(payload, list):
        values = payload
    elif isinstance(payload, dict):
        for key in ("sha256", "hashes", "blocked_sha256", "source_sha256"):
            raw = payload.get(key)
            if isinstance(raw, list):
                values.extend(str(item) for item in raw)
    return {value.lower() for value in values if re.fullmatch(r"[0-9a-fA-F]{64}", value)}


def _scan_for_card(card: sqlite3.Row, data_dir: Path) -> Path:
    relative = _clean(card["front_image"], 1000)
    if not relative:
        raise ValueError("This card has no front scan to process")
    root = data_dir.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("The card's front scan is unavailable")
    if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise ValueError("Select a JPG, JPEG, PNG, or WEBP card scan")
    return path


def _reference_cache(db: sqlite3.Connection, reference_root: Path, data_dir: Path) -> tuple[Path, int]:
    rows = db.execute(
        """SELECT id,card_number,set_code,source_filename,source_reference,sha256,
                  perceptual_hash,width,height,variant,printing,rarity,indexed_at
           FROM sam_reference_records
           WHERE game='One Piece' AND active=1 AND card_number!=''
           ORDER BY id"""
    ).fetchall()
    if not rows:
        raise ValueError("Index the local One Piece reference library before using audited SAM")
    token = _sha256_bytes("|".join(f"{row['id']}:{row['sha256']}:{row['indexed_at']}" for row in rows).encode())
    cache_dir = data_dir / "sam-audited-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"references-{token}.json"
    if not path.is_file():
        references = []
        root = reference_root.resolve()
        empty_regions = {
            "WHOLE_CARD": "", "ARTWORK": "", "CARD_NAME": "",
            "LOWER_METADATA": "", "RARITY_TREATMENT": "",
        }
        for row in rows:
            relative = Path(str(row["source_reference"]))
            asset_path = (root / relative).resolve()
            if not asset_path.is_relative_to(root) or not asset_path.is_file():
                continue
            features = json.loads(row["perceptual_hash"] or "{}")
            group = f"DEX::{str(relative.with_suffix('')).replace('\\', '/').upper()}"
            references.append({
                "asset_id": str(row["id"]), "asset_path": str(asset_path),
                "asset_sha256": row["sha256"], "asset_group_id": group,
                "commercial_printing_surrogate": group,
                "commercial_printing_authority": False,
                "family": row["card_number"], "family_resolved": True,
                "set_code": row["set_code"], "source_filename": row["source_filename"],
                "visual_features": features, "region_hashes": empty_regions,
                "quality": {"width": row["width"], "height": row["height"], "warnings": []},
                "printing_class": "STANDARD_REFERENCE_GROUP",
            })
        if not references:
            raise ValueError("Indexed One Piece reference images are unavailable")
        temporary = path.with_suffix(".tmp")
        temporary.write_text(_json({
            "provider": "DEX_OPERATIONAL_REFERENCE_INDEX",
            "recognition_authority": False,
            "printing_authority": False,
            "references": references,
        }), encoding="utf-8")
        os.replace(temporary, path)
    count = len(json.loads(path.read_text(encoding="utf-8"))["references"])
    return path, count


def _run_worker(scan_path: Path, scan_hash: str, reference_index: Path, data_dir: Path) -> dict[str, Any]:
    status = frozen_component_status()
    if not status["available"]:
        raise RuntimeError("The accepted audited SAM build failed its immutable component check")
    tesseract = _clean(os.environ.get("DEX_TESSERACT_CMD") or shutil.which("tesseract") or "", 1000)
    if not tesseract:
        raise RuntimeError("The local Tesseract runtime is unavailable")
    work = data_dir / "sam-audited-cache" / "worker"
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as temporary:
        request_path = Path(temporary) / "request.json"
        response_path = Path(temporary) / "response.json"
        request_path.write_text(_json({
            "frozen_root": str(FROZEN_ROOT), "scan_path": str(scan_path),
            "source_sha256": scan_hash, "reference_index_path": str(reference_index),
            "tesseract_command": tesseract,
        }), encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(WORKER_PATH), str(request_path), str(response_path)],
            capture_output=True, text=True, timeout=180, check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if completed.returncode or not response_path.is_file():
            code = "SAM_AUDITED_WORKER_FAILED"
            detail = (completed.stderr or completed.stdout or "worker did not produce a result").strip().splitlines()[-1]
            raise RuntimeError(f"{code}: {detail[:240]}")
        return _redact_private_paths(json.loads(response_path.read_text(encoding="utf-8")))


def _result_payload(db: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    result = json.loads(row["result_json"])
    decisions = [dict(item) for item in db.execute(
        "SELECT * FROM sam_audited_operator_decisions WHERE result_id=? ORDER BY id", (row["id"],)
    ).fetchall()]
    truths = [dict(item) for item in db.execute(
        "SELECT * FROM sam_audited_verified_truth WHERE result_id=? ORDER BY id", (row["id"],)
    ).fetchall()]
    card = db.execute("SELECT sku,front_image,sam_family_id,sam_family_certainty,sam_printing_id,sam_printing_certainty FROM cards WHERE id=?", (row["card_id"],)).fetchone()
    return {
        "result_uuid": row["result_uuid"], "request_id": row["request_id"],
        "sku": card["sku"], "scan_image_url": f"/media/{card['front_image']}" if card["front_image"] else "",
        "original_result": result, "original_result_sha256": row["result_sha256"],
        "operator_decisions": decisions, "verified_truth": truths,
        "decision_recorded": bool(decisions),
        "inventory_family_authoritative": card["sam_family_certainty"] in ("AUTHORITATIVE", "OPERATOR_CONFIRMED"),
        "exact_printing_authoritative": card["sam_printing_certainty"] == "OPERATOR_CONFIRMED",
        "exact_printing_unchanged_by_audited_trial": True,
        "recognizer_changed": False,
    }


def audited_status(db: sqlite3.Connection) -> dict[str, Any]:
    component = frozen_component_status()
    counts = db.execute(
        """SELECT COUNT(*) AS results,
                  SUM(CASE WHEN EXISTS (SELECT 1 FROM sam_audited_operator_decisions d WHERE d.result_id=r.id) THEN 1 ELSE 0 END) AS decided
           FROM sam_audited_recognition_results r"""
    ).fetchone()
    return {
        **component, "integration_version": INTEGRATION_VERSION,
        "results": int(counts["results"] or 0), "decided": int(counts["decided"] or 0),
        "pending": int(counts["results"] or 0) - int(counts["decided"] or 0),
        "inventory_write_boundary": "EXPLICIT_OPERATOR_CONFIRM_OR_CORRECT_ONLY",
        "catalog_verification_after_inference_only": True,
    }


def list_intake_cards(db: sqlite3.Connection, limit: int = 100) -> dict[str, Any]:
    rows = db.execute(
        """SELECT c.sku,c.name,c.card_number,c.status,c.front_image,b.batch_code,
                  (SELECT result_uuid FROM sam_audited_recognition_results r
                   WHERE r.card_id=c.id ORDER BY r.id DESC LIMIT 1) AS latest_result_uuid
           FROM cards c JOIN batches b ON b.id=c.batch_id
           WHERE b.game='One Piece' AND c.recycled_at IS NULL AND c.front_image IS NOT NULL
           ORDER BY CASE WHEN c.name='Needs identification' OR c.status='REVIEW' THEN 0 ELSE 1 END,
                    c.updated_at DESC,c.id DESC LIMIT ?""",
        (max(1, min(int(limit), 300)),),
    ).fetchall()
    return {"cards": [dict(row) for row in rows], "one_piece_only": True}


def recognize_card(
    db: sqlite3.Connection, sku: str, *, data_dir: Path, reference_root: Path,
    request_id: str, runner=None,
) -> dict[str, Any]:
    request_id = _clean(request_id, 160)
    if not request_id:
        raise ValueError("request_id is required")
    replay = db.execute("SELECT * FROM sam_audited_recognition_results WHERE request_id=?", (request_id,)).fetchone()
    if replay:
        payload = _result_payload(db, replay)
        payload["replayed"] = True
        return payload
    card = db.execute(
        """SELECT c.*,b.game,b.batch_code FROM cards c JOIN batches b ON b.id=c.batch_id
           WHERE c.sku=? AND c.recycled_at IS NULL""", (sku,)
    ).fetchone()
    if not card:
        raise ValueError("Card not found")
    if card["game"] != "One Piece":
        raise ValueError("The audited trial supports One Piece only")
    scan_path = _scan_for_card(card, data_dir)
    scan_hash = sha256(scan_path)
    if scan_hash in _blocklisted_hashes():
        raise ValueError("This exact scan was used in prior research and is not eligible for the audited operator trial")
    reference_index, reference_count = _reference_cache(db, reference_root, data_dir)
    started = time.perf_counter()
    result = (runner or _run_worker)(scan_path, scan_hash, reference_index, data_dir)
    result = _redact_private_paths(result)
    result["reference_asset_universe"] = reference_count
    result["integration_latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
    result["result_logged_before_operator"] = True
    result["catalog_truth_available_to_inference"] = False
    result["recognizer_changed"] = False
    canonical = _json(result)
    result_hash = _sha256_bytes(canonical.encode())
    now = utcnow()
    cursor = db.execute(
        """INSERT INTO sam_audited_recognition_results
             (result_uuid,request_id,card_id,source_sha256,build_identifier,build_fingerprint,
              suggested_family,suggested_name,evidence_state,review_state,result_json,result_sha256,recorded_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            f"SAM-AUDIT-RESULT-{uuid.uuid4()}", request_id, card["id"], scan_hash,
            BUILD_IDENTIFIER, BUILD_FINGERPRINT, result.get("suggested_family"),
            result.get("suggested_name"), result.get("evidence_state") or "UNRESOLVED",
            result.get("review_state") or "NEEDS_REVIEW", canonical, result_hash, now,
        ),
    )
    row = db.execute("SELECT * FROM sam_audited_recognition_results WHERE id=?", (cursor.lastrowid,)).fetchone()
    payload = _result_payload(db, row)
    payload["replayed"] = False
    return payload


def get_result(db: sqlite3.Connection, result_uuid: str) -> dict[str, Any]:
    row = db.execute("SELECT * FROM sam_audited_recognition_results WHERE result_uuid=?", (result_uuid,)).fetchone()
    if not row:
        raise ValueError("Audited recognition result not found")
    return _result_payload(db, row)


def normalize_printed_card_number(value: object) -> str:
    text = _clean(value, 120).strip().upper()
    match = PRINTED_CARD_NUMBER_RE.fullmatch(text)
    if not match:
        return ""
    if match.group("promo"):
        return f"P-{match.group('promo_number').upper()}"
    return f"{match.group('set').upper()}-{match.group('number').upper()}"


@lru_cache(maxsize=1)
def _catalog_indexes() -> tuple[tuple[dict[str, Any], ...], dict[str, dict[str, Any]]]:
    payload = json.loads(
        (FROZEN_ROOT / "config" / "one_piece_multi_evidence_catalog_v1.json").read_text(encoding="utf-8")
    )
    rows = tuple(payload.get("families") or [])
    by_number = {
        normalize_printed_card_number(item.get("card_number")): item
        for item in rows if normalize_printed_card_number(item.get("card_number"))
    }
    return rows, by_number


def catalog_search(
    query: str, limit: int = 30, db: sqlite3.Connection | None = None
) -> dict[str, Any]:
    raw_query = _clean(query, 120).strip()
    q = raw_query.upper()
    normalized = normalize_printed_card_number(raw_query)
    rows, by_number = _catalog_indexes()
    bounded_limit = max(1, min(int(limit), 100))
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    if normalized and normalized in by_number:
        ranked = [(0, normalized, by_number[normalized])]
    else:
        for item in rows:
            number = normalize_printed_card_number(item.get("card_number"))
            name = _clean(item.get("canonical_name"), 240)
            alternatives = " ".join(str(value) for value in item.get("alternative_names") or [])
            set_code = _clean(item.get("set_code"), 80).upper() or number.split("-", 1)[0]
            if q and q == name.upper():
                rank = 2
            elif q and (q in name.upper() or q in alternatives.upper()):
                rank = 3
            elif q and (q in set_code or q in number):
                rank = 4
            elif not q:
                rank = 5
            else:
                continue
            ranked.append((rank, number, item))
        ranked.sort(key=lambda value: (value[0], value[1]))
    matches = []
    for match_rank, number, item in ranked[:bounded_limit]:
        references: list[sqlite3.Row] = []
        if db is not None:
            references = db.execute(
                """SELECT id FROM sam_reference_records
                   WHERE game='One Piece' AND active=1 AND UPPER(card_number)=UPPER(?)
                   ORDER BY id""",
                (number,),
            ).fetchall()
        matches.append({
            "card_number": number,
            "canonical_name": _clean(item.get("canonical_name"), 240),
            "set_code": item.get("set_code") or number.split("-", 1)[0],
            "match_basis": "EXACT_PRINTED_CARD_NUMBER" if match_rank == 0 else (
                "EXACT_CARD_NAME" if match_rank == 2 else
                "PARTIAL_CARD_NAME" if match_rank == 3 else "SET_OR_PRODUCT_METADATA"
            ),
            "family_found": True,
            "reference_image_found": bool(references),
            "reference_count": len(references),
            "representative_reference_id": int(references[0]["id"]) if references else None,
            "descriptive_only_until_operator_selection": True,
        })
    return {
        "families": matches,
        "search": {
            "searched": raw_query,
            "normalized": normalized or "NOT_A_PRINTED_CARD_NUMBER",
            "catalog_result": "FOUND" if matches else "NOT_FOUND",
            "reference_result": (
                "AVAILABLE" if any(item["reference_image_found"] for item in matches)
                else "NOT_FOUND"
            ),
            "status": "FAMILY_FOUND" if matches else "NO_LOCAL_FAMILY_MATCH",
        },
        "catalog_fingerprint": BUILD_FINGERPRINT,
        "available_only_after_result_frozen": True,
        "recognition_authority": False,
    }


def _catalog_family(card_number: str) -> dict[str, Any] | None:
    number = _clean(card_number, 80).upper()
    payload = json.loads((FROZEN_ROOT / "config" / "one_piece_multi_evidence_catalog_v1.json").read_text(encoding="utf-8"))
    return next((item for item in payload.get("families") or [] if _clean(item.get("card_number"), 80).upper() == number), None)


def _apply_operator_family(
    db: sqlite3.Connection, card: sqlite3.Row, family_row: Mapping[str, Any], *,
    action: str, request_id: str, result_id: int, confidence: float | None,
) -> None:
    number = _clean(family_row.get("card_number"), 80).upper()
    name = _clean(family_row.get("canonical_name"), 240) or "Needs identification"
    set_code = _clean(family_row.get("set_code"), 80).upper() or number.split("-", 1)[0]
    family = ensure_family(db, game="One Piece", set_code=set_code, card_number=number, name=name,
                           external_descriptors={"source": BUILD_IDENTIFIER, "operator_authority": True})
    if not family:
        raise ValueError("Selected family cannot establish an inventory identity")
    prior_family_id = card["sam_family_id"]
    state = "OPERATOR_CONFIRMED" if action == "CONFIRMED_UNCHANGED" else "OPERATOR_CORRECTED"
    db.execute(
        """UPDATE cards SET card_number=?,name=?,set_name=?,status='IN_STOCK',
                  match_confidence=?,match_source='SAM Multi-Evidence Operator',match_reviewed=1,
                  matched_at=?,sam_recognition_state=?,sam_recognition_job_id=NULL,
                  sam_family_id=?,sam_family_certainty='OPERATOR_CONFIRMED',updated_at=?
           WHERE id=?""",
        (number, name, set_code, confidence, utcnow(), state, family["id"], utcnow(), card["id"]),
    )
    event_type = "FAMILY_CONFIRMED" if action == "CONFIRMED_UNCHANGED" else "FAMILY_CORRECTED"
    evidence = {
        "audited_result_id": result_id, "accepted_build": BUILD_IDENTIFIER,
        "original_suggestion_preserved": True, "operator_authority": True,
        "printing_authority_granted": False, "recognizer_changed": False,
    }
    record_event(
        db, request_id=request_id, card_id=int(card["id"]), event_type=event_type,
        family_id=int(family["id"]), prior_family_id=prior_family_id,
        prior_printing_id=card["sam_printing_id"], certainty="OPERATOR_CONFIRMED",
        actor="OPERATOR", reason_code="AUDITED_MULTI_EVIDENCE_OPERATOR_DECISION", evidence=evidence,
    )
    record_assertion(
        db, card_id=int(card["id"]), field_scope="FAMILY", family_id=int(family["id"]),
        proposed_value=number, certainty="OPERATOR_CONFIRMED", confidence=confidence,
        authority_granted=True, actor="OPERATOR", reason_code="AUDITED_OPERATOR_FAMILY_APPLIED",
        evidence={**evidence, "exact_printing_unchanged": True},
    )


def record_operator_decision(db: sqlite3.Connection, result_uuid: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    request_id = _clean(payload.get("request_id"), 160)
    if not request_id:
        raise ValueError("request_id is required")
    replay = db.execute("SELECT result_id FROM sam_audited_operator_decisions WHERE request_id=?", (request_id,)).fetchone()
    if replay:
        row = db.execute("SELECT * FROM sam_audited_recognition_results WHERE id=?", (replay["result_id"],)).fetchone()
        result = _result_payload(db, row)
        result["replayed"] = True
        return result
    row = db.execute("SELECT * FROM sam_audited_recognition_results WHERE result_uuid=?", (result_uuid,)).fetchone()
    if not row:
        raise ValueError("Audited recognition result not found")
    if db.execute("SELECT 1 FROM sam_audited_operator_decisions WHERE result_id=?", (row["id"],)).fetchone():
        raise ValueError("This frozen result already has an operator decision")
    result = json.loads(row["result_json"])
    action = _clean(payload.get("action"), 80).upper()
    if action not in ALLOWED_DECISIONS:
        raise ValueError("Choose a supported operator decision")
    selected_family = _clean(payload.get("selected_family"), 80).upper()
    selected_name = _clean(payload.get("selected_name"), 240)
    suggested = _clean(result.get("suggested_family"), 80).upper()
    if action == "CONFIRMED_UNCHANGED":
        selected_family = selected_family or suggested
        if not selected_family or selected_family != suggested:
            raise ValueError("Confirm Unchanged must preserve SAM's frozen suggested family")
    if action in {"CORRECTED_FAMILY", "CORRECTED_CARD_NUMBER"} and (not selected_family or selected_family == suggested):
        raise ValueError("Choose a different catalog family for a correction")
    if action == "CORRECTED_NAME" and not selected_name:
        raise ValueError("A corrected name is required")
    if action in {"MARKED_UNIDENTIFIED", "ESCALATED_REVIEW", "RESCAN_REQUESTED"}:
        selected_family = ""
    family_row = _catalog_family(selected_family) if selected_family else None
    if selected_family and not family_row:
        raise ValueError("Selected family is not in the frozen local One Piece catalog")
    reason = _clean(payload.get("reason_code"), 100)
    notes = _clean(payload.get("notes"), 1200)
    if action != "CONFIRMED_UNCHANGED" and (not reason or not notes):
        raise ValueError("This decision requires a reason and operator note")
    card = db.execute("SELECT * FROM cards WHERE id=?", (row["card_id"],)).fetchone()
    candidates = [str(item.get("card_number") or "") for item in result.get("candidates") or []]
    candidate_rank = candidates.index(selected_family) + 1 if selected_family in candidates else None
    identity_applied = action in WRITE_DECISIONS
    now = utcnow()
    cursor = db.execute(
        """INSERT INTO sam_audited_operator_decisions
             (decision_uuid,request_id,result_id,card_id,action,original_suggested_family,
              selected_family,selected_name,selected_candidate_rank,identity_applied,
              reason_code,notes,recognition_result_sha256,effective_at,recorded_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            f"SAM-AUDIT-DECISION-{uuid.uuid4()}", request_id, row["id"], row["card_id"], action,
            suggested or None, selected_family or None, selected_name or (family_row or {}).get("canonical_name"),
            candidate_rank, 1 if identity_applied else 0, reason, notes, row["result_sha256"],
            _clean(payload.get("effective_at"), 40) or now, now,
        ),
    )
    decision_id = int(cursor.lastrowid)
    if identity_applied:
        top = result.get("top_candidate") or {}
        confidence = float(top.get("visual_score") or 0.0) if top else None
        _apply_operator_family(
            db, card, family_row, action=action, request_id=request_id,
            result_id=int(row["id"]), confidence=confidence,
        )
    db.execute(
        """INSERT INTO sam_audited_recognition_deltas
             (delta_uuid,result_id,decision_id,truth_id,verification_state,before_json,
              after_json,forensic_json,recorded_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            f"SAM-AUDIT-DELTA-{uuid.uuid4()}", row["id"], decision_id, None, "UNVERIFIED",
            _json({"sam_suggested_family": suggested or None, "evidence_state": result.get("evidence_state"),
                   "candidate_list": candidates}),
            _json({"operator_action": action, "operator_selected_family": selected_family or None,
                   "verified_truth": None}),
            _json({"selected_family_in_top_k": candidate_rank is not None if selected_family else None,
                   "selected_family_candidate_rank": candidate_rank,
                   "operator_decision_is_verified_truth": False,
                   "recognizer_changed": False, "used_as_training_label": False}),
            now,
        ),
    )
    payload_result = _result_payload(db, row)
    payload_result["replayed"] = False
    return payload_result


def record_verified_truth(db: sqlite3.Connection, result_uuid: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    request_id = _clean(payload.get("request_id"), 160)
    if not request_id:
        raise ValueError("request_id is required")
    row = db.execute("SELECT * FROM sam_audited_recognition_results WHERE result_uuid=?", (result_uuid,)).fetchone()
    if not row:
        raise ValueError("Audited recognition result not found")
    replay = db.execute("SELECT id FROM sam_audited_verified_truth WHERE request_id=?", (request_id,)).fetchone()
    if replay:
        result = _result_payload(db, row)
        result["replayed"] = True
        return result
    decision = db.execute(
        "SELECT * FROM sam_audited_operator_decisions WHERE result_id=? ORDER BY id DESC LIMIT 1", (row["id"],)
    ).fetchone()
    if not decision:
        raise ValueError("Verified truth requires a prior operator decision")
    disposition = _clean(payload.get("disposition"), 80).upper()
    allowed = {"SAM_CORRECT", "OPERATOR_CORRECT", "BOTH_UNRESOLVED", "OPERATOR_CORRECTION_LATER_REVERSED"}
    if disposition not in allowed:
        raise ValueError("Choose a supported verified-truth disposition")
    family = _clean(payload.get("verified_family"), 80).upper()
    name = _clean(payload.get("verified_name"), 240)
    original = json.loads(row["result_json"])
    if disposition == "SAM_CORRECT":
        family = family or _clean(original.get("suggested_family"), 80).upper()
    elif disposition == "OPERATOR_CORRECT":
        family = family or _clean(decision["selected_family"], 80).upper()
    elif disposition == "BOTH_UNRESOLVED":
        family = ""
    if family and not _catalog_family(family):
        raise ValueError("Verified family is not in the frozen local catalog")
    notes = _clean(payload.get("notes"), 1200)
    if disposition == "OPERATOR_CORRECTION_LATER_REVERSED" and not notes:
        raise ValueError("A later-reversed correction requires an audit note")
    prior = db.execute(
        "SELECT id FROM sam_audited_verified_truth WHERE result_id=? ORDER BY id DESC LIMIT 1", (row["id"],)
    ).fetchone()
    if prior and not _clean(payload.get("amendment_reason"), 1200):
        raise ValueError("Amending verified truth requires an explicit reason")
    now = utcnow()
    cursor = db.execute(
        """INSERT INTO sam_audited_verified_truth
             (truth_uuid,request_id,result_id,decision_id,disposition,verified_family,
              verified_name,reason_code,notes,supersedes_truth_id,effective_at,recorded_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            f"SAM-AUDIT-TRUTH-{uuid.uuid4()}", request_id, row["id"], decision["id"], disposition,
            family or None, name or None, _clean(payload.get("reason_code"), 100), notes,
            prior["id"] if prior else None, _clean(payload.get("effective_at"), 40) or now, now,
        ),
    )
    truth_id = int(cursor.lastrowid)
    candidates = [str(item.get("card_number") or "") for item in original.get("candidates") or []]
    rank = candidates.index(family) + 1 if family in candidates else None
    db.execute(
        """INSERT INTO sam_audited_recognition_deltas
             (delta_uuid,result_id,decision_id,truth_id,verification_state,before_json,
              after_json,forensic_json,recorded_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            f"SAM-AUDIT-DELTA-{uuid.uuid4()}", row["id"], decision["id"], truth_id, "VERIFIED",
            _json({"sam_suggested_family": original.get("suggested_family"),
                   "evidence_state": original.get("evidence_state"), "candidate_list": candidates}),
            _json({"verified_disposition": disposition, "verified_family": family or None,
                   "operator_selected_family": decision["selected_family"]}),
            _json({"verified_family_in_top_k": rank is not None if family else None,
                   "verified_family_candidate_rank": rank,
                   "candidate_generation_failed": rank is None if family else None,
                   "fusion_or_ranking_failed": bool(family and rank and family != original.get("suggested_family")),
                   "sam_safely_deferred": original.get("review_state") in {"NEEDS_REVIEW", "UNIDENTIFIED"},
                   "operator_error_established": disposition == "OPERATOR_CORRECTION_LATER_REVERSED",
                   "recognizer_changed": False, "used_as_training_label": False}),
            now,
        ),
    )
    result = _result_payload(db, row)
    result["replayed"] = False
    return result
