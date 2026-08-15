#!/usr/bin/env python3
"""Create disposable v2.2 Phase 3 catalog QA storage; never overwrites a target."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a disposable DEX Phase 3 UPC demo")
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
        "DEX_SEED_DEMO": "0",
    })

    import app
    from dex_catalog import add_identifier_mapping, create_catalog_product

    app.init_db()
    with app.connect() as db:
        op16 = create_catalog_product(db, {
            "request_id": "PHASE3-DEMO-PRODUCT-OP16",
            "game": "One Piece Card Game",
            "display_name": "OP16 Booster Box",
            "set_code": "OP16",
            "set_name": "ONE PIECE CARD GAME OP16",
            "product_class": "SEALED_PRODUCT",
            "product_subtype": "BOOSTER_BOX",
            "manufacturer_product_code": "OP-16 BOX",
            "provenance": "SEED_FIXTURE",
            "verified": True,
        })
        add_identifier_mapping(db, op16["id"], {
            "request_id": "PHASE3-DEMO-MAPPING-OP16",
            "raw_identifier": "012345678905",
            "identifier_type": "UPC_A",
            "provenance": "SEED_FIXTURE",
            "verified": True,
        })

        st27 = create_catalog_product(db, {
            "request_id": "PHASE3-DEMO-PRODUCT-ST27",
            "game": "One Piece Card Game",
            "display_name": "ST27 Starter Deck",
            "set_code": "ST27",
            "set_name": "Starter Deck ST27",
            "product_class": "SEALED_PRODUCT",
            "product_subtype": "STARTER_DECK",
            "manufacturer_product_code": "ST-27",
            "provenance": "SEED_FIXTURE",
            "verified": True,
        })
        add_identifier_mapping(db, st27["id"], {
            "request_id": "PHASE3-DEMO-MAPPING-ST27",
            "raw_identifier": "4006381333931",
            "identifier_type": "EAN_13",
            "provenance": "SEED_FIXTURE",
            "verified": True,
        })
        db.commit()

    print(f"PASS: disposable Phase 3 storage created at {target}")
    print("Known UPC-A: 012345678905 -> OP16 Booster Box")
    print("Known EAN-13: 4006381333931 -> ST27 Starter Deck")
    print("Unknown valid UPC-A: 036000291452")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
