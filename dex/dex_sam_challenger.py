"""Read-only SAM Challenger v1 candidate generation.

This module is intentionally additive.  It reuses a completed SAM v1 job's
OCR evidence, visual features, ranking formula, thresholds, and authority
rules.  It never writes recognition, identity, inventory, or economic facts.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from dex_sam import (
    AUTO_MARGIN_THRESHOLD,
    AUTO_MATCH_THRESHOLD,
    AUTO_VISUAL_THRESHOLD,
    OCR_CARD_NUMBER_MIN_CONFIDENCE,
    REVIEW_THRESHOLD,
    RULES_VERSION,
    _image_features,
    _loads,
    _scan_path,
    _visual_similarity,
    clean,
)


CHALLENGER_VERSION = "sam-challenger-v1-candidate-union-shadow"
CHALLENGER_MODE = "SHADOW_ONLY"
GLOBAL_VISUAL_FAMILY_LIMIT = 64
SET_CONTEXT_FAMILY_LIMIT = 24


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def _active_references(db: sqlite3.Connection) -> list[sqlite3.Row]:
    return db.execute(
        """SELECT * FROM sam_reference_records
           WHERE game='One Piece' AND active=1
           ORDER BY id"""
    ).fetchall()


def _trusted_ocr_family(job: sqlite3.Row, evidence: dict[str, Any]) -> str:
    number = clean(job["normalized_card_number"], 40).upper()
    number_evidence = dict(evidence.get("card_number") or {})
    if (
        number
        and number_evidence.get("source") == "LOCAL_TESSERACT_OCR"
        and float(number_evidence.get("confidence") or 0.0) >= OCR_CARD_NUMBER_MIN_CONFIDENCE
    ):
        return number
    return ""


def _family_key(reference: sqlite3.Row) -> str:
    return clean(reference["card_number"], 40).upper() or f"REFERENCE-{reference['id']}"


def _candidate_union(
    references: list[sqlite3.Row],
    *,
    scan_features: dict[str, Any],
    trusted_ocr_family: str,
    contextual_number: str,
    set_code: str,
) -> tuple[list[sqlite3.Row], dict[int, float], dict[str, set[str]], list[dict[str, Any]]]:
    """Return an additive family-aware pool and precomputed visual scores."""

    visual_scores: dict[int, float] = {}
    family_best: dict[str, float] = {}
    family_rows: dict[str, list[sqlite3.Row]] = {}
    for reference in references:
        family = _family_key(reference)
        family_rows.setdefault(family, []).append(reference)
        score = (
            _visual_similarity(scan_features, dict(_loads(reference["perceptual_hash"], {})))
            if scan_features.get("hashes")
            else 0.0
        )
        visual_scores[int(reference["id"])] = score
        family_best[family] = max(score, family_best.get(family, 0.0))

    ranked_families = sorted(family_best.items(), key=lambda item: (-item[1], item[0]))
    selected_sources: dict[str, set[str]] = {}

    for family, _score in ranked_families[:GLOBAL_VISUAL_FAMILY_LIMIT]:
        selected_sources.setdefault(family, set()).add("GLOBAL_VISUAL_NEIGHBOR")

    if set_code:
        set_families = [
            (family, score)
            for family, score in ranked_families
            if any(clean(row["set_code"], 40).upper() == set_code for row in family_rows[family])
        ]
        for family, _score in set_families[:SET_CONTEXT_FAMILY_LIMIT]:
            selected_sources.setdefault(family, set()).add("INDEPENDENT_SET_CONTEXT")

    if trusted_ocr_family and trusted_ocr_family in family_rows:
        selected_sources.setdefault(trusted_ocr_family, set()).add("TRUSTED_OCR_FAMILY")
    if contextual_number and contextual_number in family_rows:
        selected_sources.setdefault(contextual_number, set()).add("EXISTING_NUMBER_CONTEXT")

    candidate_rows: list[sqlite3.Row] = []
    for family in sorted(selected_sources):
        candidate_rows.extend(family_rows[family])
    candidate_rows.sort(key=lambda row: int(row["id"]))

    family_neighbors = [
        {
            "card_number": family,
            "visual_score": round(score, 4),
            "sources": sorted(selected_sources.get(family, set())),
            "reference_count": len(family_rows[family]),
        }
        for family, score in ranked_families
        if family in selected_sources
    ]
    return candidate_rows, visual_scores, selected_sources, family_neighbors


def _metadata_available(db: sqlite3.Connection, card_number: str) -> bool:
    if not card_number:
        return False
    try:
        row = db.execute(
            """SELECT 1 FROM sam_metadata_cache
               WHERE card_number=? AND cache_state='ACTIVE' LIMIT 1""",
            (card_number,),
        ).fetchone()
    except sqlite3.OperationalError:
        return False
    return bool(row)


def shadow_recognition_for_job(
    db: sqlite3.Connection,
    job_uuid: str,
    *,
    data_dir: Path,
) -> dict[str, Any]:
    """Evaluate Challenger v1 without creating or changing any database row."""

    job = db.execute(
        "SELECT * FROM sam_recognition_jobs WHERE job_uuid=?", (clean(job_uuid, 120),)
    ).fetchone()
    if not job:
        raise ValueError("Recognition job not found")
    card = db.execute("SELECT * FROM cards WHERE id=?", (job["card_id"],)).fetchone()
    batch = db.execute("SELECT * FROM batches WHERE id=?", (job["batch_id"],)).fetchone()
    if not card or not batch or clean(batch["game"], 40) != "One Piece":
        raise ValueError("SAM Challenger supports completed One Piece jobs only")

    started = time.perf_counter()
    evidence = dict(_loads(job["evidence"], {}))
    number_evidence = dict(evidence.get("card_number") or {})
    normalized_number = clean(job["normalized_card_number"], 40).upper()
    trusted_ocr_family = _trusted_ocr_family(job, evidence)
    contextual_number = normalized_number if not trusted_ocr_family else ""
    set_code = clean(batch["set_code"], 40).upper()

    scan_path = _scan_path(card, data_dir)
    scan_features: dict[str, Any] = {"hashes": [], "bucket": ""}
    quality = dict(_loads(job["scan_quality"], {}))
    if scan_path:
        try:
            scan_features, _observed_quality = _image_features(scan_path, scan=True)
        except Exception:
            if "SCAN_IMAGE_UNREADABLE" not in quality.setdefault("warnings", []):
                quality["warnings"].append("SCAN_IMAGE_UNREADABLE")

    references = _active_references(db)
    rows, visual_scores, source_map, family_neighbors = _candidate_union(
        references,
        scan_features=scan_features,
        trusted_ocr_family=trusted_ocr_family,
        contextual_number=contextual_number,
        set_code=set_code,
    )

    scored: list[tuple[float, float, float, float, sqlite3.Row]] = []
    visual_ranked: list[tuple[float, sqlite3.Row]] = []
    for reference in rows:
        number_score = 1.0 if normalized_number and reference["card_number"] == normalized_number else 0.0
        visual_score = visual_scores.get(int(reference["id"]), 0.0)
        visual_ranked.append((visual_score, reference))
        context_score = 1.0 if set_code and reference["set_code"] == set_code else 0.0
        confidence = (
            0.55 * number_score + 0.40 * visual_score + 0.05 * context_score
            if normalized_number
            else 0.82 * visual_score + 0.18 * context_score
        )
        scored.append((round(confidence, 4), number_score, visual_score, context_score, reference))
    scored.sort(key=lambda item: (-item[0], -item[2], int(item[4]["id"])))
    visual_ranked.sort(key=lambda item: (-item[0], int(item[1]["id"])))

    best = scored[0] if scored else None
    second = scored[1] if len(scored) > 1 else None
    visual_best = visual_ranked[0] if visual_ranked else None
    margin = round(best[0] - second[0], 4) if best and second else 1.0
    warnings = list(quality.get("warnings") or [])
    exceptions: list[str] = ["POOR_SCAN_QUALITY"] if warnings else []
    scan_ocr_evidence = number_evidence.get("source") == "LOCAL_TESSERACT_OCR"
    ocr_visual_conflict = bool(
        scan_ocr_evidence
        and normalized_number
        and visual_best
        and visual_best[1]["card_number"] != normalized_number
    )
    ocr_reference_missing = bool(
        scan_ocr_evidence
        and normalized_number
        and not any(row["card_number"] == normalized_number for row in rows)
    )
    if ocr_visual_conflict:
        exceptions.append("CARD_NUMBER_OCR_CONFLICT")
    if ocr_reference_missing:
        exceptions.append("CARD_NUMBER_REFERENCE_MISSING")
    ambiguous_variant = bool(
        best
        and second
        and best[4]["card_number"] == second[4]["card_number"]
        and abs(best[2] - second[2]) < AUTO_MARGIN_THRESHOLD
    )
    if ambiguous_variant:
        exceptions.append("MULTIPLE_PLAUSIBLE_VARIANTS")
    if normalized_number and not _metadata_available(db, normalized_number):
        exceptions.append("METADATA_PROVIDER_MISSING")

    severe_quality = any(code in warnings for code in ("INSUFFICIENT_CARD_AREA", "SCAN_IMAGE_UNREADABLE"))
    if (
        best
        and best[0] >= AUTO_MATCH_THRESHOLD
        and best[1] >= 0.99
        and best[2] >= AUTO_VISUAL_THRESHOLD
        and margin >= AUTO_MARGIN_THRESHOLD
        and not ambiguous_variant
        and not severe_quality
        and not ocr_visual_conflict
        and not ocr_reference_missing
    ):
        state = "AUTO_MATCHED"
    elif best and best[0] >= REVIEW_THRESHOLD and not (severe_quality and not normalized_number):
        state = "NEEDS_REVIEW"
        if not exceptions:
            exceptions.append("LOW_RECOGNITION_CONFIDENCE")
    else:
        state = "UNIDENTIFIED"
        exceptions.append("NO_REFERENCE_MATCH")

    candidates = []
    for rank, item in enumerate(scored[:10], start=1):
        reference = item[4]
        family = _family_key(reference)
        candidates.append(
            {
                "rank": rank,
                "reference_id": int(reference["id"]),
                "card_number": reference["card_number"],
                "card_name": reference["card_name"],
                "set_code": reference["set_code"],
                "variant": reference["variant"],
                "printing": reference["printing"],
                "confidence": item[0],
                "card_number_score": item[1],
                "visual_score": item[2],
                "context_score": item[3],
                "candidate_sources": sorted(source_map.get(family, set())),
            }
        )

    family_ranked: list[dict[str, Any]] = []
    seen_families: set[str] = set()
    for item in scored:
        family = _family_key(item[4])
        if family in seen_families:
            continue
        seen_families.add(family)
        family_ranked.append(
            {
                "rank": len(family_ranked) + 1,
                "card_number": family,
                "card_name": item[4]["card_name"],
                "confidence": item[0],
                "visual_score": item[2],
                "reference_count": sum(1 for row in rows if _family_key(row) == family),
                "candidate_sources": sorted(source_map.get(family, set())),
            }
        )

    top_family = family_ranked[0] if family_ranked else None
    top_family_rows = [row for row in rows if top_family and _family_key(row) == top_family["card_number"]]
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "mode": CHALLENGER_MODE,
        "challenger_version": CHALLENGER_VERSION,
        "baseline_rules_version": RULES_VERSION,
        "job_uuid": job["job_uuid"],
        "sku": card["sku"],
        "recognition_state": state,
        "identity_applied": False,
        "database_writes": 0,
        "trusted_ocr_family": trusted_ocr_family or None,
        "trusted_ocr_is_authority": False,
        "candidate_generation": {
            "strategy": "TRUSTED_OCR_UNION_GLOBAL_VISUAL_NEIGHBORS_OPTIONAL_SET_CONTEXT",
            "reference_universe": len(references),
            "candidate_references": len(rows),
            "candidate_families": len(source_map),
            "family_numbers": sorted(source_map),
            "global_visual_family_limit": GLOBAL_VISUAL_FAMILY_LIMIT,
            "set_context_family_limit": SET_CONTEXT_FAMILY_LIMIT,
            "family_neighbors": family_neighbors,
        },
        "family_stage": {
            "top_family": top_family,
            "ranking": family_ranked[:10],
        },
        "printing_stage": {
            "family": top_family["card_number"] if top_family else None,
            "status": (
                "UNRESOLVED_VARIANT_AMBIGUITY" if ambiguous_variant else
                "SINGLE_REFERENCE_CANDIDATE" if len(top_family_rows) == 1 else
                "SEPARATE_REVIEW_REQUIRED" if top_family_rows else "NO_FAMILY"
            ),
            "reference_count": len(top_family_rows),
            "authority_granted": state == "AUTO_MATCHED",
        },
        "top_candidate": candidates[0] if candidates else None,
        "candidates": candidates,
        "evidence": {
            "card_number": number_evidence,
            "visual_top_candidate": {
                "card_number": visual_best[1]["card_number"],
                "card_name": visual_best[1]["card_name"],
                "visual_score": visual_best[0],
            } if visual_best else None,
            "margin": margin,
            "ocr_visual_conflict": ocr_visual_conflict,
            "ocr_reference_missing": ocr_reference_missing,
            "variant_ambiguity": ambiguous_variant,
            "exception_codes": sorted(set(exceptions)),
            "recognition_duration_ms": duration_ms,
            "ocr_reused_from_frozen_baseline": True,
        },
        "calculation_boundary": "IDENTITY_SHADOW_ONLY_NO_WRITES_NO_ECONOMICS",
    }


def load_shadow_comparison(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"available": False, "mode": CHALLENGER_MODE, "reason": "SHADOW_REPORT_NOT_CONFIGURED"}
    try:
        resolved = path.resolve(strict=True)
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {"available": False, "mode": CHALLENGER_MODE, "reason": "SHADOW_REPORT_UNAVAILABLE"}
    if not isinstance(payload, dict):
        return {"available": False, "mode": CHALLENGER_MODE, "reason": "SHADOW_REPORT_INVALID"}
    return {"available": True, "mode": CHALLENGER_MODE, **payload}
