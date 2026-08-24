#!/usr/bin/env python3
"""Dex TCG inventory MVP.

Dependency-light HTTP API and static-file server backed by SQLite. The Docker
image adds QR generation support, while the core application stays portable.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import mimetypes
import os
import re
import shutil
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from urllib.parse import parse_qs, quote, unquote, urlparse

from dex_acquisition import EDITABLE_FIELDS, acquisition_payload, normalize_acquisition_input
from dex_batch_economics import (
    acquisition_group_economics_payload,
    batch_economics_export_rows,
    batch_economics_payload,
)
from dex_catalog import (
    add_identifier_mapping,
    apply_catalog_product_to_line,
    catalog_contract,
    catalog_product_payload,
    correct_identifier_mapping,
    create_catalog_product,
    identifier_history,
    identify_unknown_product,
    lookup_identifier,
    scan_apply_product,
    search_catalog_products,
)
from dex_economics import CALCULATION_VERSION
from dex_documents import (
    DocumentIntegrityError,
    get_document as source_document_payload,
    get_document_store,
    list_documents as list_source_documents,
    provider_contract as document_provider_contract,
    read_document as read_source_document,
    retry_document as retry_source_document,
    tombstone_document as tombstone_source_document,
    upload_document as upload_source_document,
    verify_document as verify_source_document,
)
from dex_corrections import (
    batch_corrections_payload,
    card_has_economic_history,
    correct_acquisition_cost,
    dispose_card,
    dispose_sealed_unit,
    event_payload as economic_event_payload,
    reverse_event,
    transfer_basis,
)
from dex_migrations import apply_migrations
from dex_post_sale import (
    create_chargeback,
    create_fee_credit,
    create_postage_refund,
    create_refund,
    create_return,
    create_sale_correction,
    order_payload as post_sale_order_payload,
    reverse_event as reverse_post_sale_event,
)
from dex_portfolio_economics import (
    portfolio_economics_export_rows,
    portfolio_economics_payload,
)
from dex_legacy_economics import estimate_legacy_batch, open_readonly_database
from dex_jarvis_economics import (
    aggregate_economics_payload as jarvis_aggregate_economics_payload,
    capture_sale_input_evidence,
    card_economics_payload as jarvis_card_economics_payload,
    sale_economics_payload as jarvis_sale_economics_payload,
)
from dex_inbound import (
    acquisition_payload as inbound_acquisition_payload,
    add_acquisition_line,
    autosave_acquisition,
    autosave_acquisition_line,
    cancel_acquisition_line,
    cancel_acquisition,
    confirm_acquisition,
    confirm_line_allocation,
    create_acquisition,
    foundation_contract as inbound_foundation_contract,
    list_acquisitions,
    list_recycled_acquisitions,
    mark_reconciliation_required,
    recycle_draft_acquisition,
    restore_recycled_acquisition,
)
from dex_intake_bridge import (
    confirm_intake_routing,
    intake_preview,
    intake_status,
)
from dex_rip import (
    activate_rip,
    active_rip_for_batch,
    allocation_preview,
    batch_rips_payload,
    correct_rip,
    create_rip_session,
    deactivate_rip,
    finalize_rip,
    rip_session_payload,
)
from dex_receipts import (
    apply_proposed_facts as apply_receipt_proposed_facts,
    candidate_disposition as receipt_candidate_disposition,
    classify_receipt_line,
    extraction_provider_contract,
    extraction_job_payload as receipt_extraction_job_payload,
    generate_allocation_proposal as generate_receipt_allocation_proposal,
    get_receipt_extractor,
    match_disposition as receipt_match_disposition,
    queue_extraction as queue_receipt_extraction,
    reconcile_semantic_merchandise_line,
    receipt_intelligence_payload,
    retry_extraction as retry_receipt_extraction,
    select_manual_fallback as select_receipt_manual_fallback,
)
from dex_receipt_semantics import decide_semantic_line, semantic_review_payload
from dex_sealed import (
    acquisition_has_used_units,
    adjust_sealed_unit,
    batch_sealed_payload,
    create_sealed_sale,
    sealed_inventory_payload,
    sealed_order_payload,
    sealed_sale_preview,
    synchronize_sealed_units,
    undo_sealed_sale,
    undo_specific_sealed_sale,
)
from dex_sam import (
    AUTO_MATCH_THRESHOLD as SAM_AUTO_MATCH_THRESHOLD,
    RULES_VERSION as SAM_RULES_VERSION,
    decide_recognition,
    default_provider as default_sam_metadata_provider,
    index_reference_library,
    metadata_provider_status,
    recognition_history,
    recognition_result,
    reference_index_status,
    reference_path as sam_reference_path,
    refresh_metadata as refresh_sam_metadata,
    review_queue as sam_review_queue,
    search_references as search_sam_references,
    submit_recognition_for_sku,
)
from dex_sam_challenger import (
    load_shadow_comparison as load_sam_challenger_comparison,
    shadow_recognition_for_job as sam_challenger_shadow_for_job,
)
from dex_sam_audited import (
    audited_status as sam_audited_status,
    catalog_search as search_sam_audited_catalog,
    get_result as sam_audited_result,
    list_intake_cards as sam_audited_intake_cards,
    recognize_card as recognize_sam_audited_card,
    record_operator_decision as decide_sam_audited_result,
    record_verified_truth as verify_sam_audited_result,
)
from dex_sam_identity import ensure_family, record_assertion, record_event


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DATA_DIR = Path(os.environ.get("DEX_DATA_DIR", ROOT / "data")).resolve()
DB_PATH = Path(os.environ.get("DEX_DB_PATH", DATA_DIR / "dex.db")).resolve()
IMAGE_DIR = Path(os.environ.get("DEX_IMAGE_DIR", DATA_DIR / "images")).resolve()
INBOUND_DIR = Path(os.environ.get("DEX_INBOUND_DIR", DATA_DIR / "inbound")).resolve()
SOURCE_DB_DIR = Path(os.environ.get("DEX_SOURCE_DB_DIR", DATA_DIR / "source-database")).resolve()
ONE_PIECE_REFERENCE_DIR = Path(
    os.environ.get("DEX_ONE_PIECE_REFERENCE_DIR", SOURCE_DB_DIR)
).resolve()
SAM_CHALLENGER_REPORT_PATH = (
    Path(os.environ["DEX_SAM_CHALLENGER_REPORT_PATH"]).resolve()
    if os.environ.get("DEX_SAM_CHALLENGER_REPORT_PATH")
    else None
)
DOCUMENT_STORE = get_document_store(DATA_DIR)
RECEIPT_EXTRACTOR = get_receipt_extractor()
SAM_METADATA_PROVIDER = default_sam_metadata_provider()
HOST = os.environ.get("DEX_HOST", "0.0.0.0")
PORT = int(os.environ.get("DEX_PORT", "8080"))
MAX_BODY = 250 * 1024 * 1024
WATCH_INBOUND = os.environ.get("DEX_WATCH_INBOUND", "1") == "1"
SCAN_INTERVAL = int(os.environ.get("DEX_SCAN_INTERVAL", "5"))
APP_VERSION = "v2.4-live"
DEFAULT_TIMEZONE = os.environ.get("DEX_TIMEZONE", "America/New_York")
DEFAULT_TCG_CAPACITY = int(os.environ.get("DEX_TCG_CAPACITY", "500"))

GAME_PREFIXES = {"Pokemon": "PKM", "One Piece": "OP", "Riftbound": "RFB"}
ONE_PIECE_SET_NAMES = {
    "OP01": "Romance Dawn",
    "OP02": "Paramount War",
    "OP03": "Pillars of Strength",
    "OP04": "Kingdoms of Intrigue",
    "OP05": "Awakening of the New Era",
    "OP06": "Wings of the Captain",
    "OP07": "500 Years in the Future",
    "OP08": "Two Legends",
    "OP09": "Emperors in the New World",
    "OP10": "Royal Blood",
    "OP11": "A Fist of Divine Speed",
    "OP12": "Legacy of the Master",
    "OP13": "Carrying on His Will",
    "OP14": "The Azure Sea's Seven",
    "OP15": "Adventure on Kami's Island",
    "OP16": "The Time of Battle",
    "EB01": "Memorial Collection",
    "EB02": "Anime 25th Collection",
    "EB03": "One Piece Heroines Edition",
    "PRB01": "Premium Booster -The Best-",
    "PRB02": "ONE PIECE CARD THE BEST Vol. 2",
}
CARD_NUMBER_RE = re.compile(r"\b((?:OP|EB|ST|PRB|P)\d{1,3})[-_ ]?(\d{3}[A-Z]?)\b", re.I)
SAM_MATCH_THRESHOLD = 0.84
DB_LOCK = threading.Lock()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def business_timezone(name: str | None = None) -> ZoneInfo:
    try:
        return ZoneInfo(name or DEFAULT_TIMEZONE)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def setting(db: sqlite3.Connection, key: str, default: str) -> str:
    row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def business_today(db: sqlite3.Connection | None = None) -> date:
    name = setting(db, "timezone", DEFAULT_TIMEZONE) if db else DEFAULT_TIMEZONE
    return datetime.now(business_timezone(name)).date()


def log_action(db: sqlite3.Connection, action_type: str, description: str, payload: dict) -> None:
    db.execute(
        "INSERT INTO activity_log (created_at, action_type, description, payload) VALUES (?, ?, ?, ?)",
        (utcnow(), action_type, description, json.dumps(payload, separators=(",", ":"))),
    )


@contextmanager
def connect():
    db = sqlite3.connect(DB_PATH, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    INBOUND_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DB_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_code TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL DEFAULT 'OPEN',
                game TEXT NOT NULL,
                set_code TEXT NOT NULL,
                set_name TEXT NOT NULL DEFAULT '',
                color TEXT NOT NULL DEFAULT '',
                finish_group TEXT NOT NULL DEFAULT 'Non-Foil',
                default_condition TEXT NOT NULL DEFAULT 'Near Mint',
                acquisition_type TEXT NOT NULL,
                total_cost REAL NOT NULL DEFAULT 0,
                location TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                scan_order TEXT NOT NULL DEFAULT 'FRONT_FIRST',
                scan_mode TEXT NOT NULL DEFAULT 'FRONT_BACK',
                recycled_at TEXT,
                recycle_reason TEXT NOT NULL DEFAULT '',
                purge_after TEXT
            );

            CREATE TABLE IF NOT EXISTS cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL UNIQUE,
                batch_id INTEGER NOT NULL REFERENCES batches(id),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                card_number TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL DEFAULT 'Needs identification',
                set_name TEXT NOT NULL DEFAULT '',
                rarity TEXT NOT NULL DEFAULT '',
                color TEXT NOT NULL DEFAULT '',
                variant TEXT NOT NULL DEFAULT 'Standard',
                condition TEXT NOT NULL DEFAULT 'Near Mint',
                status TEXT NOT NULL DEFAULT 'REVIEW',
                location TEXT NOT NULL DEFAULT '',
                front_image TEXT,
                back_image TEXT,
                source_hash TEXT,
                label_printed INTEGER NOT NULL DEFAULT 0,
                market_low REAL,
                market_average REAL,
                market_high REAL,
                market_updated_at TEXT,
                listing_platform TEXT,
                listing_price REAL,
                listing_reference TEXT,
                source_card_id INTEGER REFERENCES source_cards(id),
                match_confidence REAL,
                match_source TEXT NOT NULL DEFAULT 'Manual',
                match_reviewed INTEGER NOT NULL DEFAULT 0,
                matched_at TEXT,
                sam_recognition_state TEXT,
                sam_recognition_job_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS source_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game TEXT NOT NULL DEFAULT 'One Piece',
                card_number TEXT NOT NULL,
                set_code TEXT NOT NULL,
                set_name TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL DEFAULT '',
                rarity TEXT NOT NULL DEFAULT '',
                color TEXT NOT NULL DEFAULT '',
                card_type TEXT NOT NULL DEFAULT '',
                full_image TEXT,
                small_image TEXT,
                image_hash TEXT,
                updated_at TEXT NOT NULL,
                UNIQUE(game, card_number)
            );

            CREATE TABLE IF NOT EXISTS sale_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                order_number TEXT NOT NULL DEFAULT '',
                sold_at TEXT NOT NULL,
                subtotal REAL NOT NULL DEFAULT 0,
                shipping_collected REAL NOT NULL DEFAULT 0,
                platform_fees REAL NOT NULL DEFAULT 0,
                postage_cost REAL NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS sale_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL REFERENCES sale_orders(id),
                card_id INTEGER NOT NULL UNIQUE REFERENCES cards(id),
                sale_price REAL NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS processed_scans (
                fingerprint TEXT PRIMARY KEY,
                batch_id INTEGER NOT NULL REFERENCES batches(id),
                processed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                action_type TEXT NOT NULL,
                description TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}',
                undone_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_cards_batch ON cards(batch_id);
            CREATE INDEX IF NOT EXISTS idx_cards_status ON cards(status);
            CREATE INDEX IF NOT EXISTS idx_cards_identity
                ON cards(card_number, variant, condition);
            CREATE INDEX IF NOT EXISTS idx_source_cards_identity ON source_cards(game, card_number);
            CREATE INDEX IF NOT EXISTS idx_source_cards_set ON source_cards(game, set_code);
            CREATE INDEX IF NOT EXISTS idx_sales_date ON sale_orders(sold_at);
            CREATE INDEX IF NOT EXISTS idx_activity_created ON activity_log(created_at);
            """
        )
        db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('timezone', ?)", (DEFAULT_TIMEZONE,))
        db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('tcg_capacity', ?)", (str(DEFAULT_TCG_CAPACITY),))
        db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('recycle_retention_days', '180')")
        db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('recycle_auto_purge', '0')")
        db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('sam_source_path', ?)", (str(SOURCE_DB_DIR),))
        batch_columns = {row["name"] for row in db.execute("PRAGMA table_info(batches)")}
        if "scan_order" not in batch_columns:
            db.execute("ALTER TABLE batches ADD COLUMN scan_order TEXT NOT NULL DEFAULT 'FRONT_FIRST'")
        if "scan_mode" not in batch_columns:
            db.execute("ALTER TABLE batches ADD COLUMN scan_mode TEXT NOT NULL DEFAULT 'FRONT_BACK'")
        for name, declaration in (
            ("recycled_at", "TEXT"),
            ("recycle_reason", "TEXT NOT NULL DEFAULT ''"),
            ("purge_after", "TEXT"),
        ):
            if name not in batch_columns:
                db.execute(f"ALTER TABLE batches ADD COLUMN {name} {declaration}")
        card_columns = {row["name"] for row in db.execute("PRAGMA table_info(cards)")}
        for name, declaration in (
            ("recycled_at", "TEXT"),
            ("recycle_reason", "TEXT NOT NULL DEFAULT ''"),
            ("purge_after", "TEXT"),
            ("pre_recycle_status", "TEXT"),
            ("source_card_id", "INTEGER REFERENCES source_cards(id)"),
            ("match_confidence", "REAL"),
            ("match_source", "TEXT NOT NULL DEFAULT 'Manual'"),
            ("match_reviewed", "INTEGER NOT NULL DEFAULT 0"),
            ("matched_at", "TEXT"),
            ("sam_recognition_state", "TEXT"),
            ("sam_recognition_job_id", "INTEGER"),
        ):
            if name not in card_columns:
                db.execute(f"ALTER TABLE cards ADD COLUMN {name} {declaration}")
        db.execute("CREATE INDEX IF NOT EXISTS idx_cards_source ON cards(source_card_id)")
        apply_migrations(db)


def as_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def clean_text(value: object, limit: int = 180) -> str:
    return str(value or "").strip()[:limit]


def money(value: object) -> float:
    try:
        return round(max(0.0, float(value or 0)), 2)
    except (TypeError, ValueError):
        return 0.0


def normalize_card_number(value: object) -> str:
    text = str(value or "").upper().replace("_", "-")
    match = CARD_NUMBER_RE.search(text)
    if not match:
        return ""
    prefix = match.group(1).upper()
    number = match.group(2).upper()
    return f"{prefix}-{number}"


def source_relative_path(path: Path) -> str:
    return str(path.resolve().relative_to(SOURCE_DB_DIR.resolve())).replace("\\", "/")


def source_media_url(path: str | None) -> str:
    return f"/source-media/{quote(path)}" if path else ""


def image_bit_hash(path: Path) -> str:
    try:
        from PIL import Image, ImageOps  # type: ignore

        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image).convert("L")
            image = ImageOps.autocontrast(image)
            average_image = image.resize((16, 16))
            pixels = list(average_image.tobytes())
            average = sum(pixels) / max(1, len(pixels))
            bits = ["1" if pixel >= average else "0" for pixel in pixels]

            difference_image = image.resize((17, 16))
            diff = list(difference_image.tobytes())
            for y in range(16):
                row = y * 17
                for x in range(16):
                    bits.append("1" if diff[row + x] > diff[row + x + 1] else "0")
            return f"{int(''.join(bits), 2):0{len(bits) // 4}x}"
    except Exception:
        return ""


def image_hash_similarity(left: str | None, right: str | None) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    try:
        distance = (int(left, 16) ^ int(right, 16)).bit_count()
    except ValueError:
        return 0.0
    return round(1 - (distance / (len(left) * 4)), 4)


