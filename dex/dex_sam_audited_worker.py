#!/usr/bin/env python3
"""Isolated process adapter for the byte-frozen multi-evidence recognizer.

DEX already imports a production ``dex_sam`` module.  The accepted trial also
contains a frozen module with that name, so the audited recognizer runs in this
short-lived worker with its own import path.  This adapter supplies operational
reference records and does not alter OCR, candidate generation, evidence
fusion, thresholds, or authority rules.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


BUILD_IDENTIFIER = "SAM-MULTI-EVIDENCE-BLIND-TRIAL-v1a-AUDIT-20260824"
HARNESS_VERSION = "sam-multi-evidence-dex-adapter-v1a"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: dex_sam_audited_worker.py REQUEST_JSON RESPONSE_JSON")
    request_path = Path(sys.argv[1]).resolve()
    response_path = Path(sys.argv[2]).resolve()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    frozen_root = Path(request["frozen_root"]).resolve()
    runtime_root = frozen_root / "runtime"
    scan_path = Path(request["scan_path"]).resolve()
    reference_path = Path(request["reference_index_path"]).resolve()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(runtime_root))

    import dex_sam_challenger_v2 as challenger  # type: ignore
    from vision_intake.catalog_constrained_ocr import LocalFamilyCatalog  # type: ignore
    from vision_intake.dual_ocr import DualLocalizedOcr  # type: ignore
    from vision_intake.multi_evidence import (  # type: ignore
        MultiEvidenceCatalog,
        evaluate_multi_evidence,
        recognize_dual_ocr_shadow,
    )

    core = challenger.load_frozen_core(runtime_root)
    family_catalog = LocalFamilyCatalog.from_snapshot(
        frozen_root / "config" / "one_piece_family_catalog_snapshot_v1.json"
    )
    evidence_catalog = MultiEvidenceCatalog.from_snapshot(
        frozen_root / "config" / "one_piece_multi_evidence_catalog_v1.json"
    )
    references = list(json.loads(reference_path.read_text(encoding="utf-8"))["references"])
    tesseract = str(request.get("tesseract_command") or os.environ.get("DEX_TESSERACT_CMD") or "tesseract")
    extractor = DualLocalizedOcr(family_catalog, tesseract_command=tesseract)

    started = time.perf_counter()
    dual = extractor.analyze(scan_path)
    ranked = recognize_dual_ocr_shadow(
        scan_path, references, core=core, frozen_challenger=challenger, dual=dual
    )
    name_observations = () if dual.exact_engine_agreement else extractor.analyze_names(scan_path)
    fusion = evaluate_multi_evidence(dual, name_observations, ranked, evidence_catalog)
    top = fusion.get("top_family")
    state = str(fusion.get("state") or "UNRESOLVED")
    review_state = "SUGGESTION" if state in {"STRONG_SUPPORT", "SUPPORT"} else "NEEDS_REVIEW"
    if not top:
        review_state = "UNIDENTIFIED"
    top_candidate = next(
        (row for row in fusion.get("candidates") or [] if row.get("card_number") == top), None
    )
    elapsed = round((time.perf_counter() - started) * 1000.0, 4)
    payload = {
        "recognized_at": utcnow(),
        "harness_version": HARNESS_VERSION,
        "accepted_build_identifier": BUILD_IDENTIFIER,
        "build_fingerprint": (frozen_root / "TRIAL_BUILD_FINGERPRINT.txt").read_text(encoding="utf-8").strip(),
        "source_sha256": request["source_sha256"],
        "suggested_family": top,
        "suggested_name": fusion.get("top_family_name"),
        "evidence_state": state,
        "review_state": review_state,
        "confidence_is_authority": False,
        "human_explanation": list(fusion.get("human_explanation") or []),
        "top_candidate": top_candidate,
        "candidates": list(fusion.get("candidates") or []),
        "candidate_count": int(fusion.get("candidate_count") or 0),
        "dual_ocr": dual.as_dict(),
        "name_observations": [row.as_dict() for row in name_observations],
        "conflicts": state == "CONFLICT",
        "raw_visual_ranking": ranked.get("family_stage"),
        "candidate_generation": ranked.get("candidate_generation"),
        "latency_ms": {
            "dual_ocr": round(float(dual.latency_ms), 4),
            "visual_and_fusion_total": elapsed,
            "operator_suggestion_total": elapsed,
        },
        "authority": {
            "suggestion_only": True,
            "identity_applied": False,
            "automatic_family_write": False,
            "exact_printing_authority": False,
            "variant_treatment_rarity_authority": False,
            "database_writes": 0,
            "marketplace_writes": 0,
            "wolff_writes": 0,
            "jana_writes": 0,
        },
        "operator_actions": [
            "CONFIRMED_UNCHANGED", "CORRECTED_FAMILY", "CORRECTED_CARD_NUMBER",
            "CORRECTED_NAME", "MARKED_UNIDENTIFIED", "ESCALATED_REVIEW", "RESCAN_REQUESTED",
        ],
    }
    response_path.write_text(json.dumps(payload, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
