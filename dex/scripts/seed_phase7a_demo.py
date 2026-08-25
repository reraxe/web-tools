#!/usr/bin/env python3
"""Create a disposable Phase 7A operator-QA database; never overwrites a target."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a disposable Phase 7A DEX demo")
    parser.add_argument("--output", required=True, help="New empty directory for disposable storage")
    args = parser.parse_args()
    target = Path(args.output).resolve()
    if target.exists():
        print(f"REFUSED: target already exists: {target}", file=sys.stderr)
        return 2
    target.mkdir(parents=True)

    project = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project))
    os.environ.update({
        "DEX_DATA_DIR": str(target),
        "DEX_DB_PATH": str(target / "dex.db"),
        "DEX_IMAGE_DIR": str(target / "images"),
        "DEX_INBOUND_DIR": str(target / "inbound"),
        "DEX_SOURCE_DB_DIR": str(target / "source-database"),
        "DEX_WATCH_INBOUND": "0",
        "DEX_SEED_DEMO": "1",
    })

    import app

    app.init_db()
    app.seed_demo()
    with app.connect() as db:
        batch = db.execute(
            "SELECT * FROM batches WHERE product_code='OP16-BOX'"
        ).fetchone()
        rip = app.create_rip_session(db, int(batch["id"]), {"units_opened": 1})
        db.execute(
            "UPDATE cards SET rip_session_id=? WHERE batch_id=?",
            (rip["id"], batch["id"]),
        )
        app.finalize_rip(db, int(rip["id"]), {
            "allocation_method": "EQUAL",
            "bulk_mode": "NONE",
            "confirm_all_cards_accounted": True,
            "confirm_finalization": True,
            "request_id": "PHASE7A-DEMO-FINALIZATION",
            "notes": "Disposable Phase 7A operator-QA baseline.",
        })
        cards = db.execute(
            "SELECT sku FROM cards WHERE batch_id=? ORDER BY id", (batch["id"],)
        ).fetchall()
        print(f"PASS: disposable Phase 7A storage created at {target}")
        print(f"Batch: {batch['batch_code']} / {batch['product_name']}")
        print(f"Rip: {rip['rip_code']} (1 opened unit, {len(cards)} finalized cards)")
        print("Cards: " + ", ".join(row["sku"] for row in cards))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