def source_metadata_rows() -> dict[str, dict]:
    aliases = {
        "card_number": ("card_number", "card number", "number", "code", "id", "product id"),
        "name": ("name", "card name", "product name"),
        "set_code": ("set_code", "set code", "set", "set id"),
        "set_name": ("set_name", "set name", "set title"),
        "rarity": ("rarity",),
        "color": ("color", "colour"),
        "card_type": ("card_type", "type", "card type"),
    }
    rows: dict[str, dict] = {}
    for csv_path in SOURCE_DB_DIR.rglob("*.csv"):
        try:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                if not reader.fieldnames:
                    continue
                normalized = {field.lower().strip(): field for field in reader.fieldnames}
                for raw in reader:
                    row: dict[str, str] = {}
                    for target, names in aliases.items():
                        for name in names:
                            source = normalized.get(name)
                            if source and raw.get(source):
                                row[target] = clean_text(raw.get(source), 180)
                                break
                    card_number = normalize_card_number(row.get("card_number"))
                    if not card_number:
                        continue
                    set_code = normalize_card_number(card_number).split("-", 1)[0]
                    row["card_number"] = card_number
                    row["set_code"] = clean_text(row.get("set_code"), 40).upper() or set_code
                    row["set_name"] = row.get("set_name") or ONE_PIECE_SET_NAMES.get(row["set_code"], row["set_code"])
                    rows[card_number] = {**rows.get(card_number, {}), **row}
        except OSError:
            continue
    return rows


def scan_source_database(db: sqlite3.Connection) -> dict:
    metadata = source_metadata_rows()
    records: dict[str, dict] = {}
    image_suffixes = {".jpg", ".jpeg", ".png", ".webp"}
    for path in SOURCE_DB_DIR.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in image_suffixes:
            continue
        card_number = normalize_card_number(path.stem)
        if not card_number:
            continue
        set_code = card_number.split("-", 1)[0]
        record = records.setdefault(
            card_number,
            {
                "card_number": card_number,
                "set_code": set_code,
                "set_name": ONE_PIECE_SET_NAMES.get(set_code, set_code),
                "name": "",
                "rarity": "",
                "color": "",
                "card_type": "",
                "full_image": "",
                "small_image": "",
                "image_hash": "",
            },
        )
        rel = source_relative_path(path)
        if "small" in path.stem.lower():
            record["small_image"] = rel
        else:
            record["full_image"] = rel

    for card_number, row in metadata.items():
        set_code = row.get("set_code") or card_number.split("-", 1)[0]
        record = records.setdefault(
            card_number,
            {
                "card_number": card_number,
                "set_code": set_code,
                "set_name": ONE_PIECE_SET_NAMES.get(set_code, set_code),
                "name": "",
                "rarity": "",
                "color": "",
                "card_type": "",
                "full_image": "",
                "small_image": "",
                "image_hash": "",
            },
        )
        record.update({key: row.get(key, record.get(key, "")) for key in ("set_code", "set_name", "name", "rarity", "color", "card_type")})

    indexed = 0
    hashed = 0
    now = utcnow()
    for record in records.values():
        image_rel = record.get("full_image") or record.get("small_image")
        if image_rel:
            record["image_hash"] = image_bit_hash(SOURCE_DB_DIR / image_rel)
            hashed += 1 if record["image_hash"] else 0
        db.execute(
            """
            INSERT INTO source_cards (
                game, card_number, set_code, set_name, name, rarity, color, card_type,
                full_image, small_image, image_hash, updated_at
            ) VALUES ('One Piece', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(game, card_number) DO UPDATE SET
                set_code = excluded.set_code,
                set_name = excluded.set_name,
                name = excluded.name,
                rarity = excluded.rarity,
                color = excluded.color,
                card_type = excluded.card_type,
                full_image = excluded.full_image,
                small_image = excluded.small_image,
                image_hash = excluded.image_hash,
                updated_at = excluded.updated_at
            """,
            (
                record["card_number"], clean_text(record["set_code"], 40).upper(),
                clean_text(record["set_name"]), clean_text(record["name"]),
                clean_text(record["rarity"], 60), clean_text(record["color"], 40),
                clean_text(record["card_type"], 60), record.get("full_image") or None,
                record.get("small_image") or None, record.get("image_hash") or None, now,
            ),
        )
        indexed += 1
    db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('sam_source_path', ?)", (str(SOURCE_DB_DIR),))
    db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('sam_last_scan', ?)", (now,))
    return {"indexed": indexed, "hashed": hashed, "source_path": str(SOURCE_DB_DIR), "scanned_at": now}


def source_summary(db: sqlite3.Connection) -> dict:
    row = db.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN image_hash IS NOT NULL AND image_hash != '' THEN 1 ELSE 0 END) AS with_images,
               COUNT(DISTINCT set_code) AS sets
        FROM source_cards
        """
    ).fetchone()
    return {
        "source_path": setting(db, "sam_source_path", str(SOURCE_DB_DIR)),
        "last_scan": setting(db, "sam_last_scan", ""),
        "total": int(row["total"] or 0),
        "with_images": int(row["with_images"] or 0),
        "sets": int(row["sets"] or 0),
        "threshold": SAM_MATCH_THRESHOLD,
    }


def source_payload(row: sqlite3.Row | None) -> dict | None:
    if not row:
        return None
    item = dict(row)
    item["full_image_url"] = source_media_url(item.get("full_image"))
    item["small_image_url"] = source_media_url(item.get("small_image"))
    return item


def apply_source_match(db: sqlite3.Connection, card: sqlite3.Row, source: sqlite3.Row, confidence: float, match_source: str) -> dict:
    now = utcnow()
    current_name = card["name"] if card["name"] != "Needs identification" else ""
    name = source["name"] or current_name or "Needs identification"
    set_name = source["set_name"] or card["set_name"]
    color = source["color"] or card["color"]
    status = "IN_STOCK" if name != "Needs identification" and source["card_number"] else card["status"]
    family = ensure_family(
        db, game=source["game"], set_code=source["set_code"],
        card_number=source["card_number"], name=name,
        external_descriptors={"source": "LEGACY_SOURCE_CARD", "authority": False},
    )
    if not family:
        raise ValueError("Source match does not establish a card family")
    db.execute(
        """
        UPDATE cards SET
            card_number = ?, name = ?, set_name = ?, color = ?,
            status = ?, source_card_id = ?, match_confidence = ?, match_source = ?,
            match_reviewed = ?, matched_at = ?, sam_family_id = ?,
            sam_family_certainty = 'AUTHORITATIVE', updated_at = ?
        WHERE id = ?
        """,
        (
            source["card_number"], name, set_name, color, status,
            source["id"], confidence, match_source, 1 if confidence >= SAM_MATCH_THRESHOLD else 0,
            now, family["id"], now, card["id"],
        ),
    )
    request_id = f"LEGACY-SAM-FAMILY-{uuid.uuid4()}"
    record_event(
        db, request_id=request_id, card_id=int(card["id"]), event_type="FAMILY_AUTO_APPLIED",
        family_id=int(family["id"]), prior_family_id=card["sam_family_id"],
        prior_printing_id=card["sam_printing_id"], certainty="AUTHORITATIVE", actor="SYSTEM",
        reason_code="LEGACY_SAM_FAMILY_MATCH",
        evidence={"match_source": match_source, "confidence": confidence,
                  "printing_authority_granted": False, "rarity_unchanged": True,
                  "variant_unchanged": True},
    )
    record_assertion(
        db, card_id=int(card["id"]), field_scope="FAMILY", family_id=int(family["id"]),
        proposed_value=source["card_number"], certainty="AUTHORITATIVE", confidence=confidence,
        authority_granted=True, actor="SYSTEM", reason_code="LEGACY_SAM_FAMILY_MATCH",
        evidence={"match_source": match_source, "printing_authority_granted": False},
    )
    return dict(db.execute("SELECT * FROM cards WHERE id = ?", (card["id"],)).fetchone())


def sam_match_card(db: sqlite3.Connection, card: sqlite3.Row, batch: sqlite3.Row | None = None) -> dict:
    if card["recycled_at"]:
        return {"sku": card["sku"], "matched": False, "reason": "Card is in the Recycle Bin"}
    if card["sam_recognition_state"] in ("OPERATOR_CONFIRMED", "OPERATOR_CORRECTED"):
        return {
            "sku": card["sku"], "matched": True,
            "confidence": float(card["match_confidence"] or 1),
            "match_source": "Operator-confirmed identity preserved",
            "reason": "Legacy SAM cannot overwrite an operator-confirmed identity",
        }
    normalized = normalize_card_number(card["card_number"])
    source = None
    if normalized:
        source = db.execute(
            "SELECT * FROM source_cards WHERE game = 'One Piece' AND card_number = ?",
            (normalized,),
        ).fetchone()
        if source:
            card = db.execute("SELECT * FROM cards WHERE id = ?", (card["id"],)).fetchone()
            updated = apply_source_match(db, card, source, 1.0, "Card Number")
            return {"sku": card["sku"], "matched": True, "confidence": 1.0, "match_source": "Card Number", "card": updated, "source": source_payload(source)}

    front_image = card["front_image"]
    if not front_image:
        return {"sku": card["sku"], "matched": False, "reason": "No front scan available"}
    scan_hash = image_bit_hash(DATA_DIR / front_image)
    if not scan_hash:
        return {"sku": card["sku"], "matched": False, "reason": "Front scan could not be read"}

    params: list[object] = []
    where = "WHERE game = 'One Piece' AND image_hash IS NOT NULL AND image_hash != ''"
    set_code = (batch["set_code"] if batch else "").upper()
    if set_code:
        where += " AND set_code = ?"
        params.append(set_code)
    candidates = db.execute(f"SELECT * FROM source_cards {where}", params).fetchall()
    best: tuple[float, sqlite3.Row] | None = None
    for candidate in candidates:
        confidence = image_hash_similarity(scan_hash, candidate["image_hash"])
        if best is None or confidence > best[0]:
            best = (confidence, candidate)
    if not best or best[0] < SAM_MATCH_THRESHOLD:
        return {
            "sku": card["sku"],
            "matched": False,
            "confidence": best[0] if best else 0,
            "reason": "No confident SAM match",
            "candidate": source_payload(best[1]) if best else None,
        }
    updated = apply_source_match(db, card, best[1], best[0], "Image Fingerprint")
    return {"sku": card["sku"], "matched": True, "confidence": best[0], "match_source": "Image Fingerprint", "card": updated, "source": source_payload(best[1])}


def make_batch_code(db: sqlite3.Connection, game: str) -> str:
    prefix = GAME_PREFIXES.get(game, "TCG")
    stamp = business_today(db).strftime("%Y%m%d")
    stem = f"{prefix}-B{stamp}"
    count = db.execute(
        "SELECT COUNT(*) FROM batches WHERE batch_code LIKE ?", (stem + "-%",)
    ).fetchone()[0]
    return f"{stem}-{count + 1:02d}"


def next_sku(db: sqlite3.Connection, game: str) -> str:
    prefix = GAME_PREFIXES.get(game, "TCG")
    stamp = business_today(db).strftime("%Y%m%d")
    stem = f"{prefix}-B{stamp}-"
    rows = db.execute(
        "SELECT sku FROM cards WHERE sku LIKE ? ORDER BY sku DESC LIMIT 1",
        (stem + "%",),
    ).fetchone()
    sequence = int(rows["sku"].rsplit("-", 1)[-1]) + 1 if rows else 1
    return f"{stem}{sequence:03d}"


def decode_image(data_url: str) -> tuple[bytes, str]:
    match = re.match(r"^data:(image/[a-zA-Z0-9.+-]+);base64,(.+)$", data_url, re.S)
    if not match:
        raise ValueError("Invalid image data")
    raw = base64.b64decode(match.group(2), validate=True)
    if len(raw) > 15 * 1024 * 1024:
        raise ValueError("Image exceeds 15 MB")
    mime = match.group(1).lower()
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(mime)
    if not ext:
        raise ValueError("Only JPG, PNG, and WebP images are supported")
    return raw, ext


def save_image(sku: str, side: str, data_url: str | None) -> str | None:
    if not data_url:
        return None
    raw, ext = decode_image(data_url)
    card_dir = IMAGE_DIR / sku
    card_dir.mkdir(parents=True, exist_ok=True)
    path = card_dir / f"{side}{ext}"
    path.write_bytes(raw)
    return str(path.relative_to(DATA_DIR)).replace("\\", "/")


def copy_scan_image(sku: str, side: str, source: Path) -> str:
    ext = source.suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        raise ValueError(f"Unsupported scan format: {ext}")
    card_dir = IMAGE_DIR / sku
    card_dir.mkdir(parents=True, exist_ok=True)
    destination = card_dir / f"{side}{'.jpg' if ext == '.jpeg' else ext}"
    shutil.copy2(source, destination)
    return str(destination.relative_to(DATA_DIR)).replace("\\", "/")


def scan_fingerprint(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        stat = path.stat()
        digest.update(f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode())
    return digest.hexdigest()


def pair_scan_files(files: list[Path], scan_order: str = "FRONT_FIRST") -> list[tuple[Path, Path]]:
    """Pair explicit front/back names first, then pair remaining files in order."""
    explicit: dict[str, dict[str, Path]] = {}
    remaining: list[Path] = []
    side_pattern = re.compile(r"^(.*?)[_ -](front|back)$", re.I)
    for path in sorted(files, key=lambda item: item.name.lower()):
        match = side_pattern.match(path.stem)
        if match:
            explicit.setdefault(match.group(1).lower(), {})[match.group(2).lower()] = path
        else:
            remaining.append(path)
    pairs = [
        (sides["front"], sides["back"])
        for sides in explicit.values()
        if "front" in sides and "back" in sides
    ]
    sequential = list(zip(remaining[0::2], remaining[1::2]))
    if scan_order == "BACK_FIRST":
        sequential = [(back, front) for front, back in sequential]
    pairs.extend(sequential)
    return pairs


def unprocessed_scanner_file_count(db: sqlite3.Connection, batch: sqlite3.Row) -> int:
    folder = INBOUND_DIR / batch["batch_code"]
    if not folder.exists():
        return 0
    candidates = [
        path for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
    ]
    groups = (
        [(path,) for path in sorted(candidates, key=lambda item: item.name.lower())]
        if batch["scan_mode"] == "FRONT_ONLY"
        else [tuple(pair) for pair in pair_scan_files(candidates, batch["scan_order"])]
    )
    processed = 0
    for paths in groups:
        fingerprint = scan_fingerprint(list(paths))
        if db.execute("SELECT 1 FROM processed_scans WHERE fingerprint=?", (fingerprint,)).fetchone():
            processed += len(paths)
    return max(0, len(candidates) - processed)


def ingest_file_pair(batch_id: int, front_source: Path, back_source: Path) -> dict | None:
    fingerprint = scan_fingerprint([front_source, back_source])
    with DB_LOCK, connect() as db:
        if db.execute("SELECT 1 FROM processed_scans WHERE fingerprint = ?", (fingerprint,)).fetchone():
            return None
        batch = db.execute("SELECT * FROM batches WHERE id = ? AND status = 'OPEN'", (batch_id,)).fetchone()
        if not batch:
            return None
        rip_session_id = active_rip_for_batch(db, batch_id)
        sku = next_sku(db, batch["game"])
        front = copy_scan_image(sku, "front", front_source)
        back = copy_scan_image(sku, "back", back_source)
        now = utcnow()
        cursor = db.execute(
            """
            INSERT INTO cards (
                sku, batch_id, created_at, updated_at, name, set_name, color,
                variant, condition, status, location, front_image, back_image, source_hash,
                rip_session_id
            ) VALUES (?, ?, ?, ?, 'Needs identification', ?, ?, 'Standard', ?, 'REVIEW', ?, ?, ?, ?, ?)
            """,
            (
                sku, batch_id, now, now, batch["set_name"], batch["color"],
                batch["default_condition"], batch["location"], front, back, fingerprint,
                rip_session_id,
            ),
        )
        db.execute(
            "INSERT INTO processed_scans (fingerprint, batch_id, processed_at, rip_session_id) VALUES (?, ?, ?, ?)",
            (fingerprint, batch_id, now, rip_session_id),
        )
        return dict(db.execute("SELECT * FROM cards WHERE id = ?", (cursor.lastrowid,)).fetchone())


def ingest_front_file(batch_id: int, front_source: Path) -> dict | None:
    fingerprint = scan_fingerprint([front_source])
    with DB_LOCK, connect() as db:
        if db.execute("SELECT 1 FROM processed_scans WHERE fingerprint = ?", (fingerprint,)).fetchone():
            return None
        batch = db.execute("SELECT * FROM batches WHERE id = ? AND status = 'OPEN'", (batch_id,)).fetchone()
        if not batch:
            return None
        rip_session_id = active_rip_for_batch(db, batch_id)
        sku = next_sku(db, batch["game"])
        front = copy_scan_image(sku, "front", front_source)
        now = utcnow()
        cursor = db.execute(
            """
            INSERT INTO cards (
                sku, batch_id, created_at, updated_at, name, set_name, color,
                variant, condition, status, location, front_image, source_hash, rip_session_id
            ) VALUES (?, ?, ?, ?, 'Needs identification', ?, ?, 'Standard', ?, 'REVIEW', ?, ?, ?, ?)
            """,
            (
                sku, batch_id, now, now, batch["set_name"], batch["color"],
                batch["default_condition"], batch["location"], front, fingerprint, rip_session_id,
            ),
        )
        db.execute(
            "INSERT INTO processed_scans (fingerprint, batch_id, processed_at, rip_session_id) VALUES (?, ?, ?, ?)",
            (fingerprint, batch_id, now, rip_session_id),
        )
        return dict(db.execute("SELECT * FROM cards WHERE id = ?", (cursor.lastrowid,)).fetchone())


def watch_inbound() -> None:
    while True:
        try:
            with connect() as db:
                batches = db.execute("SELECT id, batch_code, scan_order, scan_mode FROM batches WHERE status = 'OPEN'").fetchall()
            for batch in batches:
                folder = INBOUND_DIR / batch["batch_code"]
                if not folder.exists():
                    continue
                now = time.time()
                candidates = [
                    path for path in folder.iterdir()
                    if path.is_file()
                    and path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
                    and now - path.stat().st_mtime > 2
                ]
                if batch["scan_mode"] == "FRONT_ONLY":
                    for front in sorted(candidates, key=lambda item: item.name.lower()):
                        ingest_front_file(batch["id"], front)
                    continue
                for front, back in pair_scan_files(candidates, batch["scan_order"]):
                    ingest_file_pair(batch["id"], front, back)
        except Exception as exc:
            print(f"Inbound watcher: {exc}")
        time.sleep(max(2, SCAN_INTERVAL))


def recycle_maintenance() -> None:
    while True:
        try:
            purged: list[str] = []
            with DB_LOCK, connect() as db:
                if setting(db, "recycle_auto_purge", "0") == "1":
                    rows = db.execute(
                        """SELECT c.id, c.sku FROM cards c
                           LEFT JOIN sale_items si ON si.card_id = c.id
                           WHERE c.recycled_at IS NOT NULL AND c.purge_after <= ? AND si.id IS NULL
                             AND NOT EXISTS (SELECT 1 FROM rip_basis_events rbe WHERE rbe.card_id=c.id)
                             AND NOT EXISTS (SELECT 1 FROM economic_tombstones et WHERE et.entity_type='CARD' AND et.entity_id=c.id)
                             AND NOT EXISTS (SELECT 1 FROM economic_event_entries eee WHERE eee.target_type='CARD' AND eee.target_id=c.id)""",
                        (utcnow(),),
                    ).fetchall()
                    for row in rows:
                        db.execute("DELETE FROM cards WHERE id = ?", (row["id"],))
                        purged.append(row["sku"])
            for sku in purged:
                card_dir = IMAGE_DIR / sku
                if card_dir.is_dir() and card_dir.resolve().is_relative_to(IMAGE_DIR.resolve()):
                    shutil.rmtree(card_dir)
        except Exception as exc:
            print(f"Recycle maintenance: {exc}")
        time.sleep(3600)


def create_card(db: sqlite3.Connection, batch: sqlite3.Row, payload: dict) -> dict:
    sku = next_sku(db, batch["game"])
    front = save_image(sku, "front", payload.get("front_image"))
    back = save_image(sku, "back", payload.get("back_image"))
    now = utcnow()
    card_number = clean_text(payload.get("card_number"), 40).upper()
    name = clean_text(payload.get("name")) or "Needs identification"
    status = "IN_STOCK" if card_number and name != "Needs identification" else "REVIEW"
    rip_session_id = active_rip_for_batch(db, batch["id"])
    values = (
        sku,
        batch["id"],
        now,
        now,
        card_number,
        name,
        clean_text(payload.get("set_name")) or batch["set_name"],
        clean_text(payload.get("rarity"), 60),
        clean_text(payload.get("color"), 40) or batch["color"],
        clean_text(payload.get("variant"), 80) or "Standard",
        clean_text(payload.get("condition"), 40) or batch["default_condition"],
        status,
        clean_text(payload.get("location"), 80) or batch["location"],
        front,
        back,
        rip_session_id,
    )
    cursor = db.execute(
        """
        INSERT INTO cards (
            sku, batch_id, created_at, updated_at, card_number, name, set_name,
            rarity, color, variant, condition, status, location, front_image, back_image,
            rip_session_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        values,
    )
    return dict(db.execute("SELECT * FROM cards WHERE id = ?", (cursor.lastrowid,)).fetchone())


