"""Additive SAM Challenger v2 family + printing shadow evaluation.

This module never writes DEX data and never grants printing authority. Family
candidate generation/ranking reuses the frozen Challenger v1 rules. Printing
assets are grouped separately so resized twins cannot masquerade as commercial
variants.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any


CHALLENGER_VERSION = "sam-challenger-v2-variant-gauntlet-shadow"
CHALLENGER_MODE = "SHADOW_ONLY"
GLOBAL_VISUAL_FAMILY_LIMIT = 64
SET_CONTEXT_FAMILY_LIMIT = 24
AUTOMATIC_PRINTING_AUTHORITY = False
REGIONS = {
    "WHOLE_CARD": (0.00, 0.00, 1.00, 1.00),
    "ARTWORK": (0.05, 0.05, 0.95, 0.64),
    "CARD_NAME": (0.12, 0.68, 0.88, 0.90),
    "LOWER_METADATA": (0.45, 0.76, 0.995, 0.995),
    "RARITY_TREATMENT": (0.72, 0.78, 0.995, 0.995),
}
ASSET_TWIN_SUFFIX = re.compile(r"(?:[_-](?:small|thumb|thumbnail|resized|large|full))+$", re.I)
SPECIAL_TOKENS = {
    "SP": "SP",
    "WINNER": "WINNER",
    "JUDGE": "JUDGE",
    "REGIONAL": "REGIONAL",
    "TOURNAMENT": "TOURNAMENT",
    "STAMP": "STAMPED_PROMO",
    "ALT": "ALTERNATE_ART",
    "ALTERNATE": "ALTERNATE_ART",
    "PARALLEL": "ALTERNATE_ART",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_frozen_core(preserved_root: Path):
    root = str(preserved_root.resolve())
    if root not in sys.path:
        sys.path.insert(0, root)
    return importlib.import_module("dex_sam")


def normalized_asset_stem(path: Path) -> str:
    return ASSET_TWIN_SUFFIX.sub("", path.stem)


def reference_asset_group(relative_path: str) -> str:
    path = Path(relative_path)
    parent = path.parent.as_posix().upper()
    return f"LOCAL::{parent}/{normalized_asset_stem(path).upper()}"


def printing_class(asset_group: str, family: str) -> str:
    suffix = asset_group.rsplit("/", 1)[-1].upper().replace(family.upper(), "", 1)
    tokens = {token for token in re.split(r"[^A-Z0-9*]+", suffix) if token}
    if "*" in suffix or any(token.endswith("STAR") for token in tokens):
        return "STARRED_RARITY"
    for token, label in SPECIAL_TOKENS.items():
        if token in tokens:
            return label
    if re.search(r"(?:^|[_-])P\d+(?:$|[_-])", suffix):
        return "ALTERNATE_ART"
    return "STANDARD_REFERENCE_GROUP"


def _dhash(image: Any) -> str:
    from PIL import Image  # type: ignore

    resized = image.convert("L").resize((17, 16), Image.Resampling.LANCZOS)
    pixels = list(resized.tobytes())
    bits = []
    for y in range(16):
        row = y * 17
        for x in range(16):
            bits.append("1" if pixels[row + x] > pixels[row + x + 1] else "0")
    return f"{int(''.join(bits), 2):064x}"


def region_hashes(path: Path) -> dict[str, str]:
    from PIL import Image, ImageOps  # type: ignore

    with Image.open(path) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    if image.width > image.height:
        image = image.rotate(90, expand=True)
    width, height = image.size
    output: dict[str, str] = {}
    for name, bounds in REGIONS.items():
        box = (
            int(width * bounds[0]), int(height * bounds[1]),
            max(1, int(width * bounds[2])), max(1, int(height * bounds[3])),
        )
        output[name] = _dhash(ImageOps.autocontrast(image.crop(box).convert("L")))
    return output


def _hash_similarity(left: str, right: str) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    distance = (int(left, 16) ^ int(right, 16)).bit_count()
    return round(max(0.0, 1.0 - distance / (len(left) * 4)), 4)


def region_similarity(scan: dict[str, str], reference: dict[str, str]) -> dict[str, float]:
    return {name: _hash_similarity(scan.get(name, ""), reference.get(name, "")) for name in REGIONS}


def build_reference_record(path: Path, root: Path, core: Any) -> dict[str, Any]:
    relative = path.relative_to(root).as_posix()
    family = core.normalize_card_number(path.stem)
    family_resolved = bool(family)
    if not family:
        # Challenger v1 retained unnumbered DON!! assets as fallback references.
        # Keep them in the frozen universe without pretending they are a card
        # number family or allowing them to become commercial-printing truth.
        family = f"UNNUMBERED::{Path(relative).parent.as_posix().upper()}/{normalized_asset_stem(path).upper()}"
    features, quality = core._image_features(path)
    group = reference_asset_group(relative)
    return {
        "asset_id": relative,
        "asset_path": str(path.resolve()),
        "asset_sha256": sha256(path),
        "asset_group_id": group,
        "commercial_printing_surrogate": group,
        "commercial_printing_authority": False,
        "family": family,
        "family_resolved": family_resolved,
        "set_code": family.split("-", 1)[0] if family_resolved else "",
        "source_filename": path.name,
        "visual_features": features,
        "region_hashes": region_hashes(path),
        "quality": quality,
        "printing_class": printing_class(group, family),
    }


def _trusted_ocr_family(evidence: dict[str, Any], core: Any) -> str:
    normalized = core.clean(evidence.get("normalized"), 40).upper()
    if (
        normalized
        and evidence.get("source") == "LOCAL_TESSERACT_OCR"
        and float(evidence.get("confidence") or 0.0) >= core.OCR_CARD_NUMBER_MIN_CONFIDENCE
    ):
        return normalized
    return ""


def _candidate_union(
    references: list[dict[str, Any]],
    scan_features: dict[str, Any],
    trusted_ocr_family: str,
    core: Any,
) -> tuple[list[dict[str, Any]], dict[str, float], dict[str, set[str]], list[dict[str, Any]]]:
    visual_scores: dict[str, float] = {}
    family_best: dict[str, float] = {}
    family_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for reference in references:
        family = reference["family"]
        family_rows[family].append(reference)
        score = core._visual_similarity(scan_features, reference["visual_features"])
        visual_scores[reference["asset_id"]] = score
        family_best[family] = max(score, family_best.get(family, 0.0))
    ranked_families = sorted(family_best.items(), key=lambda item: (-item[1], item[0]))
    sources: dict[str, set[str]] = {}
    for family, _score in ranked_families[:GLOBAL_VISUAL_FAMILY_LIMIT]:
        sources.setdefault(family, set()).add("GLOBAL_VISUAL_NEIGHBOR")
    if trusted_ocr_family and trusted_ocr_family in family_rows:
        sources.setdefault(trusted_ocr_family, set()).add("TRUSTED_OCR_FAMILY")
    selected = [row for family in sorted(sources) for row in family_rows[family]]
    neighbors = [
        {
            "card_number": family,
            "visual_score": round(score, 4),
            "sources": sorted(sources.get(family, set())),
            "reference_count": len(family_rows[family]),
        }
        for family, score in ranked_families if family in sources
    ]
    return selected, visual_scores, sources, neighbors


def _printing_stage(
    top_family: str,
    rows: list[dict[str, Any]],
    scan_regions: dict[str, str],
    visual_scores: dict[str, float],
) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["family"] == top_family:
            groups[row["asset_group_id"]].append(row)
    ranked: list[dict[str, Any]] = []
    for group_id, assets in groups.items():
        best_asset = None
        best_score = -1.0
        best_regions: dict[str, float] = {}
        for asset in assets:
            similarities = region_similarity(scan_regions, asset["region_hashes"])
            # Artwork distinguishes alternate art; lower regions and whole-card
            # evidence keep the comparison sensitive to printing treatments.
            printing_score = round(
                0.48 * similarities["ARTWORK"]
                + 0.18 * similarities["LOWER_METADATA"]
                + 0.12 * similarities["RARITY_TREATMENT"]
                + 0.12 * similarities["CARD_NAME"]
                + 0.10 * similarities["WHOLE_CARD"],
                4,
            )
            if printing_score > best_score:
                best_asset, best_score, best_regions = asset, printing_score, similarities
        if not best_asset:
            continue
        special_class = best_asset["printing_class"]
        special = special_class != "STANDARD_REFERENCE_GROUP"
        ranked.append({
            "asset_group_id": group_id,
            "commercial_printing_surrogate": best_asset["commercial_printing_surrogate"],
            "descriptive_only": True,
            "printing_class": special_class,
            "reference_asset_count": len(assets),
            "best_reference_asset": best_asset["asset_id"],
            "printing_score": best_score,
            "family_visual_score": max(visual_scores[item["asset_id"]] for item in assets),
            "region_scores": best_regions,
            "required_marker_state": "UNRESOLVED" if special else "NOT_APPLICABLE",
            "positive_special_evidence_satisfied": False,
        })
    ranked.sort(key=lambda item: (-item["printing_score"], item["asset_group_id"]))
    margin = round(ranked[0]["printing_score"] - ranked[1]["printing_score"], 4) if len(ranked) > 1 else 0.0
    return {
        "family": top_family or None,
        "status": "UNRESOLVED_NO_AUTOMATIC_PRINTING_AUTHORITY" if ranked else "NO_FAMILY_REFERENCES",
        "printing_identity": None,
        "printing_confidence": None,
        "descriptive_top_reference_group": ranked[0] if ranked else None,
        "descriptive_margin": margin,
        "reference_groups": ranked[:10],
        "asset_twins_grouped": sum(max(0, item["reference_asset_count"] - 1) for item in ranked),
        "marker_state_contract": ["PRESENT", "ABSENT_CONFIDENT", "UNRESOLVED"],
        "authority_granted": False,
        "identity_applied": False,
    }


def recognize_shadow(
    scan_path: Path,
    references: list[dict[str, Any]],
    *,
    core: Any,
    ocr_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    scan_started = time.perf_counter()
    scan_features, quality = core._image_features(scan_path, scan=True)
    scan_regions = region_hashes(scan_path)
    scan_feature_ms = round((time.perf_counter() - scan_started) * 1000, 2)
    ocr_started = time.perf_counter()
    evidence = ocr_evidence if ocr_evidence is not None else core.read_card_number_evidence(scan_path, None)
    ocr_wall_ms = round((time.perf_counter() - ocr_started) * 1000, 2)
    trusted_ocr = _trusted_ocr_family(evidence, core)
    normalized_number = trusted_ocr

    rows, visual_scores, source_map, family_neighbors = _candidate_union(
        references, scan_features, trusted_ocr, core
    )
    scored: list[tuple[float, float, float, dict[str, Any]]] = []
    visual_ranked: list[tuple[float, dict[str, Any]]] = []
    for reference in rows:
        number_score = 1.0 if normalized_number and reference["family"] == normalized_number else 0.0
        visual_score = visual_scores[reference["asset_id"]]
        confidence = 0.55 * number_score + 0.40 * visual_score if normalized_number else 0.82 * visual_score
        scored.append((round(confidence, 4), number_score, visual_score, reference))
        visual_ranked.append((visual_score, reference))
    scored.sort(key=lambda item: (-item[0], -item[2], item[3]["asset_id"]))
    visual_ranked.sort(key=lambda item: (-item[0], item[1]["asset_id"]))
    best = scored[0] if scored else None
    second = scored[1] if len(scored) > 1 else None
    visual_best = visual_ranked[0] if visual_ranked else None
    margin = round(best[0] - second[0], 4) if best and second else 1.0
    ocr_visual_conflict = bool(
        trusted_ocr and visual_best and visual_best[1]["family"] != trusted_ocr
    )
    ambiguous_asset = bool(
        best and second and best[3]["family"] == second[3]["family"]
        and abs(best[2] - second[2]) < core.AUTO_MARGIN_THRESHOLD
    )
    warnings = list(quality.get("warnings") or [])
    severe_quality = any(code in warnings for code in ("INSUFFICIENT_CARD_AREA", "SCAN_IMAGE_UNREADABLE"))
    would_auto = bool(
        best and best[0] >= core.AUTO_MATCH_THRESHOLD and best[1] >= 0.99
        and best[2] >= core.AUTO_VISUAL_THRESHOLD and margin >= core.AUTO_MARGIN_THRESHOLD
        and not ambiguous_asset and not severe_quality and not ocr_visual_conflict
    )
    if would_auto:
        family_state = "AUTO_MATCHED"
    elif best and best[0] >= core.REVIEW_THRESHOLD and not (severe_quality and not normalized_number):
        family_state = "NEEDS_REVIEW"
    else:
        family_state = "UNIDENTIFIED"

    family_ranking: list[dict[str, Any]] = []
    seen: set[str] = set()
    for confidence, number_score, visual_score, reference in scored:
        family = reference["family"]
        if family in seen:
            continue
        seen.add(family)
        family_ranking.append({
            "rank": len(family_ranking) + 1,
            "card_number": family,
            "confidence": confidence,
            "card_number_score": number_score,
            "visual_score": visual_score,
            "candidate_sources": sorted(source_map.get(family, set())),
        })
    top_family = family_ranking[0]["card_number"] if family_ranking else ""
    printing = _printing_stage(top_family, rows, scan_regions, visual_scores)
    total_ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "mode": CHALLENGER_MODE,
        "challenger_version": CHALLENGER_VERSION,
        "identity_applied": False,
        "database_writes": 0,
        "family_stage": {
            "state": family_state,
            "top_family": family_ranking[0] if family_ranking else None,
            "ranking": family_ranking[:10],
            "would_auto_match_under_frozen_family_rules": would_auto,
            "authority_applied": False,
        },
        "printing_stage": printing,
        "candidate_generation": {
            "strategy": "FROZEN_V1_TRUSTED_OCR_UNION_GLOBAL_VISUAL_NEIGHBORS",
            "reference_asset_universe": len(references),
            "candidate_references": len(rows),
            "candidate_families": len(source_map),
            "family_numbers": sorted(source_map),
            "family_neighbors": family_neighbors,
            "trusted_ocr_family": trusted_ocr or None,
            "trusted_ocr_is_authority": False,
        },
        "evidence": {
            "card_number": evidence,
            "visual_top_family": visual_best[1]["family"] if visual_best else None,
            "visual_top_score": visual_best[0] if visual_best else None,
            "family_margin": margin,
            "ocr_visual_conflict": ocr_visual_conflict,
            "asset_twin_ambiguity": ambiguous_asset,
            "scan_quality": quality,
            "region_strategy": list(REGIONS),
        },
        "latency_ms": {
            "scan_features": scan_feature_ms,
            "ocr_wall": ocr_wall_ms,
            "ocr_reported": round(float(evidence.get("preprocessing_ms") or 0.0) + float(evidence.get("execution_ms") or 0.0), 2),
            "total": total_ms,
        },
        "policy_guards": {
            "shadow_only": True,
            "automatic_printing_authority": False,
            "tcgplayer_recognition_authority": False,
            "thresholds_changed": False,
            "production_behavior_changed": False,
        },
    }


def load_reference_index(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("recognition_authority") is not False:
        raise ValueError("Reference index must remain descriptive and non-authoritative")
    return payload, list(payload.get("references") or [])
