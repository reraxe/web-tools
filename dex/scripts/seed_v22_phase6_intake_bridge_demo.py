#!/usr/bin/env python3
"""Create disposable v2.2 Phase 6 Downstream Intake Bridge QA storage."""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a disposable DEX Phase 6 intake-routing demo")
    parser.add_argument("--output", required=True, help="New, nonexistent directory for disposable storage")
    args = parser.parse_args()
    target = Path(args.output).resolve()
    if target.exists():
        print(f"REFUSED: target already exists: {target}", file=sys.stderr)
        return 2
    target.mkdir(parents=True)
    project = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project))
    os.environ.update({
        "DEX_DATA_DIR": str(target), "DEX_DB_PATH": str(target / "dex.db"),
        "DEX_IMAGE_DIR": str(target / "images"), "DEX_INBOUND_DIR": str(target / "inbound"),
        "DEX_SOURCE_DB_DIR": str(target / "source-database"), "DEX_DOCUMENT_DIR": str(target / "source-documents"),
        "DEX_WATCH_INBOUND": "0", "DEX_SEED_DEMO": "0", "DEX_AUTO_PURGE": "0",
    })
    import app
    from dex_intake_bridge import confirm_intake_routing, intake_preview

    app.init_db()
    now = "2026-08-15T12:00:00+00:00"

    def create(db, code: str, lines: list[dict]) -> tuple[int, list[int]]:
        total = sum(line["cost"] for line in lines)
        cursor = db.execute(
            """INSERT INTO acquisitions
               (acquisition_uuid,acquisition_code,creation_request_id,state,revision,source_scope,
                merchant_name,purchased_on,order_reference,final_usd_paid_cents,financial_facts_confirmed,
                reconciliation_confirmed,confirmed_at,created_at,updated_at,payment_method)
               VALUES (?,?,?,?,1,'DOMESTIC','Phase 6 Disposable QA','2026-08-15',?,?,1,1,?,?,?,'CREDIT_DEBIT_CARD')""",
            (f"ACQ-{uuid.uuid4()}", code, f"SEED-{code}", "READY_FOR_INTAKE", f"ORDER-{code}", total, now, now, now),
        )
        acquisition_id = int(cursor.lastrowid)
        line_ids = []
        for sequence, line in enumerate(lines, 1):
            line_cursor = db.execute(
                """INSERT INTO acquisition_lines
                   (line_uuid,acquisition_id,line_sequence,product_class,game,product_name,set_code,pack_type,
                    quantity,quantity_certainty,singles_cost_mode,intended_action,assigned_landed_cost_cents,
                    allocation_method,allocation_status,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,'KNOWN',?,'DECIDE_LATER',?,'MANUAL','CONFIRMED',?,?)""",
                (f"LINE-{uuid.uuid4()}", acquisition_id, sequence, line["class"], "One Piece", line["name"],
                 line.get("set", "OP16"), line.get("pack_type", ""), line["quantity"], line.get("singles_mode", ""),
                 line["cost"], now, now),
            )
            line_ids.append(int(line_cursor.lastrowid))
        return acquisition_id, line_ids

    def route(db, acquisition_id: int, request_id: str, lines: list[dict]) -> None:
        revision = db.execute("SELECT revision FROM acquisitions WHERE id=?", (acquisition_id,)).fetchone()[0]
        payload = {"expected_revision": int(revision), "lines": lines}
        preview = intake_preview(db, acquisition_id, payload)
        confirm_intake_routing(db, acquisition_id, {
            **payload, "request_id": request_id, "preview_token": preview["preview_token"], "confirm_routing": True,
        })

    with app.connect() as db:
        partial, partial_lines = create(db, "ACQ-P6-A-SPLIT", [
            {"class": "SEALED_PRODUCT", "name": "OP16 Booster Box", "quantity": 3, "cost": 33000},
        ])
        route(db, partial, "P6-A-ROUTE", [{"line_id": partial_lines[0], "rip_open_quantity": 1, "keep_sealed_quantity": 2}])

        mixed, mixed_lines = create(db, "ACQ-P6-B-PARTIAL", [
            {"class": "SEALED_PRODUCT", "name": "OP16 Double Pack", "quantity": 4, "cost": 4800},
            {"class": "PACK_PRODUCT", "name": "OP16 Sleeved Pack", "pack_type": "Sleeved Pack", "quantity": 2, "cost": 800},
        ])
        route(db, mixed, "P6-B-ROUTE", [
            {"line_id": mixed_lines[0], "keep_sealed_quantity": 2},
            {"line_id": mixed_lines[1], "rip_open_quantity": 1, "keep_sealed_quantity": 1},
        ])

        singles, singles_lines = create(db, "ACQ-P6-C-SINGLES", [
            {"class": "SINGLE_CARDS", "name": "OP16 Purchased Singles Lot", "quantity": 6, "cost": 2100, "singles_mode": "LUMP_SUM"},
        ])
        route(db, singles, "P6-C-ROUTE", [{"line_id": singles_lines[0], "scan_identify_quantity": 6}])

        retry, retry_lines = create(db, "ACQ-P6-D-RETRY", [
            {"class": "PACK_PRODUCT", "name": "OP16 Loose Pack", "pack_type": "Loose Pack", "quantity": 2, "cost": 800},
        ])
        revision = db.execute("SELECT revision FROM acquisitions WHERE id=?", (retry,)).fetchone()[0]
        retry_payload = {"expected_revision": int(revision), "lines": [{"line_id": retry_lines[0], "keep_sealed_quantity": 2}]}
        retry_preview = intake_preview(db, retry, retry_payload)
        request = {**retry_payload, "request_id": "P6-D-RETRY", "preview_token": retry_preview["preview_token"], "confirm_routing": True}
        confirm_intake_routing(db, retry, request)
        confirm_intake_routing(db, retry, request)

    print(f"PASS: disposable Phase 6 storage created at {target}")
    print("Scenario A — 3 boxes / $330 / open 1 + keep 2: ACQ-P6-A-SPLIT")
    print("Scenario B — partial sealed route plus completed pack line: ACQ-P6-B-PARTIAL")
    print("Scenario C — acquired singles routed to scanning: ACQ-P6-C-SINGLES")
    print("Scenario D — idempotent retry already replayed: ACQ-P6-D-RETRY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