def inventory_groups(filters: dict[str, list[str]]) -> list[dict]:
    clauses = ["c.recycled_at IS NULL"]
    params: list[object] = []
    q = clean_text(filters.get("q", [""])[0], 100)
    game = clean_text(filters.get("game", [""])[0], 40)
    status = clean_text(filters.get("status", [""])[0], 30)
    platform = clean_text(filters.get("platform", [""])[0], 30)
    if q:
        clauses.append(
            "(c.name LIKE ? OR c.card_number LIKE ? OR c.sku LIKE ? OR c.location LIKE ? "
            "OR b.batch_code LIKE ? OR o.order_number LIKE ?)"
        )
        needle = f"%{q}%"
        params.extend([needle] * 6)
    if game:
        clauses.append("b.game = ?")
        params.append(game)
    if status:
        clauses.append("c.status = ?")
        params.append(status)
    if platform:
        clauses.append("COALESCE(c.listing_platform, '') = ?")
        params.append(platform)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    with connect() as db:
        rows = db.execute(
            f"""
            SELECT c.*, b.game, b.set_code, b.batch_code, b.finish_group,
                   o.order_number AS sale_order_number,
                   b.total_cost AS batch_total_cost,
                   (SELECT COUNT(*) FROM cards bc WHERE bc.batch_id = b.id) AS batch_card_count
            FROM cards c JOIN batches b ON b.id = c.batch_id
            LEFT JOIN sale_items si ON si.id = (SELECT MAX(last_si.id) FROM sale_items last_si WHERE last_si.card_id=c.id)
            LEFT JOIN sale_orders o ON o.id = si.order_id
            {where}
            """,
            params,
        ).fetchall()

    grouped: dict[str, dict] = {}
    for row in rows:
        item = dict(row)
        identity = "|".join(
            [item["game"], item["card_number"] or item["sku"], item["variant"], item["condition"]]
        )
        group = grouped.setdefault(
            identity,
            {
                "key": identity,
                "game": item["game"],
                "card_number": item["card_number"],
                "name": item["name"],
                "set_code": item["set_code"],
                "set_name": item["set_name"],
                "rarity": item["rarity"],
                "color": item["color"],
                "variant": item["variant"],
                "condition": item["condition"],
                "market_low": item["market_low"],
                "market_average": item["market_average"],
                "market_high": item["market_high"],
                "market_updated_at": item["market_updated_at"],
                "copies": [],
            },
        )
        item["allocated_cost"] = round(
            item["batch_total_cost"] / max(1, item["batch_card_count"]), 2
        )
        group["copies"].append(item)
        for field in ("market_low", "market_average", "market_high", "market_updated_at"):
            if group[field] is None and item[field] is not None:
                group[field] = item[field]

    result = list(grouped.values())
    for group in result:
        group["quantity"] = len(group["copies"])
        group["in_stock"] = sum(1 for card in group["copies"] if card["status"] in ("IN_STOCK", "REVIEW"))
        group["tcg_slots"] = sum(
            1
            for card in group["copies"]
            if card["status"] == "IN_STOCK" and card["listing_platform"] == "TCGplayer"
        )
        group["locations"] = sorted({card["location"] for card in group["copies"] if card["location"]})

    sort = clean_text(filters.get("sort", ["average_desc"])[0], 30)
    reverse = not sort.endswith("_asc")
    field = {
        "average_desc": "market_average",
        "average_asc": "market_average",
        "low_desc": "market_low",
        "low_asc": "market_low",
        "high_desc": "market_high",
        "high_asc": "market_high",
        "name_asc": "name",
        "name_desc": "name",
    }.get(sort, "market_average")
    if field == "name":
        result.sort(key=lambda x: x["name"].lower(), reverse=reverse)
    else:
        result.sort(key=lambda x: (x[field] is not None, x[field] or 0), reverse=reverse)
    return result


def dashboard() -> dict:
    with connect() as db:
        values = dict(
            db.execute(
                """
                SELECT
                    COUNT(CASE WHEN c.recycled_at IS NULL THEN 1 END) AS total_cards,
                    SUM(CASE WHEN c.status = 'IN_STOCK' AND c.recycled_at IS NULL THEN 1 ELSE 0 END) AS in_stock,
                    SUM(CASE WHEN c.status IN ('IN_STOCK', 'REVIEW', 'HOLD') AND c.recycled_at IS NULL THEN 1 ELSE 0 END) AS physically_available,
                    SUM(CASE WHEN c.status = 'REVIEW' AND c.recycled_at IS NULL THEN 1 ELSE 0 END) AS needs_review,
                    SUM(CASE WHEN c.label_printed = 0 AND c.status != 'SOLD' AND c.recycled_at IS NULL AND b.status = 'COMPLETE' THEN 1 ELSE 0 END) AS labels_waiting,
                    SUM(CASE WHEN c.listing_platform = 'TCGplayer' AND c.status = 'IN_STOCK' AND c.recycled_at IS NULL THEN 1 ELSE 0 END) AS tcg_slots,
                    SUM(CASE WHEN c.market_average >= 20 AND c.status = 'IN_STOCK' AND c.recycled_at IS NULL THEN 1 ELSE 0 END) AS ebay_candidates,
                    COALESCE(SUM(CASE WHEN c.status = 'IN_STOCK' AND c.recycled_at IS NULL THEN c.market_average ELSE 0 END), 0) AS market_value
                FROM cards c JOIN batches b ON b.id = c.batch_id
                """
            ).fetchone()
        )
        values["open_batches"] = db.execute(
            "SELECT COUNT(*) FROM batches WHERE status = 'OPEN' AND recycled_at IS NULL"
        ).fetchone()[0]
        values["tcg_capacity"] = int(setting(db, "tcg_capacity", str(DEFAULT_TCG_CAPACITY)))
        values["timezone"] = setting(db, "timezone", DEFAULT_TIMEZONE)
        values["recycled_count"] = db.execute(
            "SELECT COUNT(*) FROM cards WHERE recycled_at IS NOT NULL"
        ).fetchone()[0]
        values["recycled_acquisition_count"] = db.execute(
            "SELECT COUNT(*) FROM acquisitions WHERE recycled_at IS NOT NULL"
        ).fetchone()[0]
        values["recycle_total_count"] = int(values["recycled_count"]) + int(values["recycled_acquisition_count"])
        values["recent_batches"] = [
            dict(row)
            for row in db.execute(
                """
                SELECT b.*, COUNT(c.id) AS card_count
                FROM batches b LEFT JOIN cards c ON c.batch_id = b.id AND c.recycled_at IS NULL
                WHERE b.recycled_at IS NULL
                GROUP BY b.id ORDER BY b.created_at DESC LIMIT 5
                """
            ).fetchall()
        ]
    return values


