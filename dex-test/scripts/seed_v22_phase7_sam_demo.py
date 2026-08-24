#!/usr/bin/env python3
"""Create disposable v2.2 Phase 7 SAM recognition/operator-review QA data."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import uuid
from pathlib import Path

from PIL import Image, ImageDraw


def card_art(path: Path, number: str, *, color, accent, sample=False, poor=False) -> None:
    if poor:
        Image.new("RGB", (48, 48), "white").save(path)
        return
    image = Image.new("RGB", (500, 700), (242, 238, 220))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((18, 18, 482, 682), radius=24, outline=(20, 20, 20), width=12)
    draw.rectangle((42, 55, 458, 410), fill=color)
    draw.ellipse((125, 105, 375, 355), fill=accent, outline="white", width=12)
    draw.rectangle((55, 445, 445, 635), outline=accent, width=8)
    draw.text((65, 660), number, fill="black")
    if sample:
        draw.text((160, 300), "SAMPLE", fill="white", stroke_width=3, stroke_fill="black")
    image.save(path)


class FixtureProvider:
    name = "OPTCG_API"
    version = "phase7-disposable-fixture-v1"

    def __init__(self, rows):
        self.rows = rows

    def lookup(self, number):
        return self.rows.get(number)

    def health(self, *, probe=False):
        return {
            "provider": self.name, "provider_version": self.version,
            "configured": True, "available": False if probe else None,
            "live_probe_performed": probe, "structured_metadata_only": True,
            "physical_images_transmitted": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a disposable DEX Phase 7 SAM demo")
    parser.add_argument("--output", required=True, help="New, nonexistent disposable storage directory")
    args = parser.parse_args()
    target = Path(args.output).resolve()
    if target.exists():
        print(f"REFUSED: target already exists: {target}", file=sys.stderr)
        return 2
    target.mkdir(parents=True)
    references = target / "one-piece-references"
    references.mkdir()
    project = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project))
    os.environ.update({
        "DEX_DATA_DIR": str(target), "DEX_DB_PATH": str(target / "dex.db"),
        "DEX_IMAGE_DIR": str(target / "images"), "DEX_INBOUND_DIR": str(target / "inbound"),
        "DEX_SOURCE_DB_DIR": str(references), "DEX_ONE_PIECE_REFERENCE_DIR": str(references),
        "DEX_DOCUMENT_DIR": str(target / "source-documents"), "DEX_WATCH_INBOUND": "0",
        "DEX_SEED_DEMO": "0", "DEX_AUTO_PURGE": "0",
    })

    import app
    from dex_intake_bridge import confirm_intake_routing, intake_preview
    from dex_sam import index_reference_library, refresh_metadata, submit_recognition

    app.init_db()
    now = "2026-08-15T14:00:00+00:00"

    # Reference-only SAMPLE is deliberate. The physical scan omits it.
    card_art(references / "OP16-032.png", "OP16-032", color=(190, 35, 45), accent=(25, 75, 150), sample=True)
    card_art(references / "OP16-033.png", "OP16-033", color=(35, 140, 80), accent=(90, 40, 150))
    card_art(references / "OP16-033_p1.png", "OP16-033", color=(35, 140, 80), accent=(90, 40, 150))
    card_art(references / "OP16-034.png", "OP16-034", color=(175, 100, 25), accent=(40, 70, 150))
    card_art(references / "OP16-035.png", "OP16-035", color=(120, 45, 135), accent=(30, 130, 155))
    card_art(references / "OP16-036.png", "OP16-036", color=(25, 95, 170), accent=(190, 40, 80))

    metadata = {
        number: {
            "game": "One Piece", "card_number": number, "name": name,
            "set_code": "OP16", "set_name": "The Time of Battle", "rarity": rarity,
            "card_type": "Character", "color": color, "language": "English",
        }
        for number, name, rarity, color in (
            ("OP16-032", "Clear Match Fixture", "R", "Red"),
            ("OP16-033", "Ambiguous Parallel Fixture", "SR", "Green"),
            ("OP16-034", "Intentional Wrong Suggestion", "UC", "Yellow"),
            ("OP16-035", "Operator Correct Answer", "R", "Purple"),
            # OP16-036 intentionally absent to demonstrate provider/cache fallback.
        )
    }
    provider = FixtureProvider(metadata)
    with app.connect() as db:
        refresh_metadata(db, provider, metadata, request_id="P7-DEMO-METADATA")
        index_reference_library(db, references, request_id="P7-DEMO-INDEX")

        acquisition_id = db.execute(
            """INSERT INTO acquisitions
               (acquisition_uuid,acquisition_code,creation_request_id,state,revision,source_scope,
                merchant_name,purchased_on,order_reference,final_usd_paid_cents,
                financial_facts_confirmed,reconciliation_confirmed,confirmed_at,created_at,updated_at,payment_method)
               VALUES (?,?,?,'READY_FOR_INTAKE',1,'DOMESTIC','Phase 7 Disposable QA','2026-08-15',
                       'SAM-QA-ORDER',2500,1,1,?,?,?,'CREDIT_DEBIT_CARD')""",
            (f"ACQ-{uuid.uuid4()}", "ACQ-P7-SAM-QUEUE", "P7-DEMO-ACQ", now, now, now),
        ).lastrowid
        line_id = db.execute(
            """INSERT INTO acquisition_lines
               (line_uuid,acquisition_id,line_sequence,product_class,game,product_name,set_code,
                quantity,quantity_certainty,singles_cost_mode,intended_action,assigned_landed_cost_cents,
                allocation_method,allocation_status,created_at,updated_at)
               VALUES (?, ?,1,'SINGLE_CARDS','One Piece','Phase 7 SAM Review Lot','OP16',5,'KNOWN',
                       'LUMP_SUM','DECIDE_LATER',2500,'MANUAL','CONFIRMED',?,?)""",
            (f"LINE-{uuid.uuid4()}", acquisition_id, now, now),
        ).lastrowid
        preview_payload = {"expected_revision": 1, "lines": [{"line_id": line_id, "scan_identify_quantity": 5}]}
        preview = intake_preview(db, acquisition_id, preview_payload)
        confirm_intake_routing(db, acquisition_id, {
            **preview_payload, "request_id": "P7-DEMO-ROUTE",
            "preview_token": preview["preview_token"], "confirm_routing": True,
        })
        batch = db.execute("SELECT * FROM batches WHERE acquisition_line_id=?", (line_id,)).fetchone()

        scans = target / "fixture-scans"
        scans.mkdir()
        card_art(scans / "clear.png", "OP16-032", color=(190, 35, 45), accent=(25, 75, 150))
        card_art(scans / "ambiguous.png", "OP16-033", color=(35, 140, 80), accent=(90, 40, 150))
        shutil.copyfile(references / "OP16-034.png", scans / "wrong-top.png")
        card_art(scans / "unknown.png", "", color=(0, 0, 0), accent=(0, 0, 0), poor=True)
        shutil.copyfile(references / "OP16-036.png", scans / "provider-fallback.png")

        scenarios = (
            ("P7-HIGH", "OP16-032", scans / "clear.png"),
            ("P7-AMBIG", "OP16-033", scans / "ambiguous.png"),
            ("P7-CORRECT", "", scans / "wrong-top.png"),
            ("P7-UNKNOWN", "", scans / "unknown.png"),
            ("P7-FALLBACK", "OP16-036", scans / "provider-fallback.png"),
        )
        for suffix, number, source in scenarios:
            sku = f"OP-SAM-{suffix}"
            destination = target / "images" / sku / "front.png"
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            card_id = db.execute(
                """INSERT INTO cards
                   (sku,batch_id,created_at,updated_at,card_number,name,set_name,status,front_image,source_hash,rip_session_id)
                   VALUES (?,?,?,?,?,'Needs identification','The Time of Battle','REVIEW',?,?,?)""",
                (sku, batch["id"], now, now, number, str(destination.relative_to(target)).replace("\\", "/"), uuid.uuid4().hex,
                 db.execute("SELECT id FROM rip_sessions WHERE batch_id=?", (batch["id"],)).fetchone()[0]),
            ).lastrowid
            submit_recognition(db, card_id, data_dir=target, request_id=f"P7-DEMO-{suffix}")

    print(f"PASS: disposable Phase 7 storage created at {target}")
    print("Acquisition: ACQ-P7-SAM-QUEUE")
    print("AUTO_MATCHED: OP-SAM-P7-HIGH (SAMPLE-tolerant) and OP-SAM-P7-FALLBACK (local-only metadata fallback)")
    print("NEEDS_REVIEW: OP-SAM-P7-AMBIG and OP-SAM-P7-CORRECT")
    print("UNIDENTIFIED: OP-SAM-P7-UNKNOWN")
    print("Manual correction: review OP-SAM-P7-CORRECT, Find Match OP16-035, confirm correction")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
