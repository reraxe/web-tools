#!/usr/bin/env python3
"""Read-only Day Zero verification for a migrated disposable or LIVE database."""

from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path


EXPECTED_MIGRATIONS = tuple(f"{number:04d}" for number in range(1, 20))
COUNT_GROUPS = {
    "inventory": ("cards", "sealed_units"),
    "acquisitions": ("acquisitions",),
    "batches": ("batches",),
    "receipts_documents": (
        "acquisition_documents", "receipt_extraction_jobs", "receipt_candidate_facts",
        "receipt_lines", "receipt_semantic_lines",
    ),
    "sales": ("sale_orders", "sale_items", "sealed_sale_items"),
    "sam_operational_audit": (
        "sam_recognition_jobs", "sam_recognition_candidates", "sam_recognition_decisions",
        "sam_audited_recognition_results", "sam_audited_operator_decisions",
        "sam_audited_verified_truth", "sam_audited_recognition_deltas",
    ),
    "wolff_operational_history": (
        "rip_economic_events", "rip_basis_events", "economic_events",
        "post_sale_events", "jarvis_sale_input_evidence",
    ),
}


def verify_database(path: Path) -> dict:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = [list(row) for row in connection.execute("PRAGMA foreign_key_check")]
        migration_rows = connection.execute(
            "SELECT migration_id FROM schema_migrations ORDER BY migration_id"
        ).fetchall()
        migrations = [row[0] for row in migration_rows]
        counts = {}
        missing_tables = []
        for group, names in COUNT_GROUPS.items():
            group_counts = {}
            for name in names:
                if name not in tables:
                    missing_tables.append(name)
                    continue
                group_counts[name] = connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            counts[group] = group_counts
    prefixes = [migration.split("_", 1)[0] for migration in migrations]
    all_zero = all(value == 0 for group in counts.values() for value in group.values())
    ready = (
        integrity == "ok"
        and not foreign_keys
        and not missing_tables
        and tuple(prefixes) == EXPECTED_MIGRATIONS
        and all_zero
    )
    return {
        "status": "PASS" if ready else "FAIL",
        "database": str(path.resolve()),
        "integrity": integrity,
        "foreign_key_violations": foreign_keys,
        "migrations": migrations,
        "migration_prefixes": prefixes,
        "missing_tables": missing_tables,
        "counts": counts,
        "all_operational_counts_zero": all_zero,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error(f"database not found: {args.database}")
    report = verify_database(args.database)
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else report["status"])
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
