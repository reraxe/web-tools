#!/usr/bin/env python3
"""Compare frozen SAM v1 results with read-only Challenger v1 results."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dex_sam_challenger import CHALLENGER_VERSION, shadow_recognition_for_job


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return round(ordered[index], 2)


def metric_block(rows: list[dict], *, challenger: bool) -> dict:
    state_key = "challenger_state" if challenger else "state"
    top_key = "challenger_top_correct" if challenger else "top_correct"
    pool_key = "challenger_pool_included" if challenger else "baseline_pool_included"
    latency_key = "challenger_total_estimated_ms" if challenger else "recognition_duration_ms"
    latencies = [float(row[latency_key] or 0.0) for row in rows]
    states = Counter(row[state_key] for row in rows)
    false_auto = sum(
        1 for row in rows if row[state_key] == "AUTO_MATCHED" and not bool(row[top_key])
    )
    return {
        "correct_family_entered_candidate_pool": sum(bool(row[pool_key]) for row in rows),
        "correct_family_entered_candidate_pool_rate": round(sum(bool(row[pool_key]) for row in rows) / len(rows), 4),
        "correct_top_family": sum(bool(row[top_key]) for row in rows),
        "correct_top_family_rate": round(sum(bool(row[top_key]) for row in rows) / len(rows), 4),
        "ocr_correct": sum(bool(row["ocr_correct"]) for row in rows),
        "states": dict(sorted(states.items())),
        "false_auto_matches": false_auto,
        "latency_ms": {
            "average": round(statistics.mean(latencies), 2),
            "median": round(statistics.median(latencies), 2),
            "p95": percentile(latencies, 0.95),
            "slowest": round(max(latencies), 2),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--baseline-csv", type=Path, required=True)
    parser.add_argument("--baseline-predictions", type=Path, required=True)
    parser.add_argument("--baseline-summary", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    for path in (args.db, args.baseline_csv, args.baseline_predictions, args.baseline_summary):
        if not path.is_file():
            raise SystemExit(f"Required frozen input is missing: {path}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    before_hash = sha256(args.db)
    baseline_rows = list(csv.DictReader(args.baseline_csv.open(encoding="utf-8-sig", newline="")))
    if len(baseline_rows) != 50:
        raise SystemExit(f"Expected exactly 50 frozen baseline rows, found {len(baseline_rows)}")
    by_sku = {row["sku"]: row for row in baseline_rows}

    uri = f"file:{quote(str(args.db.resolve()).replace(chr(92), '/'), safe=':/')}?mode=ro"
    db = sqlite3.connect(uri, uri=True)
    db.row_factory = sqlite3.Row
    jobs = db.execute(
        """SELECT j.*,c.sku FROM sam_recognition_jobs j
           JOIN cards c ON c.id=j.card_id
           ORDER BY j.id"""
    ).fetchall()
    if len(jobs) != 50:
        raise SystemExit(f"Expected exactly 50 completed baseline jobs, found {len(jobs)}")

    compared: list[dict] = []
    for job in jobs:
        baseline = by_sku.get(job["sku"])
        if not baseline:
            raise SystemExit(f"Frozen baseline CSV has no row for {job['sku']}")
        challenger = shadow_recognition_for_job(
            db, job["job_uuid"], data_dir=args.data_dir.resolve()
        )
        expected = baseline["expected_card_number"]
        top = (challenger.get("family_stage") or {}).get("top_family") or {}
        family_numbers = set((challenger.get("candidate_generation") or {}).get("family_numbers") or [])
        number_evidence = (challenger.get("evidence") or {}).get("card_number") or {}
        ocr_ms = float(number_evidence.get("preprocessing_ms") or 0.0) + float(number_evidence.get("execution_ms") or 0.0)
        candidate_ms = float((challenger.get("evidence") or {}).get("recognition_duration_ms") or 0.0)
        compared.append(
            {
                "corpus_id": baseline["corpus_id"],
                "source_filename": baseline["source_filename"],
                "sku": baseline["sku"],
                "expected_card_number": expected,
                "expected_name": baseline["expected_name"],
                "ocr_result": baseline["ocr_result"],
                "ocr_correct": baseline["ocr_correct"].lower() == "true",
                "baseline_pool_included": bool(baseline["expected_candidate_rank_top5"]),
                "baseline_top_candidate": baseline["top_candidate"],
                "top_correct": baseline["top_correct"].lower() == "true",
                "state": baseline["state"],
                "recognition_duration_ms": float(baseline["recognition_duration_ms"] or 0.0),
                "challenger_pool_included": expected in family_numbers,
                "challenger_top_family": top.get("card_number", ""),
                "challenger_top_correct": top.get("card_number") == expected,
                "challenger_state": challenger["recognition_state"],
                "challenger_candidate_references": challenger["candidate_generation"]["candidate_references"],
                "challenger_candidate_families": challenger["candidate_generation"]["candidate_families"],
                "challenger_candidate_ms": candidate_ms,
                "frozen_ocr_ms": round(ocr_ms, 2),
                "challenger_total_estimated_ms": round(ocr_ms + candidate_ms, 2),
                "challenger_false_auto": challenger["recognition_state"] == "AUTO_MATCHED" and top.get("card_number") != expected,
                "trusted_ocr_family": challenger.get("trusted_ocr_family") or "",
                "ocr_visual_conflict": bool(challenger["evidence"]["ocr_visual_conflict"]),
                "variant_ambiguity": bool(challenger["evidence"]["variant_ambiguity"]),
                "exceptions": "|".join(challenger["evidence"]["exception_codes"]),
            }
        )
    db.close()
    after_hash = sha256(args.db)
    if before_hash != after_hash:
        raise SystemExit("FAIL: frozen benchmark database changed during shadow evaluation")

    baseline_metrics = metric_block(compared, challenger=False)
    challenger_metrics = metric_block(compared, challenger=True)
    original_five = [row for row in compared if row["corpus_id"] in {f"P4-{index:04d}" for index in range(1, 6)}]
    safety_gate = challenger_metrics["false_auto_matches"] == 0
    improvement_gate = (
        challenger_metrics["correct_family_entered_candidate_pool"] > 9
        and challenger_metrics["correct_top_family_rate"] > 0.18
    )
    report = {
        "report_version": "sam-challenger-shadow-comparison-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "SHADOW_ONLY",
        "production_rollout": False,
        "challenger_version": CHALLENGER_VERSION,
        "frozen_inputs": {
            "database_sha256_before": before_hash,
            "database_sha256_after": after_hash,
            "baseline_csv": {"name": args.baseline_csv.name, "sha256": sha256(args.baseline_csv)},
            "baseline_predictions": {"name": args.baseline_predictions.name, "sha256": sha256(args.baseline_predictions)},
            "baseline_summary": {"name": args.baseline_summary.name, "sha256": sha256(args.baseline_summary)},
        },
        "policy_guards": {
            "sam_v1_modified": False,
            "ocr_rerun": False,
            "thresholds_changed": False,
            "authority_rules_changed": False,
            "schema_changed": False,
            "tcgplayer_used_as_authority": False,
            "database_writes": 0,
        },
        "baseline": baseline_metrics,
        "challenger": challenger_metrics,
        "delta": {
            "candidate_pool_inclusion": challenger_metrics["correct_family_entered_candidate_pool"] - baseline_metrics["correct_family_entered_candidate_pool"],
            "correct_top_family": challenger_metrics["correct_top_family"] - baseline_metrics["correct_top_family"],
            "average_latency_ms": round(challenger_metrics["latency_ms"]["average"] - baseline_metrics["latency_ms"]["average"], 2),
        },
        "original_five": {
            "baseline_correct_top_family": sum(row["top_correct"] for row in original_five),
            "challenger_correct_top_family": sum(row["challenger_top_correct"] for row in original_five),
            "false_auto_matches": sum(row["challenger_false_auto"] for row in original_five),
            "rows": original_five,
        },
        "gates": {
            "false_auto_matches_zero": safety_gate,
            "candidate_pool_inclusion_above_9_of_50": challenger_metrics["correct_family_entered_candidate_pool"] > 9,
            "top_family_accuracy_above_18_percent": challenger_metrics["correct_top_family_rate"] > 0.18,
            "measurement_success": safety_gate and improvement_gate,
        },
        "per_scan_count": len(compared),
    }

    json_path = args.output_dir / "SAM_CHALLENGER_V1_SHADOW_COMPARISON.json"
    csv_path = args.output_dir / "SAM_CHALLENGER_V1_SHADOW_PER_SCAN.csv"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(compared[0]))
        writer.writeheader()
        writer.writerows(compared)
    print(json.dumps({
        "status": "PASS" if report["gates"]["measurement_success"] else "FAIL",
        "json": str(json_path.resolve()),
        "csv": str(csv_path.resolve()),
        "baseline": baseline_metrics,
        "challenger": challenger_metrics,
        "gates": report["gates"],
    }, indent=2))
    return 0 if safety_gate else 2


if __name__ == "__main__":
    raise SystemExit(main())