def undo_last_action(db: sqlite3.Connection) -> dict:
    action = db.execute(
        "SELECT * FROM activity_log WHERE undone_at IS NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not action:
        raise ValueError("There is no recent action to undo")
    payload = json.loads(action["payload"] or "{}")
    action_type = action["action_type"]
    if action_type == "SALE":
        order_id = int(payload["order_id"])
        if db.execute("SELECT 1 FROM post_sale_events WHERE order_id=? LIMIT 1", (order_id,)).fetchone():
            raise ValueError("This sale has post-sale history and must be corrected with linked events")
        for card in payload.get("cards", []):
            latest = db.execute("SELECT MAX(id) FROM sale_items WHERE card_id=?", (int(card["id"]),)).fetchone()[0]
            sale_item = db.execute("SELECT id FROM sale_items WHERE order_id=? AND card_id=?", (order_id, int(card["id"]))).fetchone()
            if not sale_item or int(latest or 0) != int(sale_item["id"]):
                raise ValueError("One or more exact cards are no longer eligible for Undo")
            changed = db.execute(
                "UPDATE cards SET status = ?, updated_at = ? WHERE id = ? AND status='SOLD'",
                (card.get("status", "IN_STOCK"), utcnow(), int(card["id"])),
            )
            if changed.rowcount != 1:
                raise ValueError("One or more exact cards are no longer eligible for Undo")
        db.execute(
            "UPDATE sale_orders SET canceled_at=?, cancellation_reason='OPERATOR_UNDO' WHERE id=? AND canceled_at IS NULL",
            (utcnow(), order_id),
        )
    elif action_type == "SEALED_SALE":
        undo_sealed_sale(db, int(payload["order_id"]), int(action["id"]))
    elif action_type == "BATCH_STATUS":
        db.execute(
            "UPDATE batches SET status = ?, completed_at = ? WHERE id = ?",
            (payload["old_status"], payload.get("old_completed_at"), int(payload["batch_id"])),
        )
    elif action_type == "CARD_UPDATE":
        before = payload.get("before", {})
        if not before:
            raise ValueError("This card edit cannot be restored")
        assignments = ", ".join(f"{key} = ?" for key in before)
        db.execute(
            f"UPDATE cards SET {assignments}, updated_at = ? WHERE sku = ?",
            [*before.values(), utcnow(), payload["sku"]],
        )
    elif action_type == "RECYCLE":
        db.execute(
            """UPDATE cards SET recycled_at = NULL, recycle_reason = '', purge_after = NULL,
                      status = COALESCE(pre_recycle_status, status), pre_recycle_status = NULL,
                      updated_at = ? WHERE sku = ?""",
            (utcnow(), payload["sku"]),
        )
    elif action_type == "BATCH_RECYCLE":
        now = utcnow()
        db.execute(
            "UPDATE batches SET recycled_at = NULL, recycle_reason = '', purge_after = NULL WHERE id = ?",
            (int(payload["batch_id"]),),
        )
        skus = [card["sku"] for card in payload.get("cards", []) if card.get("sku")]
        if skus:
            placeholders = ",".join("?" for _ in skus)
            db.execute(
                f"""UPDATE cards SET recycled_at = NULL, recycle_reason = '', purge_after = NULL,
                          status = COALESCE(pre_recycle_status, status), pre_recycle_status = NULL,
                          updated_at = ? WHERE sku IN ({placeholders})""",
                [now, *skus],
            )
    elif action_type == "RESTORE":
        db.execute(
            """UPDATE cards SET recycled_at = ?, recycle_reason = ?, purge_after = ?,
                      pre_recycle_status = status, updated_at = ? WHERE sku = ?""",
            (payload["recycled_at"], payload.get("reason", ""), payload.get("purge_after"), utcnow(), payload["sku"]),
        )
    elif action_type == "IMAGE_SWAP":
        db.execute(
            "UPDATE cards SET front_image = back_image, back_image = front_image, updated_at = ? WHERE sku = ?",
            (utcnow(), payload["sku"]),
        )
    else:
        raise ValueError("The latest action cannot be undone")
    db.execute("UPDATE activity_log SET undone_at = ? WHERE id = ?", (utcnow(), action["id"]))
    return {"undone": action["description"], "action_id": action["id"]}


def seed_demo() -> None:
    if os.environ.get("DEX_SEED_DEMO", "0") != "1":
        return
    with connect() as db:
        if db.execute("SELECT COUNT(*) FROM batches").fetchone()[0]:
            return
        now = utcnow()
        code = make_batch_code(db, "One Piece")
        cursor = db.execute(
            """
            INSERT INTO batches (
                batch_code, created_at, status, game, set_code, set_name, color,
                finish_group, acquisition_type, total_cost, location,
                economics_mode, economics_status, product_name, product_code,
                receipt_group_reference, invoice_reference, reporting_currency,
                original_currency, original_foreign_amount_minor,
                final_usd_paid_cents, units_acquired, purchase_subtotal_cents,
                acquisition_tax_cents, inbound_shipping_cents,
                acquisition_fees_cents, acquisition_discount_cents,
                acquisition_updated_at
            ) VALUES (?, ?, 'OPEN', 'One Piece', 'OP16', 'The Azure Sea''s Seven',
                      'Yellow', 'Rare / Foil', 'Booster Box', 660.00, 'OP16-Yellow',
                      'SEALED_RIP', 'DRAFT', 'OP16 Booster Box', 'OP16-BOX',
                      'DEMO-RECEIPT-001', 'DEMO-ORDER-001', 'USD', 'CAD', 90000,
                      66000, 6, 60000, 4800, 1500, 200, 500, ?)
            """,
            (code, now, now),
        )
        batch_id = cursor.lastrowid
        second_code = make_batch_code(db, "One Piece")
        db.execute(
            """
            INSERT INTO batches (
                batch_code, created_at, status, game, set_code, set_name, color,
                finish_group, acquisition_type, total_cost, location,
                economics_mode, economics_status, product_name, product_code,
                receipt_group_reference, invoice_reference, reporting_currency,
                final_usd_paid_cents, units_acquired, purchase_subtotal_cents,
                acquisition_tax_cents, inbound_shipping_cents,
                acquisition_fees_cents, acquisition_discount_cents,
                acquisition_updated_at
            ) VALUES (?, ?, 'OPEN', 'One Piece', 'ST27', 'Starter Deck 27',
                      'Mixed', 'Sealed', 'Starter Deck', 86.40, 'ST27-Sealed',
                      'SEALED_RIP', 'DRAFT', 'ST27 Starter Deck', 'ST27-DECK',
                      'DEMO-RECEIPT-001', 'DEMO-ORDER-001', 'USD',
                      8640, 2, 8000, 640, 0, 0, 0, ?)
            """,
            (second_code, now, now),
        )
        synchronize_sealed_units(db, batch_id)
        second_batch_id = db.execute(
            "SELECT id FROM batches WHERE batch_code=?", (second_code,)
        ).fetchone()[0]
        synchronize_sealed_units(db, second_batch_id)
        demo = [
            ("OP16-112", "Boa Hancock", "Super Rare", 6.25, 8.41, 11.80, "TCGplayer"),
            ("OP16-042", "Kikunojo", "Rare", 1.19, 1.88, 2.75, "TCGplayer"),
            ("OP16-118", "Enel", "Secret Rare", 17.40, 22.65, 29.00, "eBay"),
            ("OP16-071", "Nami", "Super Rare", 3.82, 5.12, 7.25, None),
        ]
        for index, (number, name, rarity, low, avg, high, platform) in enumerate(demo, 1):
            sku = f"OP-B{business_today(db).strftime('%Y%m%d')}-{index:03d}"
            db.execute(
                """
                INSERT INTO cards (
                    sku, batch_id, created_at, updated_at, card_number, name,
                    set_name, rarity, color, variant, condition, status, location,
                    market_low, market_average, market_high, market_updated_at,
                    listing_platform, listing_price
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Yellow', 'Standard', 'Near Mint',
                          'IN_STOCK', 'OP16-Yellow', ?, ?, ?, ?, ?, ?)
                """,
                (sku, batch_id, now, now, number, name, "The Azure Sea's Seven", rarity,
                 low, avg, high, now, platform, avg),
            )
        db.commit()


class DexHandler(BaseHTTPRequestHandler):
    server_version = f"Dex/{APP_VERSION}"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def send_json(self, value: object, status: int = 200) -> None:
        payload = json.dumps(value, separators=(",", ":"), default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def send_error_json(self, message: str, status: int = 400) -> None:
        self.send_json({"error": message}, status)

    def read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid request length") from exc
        if length <= 0 or length > MAX_BODY:
            raise ValueError("Request body is empty or too large")
        try:
            value = json.loads(self.rfile.read(length))
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid JSON") from exc
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object")
        return value

    def serve_file(self, path: Path, cache: bool = True) -> None:
        try:
            resolved = path.resolve()
            allowed = (
                resolved.is_relative_to(STATIC_DIR.resolve())
                or resolved.is_relative_to(DATA_DIR)
                or resolved.is_relative_to(SOURCE_DB_DIR.resolve())
                or resolved.is_relative_to(ONE_PIECE_REFERENCE_DIR)
            )
            if not allowed or not resolved.is_file():
                self.send_error(404)
                return
            body = resolved.read_bytes()
            mime = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=3600" if cache else "no-store")
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            self.send_error(404)

    def serve_inventory_csv(self) -> None:
        with connect() as db:
            rows = db.execute(
                """
                SELECT c.sku, c.status, b.game, b.set_code, c.card_number, c.name,
                       c.rarity, c.color, c.variant, c.condition, c.location,
                       b.batch_code, b.acquisition_type,
                       ROUND(b.total_cost / MAX(1, (SELECT COUNT(*) FROM cards bc WHERE bc.batch_id = b.id)), 2) AS allocated_cost,
                       c.market_low, c.market_average, c.market_high, c.market_updated_at,
                       c.listing_platform, c.listing_price, si.sale_price, o.sold_at,
                       o.platform AS sale_platform, o.order_number,
                       o.subtotal AS order_subtotal,
                       o.shipping_collected AS order_shipping_collected,
                       o.platform_fees AS order_platform_fees,
                       o.postage_cost AS order_postage_cost,
                        CASE WHEN o.id IS NULL THEN NULL ELSE
                            o.subtotal + o.shipping_collected - o.platform_fees - o.postage_cost
                        END AS order_net_proceeds,
                        b.economics_mode, b.economics_status, b.product_name,
                        b.product_code, b.receipt_group_reference, b.invoice_reference,
                        b.reporting_currency, b.original_currency,
                        b.original_foreign_amount_minor,
                        b.final_usd_paid_cents, b.units_acquired,
                        b.purchase_subtotal_cents, b.acquisition_tax_cents,
                        b.inbound_shipping_cents, b.acquisition_fees_cents,
                        b.acquisition_discount_cents,
                        b.cost_reconciliation_acknowledged,
                        b.acquisition_updated_at,
                        ? AS economics_calculation_version,
                        CASE WHEN r.status='FINALIZED' AND
                                  (EXISTS (SELECT 1 FROM rip_basis_events rbe
                                           WHERE rbe.card_id=c.id AND rbe.target_type='CARD')
                                   OR EXISTS (SELECT 1 FROM economic_event_entries eee
                                               WHERE eee.entry_type='BASIS' AND eee.target_type='CARD' AND eee.target_id=c.id))
                             THEN COALESCE((SELECT SUM(rbe.amount_delta_cents) FROM rip_basis_events rbe
                                    WHERE rbe.card_id=c.id AND rbe.target_type='CARD'),0)
                                  + COALESCE((SELECT SUM(eee.amount_delta_cents) FROM economic_event_entries eee
                                    WHERE eee.entry_type='BASIS' AND eee.target_type='CARD' AND eee.target_id=c.id),0)
                        END AS authoritative_card_basis_cents,
                        CASE WHEN r.status='FINALIZED' AND
                                  EXISTS (SELECT 1 FROM rip_basis_events rbe
                                           WHERE rbe.card_id=c.id AND rbe.target_type='CARD')
                             THEN 'FINALIZED' ELSE 'UNKNOWN' END AS card_basis_status,
                        r.rip_code, r.finalized_at AS rip_finalized_at,
                        b.final_usd_paid_cents AS preserved_source_acquisition_cost_cents,
                        CASE WHEN b.final_usd_paid_cents IS NULL THEN NULL ELSE
                          b.final_usd_paid_cents + COALESCE((SELECT SUM(eee.amount_delta_cents)
                            FROM economic_event_entries eee
                            WHERE eee.entry_type='ACQUISITION_COST' AND eee.target_type='BATCH' AND eee.target_id=b.id),0)
                        END AS current_authoritative_acquisition_cost_cents
                FROM cards c
                JOIN batches b ON b.id = c.batch_id
                LEFT JOIN sale_items si ON si.id = (SELECT MAX(last_si.id) FROM sale_items last_si WHERE last_si.card_id=c.id)
                LEFT JOIN sale_orders o ON o.id = si.order_id
                LEFT JOIN rip_sessions r ON r.id = c.rip_session_id
                WHERE c.recycled_at IS NULL
                ORDER BY c.id
                """,
                (CALCULATION_VERSION,),
            ).fetchall()
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        headers = list(rows[0].keys()) if rows else [
            "sku", "status", "game", "set_code", "card_number", "name", "rarity",
            "color", "variant", "condition", "location", "batch_code",
            "acquisition_type", "allocated_cost", "market_low", "market_average",
            "market_high", "market_updated_at", "listing_platform", "listing_price",
            "sale_price", "sold_at", "sale_platform", "order_number",
            "order_subtotal", "order_shipping_collected", "order_platform_fees",
            "order_postage_cost", "order_net_proceeds", "economics_mode",
            "economics_status", "product_name", "product_code",
            "receipt_group_reference", "invoice_reference", "reporting_currency",
            "original_currency", "original_foreign_amount_minor",
            "final_usd_paid_cents", "units_acquired", "purchase_subtotal_cents",
            "acquisition_tax_cents", "inbound_shipping_cents",
            "acquisition_fees_cents", "acquisition_discount_cents",
            "cost_reconciliation_acknowledged", "acquisition_updated_at",
            "economics_calculation_version", "authoritative_card_basis_cents",
            "card_basis_status", "rip_code", "rip_finalized_at",
            "preserved_source_acquisition_cost_cents", "current_authoritative_acquisition_cost_cents",
        ]
        writer.writerow(headers)
        writer.writerows(tuple(row) for row in rows)
        body = output.getvalue().encode("utf-8-sig")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        with connect() as db:
            stamp = business_today(db).isoformat()
        self.send_header("Content-Disposition", f'attachment; filename="dex-inventory-{stamp}.csv"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_sales_csv(self) -> None:
        with connect() as db:
            source_rows = db.execute(
                """
                SELECT o.sold_at, o.platform, o.order_number,
                       (SELECT GROUP_CONCAT(c.sku, ' | ')
                          FROM sale_items si JOIN cards c ON c.id=si.card_id
                         WHERE si.order_id=o.id) AS skus,
                       (SELECT COUNT(*) FROM sale_items si WHERE si.order_id=o.id) AS card_count,
                       o.subtotal, o.shipping_collected, o.platform_fees,
                       o.postage_cost,
                       o.subtotal + o.shipping_collected - o.platform_fees - o.postage_cost AS net_proceeds,
                       o.order_type,
                       (SELECT GROUP_CONCAT(su.unit_code, ' | ')
                          FROM sealed_sale_items ssi JOIN sealed_units su ON su.id=ssi.sealed_unit_id
                         WHERE ssi.order_id=o.id) AS sealed_unit_codes,
                       (SELECT COUNT(*) FROM sealed_sale_items ssi WHERE ssi.order_id=o.id) AS sealed_unit_count,
                       o.merchandise_total_cents, o.shipping_collected_cents,
                       o.marketplace_fees_cents, o.actual_postage_cents,
                       o.marketplace_tax_cents,
                       CASE WHEN o.order_type='SEALED' THEN
                           o.merchandise_total_cents + o.shipping_collected_cents
                           - o.marketplace_fees_cents - o.actual_postage_cents
                       END AS sealed_net_proceeds_cents,
                       CASE WHEN o.order_type='SEALED' THEN
                           (SELECT COALESCE(SUM(ssi.basis_cents),0)
                              FROM sealed_sale_items ssi WHERE ssi.order_id=o.id)
                       END AS sealed_sold_basis_cents,
                       o.canceled_at, o.cancellation_reason,
                       ? AS calculation_version,
                       CASE WHEN o.canceled_at IS NULL THEN 1 ELSE 0 END AS economics_included,
                       CASE WHEN o.order_type='SEALED' THEN 'EXACT_SEALED_ITEM_STABLE_ID'
                            ELSE 'WEIGHTED_SALE_ITEM_STABLE_ID' END AS attribution_method,
                       CASE WHEN o.order_type='SEALED' THEN
                           (SELECT GROUP_CONCAT(DISTINCT ssi.batch_id) FROM sealed_sale_items ssi WHERE ssi.order_id=o.id)
                           ELSE (SELECT GROUP_CONCAT(DISTINCT c.batch_id)
                                   FROM sale_items si JOIN cards c ON c.id=si.card_id WHERE si.order_id=o.id)
                       END AS attributed_batch_ids,
                       o.id AS dex_order_id
                FROM sale_orders o
                ORDER BY o.sold_at, o.id
                """,
                (CALCULATION_VERSION,),
            ).fetchall()
            rows = []
            for source in source_rows:
                row = dict(source)
                detail = post_sale_order_payload(db, int(source["dex_order_id"]))
                effective = detail["financials"]["effective"]
                row.update({
                    "post_sale_event_count": detail["post_sale_event_count"],
                    "post_sale_event_ids": " | ".join(event["event_id"] for event in detail["events"]),
                    "effective_merchandise_cents": effective["merchandise_cents"],
                    "effective_shipping_collected_cents": effective["shipping_cents"],
                    "effective_marketplace_fees_cents": effective["marketplace_fees_cents"],
                    "effective_actual_postage_cents": effective["postage_cents"],
                    "effective_other_net_cents": effective["other_net_cents"],
                    "effective_net_proceeds_cents": effective["net_proceeds_cents"],
                    "effective_sold_basis_cents": detail["sold_basis_cents"],
                    "effective_realized_profit_loss_cents": detail["realized_profit_loss_cents"],
                    "returned_item_count": sum(1 for item in detail["items"] if item["returned"]),
                })
                rows.append(row)
            stamp = business_today(db).isoformat()
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        headers = list(rows[0].keys()) if rows else [
            "sold_at", "platform", "order_number", "skus", "card_count",
            "subtotal", "shipping_collected", "platform_fees", "postage_cost", "net_proceeds",
            "order_type", "sealed_unit_codes", "sealed_unit_count",
            "merchandise_total_cents", "shipping_collected_cents",
            "marketplace_fees_cents", "actual_postage_cents", "marketplace_tax_cents",
            "sealed_net_proceeds_cents", "sealed_sold_basis_cents",
            "canceled_at", "cancellation_reason", "calculation_version",
            "economics_included", "attribution_method", "attributed_batch_ids", "dex_order_id",
            "post_sale_event_count", "post_sale_event_ids",
            "effective_merchandise_cents", "effective_shipping_collected_cents",
            "effective_marketplace_fees_cents", "effective_actual_postage_cents",
            "effective_other_net_cents", "effective_net_proceeds_cents",
            "effective_sold_basis_cents", "effective_realized_profit_loss_cents",
            "returned_item_count",
        ]
        writer.writerow(headers)
        writer.writerows(tuple(row.values()) if isinstance(row, dict) else tuple(row) for row in rows)
        body = output.getvalue().encode("utf-8-sig")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="dex-sales-{stamp}.csv"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_batch_economics_csv(self, query: dict[str, list[str]]) -> None:
        batch_id: int | None = None
        if query.get("batch_id"):
            try:
                batch_id = int(query["batch_id"][0])
            except (TypeError, ValueError) as exc:
                raise ValueError("batch_id must be a whole number") from exc
        with open_readonly_database(DB_PATH) as db:
            rows = batch_economics_export_rows(db, batch_id)
            stamp = business_today(db).isoformat()
        preferred = [
            "calculation_version", "economics_state", "batch_id", "batch_code",
            "economics_mode", "economics_status", "product_name",
            "receipt_group_reference", "authoritative_cost_cents",
            "realized_gross_merchandise_cents", "realized_shipping_collected_cents",
            "realized_marketplace_fees_cents", "realized_actual_postage_cents",
            "realized_net_proceeds_cents", "sold_basis_cents",
            "sold_basis_known_count", "sold_basis_total_count",
            "realized_profit_loss_cents", "cost_recovery_percent",
            "remaining_known_basis_cents", "remaining_basis_complete",
            "remaining_market_value_cents", "remaining_market_valued_count",
            "remaining_market_total_count", "remaining_market_freshness",
            "remaining_market_complete", "remaining_listed_value_cents",
            "remaining_listed_valued_count", "remaining_listed_total_count",
            "remaining_listed_freshness", "remaining_listed_complete",
            "current_economic_position_cents", "current_position_complete",
            "projected_listed_position_cents", "projected_listed_position_complete",
            "excluded_known_basis_cents", "materially_incomplete", "warning_codes",
            "preserved_source_cost_cents", "acquisition_correction_delta_cents",
            "operational_loss_cents", "realized_other_net_cents",
        ]
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=preferred, extrasaction="ignore", restval="")
        writer.writeheader()
        writer.writerows(rows)
        body = output.getvalue().encode("utf-8-sig")
        suffix = f"-batch-{batch_id}" if batch_id is not None else ""
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="dex-batch-economics{suffix}-{stamp}.csv"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_portfolio_economics_csv(self) -> None:
        with open_readonly_database(DB_PATH) as db:
            rows = portfolio_economics_export_rows(db)
            stamp = business_today(db).isoformat()
        preferred = [
            "calculation_version", "generated_at", "economics_state",
            "finalized_batch_count", "authoritative_unfinalized_batch_count",
            "legacy_estimate_batch_count", "authoritative_acquisition_cost_cents",
            "effective_realized_merchandise_cents", "effective_shipping_collected_cents",
            "effective_marketplace_fees_cents", "effective_actual_postage_cents",
            "effective_other_net_cents", "effective_realized_net_proceeds_cents",
            "active_sold_basis_cents", "sold_basis_known_count",
            "sold_basis_total_count", "sold_basis_complete",
            "realized_profit_loss_cents", "cost_recovery_percent",
            "operational_loss_cents", "remaining_known_basis_cents",
            "remaining_card_count", "remaining_sealed_unit_count",
            "remaining_known_bulk_quantity", "bulk_quantity_unknown",
            "remaining_market_value_cents", "remaining_market_valued_count",
            "remaining_market_total_count", "remaining_market_complete",
            "remaining_market_freshness", "remaining_listed_value_cents",
            "remaining_listed_valued_count", "remaining_listed_total_count",
            "remaining_listed_complete", "remaining_listed_freshness",
            "current_economic_position_cents", "current_position_complete",
            "projected_listed_position_cents", "projected_listed_position_complete",
            "unique_order_count", "attributed_item_count",
            "duplicate_attribution_count", "realized_reconciliation_difference_cents",
            "materially_incomplete", "warning_codes", "receipt_group_notice",
        ]
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=preferred, extrasaction="ignore", restval="")
        writer.writeheader()
        writer.writerows(rows)
        body = output.getvalue().encode("utf-8-sig")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="dex-operational-economics-{stamp}.csv"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        try:
            if path == "/api/health":
                self.send_json({"status": "ok", "name": "Dex", "version": APP_VERSION, "time": utcnow()})
            elif path == "/api/dashboard":
                self.send_json(dashboard())
            elif path == "/api/inventory":
                self.send_json({"groups": inventory_groups(query)})
            elif path == "/api/export/inventory.csv":
                self.serve_inventory_csv()
            elif path == "/api/export/sales.csv":
                self.serve_sales_csv()
            elif path == "/api/export/batch-economics.csv":
                self.serve_batch_economics_csv(query)
            elif path == "/api/export/portfolio-economics.csv":
                self.serve_portfolio_economics_csv()
            elif path == "/api/portfolio/economics":
                with open_readonly_database(DB_PATH) as db:
                    result = portfolio_economics_payload(db)
                self.send_json(result)
            elif path == "/api/jarvis/economics/summary":
                with open_readonly_database(DB_PATH) as db:
                    result = jarvis_aggregate_economics_payload(db)
                self.send_json(result)
            elif re.fullmatch(r"/api/jarvis/economics/cards/[A-Z0-9-]+", path):
                sku = unquote(path.rsplit("/", 1)[-1])
                try:
                    with open_readonly_database(DB_PATH) as db:
                        result = jarvis_card_economics_payload(db, sku)
                except ValueError:
                    self.send_error_json("Card economics not found", 404)
                else:
                    self.send_json(result)
            elif re.fullmatch(r"/api/jarvis/economics/sales/\d+", path):
                order_id = int(path.rsplit("/", 1)[-1])
                try:
                    with open_readonly_database(DB_PATH) as db:
                        result = jarvis_sale_economics_payload(db, order_id)
                except ValueError:
                    self.send_error_json("Sale economics not found", 404)
                else:
                    self.send_json(result)
            elif path.startswith("/api/jarvis/economics/"):
                self.send_error_json("JARVIS economics endpoint not found", 404)
            elif path == "/api/inbound/foundation":
                self.send_json(inbound_foundation_contract())
            elif path == "/api/document-providers/status":
                self.send_json(document_provider_contract(DOCUMENT_STORE))
            elif path == "/api/receipt-extraction/providers/status":
                self.send_json(extraction_provider_contract(RECEIPT_EXTRACTOR))
            elif path == "/api/catalog/contract":
                self.send_json(catalog_contract())
            elif path == "/api/catalog/products":
                with connect() as db:
                    products = search_catalog_products(
                        db,
                        query.get("q", [""])[0],
                        query.get("product_class", [""])[0],
                        include_inactive=query.get("include_inactive", ["0"])[0] == "1",
                    )
                self.send_json({"products": products})
            elif re.fullmatch(r"/api/catalog/products/\d+", path):
                product_id = int(path.rsplit("/", 1)[-1])
                with connect() as db:
                    result = catalog_product_payload(db, product_id)
                self.send_json(result)
            elif path == "/api/catalog/identifiers/lookup":
                with connect() as db:
                    result = lookup_identifier(
                        db,
                        query.get("identifier", [""])[0],
                        query.get("identifier_type", [""])[0],
                    )
                self.send_json(result)
            elif re.fullmatch(r"/api/catalog/identifiers/\d+/history", path):
                identifier_id = int(path.split("/")[4])
                with connect() as db:
                    result = identifier_history(db, identifier_id)
                self.send_json(result)
            elif path == "/api/acquisitions":
                with connect() as db:
                    result = list_acquisitions(db)
                self.send_json({"acquisitions": result})
            elif re.fullmatch(r"/api/acquisitions/\d+", path):
                acquisition_id = int(path.rsplit("/", 1)[-1])
                with connect() as db:
                    result = inbound_acquisition_payload(db, acquisition_id)
                self.send_json(result)
            elif re.fullmatch(r"/api/acquisitions/\d+/intake-routing", path):
                acquisition_id = int(path.split("/")[3])
                with connect() as db:
                    result = intake_status(db, acquisition_id)
                self.send_json(result)
            elif re.fullmatch(r"/api/acquisitions/\d+/intake-routing/(links|continue)", path):
                acquisition_id = int(path.split("/")[3])
                with connect() as db:
                    routing = intake_status(db, acquisition_id)
                links = [link for line in routing["lines"] for link in line["links"]]
                self.send_json({
                    "acquisition_id": acquisition_id,
                    "state": routing["state"],
                    "links": links,
                    "recommended_action": (
                        "CONTINUE_INTAKE" if routing["summary"]["quantity_undecided"]
                        else "VIEW_INVENTORY"
                    ),
                })
            elif re.fullmatch(r"/api/acquisitions/\d+/documents", path):
                acquisition_id = int(path.split("/")[3])
                with connect() as db:
                    result = list_source_documents(db, acquisition_id)
                self.send_json({"documents": result})
            elif re.fullmatch(r"/api/acquisition-documents/\d+", path):
                document_id = int(path.split("/")[3])
                with connect() as db:
                    result = source_document_payload(db, document_id)
                self.send_json({"document": result})
            elif re.fullmatch(r"/api/acquisition-documents/\d+/content", path):
                document_id = int(path.split("/")[3])
                try:
                    with connect() as db:
                        document, body = read_source_document(db, document_id, DOCUMENT_STORE)
                except DocumentIntegrityError:
                    with DB_LOCK, connect() as db:
                        db.execute("BEGIN IMMEDIATE")
                        verify_source_document(
                            db, document_id,
                            {"request_id": f"AUTO-INTEGRITY-{document_id}-{uuid.uuid4()}"},
                            DOCUMENT_STORE,
                        )
                    raise
                disposition = f'inline; filename="{document["safe_filename"]}"'
                self.send_response(200)
                self.send_header("Content-Type", document["detected_mime_type"])
                self.send_header("Content-Disposition", disposition)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store, private")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy", "default-src 'none'; sandbox")
                self.end_headers()
                self.wfile.write(body)
            elif re.fullmatch(r"/api/acquisitions/\d+/receipt-intelligence", path):
                acquisition_id = int(path.split("/")[3])
                with connect() as db:
                    result = receipt_intelligence_payload(db, acquisition_id)
                self.send_json(result)
            elif re.fullmatch(r"/api/acquisitions/\d+/receipt-semantics", path):
                acquisition_id = int(path.split("/")[3])
                with connect() as db:
                    result = semantic_review_payload(db, acquisition_id)
                self.send_json(result)
            elif re.fullmatch(r"/api/receipt-extractions/RCPT-JOB-[0-9a-f-]+", path):
                job_uuid = path.rsplit("/", 1)[-1]
                with connect() as db:
                    result = receipt_extraction_job_payload(db, job_uuid)
                self.send_json(result)
            elif path == "/api/settings":
                with connect() as db:
                    values = {row["key"]: row["value"] for row in db.execute("SELECT key, value FROM settings")}
                values["tcg_capacity"] = int(values.get("tcg_capacity", DEFAULT_TCG_CAPACITY))
                values["recycle_retention_days"] = int(values.get("recycle_retention_days", 180))
                values["recycle_auto_purge"] = values.get("recycle_auto_purge", "0") == "1"
                self.send_json(values)
            elif path == "/api/sam/provider/health":
                probe = query.get("probe", ["0"])[0] == "1"
                with connect() as db:
                    result = metadata_provider_status(db, SAM_METADATA_PROVIDER, probe=probe)
                self.send_json(result)
            elif path == "/api/sam/metadata/status":
                with connect() as db:
                    result = metadata_provider_status(db, SAM_METADATA_PROVIDER, probe=False)
                self.send_json(result)
            elif path == "/api/sam/references/status":
                with connect() as db:
                    result = reference_index_status(db, ONE_PIECE_REFERENCE_DIR)
                self.send_json(result)
            elif path == "/api/sam/references/search":
                filters = {key: values[0] for key, values in query.items() if values}
                with connect() as db:
                    result = search_sam_references(db, filters)
                self.send_json(result)
            elif re.fullmatch(r"/api/sam/references/\d+/image", path):
                reference_id = int(path.split("/")[4])
                with connect() as db:
                    _, image_path = sam_reference_path(db, reference_id, ONE_PIECE_REFERENCE_DIR)
                body = image_path.read_bytes()
                content_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "private, max-age=3600")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            elif path == "/api/sam/review-queues":
                batch_id = int(query["batch_id"][0]) if query.get("batch_id") else None
                with connect() as db:
                    result = sam_review_queue(db, batch_id=batch_id)
                self.send_json(result)
            elif path == "/api/sam/audited/status":
                with connect() as db:
                    result = sam_audited_status(db)
                self.send_json(result)
            elif path == "/api/sam/audited/intake":
                with connect() as db:
                    result = sam_audited_intake_cards(db, int(query.get("limit", ["100"])[0]))
                self.send_json(result)
            elif path == "/api/sam/audited/catalog-search":
                result_uuid = clean_text(query.get("result_uuid", [""])[0], 120)
                if not result_uuid:
                    raise ValueError("Catalog verification opens only after an audited SAM result is frozen")
                with connect() as db:
                    sam_audited_result(db, result_uuid)
                result = search_sam_audited_catalog(query.get("q", [""])[0], int(query.get("limit", ["30"])[0]))
                self.send_json(result)
            elif re.fullmatch(r"/api/sam/audited/results/SAM-AUDIT-RESULT-[0-9a-f-]+", path):
                result_uuid = path.rsplit("/", 1)[-1]
                with connect() as db:
                    result = sam_audited_result(db, result_uuid)
                self.send_json(result)
            elif path == "/api/sam/challenger/comparison":
                self.send_json(load_sam_challenger_comparison(SAM_CHALLENGER_REPORT_PATH))
            elif re.fullmatch(r"/api/sam/recognitions/SAM-JOB-[0-9a-f-]+/challenger", path):
                job_uuid = path.split("/")[-2]
                with open_readonly_database(DB_PATH) as db:
                    result = sam_challenger_shadow_for_job(db, job_uuid, data_dir=DATA_DIR)
                self.send_json(result)
            elif re.fullmatch(r"/api/sam/recognitions/SAM-JOB-[0-9a-f-]+", path):
                job_uuid = path.rsplit("/", 1)[-1]
                with connect() as db:
                    result = recognition_result(db, job_uuid)
                self.send_json(result)
            elif re.fullmatch(r"/api/cards/[A-Z0-9-]+/sam/history", path):
                sku = unquote(path.split("/")[3])
                with connect() as db:
                    card = db.execute("SELECT id FROM cards WHERE sku=?", (sku,)).fetchone()
                    if not card:
                        raise ValueError("Card not found")
                    result = recognition_history(db, card["id"])
                self.send_json(result)
            elif path == "/api/sam/source":
                with connect() as db:
                    rows = db.execute(
                        """
                        SELECT * FROM source_cards
                        ORDER BY set_code, card_number
                        LIMIT 400
                        """
                    ).fetchall()
                    payload = {
                        "summary": source_summary(db),
                        "cards": [source_payload(row) for row in rows],
                        "phase7": {
                            "provider": metadata_provider_status(db, SAM_METADATA_PROVIDER, probe=False),
                            "references": reference_index_status(db, ONE_PIECE_REFERENCE_DIR),
                            "review": sam_review_queue(db),
                            "rules_version": SAM_RULES_VERSION,
                            "auto_match_threshold": SAM_AUTO_MATCH_THRESHOLD,
                            "challenger": load_sam_challenger_comparison(SAM_CHALLENGER_REPORT_PATH),
                            "audited": sam_audited_status(db),
                            "audited_intake": sam_audited_intake_cards(db),
                        },
                    }
                self.send_json(payload)
            elif path == "/api/activity":
                with connect() as db:
                    rows = db.execute(
                        "SELECT id, created_at, action_type, description, undone_at FROM activity_log ORDER BY id DESC LIMIT 10"
                    ).fetchall()
                self.send_json({"actions": [dict(row) for row in rows]})
            elif path == "/api/batches":
                with connect() as db:
                    rows = db.execute(
                        """
                        SELECT b.*, COUNT(c.id) AS card_count,
                               SUM(CASE WHEN c.status = 'REVIEW' THEN 1 ELSE 0 END) AS review_count
                        FROM batches b LEFT JOIN cards c ON c.batch_id = b.id AND c.recycled_at IS NULL
                        WHERE b.recycled_at IS NULL
                        GROUP BY b.id ORDER BY b.created_at DESC
                        """
                    ).fetchall()
                self.send_json({"batches": [dict(row) for row in rows]})
            elif re.fullmatch(r"/api/batches/\d+/economics/estimate", path):
                batch_id = int(path.split("/")[3])
                with open_readonly_database(DB_PATH) as db:
                    estimate = estimate_legacy_batch(db, batch_id)
                if estimate is None:
                    self.send_error_json("Batch not found", 404)
                else:
                    self.send_json(estimate)
            elif re.fullmatch(r"/api/batches/\d+/economics/report", path):
                batch_id = int(path.split("/")[3])
                with open_readonly_database(DB_PATH) as db:
                    result = batch_economics_payload(db, batch_id)
                self.send_json(result)
            elif re.fullmatch(r"/api/batches/\d+/corrections", path):
                batch_id = int(path.split("/")[3])
                with open_readonly_database(DB_PATH) as db:
                    result = batch_corrections_payload(db, batch_id)
                self.send_json(result)
            elif re.fullmatch(r"/api/economic-events/[^/]+", path):
                event_id = unquote(path.split("/")[3])
                with open_readonly_database(DB_PATH) as db:
                    result = economic_event_payload(db, event_id)
                self.send_json(result)
            elif re.fullmatch(r"/api/acquisition-groups/[^/]+/economics", path):
                reference = unquote(path.split("/")[3])
                with open_readonly_database(DB_PATH) as db:
                    result = acquisition_group_economics_payload(db, reference)
                self.send_json(result)
            elif re.fullmatch(r"/api/batches/\d+/economics", path):
                batch_id = int(path.split("/")[3])
                with connect() as db:
                    facts = acquisition_payload(db, batch_id)
                if facts is None:
                    self.send_error_json("Batch not found", 404)
                else:
                    self.send_json(facts)
            elif re.fullmatch(r"/api/batches/\d+/rips", path):
                batch_id = int(path.split("/")[3])
                with connect() as db:
                    result = batch_rips_payload(db, batch_id)
                self.send_json(result)
            elif re.fullmatch(r"/api/rip-sessions/\d+", path):
                rip_id = int(path.split("/")[3])
                with connect() as db:
                    result = rip_session_payload(db, rip_id)
                self.send_json(result)
            elif path == "/api/sealed-inventory":
                with connect() as db:
                    result = sealed_inventory_payload(db)
                self.send_json(result)
            elif re.fullmatch(r"/api/batches/\d+/sealed-units", path):
                batch_id = int(path.split("/")[3])
                with connect() as db:
                    result = batch_sealed_payload(db, batch_id)
                self.send_json(result)
            elif re.fullmatch(r"/api/sealed-sales/\d+", path):
                order_id = int(path.split("/")[3])
                with connect() as db:
                    result = sealed_order_payload(db, order_id)
                self.send_json(result)
            elif re.fullmatch(r"/api/sales/\d+", path):
                order_id = int(path.split("/")[3])
                with connect() as db:
                    result = post_sale_order_payload(db, order_id)
                    if result["order_type"] == "SEALED":
                        sealed_detail = sealed_order_payload(db, order_id)
                        result["undo_eligible"] = sealed_detail["undo_eligible"]
                        result["undo_eligibility_reason"] = sealed_detail["undo_eligibility_reason"]
                    else:
                        result["undo_eligible"] = False
                        result["undo_eligibility_reason"] = "Card sale Undo remains available only through the existing latest-action control."
                self.send_json(result)
            elif re.fullmatch(r"/api/batches/\d+", path):
                batch_id = int(path.rsplit("/", 1)[-1])
                with connect() as db:
                    batch = db.execute("SELECT * FROM batches WHERE id = ? AND recycled_at IS NULL", (batch_id,)).fetchone()
                    cards = db.execute(
                        """
                        SELECT c.*, sc.card_number AS source_card_number, sc.name AS source_name,
                               sc.full_image AS source_full_image, sc.small_image AS source_small_image
                        FROM cards c LEFT JOIN source_cards sc ON sc.id = c.source_card_id
                        WHERE c.batch_id = ? AND c.recycled_at IS NULL
                        ORDER BY c.id
                        """,
                        (batch_id,),
                    ).fetchall()
                if not batch:
                    self.send_error_json("Batch not found", 404)
                else:
                    self.send_json({"batch": dict(batch), "cards": [dict(row) for row in cards]})
            elif re.fullmatch(r"/api/cards/[A-Z0-9-]+", path):
                sku = unquote(path.rsplit("/", 1)[-1])
                with connect() as db:
                    row = db.execute(
                        """SELECT c.*, b.game, b.set_code, b.batch_code, b.acquisition_type,
                                  b.total_cost, b.finish_group,
                                  sc.card_number AS source_card_number, sc.name AS source_name,
                                  sc.set_code AS source_set_code, sc.set_name AS source_set_name,
                                  sc.rarity AS source_rarity, sc.color AS source_color,
                                  sc.full_image AS source_full_image, sc.small_image AS source_small_image
                           FROM cards c JOIN batches b ON b.id = c.batch_id
                           LEFT JOIN source_cards sc ON sc.id = c.source_card_id
                           WHERE c.sku = ?""",
                        (sku,),
                    ).fetchone()
                if not row:
                    self.send_error_json("Card not found", 404)
                else:
                    item = dict(row)
                    item["source_full_image_url"] = source_media_url(item.get("source_full_image"))
                    item["source_small_image_url"] = source_media_url(item.get("source_small_image"))
                    self.send_json(item)
            elif path == "/api/labels":
                with connect() as db:
                    selected_sku = clean_text(query.get("sku", [""])[0], 40)
                    extra = "AND c.sku = ?" if selected_sku else ""
                    params = (selected_sku,) if selected_sku else ()
                    rows = db.execute(
                        f"""
                        SELECT c.*, b.game, b.set_code FROM cards c
                        JOIN batches b ON b.id = c.batch_id
                        WHERE (c.label_printed = 0 OR ? != '')
                          AND (b.status = 'COMPLETE' OR ? != '')
                          AND c.status != 'SOLD' AND c.recycled_at IS NULL {extra}
                        ORDER BY c.id
                        """,
                        ((selected_sku, selected_sku) + params),
                    ).fetchall()
                self.send_json({"labels": [dict(row) for row in rows]})
            elif path == "/api/recycle":
                search = clean_text(query.get("q", [""])[0], 100)
                params: list[object] = []
                search_sql = ""
                if search:
                    search_sql = "AND (c.sku LIKE ? OR c.name LIKE ? OR c.card_number LIKE ? OR b.batch_code LIKE ?)"
                    params.extend([f"%{search}%"] * 4)
                with connect() as db:
                    rows = db.execute(
                        f"""
                        SELECT c.*, b.game, b.set_code, b.batch_code,
                               CASE WHEN EXISTS (SELECT 1 FROM sale_items history_si WHERE history_si.card_id=c.id)
                                    THEN 1 ELSE 0 END AS protected_sale,
                               CASE WHEN EXISTS (SELECT 1 FROM rip_basis_events rbe WHERE rbe.card_id=c.id)
                                      OR EXISTS (SELECT 1 FROM economic_tombstones et WHERE et.entity_type='CARD' AND et.entity_id=c.id)
                                      OR EXISTS (SELECT 1 FROM economic_event_entries eee WHERE eee.target_type='CARD' AND eee.target_id=c.id)
                                    THEN 1 ELSE 0 END AS protected_economics,
                               (SELECT e.event_id FROM economic_tombstones et
                                  JOIN economic_events e ON e.event_id=et.event_id
                                  LEFT JOIN economic_events er ON er.reverses_event_id=e.event_id
                                 WHERE et.entity_type='CARD' AND et.entity_id=c.id AND er.event_id IS NULL
                                 ORDER BY et.id DESC LIMIT 1) AS active_disposition_event_id,
                               (SELECT pse.event_id FROM post_sale_return_items psri
                                  JOIN post_sale_events pse ON pse.event_id=psri.event_id
                                  LEFT JOIN post_sale_events psr ON psr.reverses_event_id=pse.event_id
                                 WHERE psri.item_type='CARD' AND psri.entity_id=c.id
                                   AND psri.outcome='DAMAGED_EXCLUDED' AND psr.event_id IS NULL
                                 ORDER BY psri.id DESC LIMIT 1) AS active_return_event_id,
                               (SELECT pse.order_id FROM post_sale_return_items psri
                                  JOIN post_sale_events pse ON pse.event_id=psri.event_id
                                  LEFT JOIN post_sale_events psr ON psr.reverses_event_id=pse.event_id
                                 WHERE psri.item_type='CARD' AND psri.entity_id=c.id
                                   AND psri.outcome='DAMAGED_EXCLUDED' AND psr.event_id IS NULL
                                 ORDER BY psri.id DESC LIMIT 1) AS active_return_order_id,
                               MAX(0, CAST(julianday(c.purge_after) - julianday('now') AS INTEGER)) AS days_remaining
                        FROM cards c JOIN batches b ON b.id = c.batch_id
                        WHERE c.recycled_at IS NOT NULL {search_sql}
                        ORDER BY c.recycled_at DESC
                        """,
                        params,
                    ).fetchall()
                    recycled_acquisitions = list_recycled_acquisitions(db, search)
                self.send_json({"cards": [dict(row) for row in rows], "acquisitions": recycled_acquisitions})
            elif path == "/api/sales":
                with connect() as db:
                    ids = [row[0] for row in db.execute("SELECT id FROM sale_orders ORDER BY sold_at DESC, id DESC LIMIT 100").fetchall()]
                    sales = []
                    for order_id in ids:
                        detail = post_sale_order_payload(db, int(order_id))
                        effective = detail["financials"]["effective"]
                        detail.update({
                            "merchandise_effective_cents": effective["merchandise_cents"],
                            "shipping_effective_cents": effective["shipping_cents"],
                            "fees_effective_cents": effective["marketplace_fees_cents"],
                            "postage_effective_cents": effective["postage_cents"],
                            "effective_fees_plus_postage_cents": effective["marketplace_fees_cents"] + effective["postage_cents"],
                            "net_proceeds_cents": effective["net_proceeds_cents"],
                            "subtotal": effective["merchandise_cents"] / 100,
                            "shipping_collected": effective["shipping_cents"] / 100,
                            "fees_plus_postage": (effective["marketplace_fees_cents"] + effective["postage_cents"]) / 100,
                            "net_proceeds": effective["net_proceeds_cents"] / 100,
                        })
                        sales.append(detail)
                self.send_json({"calculation_version": CALCULATION_VERSION, "sales": sales})
            elif path == "/api/qr":
                self.serve_qr(clean_text(query.get("value", [""])[0], 160))
            elif path.startswith("/media/"):
                rel = unquote(path.removeprefix("/media/"))
                self.serve_file(DATA_DIR / rel)
            elif path.startswith("/source-media/"):
                rel = unquote(path.removeprefix("/source-media/"))
                source_path = SOURCE_DB_DIR / rel
                if not source_path.is_file():
                    source_path = ONE_PIECE_REFERENCE_DIR / rel
                self.serve_file(source_path)
            elif path == "/":
                self.serve_file(STATIC_DIR / "index.html", cache=False)
            else:
                candidate = STATIC_DIR / path.lstrip("/")
                if candidate.is_file():
                    self.serve_file(candidate)
                elif "." not in Path(path).name:
                    self.serve_file(STATIC_DIR / "index.html", cache=False)
                else:
                    self.send_error(404)
        except Exception as exc:  # Keep the API response useful during the pilot.
            self.send_error_json(str(exc), 500)

    def serve_qr(self, value: str) -> None:
        if not value:
            self.send_error_json("Missing QR value")
            return
        try:
            import qrcode  # type: ignore

            image = qrcode.make(value, box_size=6, border=2)
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            body = buffer.getvalue()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(body)
        except ImportError:
            # Local no-dependency preview; Docker installs the real QR renderer.
            escaped = quote(value, safe="")
            svg = f"""<svg xmlns='http://www.w3.org/2000/svg' width='120' height='120'
              viewBox='0 0 120 120'><rect width='120' height='120' fill='white'/>
              <rect x='8' y='8' width='104' height='104' fill='none' stroke='#141918' stroke-width='5'/>
              <path d='M18 18h26v26H18zm58 0h26v26H76zM18 76h26v26H18zM54 54h12v12H54zm18 0h12v12H72zM54 72h12v12H54zm18 18h30v12H72z'
                fill='#141918'/><title>{escaped}</title></svg>""".encode()
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Content-Length", str(len(svg)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(svg)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        try:
            payload = self.read_json()
            if path == "/api/sam/source/rescan":
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = scan_source_database(db)
                    phase7_index = index_reference_library(
                        db,
                        ONE_PIECE_REFERENCE_DIR,
                        request_id=clean_text(payload.get("request_id"), 120) or f"LEGACY-RESCAN-{uuid.uuid4()}",
                    )
                    result["summary"] = source_summary(db)
                    result["phase7_index"] = phase7_index
                self.send_json(result)
            elif path == "/api/sam/metadata/refresh":
                card_numbers = payload.get("card_numbers", [])
                if not isinstance(card_numbers, list):
                    raise ValueError("card_numbers must be a list")
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = refresh_sam_metadata(
                        db, SAM_METADATA_PROVIDER, card_numbers,
                        request_id=payload.get("request_id", ""),
                    )
                self.send_json(result)
            elif path in ("/api/sam/references/index", "/api/sam/references/reindex"):
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = index_reference_library(
                        db, ONE_PIECE_REFERENCE_DIR,
                        request_id=payload.get("request_id", ""),
                    )
                self.send_json(result)
            elif re.fullmatch(r"/api/sam/recognitions/SAM-JOB-[0-9a-f-]+/decision", path):
                job_uuid = path.split("/")[4]
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = decide_recognition(db, job_uuid, payload)
                self.send_json(result)
            elif re.fullmatch(r"/api/sam/audited/cards/[A-Z0-9-]+/recognize", path):
                sku = unquote(path.split("/")[5])
                with DB_LOCK, connect() as db:
                    result = recognize_sam_audited_card(
                        db, sku, data_dir=DATA_DIR, reference_root=ONE_PIECE_REFERENCE_DIR,
                        request_id=payload.get("request_id", ""),
                    )
                self.send_json(result, 201)
            elif re.fullmatch(r"/api/sam/audited/results/SAM-AUDIT-RESULT-[0-9a-f-]+/decision", path):
                result_uuid = path.split("/")[5]
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = decide_sam_audited_result(db, result_uuid, payload)
                self.send_json(result)
            elif re.fullmatch(r"/api/sam/audited/results/SAM-AUDIT-RESULT-[0-9a-f-]+/verified-truth", path):
                result_uuid = path.split("/")[5]
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = verify_sam_audited_result(db, result_uuid, payload)
                self.send_json(result)
            elif path == "/api/catalog/products":
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = create_catalog_product(db, payload)
                self.send_json(result, 201)
            elif re.fullmatch(r"/api/catalog/products/\d+/identifiers", path):
                product_id = int(path.split("/")[4])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = add_identifier_mapping(db, product_id, payload)
                self.send_json(result, 201)
            elif re.fullmatch(r"/api/catalog/identifiers/\d+/correct", path):
                identifier_id = int(path.split("/")[4])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = correct_identifier_mapping(db, identifier_id, payload)
                self.send_json(result)
            elif path == "/api/acquisitions":
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = create_acquisition(db, payload)
                self.send_json(result, 201)
            elif re.fullmatch(r"/api/acquisitions/\d+/documents", path):
                acquisition_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = upload_source_document(db, acquisition_id, payload, DOCUMENT_STORE)
                    result["acquisition_payload"] = inbound_acquisition_payload(db, acquisition_id)
                self.send_json(result, 201)
            elif re.fullmatch(r"/api/acquisition-documents/\d+/retry", path):
                document_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = retry_source_document(db, document_id, payload, DOCUMENT_STORE)
                    acquisition_id = int(result["document"]["acquisition_id"])
                    result["acquisition_payload"] = inbound_acquisition_payload(db, acquisition_id)
                self.send_json(result, 201)
            elif re.fullmatch(r"/api/acquisition-documents/\d+/verify", path):
                document_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = verify_source_document(db, document_id, payload, DOCUMENT_STORE)
                self.send_json(result)
            elif re.fullmatch(r"/api/acquisition-documents/\d+/tombstone", path):
                document_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = tombstone_source_document(db, document_id, payload, DOCUMENT_STORE)
                    acquisition_id = int(result["document"]["acquisition_id"])
                    result["acquisition_payload"] = inbound_acquisition_payload(db, acquisition_id)
                self.send_json(result)
            elif re.fullmatch(r"/api/acquisition-documents/\d+/extractions", path):
                document_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = queue_receipt_extraction(db, document_id, payload, DOCUMENT_STORE, RECEIPT_EXTRACTOR)
                    acquisition_id = int(db.execute("SELECT acquisition_id FROM receipt_extraction_jobs WHERE id=?", (result["id"],)).fetchone()[0])
                    result["acquisition_payload"] = inbound_acquisition_payload(db, acquisition_id)
                self.send_json(result, 201)
            elif re.fullmatch(r"/api/receipt-extractions/RCPT-JOB-[0-9a-f-]+/retry", path):
                job_uuid = path.split("/")[3]
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = retry_receipt_extraction(db, job_uuid, payload, DOCUMENT_STORE, RECEIPT_EXTRACTOR)
                    acquisition_id = int(result["acquisition_id"])
                    result["acquisition_payload"] = inbound_acquisition_payload(db, acquisition_id)
                self.send_json(result, 201)
            elif re.fullmatch(r"/api/acquisitions/\d+/receipt-candidates/apply", path):
                acquisition_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = apply_receipt_proposed_facts(db, acquisition_id, payload)
                    result["acquisition_payload"] = inbound_acquisition_payload(db, acquisition_id)
                self.send_json(result)
            elif re.fullmatch(r"/api/receipt-candidates/\d+/disposition", path):
                candidate_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = receipt_candidate_disposition(db, candidate_id, payload)
                    acquisition_id = int(db.execute("SELECT acquisition_id FROM receipt_candidate_facts WHERE id=?", (candidate_id,)).fetchone()[0])
                    result["acquisition_payload"] = inbound_acquisition_payload(db, acquisition_id)
                self.send_json(result)
            elif re.fullmatch(r"/api/receipt-lines/\d+/classification", path):
                receipt_line_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = classify_receipt_line(db, receipt_line_id, payload)
                    acquisition_id = int(db.execute("SELECT acquisition_id FROM receipt_lines WHERE id=?", (receipt_line_id,)).fetchone()[0])
                    result["acquisition_payload"] = inbound_acquisition_payload(db, acquisition_id)
                self.send_json(result)
            elif re.fullmatch(r"/api/receipt-semantic-lines/RCPT-SEM-[0-9a-f-]+/decision", path):
                semantic_uuid = path.split("/")[3]
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = decide_semantic_line(db, semantic_uuid, payload)
                    reconcile_semantic_merchandise_line(
                        db, result, str(payload.get("request_id") or "RECEIPT-SEMANTIC")
                    )
                    acquisition_id = int(result["acquisition_id"])
                    result["acquisition_payload"] = inbound_acquisition_payload(db, acquisition_id)
                self.send_json(result)
            elif re.fullmatch(r"/api/receipt-line-matches/\d+/disposition", path):
                match_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = receipt_match_disposition(db, match_id, payload)
                    acquisition_id = int(db.execute("SELECT r.acquisition_id FROM receipt_line_matches m JOIN receipt_lines r ON r.id=m.receipt_line_id WHERE m.id=?", (match_id,)).fetchone()[0])
                    result["acquisition_payload"] = inbound_acquisition_payload(db, acquisition_id)
                self.send_json(result)
            elif re.fullmatch(r"/api/acquisitions/\d+/receipt-allocation-proposals", path):
                acquisition_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = generate_receipt_allocation_proposal(db, acquisition_id, payload)
                    result["acquisition_payload"] = inbound_acquisition_payload(db, acquisition_id)
                self.send_json(result, 201)
            elif re.fullmatch(r"/api/acquisitions/\d+/receipt-manual-fallback", path):
                acquisition_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = select_receipt_manual_fallback(db, acquisition_id, payload)
                    result["acquisition_payload"] = inbound_acquisition_payload(db, acquisition_id)
                self.send_json(result)
            elif re.fullmatch(r"/api/acquisitions/\d+/product-scan", path):
                acquisition_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = scan_apply_product(db, acquisition_id, payload)
                self.send_json(result)
            elif re.fullmatch(r"/api/acquisitions/\d+/identify-product", path):
                acquisition_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = identify_unknown_product(db, acquisition_id, payload)
                self.send_json(result)
            elif re.fullmatch(r"/api/acquisitions/\d+/lines", path):
                acquisition_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = add_acquisition_line(db, acquisition_id, payload)
                self.send_json(result, 201)
            elif re.fullmatch(r"/api/acquisitions/\d+/reconciliation", path):
                acquisition_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = mark_reconciliation_required(db, acquisition_id, payload)
                self.send_json(result)
            elif re.fullmatch(r"/api/acquisition-lines/\d+/catalog-product", path):
                line_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = apply_catalog_product_to_line(db, line_id, payload)
                self.send_json(result)
            elif re.fullmatch(r"/api/acquisitions/\d+/confirm", path):
                acquisition_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = confirm_acquisition(db, acquisition_id, payload)
                self.send_json(result)
            elif re.fullmatch(r"/api/acquisitions/\d+/intake-routing/preview", path):
                acquisition_id = int(path.split("/")[3])
                with connect() as db:
                    result = intake_preview(db, acquisition_id, payload)
                self.send_json(result)
            elif re.fullmatch(r"/api/acquisitions/\d+/intake-routing/additional/preview", path):
                acquisition_id = int(path.split("/")[3])
                with connect() as db:
                    result = intake_preview(db, acquisition_id, payload)
                self.send_json(result)
            elif re.fullmatch(r"/api/acquisitions/\d+/intake-routing/confirm", path):
                acquisition_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = confirm_intake_routing(db, acquisition_id, payload)
                self.send_json(result)
            elif re.fullmatch(r"/api/acquisitions/\d+/intake-routing/additional/confirm", path):
                acquisition_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = confirm_intake_routing(db, acquisition_id, payload)
                self.send_json(result)
            elif re.fullmatch(r"/api/acquisitions/\d+/cancel", path):
                acquisition_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = cancel_acquisition(db, acquisition_id, payload)
                self.send_json(result)
            elif re.fullmatch(r"/api/acquisitions/\d+/recycle", path):
                acquisition_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = recycle_draft_acquisition(db, acquisition_id, payload)
                self.send_json(result)
            elif re.fullmatch(r"/api/acquisitions/\d+/restore", path):
                acquisition_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = restore_recycled_acquisition(db, acquisition_id, payload)
                self.send_json(result)
            elif re.fullmatch(r"/api/acquisition-lines/\d+/confirm-allocation", path):
                line_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = confirm_line_allocation(db, line_id, payload)
                self.send_json(result)
            elif re.fullmatch(r"/api/acquisition-lines/\d+/cancel", path):
                line_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = cancel_acquisition_line(db, line_id, payload)
                self.send_json(result)
            elif path == "/api/batches":
                game = clean_text(payload.get("game"), 40)
                set_code = clean_text(payload.get("set_code"), 40).upper()
                acquisition = clean_text(payload.get("acquisition_type"), 40)
                if game not in GAME_PREFIXES or not set_code or not acquisition:
                    raise ValueError("Game, set, and acquisition type are required")
                economics = None
                if "economics_mode" in payload:
                    economics = normalize_acquisition_input(payload)
                with connect() as db:
                    code = make_batch_code(db, game)
                    location = clean_text(payload.get("location"), 80)
                    if not location:
                        color = clean_text(payload.get("color"), 40)
                        location = f"{set_code}-{color}" if color else set_code
                    now = utcnow()
                    base_fields = {
                        "batch_code": code,
                        "created_at": now,
                        "game": game,
                        "set_code": set_code,
                        "set_name": clean_text(payload.get("set_name")),
                        "color": clean_text(payload.get("color"), 40),
                        "finish_group": clean_text(payload.get("finish_group"), 60) or "Non-Foil",
                        "default_condition": clean_text(payload.get("default_condition"), 40) or "Near Mint",
                        "acquisition_type": acquisition,
                        "total_cost": money(payload.get("total_cost")),
                        "location": location,
                        "notes": clean_text(payload.get("notes"), 500),
                        "scan_order": "BACK_FIRST" if payload.get("scan_order") == "BACK_FIRST" else "FRONT_FIRST",
                        "scan_mode": "FRONT_ONLY" if payload.get("scan_mode") == "FRONT_ONLY" else "FRONT_BACK",
                    }
                    if economics is not None:
                        for field in EDITABLE_FIELDS:
                            base_fields[field] = economics[field]
                        base_fields["reporting_currency"] = "USD"
                        base_fields["economics_status"] = (
                            "ESTIMATED" if economics["economics_mode"] == "LEGACY" else "DRAFT"
                        )
                        base_fields["acquisition_updated_at"] = now
                        final_cents = economics["final_usd_paid_cents"]
                        base_fields["total_cost"] = 0.0 if final_cents is None else final_cents / 100
                    columns = ", ".join(base_fields)
                    placeholders = ", ".join("?" for _ in base_fields)
                    cursor = db.execute(
                        f"INSERT INTO batches ({columns}) VALUES ({placeholders})",
                        tuple(base_fields.values()),
                    )
                    if economics is not None:
                        synchronize_sealed_units(db, int(cursor.lastrowid))
                    if economics is not None:
                        log_action(
                            db,
                            "ACQUISITION_CREATE",
                            f"Recorded acquisition facts for {code}",
                            {"batch_id": cursor.lastrowid, "facts": {field: economics[field] for field in EDITABLE_FIELDS}},
                        )
                    batch = dict(db.execute("SELECT * FROM batches WHERE id = ?", (cursor.lastrowid,)).fetchone())
                (INBOUND_DIR / code).mkdir(parents=True, exist_ok=True)
                self.send_json(batch, 201)
            elif re.fullmatch(r"/api/batches/\d+/rips", path):
                batch_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = create_rip_session(db, batch_id, payload)
                self.send_json(result, 201)
            elif re.fullmatch(r"/api/batches/\d+/corrections/acquisition", path):
                batch_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = correct_acquisition_cost(db, batch_id, payload)
                self.send_json(result, 201)
            elif re.fullmatch(r"/api/batches/\d+/corrections/basis-transfer", path):
                batch_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = transfer_basis(db, batch_id, payload)
                self.send_json(result, 201)
            elif re.fullmatch(r"/api/cards/[A-Z0-9-]+/disposition", path):
                sku = unquote(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = dispose_card(db, sku, payload)
                self.send_json(result, 201)
            elif re.fullmatch(r"/api/sealed-units/\d+/disposition", path):
                unit_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = dispose_sealed_unit(db, unit_id, payload)
                self.send_json(result, 201)
            elif re.fullmatch(r"/api/economic-events/[^/]+/reverse", path):
                event_id = unquote(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = reverse_event(db, event_id, payload)
                self.send_json(result, 201)
            elif re.fullmatch(r"/api/sales/\d+/(refunds|full-refund|returns|chargebacks|fee-credits|postage-refunds|corrections)", path):
                parts = path.split("/")
                order_id = int(parts[3])
                action = parts[4]
                handlers = {
                    "refunds": lambda db: create_refund(db, order_id, payload),
                    "full-refund": lambda db: create_refund(db, order_id, payload, full=True),
                    "returns": lambda db: create_return(db, order_id, payload),
                    "chargebacks": lambda db: create_chargeback(db, order_id, payload),
                    "fee-credits": lambda db: create_fee_credit(db, order_id, payload),
                    "postage-refunds": lambda db: create_postage_refund(db, order_id, payload),
                    "corrections": lambda db: create_sale_correction(db, order_id, payload),
                }
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = handlers[action](db)
                self.send_json(result, 201)
            elif re.fullmatch(r"/api/post-sale-events/[^/]+/reverse", path):
                event_id = unquote(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = reverse_post_sale_event(db, event_id, payload)
                self.send_json(result, 201)
            elif path == "/api/sealed-sales/preview":
                with connect() as db:
                    result = sealed_sale_preview(db, payload)
                self.send_json(result)
            elif path == "/api/sealed-sales":
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = create_sealed_sale(db, payload, business_today(db).isoformat())
                    capture_sale_input_evidence(db, int(result["id"]), payload, order_type="SEALED")
                self.send_json(result, 201)
            elif re.fullmatch(r"/api/sealed-sales/\d+/undo", path):
                order_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = undo_specific_sealed_sale(db, order_id)
                self.send_json(result)
            elif re.fullmatch(r"/api/sealed-units/\d+/adjust", path):
                unit_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = adjust_sealed_unit(db, unit_id, payload)
                self.send_json(result, 201)
            elif re.fullmatch(r"/api/rip-sessions/\d+/activate", path):
                rip_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    current = db.execute(
                        """SELECT r.*, b.batch_code, b.scan_order, b.scan_mode
                           FROM settings s JOIN rip_sessions r ON r.id=CAST(s.value AS INTEGER)
                           JOIN batches b ON b.id=r.batch_id
                           WHERE s.key='active_rip_session_id' AND s.value<>'' AND r.status='ACTIVE'"""
                    ).fetchone()
                    if current and current["id"] != rip_id:
                        pending = unprocessed_scanner_file_count(db, current)
                        if pending and not payload.get("confirm_switch"):
                            self.send_json(
                                {
                                    "error": f"{pending} unprocessed scanner file(s) remain for {current['rip_code']}",
                                    "requires_confirmation": True,
                                    "unprocessed_files": pending,
                                    "active_rip_session_id": current["id"],
                                },
                                409,
                            )
                            return
                    result = activate_rip(db, rip_id)
                self.send_json(result)
            elif re.fullmatch(r"/api/rip-sessions/\d+/deactivate", path):
                rip_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    result = deactivate_rip(db, rip_id)
                self.send_json(result)
            elif re.fullmatch(r"/api/rip-sessions/\d+/preview", path):
                rip_id = int(path.split("/")[3])
                with connect() as db:
                    result = allocation_preview(db, rip_id, payload)
                self.send_json(result)
            elif re.fullmatch(r"/api/rip-sessions/\d+/finalize", path):
                rip_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    result = finalize_rip(db, rip_id, payload)
                self.send_json(result)
            elif re.fullmatch(r"/api/rip-sessions/\d+/corrections", path):
                rip_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    result = correct_rip(db, rip_id, payload)
                self.send_json(result, 201)
            elif re.fullmatch(r"/api/batches/\d+/cards", path):
                batch_id = int(path.split("/")[3])
                with connect() as db:
                    batch = db.execute("SELECT * FROM batches WHERE id = ? AND recycled_at IS NULL", (batch_id,)).fetchone()
                    if not batch:
                        self.send_error_json("Batch not found", 404)
                        return
                    if batch["status"] != "OPEN":
                        raise ValueError("Reopen this batch before adding cards")
                    card = create_card(db, batch, payload)
                self.send_json(card, 201)
            elif re.fullmatch(r"/api/batches/\d+/cards/bulk", path):
                batch_id = int(path.split("/")[3])
                items = payload.get("cards", [])
                if not isinstance(items, list) or not items:
                    raise ValueError("Add at least one front/back image pair")
                if len(items) > 100:
                    raise ValueError("A browser upload is limited to 100 cards at a time")
                with connect() as db:
                    batch = db.execute("SELECT * FROM batches WHERE id = ? AND recycled_at IS NULL", (batch_id,)).fetchone()
                    if not batch:
                        self.send_error_json("Batch not found", 404)
                        return
                    if batch["status"] != "OPEN":
                        raise ValueError("Reopen this batch before adding cards")
                    cards = [create_card(db, batch, item if isinstance(item, dict) else {}) for item in items]
                self.send_json({"cards": cards, "created": len(cards)}, 201)
            elif re.fullmatch(r"/api/batches/\d+/sam(?:/recognize)?", path):
                batch_id = int(path.split("/")[3])
                requested = payload.get("skus", [])
                if requested is not None and not isinstance(requested, list):
                    raise ValueError("Selected SKUs must be a list")
                requested_skus = [clean_text(sku, 40).upper() for sku in requested if clean_text(sku, 40)]
                with DB_LOCK, connect() as db:
                    batch = db.execute("SELECT * FROM batches WHERE id = ? AND recycled_at IS NULL", (batch_id,)).fetchone()
                    if not batch:
                        self.send_error_json("Batch not found", 404)
                        return
                    params: list[object] = [batch_id]
                    where = "batch_id = ? AND recycled_at IS NULL"
                    if requested_skus:
                        placeholders = ",".join("?" for _ in requested_skus)
                        where += f" AND sku IN ({placeholders})"
                        params.extend(requested_skus)
                    cards = db.execute(f"SELECT * FROM cards WHERE {where} ORDER BY id", params).fetchall()
                    if path.endswith("/recognize"):
                        base_request_id = clean_text(payload.get("request_id"), 100) or f"SAM-BATCH-{uuid.uuid4()}"
                        results = [
                            submit_recognition_for_sku(
                                db, card["sku"], data_dir=DATA_DIR,
                                request_id=f"{base_request_id}-{card['id']}",
                            )
                            for card in cards
                        ]
                    else:
                        results = [sam_match_card(db, card, batch) for card in cards]
                if not path.endswith("/recognize"):
                    matched = sum(1 for result in results if result.get("matched"))
                    self.send_json({"batch_id": batch_id, "matched": matched, "checked": len(results), "results": results})
                    return
                matched = sum(1 for result in results if result.get("effective_state") in ("AUTO_MATCHED", "OPERATOR_CONFIRMED", "OPERATOR_CORRECTED"))
                self.send_json({
                    "batch_id": batch_id, "matched": matched, "checked": len(results),
                    "needs_review": sum(1 for result in results if result.get("effective_state") == "NEEDS_REVIEW"),
                    "unidentified": sum(1 for result in results if result.get("effective_state") == "UNIDENTIFIED"),
                    "scanning_blocked": False, "results": results,
                })
            elif re.fullmatch(r"/api/batches/\d+/complete", path):
                batch_id = int(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    previous = db.execute("SELECT * FROM batches WHERE id = ? AND recycled_at IS NULL", (batch_id,)).fetchone()
                    if not previous:
                        self.send_error_json("Batch not found", 404)
                        return
                    active_rip = db.execute(
                        """SELECT r.id
                           FROM rip_sessions r
                           JOIN settings s
                             ON s.key = 'active_rip_session_id'
                            AND s.value = CAST(r.id AS TEXT)
                           WHERE r.batch_id = ? AND r.status = 'ACTIVE'""",
                        (batch_id,),
                    ).fetchone()
                    if active_rip:
                        deactivate_rip(db, active_rip["id"])
                    db.execute(
                        "UPDATE batches SET status = 'COMPLETE', completed_at = ? WHERE id = ?",
                        (utcnow(), batch_id),
                    )
                    log_action(db, "BATCH_STATUS", f"Completed {previous['batch_code']}", {
                        "batch_id": batch_id, "old_status": previous["status"],
                        "old_completed_at": previous["completed_at"],
                    })
                    batch = db.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
                if not batch:
                    self.send_error_json("Batch not found", 404)
                else:
                    self.send_json(dict(batch))
            elif re.fullmatch(r"/api/batches/\d+/reopen", path):
                batch_id = int(path.split("/")[3])
                with connect() as db:
                    previous = db.execute("SELECT * FROM batches WHERE id = ? AND recycled_at IS NULL", (batch_id,)).fetchone()
                    if not previous:
                        self.send_error_json("Batch not found", 404)
                        return
                    db.execute("UPDATE batches SET status = 'OPEN' WHERE id = ?", (batch_id,))
                    log_action(db, "BATCH_STATUS", f"Reopened {previous['batch_code']}", {
                        "batch_id": batch_id, "old_status": previous["status"],
                        "old_completed_at": previous["completed_at"],
                    })
                    batch = db.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
                self.send_json(dict(batch))
            elif re.fullmatch(r"/api/batches/\d+/recycle", path):
                batch_id = int(path.split("/")[3])
                reason = clean_text(payload.get("reason"), 240)
                with connect() as db:
                    batch = db.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
                    if not batch:
                        self.send_error_json("Batch not found", 404)
                        return
                    if batch["recycled_at"]:
                        raise ValueError("Batch is already in the Recycle Bin")
                    cards = db.execute(
                        "SELECT id, sku FROM cards WHERE batch_id = ? AND recycled_at IS NULL ORDER BY id",
                        (batch_id,),
                    ).fetchall()
                    retention = max(1, int(setting(db, "recycle_retention_days", "180")))
                    recycled_at = utcnow()
                    purge_after = (datetime.now(timezone.utc) + timedelta(days=retention)).isoformat(timespec="seconds")
                    db.execute(
                        "UPDATE batches SET recycled_at = ?, recycle_reason = ?, purge_after = ? WHERE id = ?",
                        (recycled_at, reason, purge_after, batch_id),
                    )
                    if cards:
                        db.execute(
                            """UPDATE cards SET recycled_at = ?, recycle_reason = ?, purge_after = ?,
                                      pre_recycle_status = status, updated_at = ?
                               WHERE batch_id = ? AND recycled_at IS NULL""",
                            (recycled_at, reason or f"Batch {batch['batch_code']} recycled", purge_after, recycled_at, batch_id),
                        )
                    log_action(db, "BATCH_RECYCLE", f"Moved {batch['batch_code']} to Recycle Bin", {
                        "batch_id": batch_id,
                        "batch_code": batch["batch_code"],
                        "recycled_at": recycled_at,
                        "reason": reason,
                        "purge_after": purge_after,
                        "cards": [dict(row) for row in cards],
                    })
                    updated = db.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
                self.send_json({"batch": dict(updated), "recycled": len(cards), "skus": [row["sku"] for row in cards]})
            elif re.fullmatch(r"/api/cards/[A-Z0-9-]+/swap-images", path):
                sku = unquote(path.split("/")[3])
                with connect() as db:
                    card = db.execute("SELECT * FROM cards WHERE sku = ?", (sku,)).fetchone()
                    if not card:
                        self.send_error_json("Card not found", 404)
                        return
                    if not card["front_image"] or not card["back_image"]:
                        raise ValueError("Both card images are required before they can be swapped")
                    db.execute(
                        "UPDATE cards SET front_image = ?, back_image = ?, updated_at = ? WHERE sku = ?",
                        (card["back_image"], card["front_image"], utcnow(), sku),
                    )
                    log_action(db, "IMAGE_SWAP", f"Swapped images for {sku}", {"sku": sku})
                    card = db.execute("SELECT * FROM cards WHERE sku = ?", (sku,)).fetchone()
                self.send_json(dict(card))
            elif re.fullmatch(r"/api/cards/[A-Z0-9-]+/sam(?:/recognize)?", path):
                sku = unquote(path.split("/")[3])
                with DB_LOCK, connect() as db:
                    if path.endswith("/recognize"):
                        db.execute("BEGIN IMMEDIATE")
                        result = submit_recognition_for_sku(
                            db, sku, data_dir=DATA_DIR,
                            request_id=clean_text(payload.get("request_id"), 120) or f"SAM-CARD-{uuid.uuid4()}",
                        )
                    else:
                        card = db.execute("SELECT * FROM cards WHERE sku = ?", (sku,)).fetchone()
                        if not card:
                            self.send_error_json("Card not found", 404)
                            return
                        batch = db.execute("SELECT * FROM batches WHERE id = ?", (card["batch_id"],)).fetchone()
                        result = sam_match_card(db, card, batch)
                if not path.endswith("/recognize"):
                    self.send_json(result)
                    return
                result["matched"] = result.get("effective_state") in ("AUTO_MATCHED", "OPERATOR_CONFIRMED", "OPERATOR_CORRECTED")
                result["confidence"] = result["job"]["confidence"]
                result["match_source"] = "SAM Phase 7"
                result["source"] = result.get("top_candidate")
                result["reason"] = "Operator review required" if result.get("effective_state") == "NEEDS_REVIEW" else "No trustworthy identity" if result.get("effective_state") == "UNIDENTIFIED" else "Trusted identity"
                self.send_json(result)
            elif re.fullmatch(r"/api/cards/[A-Z0-9-]+/recycle", path):
                sku = unquote(path.split("/")[3])
                reason = clean_text(payload.get("reason"), 240)
                with connect() as db:
                    card = db.execute("SELECT * FROM cards WHERE sku = ?", (sku,)).fetchone()
                    if not card:
                        self.send_error_json("Card not found", 404)
                        return
                    if card["recycled_at"]:
                        raise ValueError("Card is already in the Recycle Bin")
                    retention = max(1, int(setting(db, "recycle_retention_days", "180")))
                    recycled_at = utcnow()
                    purge_after = (datetime.now(timezone.utc) + timedelta(days=retention)).isoformat(timespec="seconds")
                    db.execute(
                        """UPDATE cards SET recycled_at = ?, recycle_reason = ?, purge_after = ?,
                                  pre_recycle_status = status, updated_at = ? WHERE sku = ?""",
                        (recycled_at, reason, purge_after, recycled_at, sku),
                    )
                    log_action(db, "RECYCLE", f"Moved {sku} to Recycle Bin", {"sku": sku})
                    card = db.execute("SELECT * FROM cards WHERE sku = ?", (sku,)).fetchone()
                self.send_json(dict(card))
            elif re.fullmatch(r"/api/cards/[A-Z0-9-]+/restore", path):
                sku = unquote(path.split("/")[3])
                with connect() as db:
                    card = db.execute("SELECT * FROM cards WHERE sku = ?", (sku,)).fetchone()
                    if not card:
                        self.send_error_json("Card not found", 404)
                        return
                    if not card["recycled_at"]:
                        raise ValueError("Card is not in the Recycle Bin")
                    active_disposition = db.execute(
                        """SELECT e.event_id FROM economic_tombstones et
                             JOIN economic_events e ON e.event_id=et.event_id
                             LEFT JOIN economic_events er ON er.reverses_event_id=e.event_id
                            WHERE et.entity_type='CARD' AND et.entity_id=? AND er.event_id IS NULL
                            ORDER BY et.id DESC LIMIT 1""",
                        (card["id"],),
                    ).fetchone()
                    if active_disposition:
                        raise ValueError(f"Restore this card by reversing economic event {active_disposition['event_id']}")
                    active_return = db.execute(
                        """SELECT pse.event_id FROM post_sale_return_items psri
                             JOIN post_sale_events pse ON pse.event_id=psri.event_id
                             LEFT JOIN post_sale_events reversal ON reversal.reverses_event_id=pse.event_id
                            WHERE psri.item_type='CARD' AND psri.entity_id=?
                              AND psri.outcome='DAMAGED_EXCLUDED' AND reversal.event_id IS NULL
                            LIMIT 1""",
                        (card["id"],),
                    ).fetchone()
                    if active_return:
                        raise ValueError(f"Restore this card by reversing post-sale event {active_return['event_id']} from Sales")
                    log_action(db, "RESTORE", f"Restored {sku}", {
                        "sku": sku, "recycled_at": card["recycled_at"],
                        "reason": card["recycle_reason"], "purge_after": card["purge_after"],
                    })
                    db.execute(
                        """UPDATE cards SET recycled_at = NULL, recycle_reason = '', purge_after = NULL,
                                  status = COALESCE(pre_recycle_status, status), pre_recycle_status = NULL,
                                  updated_at = ? WHERE sku = ?""",
                        (utcnow(), sku),
                    )
                    db.execute(
                        "UPDATE batches SET recycled_at = NULL, recycle_reason = '', purge_after = NULL WHERE id = ?",
                        (card["batch_id"],),
                    )
                    card = db.execute("SELECT * FROM cards WHERE sku = ?", (sku,)).fetchone()
                self.send_json(dict(card))
            elif re.fullmatch(r"/api/cards/[A-Z0-9-]+/purge", path):
                sku = unquote(path.split("/")[3])
                with connect() as db:
                    card = db.execute("SELECT * FROM cards WHERE sku = ?", (sku,)).fetchone()
                    if not card:
                        self.send_error_json("Card not found", 404)
                        return
                    if not card["recycled_at"]:
                        raise ValueError("Move the card to the Recycle Bin before permanently deleting it")
                    if db.execute("SELECT 1 FROM sale_items WHERE card_id = ?", (card["id"],)).fetchone():
                        raise ValueError("Sold cards are protected for financial and audit history")
                    if card_has_economic_history(db, int(card["id"])):
                        raise ValueError("Cards with economic history are protected by a durable tombstone and cannot be hard-deleted")
                    db.execute("DELETE FROM cards WHERE id = ?", (card["id"],))
                    now = utcnow()
                    db.execute(
                        """INSERT INTO activity_log
                           (created_at, action_type, description, payload, undone_at)
                           VALUES (?, 'PERMANENT_PURGE', ?, ?, ?)""",
                        (now, f"Permanently deleted {sku}", json.dumps({"sku": sku}), now),
                    )
                card_dir = IMAGE_DIR / sku
                if card_dir.is_dir() and card_dir.resolve().is_relative_to(IMAGE_DIR.resolve()):
                    shutil.rmtree(card_dir)
                self.send_json({"sku": sku, "purged": True})
            elif path == "/api/labels/printed":
                skus = payload.get("skus", [])
                if not isinstance(skus, list) or not skus:
                    raise ValueError("Select at least one label")
                with connect() as db:
                    placeholders = ",".join("?" for _ in skus)
                    db.execute(f"UPDATE cards SET label_printed = 1 WHERE sku IN ({placeholders})", skus)
                self.send_json({"updated": len(skus)})
            elif path == "/api/labels/requeue":
                sku = clean_text(payload.get("sku"), 40).upper()
                if not sku:
                    raise ValueError("SKU is required")
                with connect() as db:
                    cursor = db.execute(
                        """UPDATE cards SET label_printed = 0 WHERE sku = ? AND status != 'SOLD'
                           AND recycled_at IS NULL AND batch_id IN
                               (SELECT id FROM batches WHERE status = 'COMPLETE')""",
                        (sku,),
                    )
                if not cursor.rowcount:
                    raise ValueError("Card was not found or is already sold")
                self.send_json({"sku": sku, "queued": True})
            elif path == "/api/settings":
                timezone_name = clean_text(payload.get("timezone"), 80) or DEFAULT_TIMEZONE
                business_timezone(timezone_name)
                try:
                    capacity = max(1, int(payload.get("tcg_capacity", DEFAULT_TCG_CAPACITY)))
                except (TypeError, ValueError) as exc:
                    raise ValueError("TCGplayer capacity must be a whole number") from exc
                with connect() as db:
                    db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('timezone', ?)", (timezone_name,))
                    db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('tcg_capacity', ?)", (str(capacity),))
                    retention = max(1, int(payload.get("recycle_retention_days", setting(db, "recycle_retention_days", "180"))))
                    auto_purge = "1" if str(payload.get("recycle_auto_purge", "0")) in ("1", "true", "on") else "0"
                    db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('recycle_retention_days', ?)", (str(retention),))
                    db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('recycle_auto_purge', ?)", (auto_purge,))
                self.send_json({"timezone": timezone_name, "tcg_capacity": capacity, "recycle_retention_days": retention, "recycle_auto_purge": auto_purge})
            elif path == "/api/undo":
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = undo_last_action(db)
                self.send_json(result)
            elif path == "/api/sales":
                skus = payload.get("skus", [])
                if payload.get("sealed_unit_ids"):
                    raise ValueError("Card and sealed-product items cannot be combined in one order")
                platform = clean_text(payload.get("platform"), 30)
                if platform not in ("eBay", "TCGplayer") or not isinstance(skus, list) or not skus:
                    raise ValueError("Platform and at least one SKU are required")
                unique_skus = list(dict.fromkeys(clean_text(sku, 40) for sku in skus))
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    placeholders = ",".join("?" for _ in unique_skus)
                    cards = db.execute(
                        f"SELECT * FROM cards WHERE sku IN ({placeholders})", unique_skus
                    ).fetchall()
                    if len(cards) != len(unique_skus):
                        found = {row["sku"] for row in cards}
                        raise ValueError("Unknown SKU: " + ", ".join(s for s in unique_skus if s not in found))
                    unavailable = [row["sku"] for row in cards if row["status"] == "SOLD" or row["recycled_at"]]
                    if unavailable:
                        raise ValueError("Already sold: " + ", ".join(unavailable))
                    subtotal = money(payload.get("subtotal"))
                    cursor = db.execute(
                        """
                        INSERT INTO sale_orders (
                            platform, order_number, sold_at, subtotal, shipping_collected,
                            platform_fees, postage_cost, notes, order_type,
                            merchandise_total_cents, shipping_collected_cents,
                            marketplace_fees_cents, actual_postage_cents
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'CARD', ?, ?, ?, ?)
                        """,
                        (
                            platform, clean_text(payload.get("order_number"), 80),
                            clean_text(payload.get("sold_at"), 30) or business_today(db).isoformat(),
                            subtotal, money(payload.get("shipping_collected")),
                            money(payload.get("platform_fees")), money(payload.get("postage_cost")),
                            clean_text(payload.get("notes"), 500),
                            int(round(subtotal * 100)),
                            int(round(money(payload.get("shipping_collected")) * 100)),
                            int(round(money(payload.get("platform_fees")) * 100)),
                            int(round(money(payload.get("postage_cost")) * 100)),
                        ),
                    )
                    order_id = cursor.lastrowid
                    capture_sale_input_evidence(db, int(order_id), payload, order_type="CARD")
                    per_item = round(subtotal / len(cards), 2)
                    for card in cards:
                        db.execute(
                            "INSERT INTO sale_items (order_id, card_id, sale_price) VALUES (?, ?, ?)",
                            (order_id, card["id"], per_item),
                        )
                        changed = db.execute(
                            """UPDATE cards SET status = 'SOLD', updated_at = ?
                               WHERE id = ? AND status <> 'SOLD' AND recycled_at IS NULL""",
                            (utcnow(), card["id"]),
                        )
                        if changed.rowcount != 1:
                            raise sqlite3.IntegrityError("A card was sold by another operation")
                    log_action(db, "SALE", f"Completed {platform} order with {len(cards)} card(s)", {
                        "order_id": order_id,
                        "cards": [{"id": card["id"], "status": card["status"]} for card in cards],
                    })
                    order = dict(db.execute("SELECT * FROM sale_orders WHERE id = ?", (order_id,)).fetchone())
                self.send_json(order, 201)
            else:
                self.send_error_json("Not found", 404)
        except ValueError as exc:
            self.send_error_json(str(exc), 400)
        except sqlite3.IntegrityError as exc:
            self.send_error_json(f"Database conflict: {exc}", 409)
        except Exception as exc:
            self.send_error_json(str(exc), 500)

    def do_PATCH(self) -> None:
        path = urlparse(self.path).path.rstrip("/")
        try:
            payload = self.read_json()
            acquisition_match = re.fullmatch(r"/api/acquisitions/(\d+)", path)
            if acquisition_match:
                acquisition_id = int(acquisition_match.group(1))
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = autosave_acquisition(db, acquisition_id, payload)
                self.send_json(result)
                return
            line_match = re.fullmatch(r"/api/acquisition-lines/(\d+)", path)
            if line_match:
                line_id = int(line_match.group(1))
                with DB_LOCK, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    result = autosave_acquisition_line(db, line_id, payload)
                self.send_json(result)
                return
            economics_match = re.fullmatch(r"/api/batches/(\d+)/economics", path)
            if economics_match:
                batch_id = int(economics_match.group(1))
                with DB_LOCK, connect() as db:
                    previous = db.execute(
                        "SELECT * FROM batches WHERE id = ? AND recycled_at IS NULL", (batch_id,)
                    ).fetchone()
                    if not previous:
                        self.send_error_json("Batch not found", 404)
                        return
                    if previous["economics_status"] == "FINALIZED":
                        raise ValueError("Finalized economics require the audited correction workflow")
                    economics = normalize_acquisition_input(payload, dict(previous))
                    if acquisition_has_used_units(db, batch_id) and any(
                        previous[field] != economics[field] for field in EDITABLE_FIELDS
                    ):
                        raise ValueError(
                            "Acquisition facts are locked after a sealed unit is opened, sold, or adjusted"
                        )
                    updates = {field: economics[field] for field in EDITABLE_FIELDS}
                    updates["reporting_currency"] = "USD"
                    updates["economics_status"] = (
                        "ESTIMATED" if economics["economics_mode"] == "LEGACY" else "DRAFT"
                    )
                    updates["acquisition_updated_at"] = utcnow()
                    final_cents = economics["final_usd_paid_cents"]
                    updates["total_cost"] = 0.0 if final_cents is None else final_cents / 100
                    changed = {
                        field: {"before": previous[field], "after": value}
                        for field, value in updates.items()
                        if previous[field] != value
                    }
                    if changed:
                        assignments = ", ".join(f"{field} = ?" for field in updates)
                        db.execute(
                            f"UPDATE batches SET {assignments} WHERE id = ?",
                            [*updates.values(), batch_id],
                        )
                        synchronize_sealed_units(db, batch_id)
                        log_action(
                            db,
                            "ACQUISITION_UPDATE",
                            f"Updated acquisition facts for {previous['batch_code']}",
                            {"batch_id": batch_id, "changes": changed},
                        )
                    facts = acquisition_payload(db, batch_id)
                self.send_json(facts)
                return
            batch_match = re.fullmatch(r"/api/batches/(\d+)", path)
            if batch_match:
                allowed = {"color", "finish_group", "location", "scan_order", "scan_mode"}
                updates = {
                    key: clean_text(value, 80)
                    for key, value in payload.items()
                    if key in allowed
                }
                if not updates:
                    raise ValueError("No scan-group fields supplied")
                if "scan_order" in updates and updates["scan_order"] not in ("FRONT_FIRST", "BACK_FIRST"):
                    raise ValueError("Scan order must be Front First or Back First")
                if "scan_mode" in updates and updates["scan_mode"] not in ("FRONT_BACK", "FRONT_ONLY"):
                    raise ValueError("Scan type must be Front + Back or Front Only")
                assignments = ", ".join(f"{key} = ?" for key in updates)
                with connect() as db:
                    batch_id = int(batch_match.group(1))
                    if not db.execute("SELECT 1 FROM batches WHERE id = ? AND recycled_at IS NULL", (batch_id,)).fetchone():
                        self.send_error_json("Batch not found", 404)
                        return
                    db.execute(f"UPDATE batches SET {assignments} WHERE id = ?", [*updates.values(), batch_id])
                    row = db.execute(
                        "SELECT * FROM batches WHERE id = ?", (batch_id,)
                    ).fetchone()
                if not row:
                    self.send_error_json("Batch not found", 404)
                else:
                    self.send_json(dict(row))
                return
            match = re.fullmatch(r"/api/cards/([A-Z0-9-]+)", path)
            if not match:
                self.send_error_json("Not found", 404)
                return
            sku = unquote(match.group(1))
            allowed = {
                "card_number", "name", "set_name", "rarity", "color", "variant",
                "condition", "status", "location", "market_low", "market_average",
                "market_high", "listing_platform", "listing_price", "listing_reference",
            }
            updates = {key: value for key, value in payload.items() if key in allowed}
            if not updates:
                raise ValueError("No editable fields supplied")
            for field in ("market_low", "market_average", "market_high", "listing_price"):
                if field in updates:
                    updates[field] = money(updates[field]) if updates[field] not in (None, "") else None
            for field in set(updates) - {"market_low", "market_average", "market_high", "listing_price"}:
                updates[field] = clean_text(updates[field], 180)
            if any(field in updates for field in ("market_low", "market_average", "market_high")):
                updates["market_updated_at"] = utcnow()
            updates["updated_at"] = utcnow()
            with connect() as db:
                previous = db.execute("SELECT * FROM cards WHERE sku = ?", (sku,)).fetchone()
                if not previous:
                    self.send_error_json("Card not found", 404)
                    return
                family_edited = any(field in updates for field in ("card_number", "name", "set_name"))
                printing_text_edited = any(field in updates for field in ("variant", "rarity"))
                family = None
                if family_edited:
                    family_game = db.execute(
                        "SELECT game FROM batches WHERE id=?", (previous["batch_id"],)
                    ).fetchone()
                    family = ensure_family(
                        db, game=family_game["game"] if family_game else "Unknown",
                        set_code=updates.get("set_name", previous["set_name"]),
                        card_number=updates.get("card_number", previous["card_number"]),
                        name=updates.get("name", previous["name"]),
                        external_descriptors={"source": "DIRECT_CARD_EDITOR", "authority": False},
                    )
                    if family:
                        updates["sam_family_id"] = int(family["id"])
                        updates["sam_family_certainty"] = "OPERATOR_CONFIRMED"
                if printing_text_edited:
                    updates["sam_legacy_identity_provenance"] = "OPERATOR_CONFIRMED"
                undo_fields = {
                    key: previous[key] for key in updates
                    if key not in ("updated_at", "market_updated_at") and key in previous.keys()
                }
                assignments = ", ".join(f"{key} = ?" for key in updates)
                db.execute(
                    f"UPDATE cards SET {assignments} WHERE sku = ?",
                    [*updates.values(), sku],
                )
                if family:
                    manual_request = f"MANUAL-FAMILY-{uuid.uuid4()}"
                    event_id = record_event(
                        db, request_id=manual_request, card_id=int(previous["id"]),
                        event_type="MANUAL_IDENTITY_EDIT", family_id=int(family["id"]),
                        prior_family_id=previous["sam_family_id"],
                        prior_printing_id=previous["sam_printing_id"],
                        certainty="OPERATOR_CONFIRMED", actor="OPERATOR",
                        reason_code="DIRECT_CARD_FAMILY_EDIT",
                        evidence={"printing_authority_granted": False},
                    )
                    record_assertion(
                        db, card_id=int(previous["id"]), field_scope="FAMILY",
                        family_id=int(family["id"]),
                        proposed_value=updates.get("card_number", previous["card_number"]),
                        certainty="OPERATOR_CONFIRMED", authority_granted=True, actor="OPERATOR",
                        reason_code="DIRECT_CARD_FAMILY_EDIT",
                        evidence={"decision_event_id": event_id, "printing_authority_granted": False},
                    )
                if printing_text_edited:
                    manual_request = f"MANUAL-PRINTING-TEXT-{uuid.uuid4()}"
                    event_id = record_event(
                        db, request_id=manual_request, card_id=int(previous["id"]),
                        event_type="MANUAL_IDENTITY_EDIT",
                        family_id=int(family["id"]) if family else previous["sam_family_id"],
                        prior_family_id=previous["sam_family_id"],
                        prior_printing_id=previous["sam_printing_id"],
                        certainty="OPERATOR_CONFIRMED", actor="OPERATOR",
                        reason_code="DIRECT_LEGACY_PRINTING_TEXT_EDIT",
                        evidence={"commercial_printing_authority_granted": False,
                                  "variant": updates.get("variant", previous["variant"]),
                                  "rarity": updates.get("rarity", previous["rarity"])},
                    )
                    record_assertion(
                        db, card_id=int(previous["id"]), field_scope="PRINTING",
                        family_id=int(family["id"]) if family else previous["sam_family_id"],
                        proposed_value=updates.get("variant", previous["variant"]),
                        certainty="OPERATOR_CONFIRMED", authority_granted=False, actor="OPERATOR",
                        reason_code="DIRECT_LEGACY_PRINTING_TEXT_EDIT",
                        evidence={"decision_event_id": event_id,
                                  "commercial_printing_id": None,
                                  "legacy_text_only": True},
                    )
                log_action(db, "CARD_UPDATE", f"Updated {sku}", {"sku": sku, "before": undo_fields})
                row = db.execute("SELECT * FROM cards WHERE sku = ?", (sku,)).fetchone()
            if not row:
                self.send_error_json("Card not found", 404)
            else:
                self.send_json(dict(row))
        except ValueError as exc:
            self.send_error_json(str(exc), 400)
        except Exception as exc:
            self.send_error_json(str(exc), 500)


def run() -> None:
    init_db()
    seed_demo()
    if WATCH_INBOUND:
        threading.Thread(target=watch_inbound, name="dex-inbound", daemon=True).start()
    threading.Thread(target=recycle_maintenance, name="dex-recycle", daemon=True).start()
    server = ThreadingHTTPServer((HOST, PORT), DexHandler)
    print(f"Dex is running at http://127.0.0.1:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
