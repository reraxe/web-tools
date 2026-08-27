"""Deterministic TCGplayer opening-inventory and reconciliation services.

TCGplayer snapshots are immutable marketplace observations.  They become
physical inventory only through an explicit opening bootstrap.  Later snapshots
never overwrite DEX-owned quantity; they create reconciliation evidence and a
manual Staged Inventory CSV delta instead.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo


CONTRACT_VERSION = "tcgplayer-seller-csv-2026-04-04-v1"
CALCULATION_VERSION = "tcgplayer-inventory-reconciliation-v1"
DEFAULT_MAX_SNAPSHOT_AGE_HOURS = 24
DEFAULT_DESTRUCTIVE_ABSOLUTE = 1000
DEFAULT_DESTRUCTIVE_PERCENT = Decimal("0.25")

REQUIRED_HEADERS = (
    "TCGplayer Id",
    "Product Line",
    "Set Name",
    "Product Name",
    "Number",
    "Rarity",
    "Condition",
    "Total Quantity",
    "Add to Quantity",
    "TCG Marketplace Price",
)

HEADER_ALIASES = {
    "tcgplayer id": "TCGplayer Id",
    "tcgplayer id#": "TCGplayer Id",
    "tcgplayer sku": "TCGplayer Id",
    "product line": "Product Line",
    "set name": "Set Name",
    "product name": "Product Name",
    "title": "Title",
    "number": "Number",
    "rarity": "Rarity",
    "condition": "Condition",
    "language": "Language",
    "tcg market price": "TCG Market Price",
    "tcg direct low": "TCG Direct Low",
    "tcg low price with shipping": "TCG Low Price With Shipping",
    "tcg low w/ shipping": "TCG Low Price With Shipping",
    "tcg low price": "TCG Low Price",
    "total quantity": "Total Quantity",
    "pending quantity": "Pending Quantity",
    "add to quantity": "Add to Quantity",
    "tcg marketplace price": "TCG Marketplace Price",
    "photo url": "Photo URL",
    "my store reserve quantity": "My Store Reserve Quantity",
    "my store price": "My Store Price",
}

CARD_NUMBER_RE = re.compile(
    r"\b(?:(?P<set>(?:OP|EB|ST|PRB)\d{1,3})[-_\s‐‑‒–—―]?(?P<number>\d{3}[A-Z]?)|"
    r"(?P<promo>P)[-_\s‐‑‒–—―]?(?P<promo_number>\d{3}[A-Z]?))\b",
    re.I,
)
EXPORT_TIMESTAMP_RE = re.compile(r"(20\d{6})[_-](\d{6})")
SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _required_text(value: object, label: str, maximum: int = 180) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} is required")
    if len(text) > maximum:
        raise ValueError(f"{label} is too long")
    return text


def _clean(value: object, maximum: int = 500) -> str:
    return str(value or "").strip()[:maximum]


def _canonical_header(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.strip()).lower()
    return HEADER_ALIASES.get(normalized, value.strip())


def _integer(value: object, label: str, *, minimum: int | None = None) -> int:
    text = str(value if value is not None else "").strip()
    if not re.fullmatch(r"[+-]?\d+", text):
        raise ValueError(f"{label} must be a whole number")
    result = int(text)
    if minimum is not None and result < minimum:
        raise ValueError(f"{label} must be at least {minimum}")
    return result


def _optional_integer(value: object, label: str, *, minimum: int = 0) -> int | None:
    if str(value if value is not None else "").strip() == "":
        return None
    return _integer(value, label, minimum=minimum)


def _money_cents(value: object) -> int | None:
    text = str(value if value is not None else "").strip()
    if not text or text.upper() in {"N/A", "NA", "NONE", "NULL", "-"}:
        return None
    try:
        amount = Decimal(text.replace("$", "").replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid money value: {text}") from exc
    if amount < 0:
        raise ValueError("Marketplace price values cannot be negative")
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _normalize_card_number(*values: object) -> str:
    for value in values:
        match = CARD_NUMBER_RE.search(str(value or ""))
        if match:
            if match.group("promo"):
                return f"P-{match.group('promo_number').upper()}"
            return f"{match.group('set').upper()}-{match.group('number').upper()}"
    return ""


def _source_timestamp(filename: str, explicit: str | None) -> tuple[str, str]:
    if explicit:
        try:
            parsed = datetime.fromisoformat(str(explicit).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("source_export_timestamp must be ISO-8601") from exc
        if parsed.tzinfo is None:
            raise ValueError("source_export_timestamp must include a timezone")
        return parsed.astimezone(timezone.utc).isoformat(timespec="seconds"), "OPERATOR_SUPPLIED"
    match = EXPORT_TIMESTAMP_RE.search(filename)
    if not match:
        raise ValueError("Source export timestamp is required when it is not present in the filename")
    local = datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S").replace(
        tzinfo=ZoneInfo("America/New_York")
    )
    return local.astimezone(timezone.utc).isoformat(timespec="seconds"), "FILENAME_INFERRED"


def _catalog_families(path: Path | None) -> dict[str, dict]:
    if path is None or not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, dict] = {}
    for family in payload.get("families", []):
        number = _normalize_card_number(family.get("card_number"))
        if number:
            result[number] = family
    return result


def _commercial_product_type(
    product_line: str, product_name: str, condition_name: str, card_number: str, total_quantity: int
) -> tuple[str, str]:
    """Classify commercial inventory without granting One Piece family authority."""

    name = product_name.strip().upper()
    condition = condition_name.strip().upper()
    if condition == "UNOPENED" or any(token in name for token in (
        "STARTER DECK", "PREMIUM CARD COLLECTION", "BOOSTER BOX", "BOOSTER PACK",
        "DOUBLE PACK", "GIFT COLLECTION", "DEVIL FRUITS COLLECTION",
    )):
        commercial_type = "SEALED_PRODUCT"
    elif name.startswith("DON!! CARD"):
        commercial_type = "DON_CARD"
    elif card_number:
        commercial_type = "SINGLE_CARD"
    else:
        commercial_type = "OTHER_COMMERCIAL_PRODUCT"
    return ("ZERO_QUANTITY_REFERENCE" if total_quantity == 0 else commercial_type), commercial_type


def _disposition(
    product_line: str, tcgplayer_id: str, card_number: str, families: dict[str, dict],
    *, product_type: str, commercial_product_type: str,
) -> tuple[str, str, str]:
    if not tcgplayer_id:
        return "DO_NOT_IMPORT", "MISSING_TCGPLAYER_ID", ""
    if product_line.strip().lower() != "one piece card game":
        return "AUTO_IMPORT", "STRUCTURED_TCGPLAYER_COMMERCIAL_IDENTITY", ""
    if product_type == "ZERO_QUANTITY_REFERENCE":
        return "AUTO_IMPORT", "ZERO_QUANTITY_REFERENCE_ONLY", ""
    if commercial_product_type == "SEALED_PRODUCT":
        return "AUTO_IMPORT", "SEALED_COMMERCIAL_IDENTITY_CONFIRMED", ""
    if not card_number:
        if commercial_product_type == "DON_CARD":
            return "REVIEW_IMPORT", "DON_COMMERCIAL_IDENTITY_FAMILY_UNRESOLVED", ""
        return "REVIEW_IMPORT", "COMMERCIAL_IDENTITY_CONFIRMED_FAMILY_UNRESOLVED", ""
    family = families.get(card_number)
    if not family:
        return "REVIEW_IMPORT", "ONE_PIECE_FAMILY_NOT_IN_FROZEN_CATALOG", card_number
    return "AUTO_IMPORT", "EXACT_ONE_PIECE_CARD_NUMBER_IN_FROZEN_CATALOG", card_number


def _parse_csv(content: bytes, catalog_path: Path | None) -> tuple[list[str], list[dict]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("TCGplayer CSV must be UTF-8 encoded") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if not reader.fieldnames:
        raise ValueError("TCGplayer CSV has no header row")
    original_headers = [str(value or "").strip() for value in reader.fieldnames]
    canonical_by_original = {header: _canonical_header(header) for header in original_headers}
    canonical_headers = set(canonical_by_original.values())
    missing = [header for header in REQUIRED_HEADERS if header not in canonical_headers]
    if missing:
        raise ValueError("Missing required TCGplayer CSV headers: " + ", ".join(missing))
    families = _catalog_families(catalog_path)
    seen_ids: set[str] = set()
    rows: list[dict] = []
    for row_number, source in enumerate(reader, 2):
        canonical = {canonical_by_original[key]: value for key, value in source.items() if key is not None}
        tcgplayer_id = _required_text(canonical.get("TCGplayer Id"), f"Row {row_number} TCGplayer Id", 80)
        if tcgplayer_id in seen_ids:
            raise ValueError(f"Duplicate TCGplayer Id {tcgplayer_id} at row {row_number}")
        seen_ids.add(tcgplayer_id)
        product_line = _required_text(canonical.get("Product Line"), f"Row {row_number} Product Line")
        total_quantity = _integer(canonical.get("Total Quantity"), f"Row {row_number} Total Quantity", minimum=0)
        source_add = _integer(canonical.get("Add to Quantity"), f"Row {row_number} Add to Quantity")
        pending = _optional_integer(canonical.get("Pending Quantity"), f"Row {row_number} Pending Quantity")
        number = _normalize_card_number(canonical.get("Number"), canonical.get("Product Name"), canonical.get("Title"))
        product_name = _required_text(canonical.get("Product Name"), f"Row {row_number} Product Name", 300)
        condition_name = _clean(canonical.get("Condition"), 120)
        product_type, commercial_product_type = _commercial_product_type(
            product_line, product_name, condition_name, number, total_quantity
        )
        disposition, reason, family_key = _disposition(
            product_line, tcgplayer_id, number, families,
            product_type=product_type, commercial_product_type=commercial_product_type,
        )
        rows.append({
            "source_row_number": row_number,
            "tcgplayer_id": tcgplayer_id,
            "product_line": product_line,
            "set_name": _clean(canonical.get("Set Name"), 240),
            "product_name": product_name,
            "title": _clean(canonical.get("Title"), 300),
            "card_number": number,
            "rarity": _clean(canonical.get("Rarity"), 120),
            "condition_name": condition_name,
            "language": _clean(canonical.get("Language"), 80),
            "total_quantity": total_quantity,
            "pending_quantity": pending,
            "source_add_to_quantity": source_add,
            "market_price_cents": _money_cents(canonical.get("TCG Market Price")),
            "direct_low_cents": _money_cents(canonical.get("TCG Direct Low")),
            "low_with_shipping_cents": _money_cents(canonical.get("TCG Low Price With Shipping")),
            "low_price_cents": _money_cents(canonical.get("TCG Low Price")),
            "marketplace_price_cents": _money_cents(canonical.get("TCG Marketplace Price")),
            "import_disposition": disposition,
            "disposition_reason": reason,
            "one_piece_family_key": family_key,
            "product_type": product_type,
            "commercial_product_type": commercial_product_type,
            "raw_row_json": json.dumps(source, separators=(",", ":"), ensure_ascii=False),
        })
    if not rows:
        raise ValueError("TCGplayer CSV contains no product rows")
    return original_headers, rows


def _artifact_path(root: Path, source_hash: str) -> tuple[Path, str]:
    relative = Path(source_hash[:2]) / f"{source_hash}.csv"
    return root / relative, relative.as_posix()


def _write_artifact(root: Path, content: bytes, source_hash: str) -> str:
    target, relative = _artifact_path(root, source_hash)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != source_hash:
            raise ValueError("Existing TCGplayer source artifact failed its SHA-256 check")
        return relative
    with target.open("xb") as handle:
        handle.write(content)
    if hashlib.sha256(target.read_bytes()).hexdigest() != source_hash:
        raise ValueError("Stored TCGplayer source artifact failed its SHA-256 check")
    return relative


def _owned_quantity(db: sqlite3.Connection, pool_id: int) -> int:
    return int(db.execute(
        "SELECT COALESCE(SUM(quantity_delta),0) FROM inventory_quantity_events WHERE pool_id=?",
        (pool_id,),
    ).fetchone()[0])


def _pool_payload(db: sqlite3.Connection, row: sqlite3.Row | dict) -> dict:
    pool = dict(row)
    _, commercial_product_type = _commercial_product_type(
        pool["product_line"], pool["product_name"], pool["condition_name"],
        pool["card_number"], 1,
    )
    owned = _owned_quantity(db, int(pool["id"]))
    physically_reconciled = int(db.execute(
        "SELECT COALESCE(SUM(quantity),0) FROM inventory_physical_reconciliation_events WHERE pool_id=?",
        (pool["id"],),
    ).fetchone()[0])
    observation = db.execute(
        """SELECT * FROM tcgplayer_channel_observations WHERE pool_id=?
           ORDER BY source_export_timestamp DESC,id DESC LIMIT 1""",
        (pool["id"],),
    ).fetchone()
    expected = max(0, owned - int(pool.get("reserved_quantity", 0)))
    observed = int(observation["observed_total_quantity"]) if observation else None
    pool.update({
        "owned_quantity": owned,
        "reserved_quantity": int(pool.get("reserved_quantity", 0)),
        "available_quantity": expected,
        "physically_reconciled_quantity": physically_reconciled,
        "tcgplayer_expected_quantity": expected,
        "tcgplayer_observed_quantity": observed,
        "tcgplayer_pending_quantity": observation["observed_pending_quantity"] if observation else None,
        "snapshot_timestamp": observation["source_export_timestamp"] if observation else None,
        "sync_status": "STALE_SNAPSHOT" if observation is None else ("MATCHED" if expected == observed else "SYNC_NEEDED"),
        "product_type": commercial_product_type,
        "commercial_identity_status": "COMMERCIAL_IDENTITY_CONFIRMED",
        "family_identity_status": "FAMILY_IDENTIFIED" if pool.get("card_number") else "FAMILY_UNRESOLVED",
        "sam_family_authority_granted": False,
    })
    return pool


def _batch_payload(db: sqlite3.Connection, row: sqlite3.Row | dict) -> dict:
    batch = dict(row)
    batch["headers"] = json.loads(batch.pop("headers_json"))
    batch["game_summary"] = [dict(item) for item in db.execute(
        """SELECT product_line,COUNT(*) AS row_count,
                  SUM(CASE WHEN total_quantity>0 THEN 1 ELSE 0 END) AS positive_row_count,
                  SUM(total_quantity) AS total_quantity
           FROM tcgplayer_snapshot_rows WHERE import_batch_id=?
           GROUP BY product_line ORDER BY product_line""",
        (batch["id"],),
    )]
    decisions: dict[int, dict] = {}
    for event in db.execute(
        """SELECT payload_json FROM tcgplayer_inventory_audit_events
           WHERE import_batch_id=? AND event_type='ROW_OPERATOR_DECISION' ORDER BY id""",
        (batch["id"],),
    ):
        payload = json.loads(event["payload_json"])
        decisions[int(payload["snapshot_row_id"])] = payload
    review_rows = []
    for item in db.execute(
        """SELECT id,source_row_number,tcgplayer_id,product_line,set_name,product_name,
                  title,card_number,rarity,condition_name,language,total_quantity,
                  import_disposition,disposition_reason
           FROM tcgplayer_snapshot_rows
           WHERE import_batch_id=? AND product_line='One Piece Card Game'
             AND import_disposition!='AUTO_IMPORT' AND total_quantity>0
           ORDER BY source_row_number""",
        (batch["id"],),
    ):
        review = dict(item)
        product_type, commercial_product_type = _commercial_product_type(
            review["product_line"], review["product_name"], review["condition_name"],
            review["card_number"], int(review["total_quantity"]),
        )
        review["product_type"] = product_type
        review["commercial_product_type"] = commercial_product_type
        review["commercial_identity_status"] = "COMMERCIAL_IDENTITY_CONFIRMED"
        review["family_identity_status"] = "FAMILY_IDENTIFIED" if review["card_number"] else "UNRECOGNIZED_FAMILY"
        review["operator_decision"] = decisions.get(int(item["id"]))
        review_rows.append(review)
    batch["operator_review_rows"] = review_rows
    confirmed_quantity = sum(
        int(item["total_quantity"])
        for item in review_rows
        if (item["operator_decision"] or {}).get("decision") in {
            "OPERATOR_CONFIRMED", "IMPORT_COMMERCIAL_UNRESOLVED"
        }
    )
    auto_quantity = int(db.execute(
        """SELECT COALESCE(SUM(total_quantity),0) FROM tcgplayer_snapshot_rows
           WHERE import_batch_id=? AND import_disposition='AUTO_IMPORT' AND total_quantity>0""",
        (batch["id"],),
    ).fetchone()[0])
    batch["auto_import_quantity"] = auto_quantity
    batch["operator_confirmed_quantity"] = confirmed_quantity
    batch["quantity_eligible_for_bootstrap"] = auto_quantity + confirmed_quantity
    batch["proposed_dex_owned_quantity"] = auto_quantity + confirmed_quantity
    unresolved_rows = []
    for item in db.execute(
        """SELECT product_line,product_name,condition_name,card_number,total_quantity
           FROM tcgplayer_snapshot_rows
           WHERE import_batch_id=? AND product_line='One Piece Card Game' AND card_number=''
           ORDER BY source_row_number""",
        (batch["id"],),
    ):
        product_type, commercial_product_type = _commercial_product_type(
            item["product_line"], item["product_name"], item["condition_name"],
            item["card_number"], int(item["total_quantity"]),
        )
        unresolved_rows.append({
            "product_type": product_type,
            "commercial_product_type": commercial_product_type,
            "quantity": int(item["total_quantity"]),
        })
    breakdown: dict[str, dict[str, int]] = {}
    for item in unresolved_rows:
        bucket = breakdown.setdefault(item["product_type"], {"rows": 0, "quantity": 0})
        bucket["rows"] += 1
        bucket["quantity"] += item["quantity"]
    batch["unresolved_product_type_breakdown"] = breakdown
    commercial_identity_only_quantity = sum(
        item["quantity"] for item in unresolved_rows
        if item["product_type"] in {"DON_CARD", "OTHER_COMMERCIAL_PRODUCT"}
    )
    sealed_product_quantity = sum(
        item["quantity"] for item in unresolved_rows
        if item["product_type"] == "SEALED_PRODUCT"
    )
    excluded_owned_quantity = sum(
        int(item["total_quantity"]) for item in review_rows
        if (item["operator_decision"] or {}).get("decision") == "REMAIN_EXCLUDED"
    )
    undecided_reviewable_quantity = sum(
        int(item["total_quantity"]) for item in review_rows
        if not item["operator_decision"]
    )
    batch["commercial_identity_only_quantity"] = commercial_identity_only_quantity
    batch["sealed_product_quantity"] = sealed_product_quantity
    batch["truly_excluded_owned_quantity"] = excluded_owned_quantity
    batch["proposed_dex_owned_quantity"] = auto_quantity + confirmed_quantity + undecided_reviewable_quantity
    disposition_totals = {
        item["import_disposition"]: {
            "rows": int(item["row_count"]), "quantity": int(item["total_quantity"] or 0)
        }
        for item in db.execute(
            """SELECT import_disposition,COUNT(*) AS row_count,SUM(total_quantity) AS total_quantity
               FROM tcgplayer_snapshot_rows WHERE import_batch_id=? GROUP BY import_disposition""",
            (batch["id"],),
        )
    }
    batch["disposition_totals"] = disposition_totals
    batch["one_piece_disposition_totals"] = {
        item["import_disposition"]: {
            "rows": int(item["row_count"]), "quantity": int(item["total_quantity"] or 0)
        }
        for item in db.execute(
            """SELECT import_disposition,COUNT(*) AS row_count,SUM(total_quantity) AS total_quantity
               FROM tcgplayer_snapshot_rows
               WHERE import_batch_id=? AND product_line='One Piece Card Game'
               GROUP BY import_disposition""",
            (batch["id"],),
        )
    }
    one_piece = db.execute(
        """SELECT COUNT(*) AS row_count,COALESCE(SUM(total_quantity),0) AS quantity
           FROM tcgplayer_snapshot_rows WHERE import_batch_id=? AND product_line='One Piece Card Game'""",
        (batch["id"],),
    ).fetchone()
    non_one_piece = db.execute(
        """SELECT COUNT(*) AS row_count,COALESCE(SUM(total_quantity),0) AS quantity
           FROM tcgplayer_snapshot_rows WHERE import_batch_id=? AND product_line!='One Piece Card Game'""",
        (batch["id"],),
    ).fetchone()
    batch["one_piece_pool"] = {"rows": int(one_piece["row_count"]), "quantity": int(one_piece["quantity"])}
    batch["non_one_piece_pool"] = {"rows": int(non_one_piece["row_count"]), "quantity": int(non_one_piece["quantity"])}
    return batch


def decide_import_row(
    db: sqlite3.Connection,
    import_uuid: str,
    snapshot_row_id: int,
    payload: dict,
    *,
    one_piece_catalog_path: Path | None = None,
) -> dict:
    batch = db.execute(
        "SELECT * FROM tcgplayer_import_batches WHERE import_uuid=?", (import_uuid,)
    ).fetchone()
    if not batch:
        raise ValueError("TCGplayer import was not found")
    if batch["status"] != "PREVIEWED":
        raise ValueError("Operator row decisions must be completed before applying the snapshot")
    row = db.execute(
        "SELECT * FROM tcgplayer_snapshot_rows WHERE id=? AND import_batch_id=?",
        (snapshot_row_id, batch["id"]),
    ).fetchone()
    if not row or row["product_line"] != "One Piece Card Game" or row["import_disposition"] == "AUTO_IMPORT":
        raise ValueError("This source row does not require an operator import decision")
    request_id = _required_text(payload.get("request_id"), "request_id", 160)
    existing = db.execute(
        "SELECT payload_json FROM tcgplayer_inventory_audit_events WHERE request_id=?",
        (request_id,),
    ).fetchone()
    if existing:
        return json.loads(existing["payload_json"])
    decision = _required_text(payload.get("decision"), "decision", 60).upper()
    if decision not in {"OPERATOR_CONFIRMED", "IMPORT_COMMERCIAL_UNRESOLVED", "REMAIN_EXCLUDED"}:
        raise ValueError("Choose Confirm family, Import with family unresolved, or Exclude")
    notes = _required_text(payload.get("notes"), "operator note", 1000)
    confirmed_card_number = ""
    if decision == "OPERATOR_CONFIRMED":
        confirmed_card_number = _normalize_card_number(payload.get("card_number"))
        if not confirmed_card_number:
            raise ValueError("An exact printed One Piece card number is required")
        if confirmed_card_number not in _catalog_families(one_piece_catalog_path):
            raise ValueError("The operator-confirmed card number is not in the frozen One Piece catalog")
    product_type, commercial_product_type = _commercial_product_type(
        row["product_line"], row["product_name"], row["condition_name"],
        row["card_number"], int(row["total_quantity"]),
    )
    if decision == "IMPORT_COMMERCIAL_UNRESOLVED":
        if int(row["total_quantity"]) <= 0:
            raise ValueError("Zero-quantity references do not create owned inventory")
        if commercial_product_type not in {"DON_CARD", "OTHER_COMMERCIAL_PRODUCT"}:
            raise ValueError("This product type does not use family-unresolved commercial import")
    decision_payload = {
        "snapshot_row_id": int(row["id"]),
        "source_row_number": int(row["source_row_number"]),
        "tcgplayer_id": row["tcgplayer_id"],
        "decision": decision,
        "confirmed_card_number": confirmed_card_number,
        "product_type": product_type,
        "commercial_product_type": commercial_product_type,
        "commercial_identity_status": "COMMERCIAL_IDENTITY_CONFIRMED",
        "family_identity_status": (
            "FAMILY_IDENTIFIED" if confirmed_card_number else "FAMILY_UNRESOLVED"
        ),
        "notes": notes,
    }
    db.execute(
        """INSERT INTO tcgplayer_inventory_audit_events
           (event_uuid,request_id,import_batch_id,event_type,payload_json,recorded_at)
           VALUES (?,?,?,?,?,?)""",
        (f"TCG-AUDIT-{uuid.uuid4()}", request_id, batch["id"], "ROW_OPERATOR_DECISION",
         json.dumps(decision_payload, separators=(",", ":")), _now()),
    )
    return decision_payload


def preview_import(
    db: sqlite3.Connection,
    artifact_root: Path,
    *,
    filename: str,
    content: bytes,
    request_id: str,
    source_export_timestamp: str | None = None,
    one_piece_catalog_path: Path | None = None,
) -> dict:
    request = _required_text(request_id, "request_id", 160)
    request_match = db.execute(
        "SELECT import_batch_id FROM tcgplayer_inventory_audit_events WHERE request_id=? AND event_type='IMPORT_PREVIEWED'",
        (request,),
    ).fetchone()
    if request_match:
        prior = db.execute("SELECT * FROM tcgplayer_import_batches WHERE id=?", (request_match["import_batch_id"],)).fetchone()
        return _batch_payload(db, prior)
    source_filename = SAFE_FILENAME_RE.sub("_", Path(filename).name)[:240]
    if not source_filename.lower().endswith(".csv"):
        raise ValueError("Select a TCGplayer CSV export")
    if not content or len(content) > 10 * 1024 * 1024:
        raise ValueError("TCGplayer CSV must be between 1 byte and 10 MB")
    source_hash = hashlib.sha256(content).hexdigest()
    existing = db.execute("SELECT * FROM tcgplayer_import_batches WHERE source_sha256=?", (source_hash,)).fetchone()
    if existing:
        return _batch_payload(db, existing)
    timestamp, timestamp_basis = _source_timestamp(source_filename, source_export_timestamp)
    headers, rows = _parse_csv(content, one_piece_catalog_path)
    artifact_relative = _write_artifact(artifact_root, content, source_hash)
    import_mode = "BOOTSTRAP" if not db.execute(
        "SELECT 1 FROM tcgplayer_import_batches WHERE status='APPLIED' LIMIT 1"
    ).fetchone() else "RECONCILIATION"
    counts = {
        "positive": sum(1 for row in rows if row["total_quantity"] > 0),
        "zero": sum(1 for row in rows if row["total_quantity"] == 0),
        "total": sum(row["total_quantity"] for row in rows),
        "auto": sum(1 for row in rows if row["import_disposition"] == "AUTO_IMPORT"),
        "review": sum(1 for row in rows if row["import_disposition"] == "REVIEW_IMPORT"),
        "blocked": sum(1 for row in rows if row["import_disposition"] == "DO_NOT_IMPORT"),
    }
    now = _now()
    import_uuid = f"TCG-IMPORT-{uuid.uuid4()}"
    cursor = db.execute(
        """INSERT INTO tcgplayer_import_batches
           (import_uuid,preview_request_id,source_filename,source_sha256,source_export_timestamp,
            source_timestamp_basis,artifact_relative_path,import_mode,status,contract_version,
            headers_json,row_count,positive_quantity_row_count,zero_quantity_row_count,
            source_total_quantity,auto_import_row_count,review_import_row_count,
            do_not_import_row_count,previewed_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (import_uuid, request, source_filename, source_hash, timestamp, timestamp_basis,
         artifact_relative, import_mode, "PREVIEWED", CONTRACT_VERSION,
         json.dumps(headers, separators=(",", ":")), len(rows), counts["positive"], counts["zero"],
         counts["total"], counts["auto"], counts["review"], counts["blocked"], now),
    )
    batch_id = int(cursor.lastrowid)
    for row in rows:
        db.execute(
            """INSERT INTO tcgplayer_snapshot_rows
               (import_batch_id,source_row_number,tcgplayer_id,product_line,set_name,product_name,
                title,card_number,rarity,condition_name,language,total_quantity,pending_quantity,
                source_add_to_quantity,market_price_cents,direct_low_cents,low_with_shipping_cents,
                low_price_cents,marketplace_price_cents,import_disposition,disposition_reason,
                one_piece_family_key,raw_row_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (batch_id, row["source_row_number"], row["tcgplayer_id"], row["product_line"],
             row["set_name"], row["product_name"], row["title"], row["card_number"], row["rarity"],
             row["condition_name"], row["language"], row["total_quantity"], row["pending_quantity"],
             row["source_add_to_quantity"], row["market_price_cents"], row["direct_low_cents"],
             row["low_with_shipping_cents"], row["low_price_cents"], row["marketplace_price_cents"],
             row["import_disposition"], row["disposition_reason"], row["one_piece_family_key"],
             row["raw_row_json"]),
        )
    db.execute(
        """INSERT INTO tcgplayer_inventory_audit_events
           (event_uuid,request_id,import_batch_id,event_type,payload_json,recorded_at)
           VALUES (?,?,?,?,?,?)""",
        (f"TCG-AUDIT-{uuid.uuid4()}", request, batch_id, "IMPORT_PREVIEWED",
         json.dumps({"source_sha256": source_hash, "row_count": len(rows), "mode": import_mode}, separators=(",", ":")), now),
    )
    return _batch_payload(db, db.execute("SELECT * FROM tcgplayer_import_batches WHERE id=?", (batch_id,)).fetchone())


def get_import(db: sqlite3.Connection, import_uuid: str) -> dict:
    row = db.execute("SELECT * FROM tcgplayer_import_batches WHERE import_uuid=?", (import_uuid,)).fetchone()
    if not row:
        raise ValueError("TCGplayer import was not found")
    payload = _batch_payload(db, row)
    payload["disposition_summary"] = [dict(item) for item in db.execute(
        """SELECT import_disposition,disposition_reason,COUNT(*) AS row_count,SUM(total_quantity) AS total_quantity
           FROM tcgplayer_snapshot_rows WHERE import_batch_id=?
           GROUP BY import_disposition,disposition_reason ORDER BY import_disposition,disposition_reason""",
        (row["id"],),
    )]
    return payload


def _create_pool(db: sqlite3.Connection, row: sqlite3.Row, now: str, source_type: str) -> int:
    existing = db.execute("SELECT id FROM inventory_pools WHERE tcgplayer_id=?", (row["tcgplayer_id"],)).fetchone()
    if existing:
        return int(existing["id"])
    cursor = db.execute(
        """INSERT INTO inventory_pools
           (pool_uuid,tcgplayer_id,game,product_line,set_name,product_name,card_number,rarity,
            condition_name,language,source_type,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (f"INV-POOL-{uuid.uuid4()}", row["tcgplayer_id"], row["product_line"], row["product_line"],
         row["set_name"], row["product_name"], row["card_number"], row["rarity"],
         row["condition_name"], row["language"], source_type, now, now),
    )
    return int(cursor.lastrowid)


def _quantity_event(
    db: sqlite3.Connection,
    *,
    pool_id: int,
    request_id: str,
    event_type: str,
    quantity_delta: int,
    import_batch_id: int | None = None,
    reason_code: str = "",
    notes: str = "",
    effective_at: str | None = None,
    reverses_event_id: int | None = None,
    payload: dict | None = None,
) -> dict:
    existing = db.execute("SELECT * FROM inventory_quantity_events WHERE request_id=?", (request_id,)).fetchone()
    if existing:
        return dict(existing)
    if quantity_delta == 0:
        raise ValueError("Inventory quantity event must change quantity")
    prior = _owned_quantity(db, pool_id)
    resulting = prior + int(quantity_delta)
    if resulting < 0:
        raise ValueError("Inventory event would make owned quantity negative")
    now = _now()
    cursor = db.execute(
        """INSERT INTO inventory_quantity_events
           (event_uuid,request_id,pool_id,import_batch_id,event_type,quantity_delta,
            prior_owned_quantity,resulting_owned_quantity,reverses_event_id,reason_code,notes,
            effective_at,recorded_at,payload_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (f"INV-EVENT-{uuid.uuid4()}", request_id, pool_id, import_batch_id, event_type,
         int(quantity_delta), prior, resulting, reverses_event_id, _clean(reason_code, 120),
         _clean(notes, 1000), effective_at or now, now,
         json.dumps(payload or {}, separators=(",", ":"))),
    )
    db.execute("UPDATE inventory_pools SET updated_at=? WHERE id=?", (now, pool_id))
    return dict(db.execute("SELECT * FROM inventory_quantity_events WHERE id=?", (cursor.lastrowid,)).fetchone())


def _observe_and_reconcile(db: sqlite3.Connection, batch: sqlite3.Row, row: sqlite3.Row, pool_id: int, now: str) -> None:
    db.execute(
        """INSERT INTO tcgplayer_channel_observations
           (observation_uuid,import_batch_id,pool_id,observed_total_quantity,
            observed_pending_quantity,marketplace_price_cents,source_export_timestamp,recorded_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (f"TCG-OBS-{uuid.uuid4()}", batch["id"], pool_id, row["total_quantity"],
         row["pending_quantity"], row["marketplace_price_cents"], batch["source_export_timestamp"], now),
    )
    pool = db.execute("SELECT * FROM inventory_pools WHERE id=?", (pool_id,)).fetchone()
    expected = max(0, _owned_quantity(db, pool_id) - int(pool["reserved_quantity"]))
    observed = int(row["total_quantity"])
    db.execute(
        "UPDATE tcgplayer_reconciliation_items SET status='SUPERSEDED' WHERE pool_id=? AND status='OPEN'",
        (pool_id,),
    )
    if expected != observed:
        db.execute(
            """INSERT INTO tcgplayer_reconciliation_items
               (reconciliation_uuid,import_batch_id,pool_id,expected_quantity,observed_quantity,
                difference,status,reason_code,created_at)
               VALUES (?,?,?,?,?,?,'OPEN',?,?)""",
            (f"TCG-REC-{uuid.uuid4()}", batch["id"], pool_id, expected, observed,
             observed - expected, "CHANNEL_QUANTITY_DIFFERS_FROM_DEX_PHYSICAL_TRUTH", now),
        )


def apply_import(db: sqlite3.Connection, import_uuid: str, *, request_id: str) -> dict:
    request = _required_text(request_id, "request_id", 160)
    batch = db.execute("SELECT * FROM tcgplayer_import_batches WHERE import_uuid=?", (import_uuid,)).fetchone()
    if not batch:
        raise ValueError("TCGplayer import was not found")
    if batch["status"] == "APPLIED":
        return get_import(db, import_uuid)
    if batch["import_mode"] == "BOOTSTRAP" and db.execute(
        "SELECT 1 FROM tcgplayer_import_batches WHERE status='APPLIED' AND import_mode='BOOTSTRAP' LIMIT 1"
    ).fetchone():
        raise ValueError("Opening inventory was already bootstrapped; import this as a reconciliation snapshot")
    rows = db.execute(
        "SELECT * FROM tcgplayer_snapshot_rows WHERE import_batch_id=? ORDER BY source_row_number",
        (batch["id"],),
    ).fetchall()
    operator_decisions: dict[int, dict] = {}
    for event in db.execute(
        """SELECT payload_json FROM tcgplayer_inventory_audit_events
           WHERE import_batch_id=? AND event_type='ROW_OPERATOR_DECISION' ORDER BY id""",
        (batch["id"],),
    ):
        decision = json.loads(event["payload_json"])
        operator_decisions[int(decision["snapshot_row_id"])] = decision
    now = _now()
    imported_pools = 0
    imported_quantity = 0
    observations = 0
    operator_confirmed_rows = 0
    for source_row in rows:
        row: sqlite3.Row | dict = source_row
        if source_row["import_disposition"] != "AUTO_IMPORT":
            decision = operator_decisions.get(int(source_row["id"]))
            if not decision or decision.get("decision") not in {
                "OPERATOR_CONFIRMED", "IMPORT_COMMERCIAL_UNRESOLVED"
            }:
                continue
            row = dict(source_row)
            row["card_number"] = decision.get("confirmed_card_number", "")
            row["one_piece_family_key"] = decision.get("confirmed_card_number", "")
            operator_confirmed_rows += 1
        if int(row["total_quantity"]) <= 0 and not db.execute(
            "SELECT 1 FROM inventory_pools WHERE tcgplayer_id=?", (row["tcgplayer_id"],)
        ).fetchone():
            continue
        pool_row = db.execute("SELECT id FROM inventory_pools WHERE tcgplayer_id=?", (row["tcgplayer_id"],)).fetchone()
        pool_id = int(pool_row["id"]) if pool_row else _create_pool(
            db, row, now, "TCGPLAYER_BOOTSTRAP" if batch["import_mode"] == "BOOTSTRAP" else "TCGPLAYER_SNAPSHOT"
        )
        if not pool_row:
            imported_pools += 1
        if batch["import_mode"] == "BOOTSTRAP" and int(row["total_quantity"]) > 0:
            if _owned_quantity(db, pool_id) != 0:
                raise ValueError(f"Opening inventory pool {row['tcgplayer_id']} already has owned quantity")
            _quantity_event(
                db, pool_id=pool_id,
                request_id=f"{request}:{row['tcgplayer_id']}:BOOTSTRAP",
                event_type="TCGPLAYER_BOOTSTRAP", quantity_delta=int(row["total_quantity"]),
                import_batch_id=int(batch["id"]), reason_code="OPENING_STRUCTURED_INVENTORY",
                payload={
                    "source_sha256": batch["source_sha256"],
                    "product_type": _commercial_product_type(
                        row["product_line"], row["product_name"], row["condition_name"],
                        row["card_number"], int(row["total_quantity"]),
                    )[1],
                    "commercial_identity_status": "COMMERCIAL_IDENTITY_CONFIRMED",
                    "family_identity_status": "FAMILY_IDENTIFIED" if row["card_number"] else "FAMILY_UNRESOLVED",
                    "sam_family_authority_granted": False,
                },
            )
            imported_quantity += int(row["total_quantity"])
        _observe_and_reconcile(db, batch, row, pool_id, now)
        observations += 1
    event_watermark = int(db.execute("SELECT COALESCE(MAX(id),0) FROM inventory_quantity_events").fetchone()[0])
    db.execute(
        "UPDATE tcgplayer_import_batches SET status='APPLIED',applied_at=?,inventory_event_watermark_id=? WHERE id=?",
        (now, event_watermark, batch["id"]),
    )
    db.execute(
        """INSERT INTO tcgplayer_inventory_audit_events
           (event_uuid,request_id,import_batch_id,event_type,payload_json,recorded_at)
           VALUES (?,?,?,?,?,?)""",
        (f"TCG-AUDIT-{uuid.uuid4()}", request, batch["id"], "IMPORT_APPLIED",
         json.dumps({"mode": batch["import_mode"], "pools_created": imported_pools,
                     "owned_quantity_added": imported_quantity, "observations": observations,
                     "operator_confirmed_rows": operator_confirmed_rows}, separators=(",", ":")), now),
    )
    return get_import(db, import_uuid)


def record_inventory_event(db: sqlite3.Connection, pool_id: int, payload: dict) -> dict:
    pool = db.execute("SELECT * FROM inventory_pools WHERE id=? AND active=1", (pool_id,)).fetchone()
    if not pool:
        raise ValueError("Inventory pool was not found")
    event_type = _required_text(payload.get("event_type"), "event_type", 80).upper()
    allowed = {
        "SAM_INTAKE", "MANUAL_ACQUISITION", "TCGPLAYER_SALE", "EBAY_SALE",
        "SHOPIFY_SALE", "DIRECT_SALE", "DAMAGE_WRITE_OFF", "INVENTORY_CORRECTION",
        "REFUND_RETURN", "REVERSAL",
    }
    if event_type not in allowed:
        raise ValueError("Unsupported inventory event type")
    request_id = _required_text(payload.get("request_id"), "request_id", 160)
    quantity_delta = _integer(payload.get("quantity_delta"), "quantity_delta")
    reverses_event_id = None
    if event_type == "REVERSAL":
        reverses_event_id = _integer(payload.get("reverses_event_id"), "reverses_event_id", minimum=1)
        source = db.execute("SELECT * FROM inventory_quantity_events WHERE id=? AND pool_id=?", (reverses_event_id, pool_id)).fetchone()
        if not source:
            raise ValueError("Original inventory event was not found")
        if db.execute("SELECT 1 FROM inventory_quantity_events WHERE reverses_event_id=?", (reverses_event_id,)).fetchone():
            raise ValueError("Original inventory event was already reversed")
        if quantity_delta != -int(source["quantity_delta"]):
            raise ValueError("Reversal quantity must exactly invert the original event")
    event = _quantity_event(
        db, pool_id=pool_id, request_id=request_id, event_type=event_type,
        quantity_delta=quantity_delta, reason_code=payload.get("reason_code", ""),
        notes=payload.get("notes", ""), effective_at=payload.get("effective_at"),
        reverses_event_id=reverses_event_id,
    )
    return {"event": event, "pool": _pool_payload(db, db.execute("SELECT * FROM inventory_pools WHERE id=?", (pool_id,)).fetchone())}


def _reconciliation_payload(db: sqlite3.Connection, item: sqlite3.Row | dict) -> dict:
    result = dict(item)
    pool = db.execute("SELECT * FROM inventory_pools WHERE id=?", (result["pool_id"],)).fetchone()
    observations = db.execute(
        """SELECT observed_total_quantity,source_export_timestamp FROM tcgplayer_channel_observations
           WHERE pool_id=? ORDER BY source_export_timestamp DESC,id DESC LIMIT 2""",
        (result["pool_id"],),
    ).fetchall()
    current = int(observations[0]["observed_total_quantity"]) if observations else int(result["observed_quantity"])
    previous = int(observations[1]["observed_total_quantity"]) if len(observations) > 1 else None
    snapshot_delta = current - previous if previous is not None else None
    if snapshot_delta is not None and snapshot_delta < 0:
        classification = "LIKELY_SALE"
    elif snapshot_delta is not None and snapshot_delta > 0:
        classification = "REVIEW_REQUIRED"
    else:
        classification = "DISCREPANCY_REVIEW"
    result.update({
        "tcgplayer_id": pool["tcgplayer_id"],
        "product_line": pool["product_line"],
        "set_name": pool["set_name"],
        "product_name": pool["product_name"],
        "card_number": pool["card_number"],
        "condition_name": pool["condition_name"],
        "owned_quantity": _owned_quantity(db, int(pool["id"])),
        "previous_observed_quantity": previous,
        "current_observed_quantity": current,
        "snapshot_delta": snapshot_delta,
        "proposed_disposition": classification,
    })
    return result


def decide_reconciliation(db: sqlite3.Connection, reconciliation_id: int, payload: dict) -> dict:
    request_id = _required_text(payload.get("request_id"), "request_id", 160)
    existing = db.execute(
        "SELECT payload_json FROM tcgplayer_inventory_audit_events WHERE request_id=?",
        (request_id,),
    ).fetchone()
    if existing:
        decision = json.loads(existing["payload_json"])
        item = db.execute("SELECT * FROM tcgplayer_reconciliation_items WHERE id=?", (reconciliation_id,)).fetchone()
        return {"decision": decision, "reconciliation": _reconciliation_payload(db, item)}
    item = db.execute(
        "SELECT * FROM tcgplayer_reconciliation_items WHERE id=?", (reconciliation_id,)
    ).fetchone()
    if not item or item["status"] != "OPEN":
        raise ValueError("This reconciliation item is no longer open")
    action = _required_text(payload.get("action"), "action", 80).upper()
    if action not in {"CONFIRM_SALE", "REVIEW", "DISMISS_RESOLVE"}:
        raise ValueError("Choose Confirm sale, Review, or Dismiss/resolve")
    notes = _clean(payload.get("notes"), 1000)
    reason_code = _clean(payload.get("reason_code"), 120).upper()
    view = _reconciliation_payload(db, item)
    now = _now()
    event = None
    if action == "CONFIRM_SALE":
        snapshot_delta = view["snapshot_delta"]
        expected_sale = int(item["expected_quantity"]) - int(item["observed_quantity"])
        if snapshot_delta is None or snapshot_delta >= 0:
            raise ValueError("Only a marketplace quantity decrease can be confirmed as a sale")
        if expected_sale <= 0 or expected_sale != -int(snapshot_delta):
            raise ValueError("The marketplace decrease does not exactly reconcile to DEX quantity; review it instead")
        event = _quantity_event(
            db,
            pool_id=int(item["pool_id"]),
            request_id=f"{request_id}:QUANTITY",
            event_type="TCGPLAYER_SALE",
            quantity_delta=-expected_sale,
            import_batch_id=int(item["import_batch_id"]),
            reason_code="OPERATOR_CONFIRMED_SNAPSHOT_SALE",
            notes=notes,
            payload={"reconciliation_uuid": item["reconciliation_uuid"]},
        )
        reason_code = "OPERATOR_CONFIRMED_SNAPSHOT_SALE"
        db.execute(
            "UPDATE tcgplayer_reconciliation_items SET status='RESOLVED',reason_code=?,resolved_at=? WHERE id=?",
            (reason_code, now, reconciliation_id),
        )
    elif action == "REVIEW":
        reason_code = reason_code or "OPERATOR_REVIEW_REQUIRED"
    else:
        reason_code = _required_text(reason_code, "reason_code", 120).upper()
        notes = _required_text(notes, "notes", 1000)
        db.execute(
            "UPDATE tcgplayer_reconciliation_items SET status='RESOLVED',reason_code=?,resolved_at=? WHERE id=?",
            (reason_code, now, reconciliation_id),
        )
    decision = {
        "reconciliation_id": int(reconciliation_id),
        "reconciliation_uuid": item["reconciliation_uuid"],
        "action": action,
        "reason_code": reason_code,
        "notes": notes,
        "quantity_event_id": int(event["id"]) if event else None,
    }
    db.execute(
        """INSERT INTO tcgplayer_inventory_audit_events
           (event_uuid,request_id,import_batch_id,pool_id,event_type,payload_json,recorded_at)
           VALUES (?,?,?,?,?,?,?)""",
        (f"TCG-AUDIT-{uuid.uuid4()}", request_id, item["import_batch_id"], item["pool_id"],
         f"RECONCILIATION_{action}", json.dumps(decision, separators=(",", ":")), now),
    )
    current = db.execute("SELECT * FROM tcgplayer_reconciliation_items WHERE id=?", (reconciliation_id,)).fetchone()
    return {"decision": decision, "reconciliation": _reconciliation_payload(db, current)}


def reconcile_sam_copy(db: sqlite3.Connection, pool_id: int, payload: dict) -> dict:
    pool = db.execute("SELECT * FROM inventory_pools WHERE id=? AND active=1", (pool_id,)).fetchone()
    if not pool:
        raise ValueError("Inventory pool was not found")
    request_id = _required_text(payload.get("request_id"), "request_id", 160)
    existing = db.execute("SELECT * FROM inventory_physical_reconciliation_events WHERE request_id=?", (request_id,)).fetchone()
    if existing:
        return {"reconciliation": dict(existing), "pool": _pool_payload(db, pool)}
    action = _required_text(payload.get("action"), "action", 80).upper()
    if action not in {"RECONCILE_EXISTING_COPY", "ADD_AS_NEW_INTAKE"}:
        raise ValueError("Choose whether this is an existing copy or new intake")
    quantity = _integer(payload.get("quantity", 1), "quantity", minimum=1)
    card_id = _optional_integer(payload.get("card_id"), "card_id", minimum=1)
    if card_id is not None and not db.execute("SELECT 1 FROM cards WHERE id=?", (card_id,)).fetchone():
        raise ValueError("SAM card was not found")
    quantity_event_id = None
    if action == "ADD_AS_NEW_INTAKE":
        quantity_event = _quantity_event(
            db, pool_id=pool_id, request_id=f"{request_id}:QUANTITY", event_type="SAM_INTAKE",
            quantity_delta=quantity, reason_code="NEW_POST_BOOTSTRAP_INTAKE",
            notes=payload.get("notes", ""), payload={"card_id": card_id},
        )
        quantity_event_id = quantity_event["id"]
    now = _now()
    cursor = db.execute(
        """INSERT INTO inventory_physical_reconciliation_events
           (event_uuid,request_id,pool_id,card_id,action,quantity,inventory_quantity_event_id,
            reason_code,notes,recorded_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (f"INV-PHYSICAL-{uuid.uuid4()}", request_id, pool_id, card_id, action, quantity,
         quantity_event_id, _clean(payload.get("reason_code"), 120), _clean(payload.get("notes"), 1000), now),
    )
    reconciled = int(db.execute(
        "SELECT COALESCE(SUM(quantity),0) FROM inventory_physical_reconciliation_events WHERE pool_id=?",
        (pool_id,),
    ).fetchone()[0])
    owned = _owned_quantity(db, pool_id)
    state = "NEW_POST_BOOTSTRAP_INTAKE" if action == "ADD_AS_NEW_INTAKE" else (
        "PHYSICALLY_RECONCILED" if reconciled >= owned else "BOOTSTRAPPED_UNRECONCILED"
    )
    db.execute("UPDATE inventory_pools SET physical_reconciliation_status=?,updated_at=? WHERE id=?", (state, now, pool_id))
    return {
        "reconciliation": dict(db.execute("SELECT * FROM inventory_physical_reconciliation_events WHERE id=?", (cursor.lastrowid,)).fetchone()),
        "pool": _pool_payload(db, db.execute("SELECT * FROM inventory_pools WHERE id=?", (pool_id,)).fetchone()),
    }


def _latest_batch(db: sqlite3.Connection) -> sqlite3.Row | None:
    return db.execute(
        """SELECT * FROM tcgplayer_import_batches WHERE status='APPLIED'
           ORDER BY source_export_timestamp DESC,id DESC LIMIT 1"""
    ).fetchone()


def export_preview(db: sqlite3.Connection, *, now: datetime | None = None) -> dict:
    batch = _latest_batch(db)
    if not batch:
        return {
            "available": False, "reason": "NO_APPLIED_SNAPSHOT", "calculation_version": CALCULATION_VERSION,
            "increasing_products": 0, "decreasing_products": 0, "unchanged_products": 0,
            "copies_added": 0, "copies_removed": 0, "warnings": ["Import and apply a TCGplayer snapshot first."],
        }
    current = now or datetime.now(timezone.utc)
    snapshot_at = datetime.fromisoformat(batch["source_export_timestamp"].replace("Z", "+00:00"))
    age_hours = max(0, (current - snapshot_at).total_seconds() / 3600)
    max_age = int(os.environ.get("DEX_TCGPLAYER_SNAPSHOT_MAX_AGE_HOURS", DEFAULT_MAX_SNAPSHOT_AGE_HOURS))
    events_after_snapshot = int(db.execute(
        """SELECT COUNT(*) FROM inventory_quantity_events
           WHERE id > ? AND (import_batch_id IS NULL OR import_batch_id != ?)""",
        (int(batch["inventory_event_watermark_id"] or 0), int(batch["id"])),
    ).fetchone()[0])
    stale_by_age = age_hours > max_age
    superseded_by_dex_events = events_after_snapshot > 0
    stale = stale_by_age or superseded_by_dex_events
    rows = db.execute("SELECT * FROM tcgplayer_snapshot_rows WHERE import_batch_id=? ORDER BY source_row_number", (batch["id"],)).fetchall()
    changes: list[dict] = []
    warnings: list[str] = []
    increasing = decreasing = unchanged = added = removed = 0
    missing_price = 0
    for row in rows:
        pool = db.execute("SELECT * FROM inventory_pools WHERE tcgplayer_id=? AND active=1", (row["tcgplayer_id"],)).fetchone()
        if not pool:
            if int(row["total_quantity"]) > 0:
                warnings.append(f"TCGplayer Id {row['tcgplayer_id']} has no authoritative DEX pool.")
            continue
        desired = max(0, _owned_quantity(db, int(pool["id"])) - int(pool["reserved_quantity"]))
        observed = int(row["total_quantity"])
        delta = desired - observed
        changes.append({"row": row, "pool_id": pool["id"], "desired": desired, "observed": observed, "delta": delta})
        if delta > 0:
            increasing += 1
            added += delta
        elif delta < 0:
            decreasing += 1
            removed += -delta
        else:
            unchanged += 1
        if delta and row["marketplace_price_cents"] is None:
            missing_price += 1
    total_observed = sum(int(item["observed"]) for item in changes)
    absolute_limit = int(os.environ.get("DEX_TCGPLAYER_DESTRUCTIVE_DELTA_ABSOLUTE", DEFAULT_DESTRUCTIVE_ABSOLUTE))
    percent_limit = Decimal(os.environ.get("DEX_TCGPLAYER_DESTRUCTIVE_DELTA_PERCENT", str(DEFAULT_DESTRUCTIVE_PERCENT)))
    destructive = removed >= absolute_limit or (
        total_observed >= 100 and Decimal(removed) >= Decimal(total_observed) * percent_limit
    )
    if stale_by_age:
        warnings.insert(0, "STALE TCGPLAYER SNAPSHOT — re-export before sync.")
    if superseded_by_dex_events:
        warnings.insert(0, "NEW DEX INVENTORY EVENTS AFTER SNAPSHOT — import a fresh TCGplayer export before sync.")
    if missing_price:
        warnings.append(f"{missing_price} changed row(s) lack the required TCG Marketplace Price.")
    if destructive:
        warnings.append("DESTRUCTIVE DELTA REVIEW REQUIRED — proposed removals exceed the safety threshold.")
    return {
        "available": True,
        "calculation_version": CALCULATION_VERSION,
        "import_uuid": batch["import_uuid"],
        "source_filename": batch["source_filename"],
        "source_export_timestamp": batch["source_export_timestamp"],
        "source_sha256": batch["source_sha256"],
        "snapshot_age_hours": round(age_hours, 2),
        "freshness_limit_hours": max_age,
        "stale": stale,
        "stale_by_age": stale_by_age,
        "superseded_by_dex_events": superseded_by_dex_events,
        "dex_events_after_snapshot": events_after_snapshot,
        "increasing_products": increasing,
        "decreasing_products": decreasing,
        "unchanged_products": unchanged,
        "copies_added": added,
        "copies_removed": removed,
        "missing_required_price_count": missing_price,
        "destructive_delta": destructive,
        "destructive_absolute_limit": absolute_limit,
        "destructive_percent_limit": float(percent_limit),
        "warnings": warnings,
        "_changes": changes,
        "_batch": batch,
    }


def generate_update_csv(
    db: sqlite3.Connection,
    *,
    request_id: str,
    confirm_destructive: bool = False,
    reason_code: str = "",
    notes: str = "",
    now: datetime | None = None,
) -> dict:
    request = _required_text(request_id, "request_id", 160)
    if db.execute("SELECT 1 FROM tcgplayer_inventory_audit_events WHERE request_id=?", (request,)).fetchone():
        raise ValueError("This export request was already used; no duplicate CSV was generated")
    preview = export_preview(db, now=now)
    if not preview["available"]:
        raise ValueError("Apply a TCGplayer snapshot before exporting updates")
    if preview["stale"]:
        raise ValueError("STALE TCGPLAYER SNAPSHOT — re-export before sync")
    if preview["missing_required_price_count"]:
        raise ValueError("Changed rows require a preserved TCG Marketplace Price")
    if preview["destructive_delta"]:
        if not confirm_destructive:
            raise ValueError("Destructive delta review and explicit confirmation are required")
        _required_text(reason_code, "reason_code", 120)
        _required_text(notes, "notes", 1000)
    batch = preview.pop("_batch")
    changes = preview.pop("_changes")
    headers = json.loads(batch["headers_json"])
    add_header = next(header for header in headers if _canonical_header(header) == "Add to Quantity")
    marketplace_header = next(header for header in headers if _canonical_header(header) == "TCG Marketplace Price")
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    exported_rows = 0
    for change in changes:
        if change["delta"] == 0:
            continue
        source = json.loads(change["row"]["raw_row_json"])
        source[add_header] = str(change["delta"])
        if not str(source.get(marketplace_header, "")).strip():
            raise ValueError("TCG Marketplace Price must be preserved for every changed row")
        writer.writerow(source)
        exported_rows += 1
    body = output.getvalue().encode("utf-8-sig")
    now_text = _now()
    db.execute(
        """INSERT INTO tcgplayer_inventory_audit_events
           (event_uuid,request_id,import_batch_id,event_type,payload_json,recorded_at)
           VALUES (?,?,?,?,?,?)""",
        (f"TCG-AUDIT-{uuid.uuid4()}", request, batch["id"], "UPDATE_CSV_GENERATED",
         json.dumps({"exported_rows": exported_rows, "copies_added": preview["copies_added"],
                     "copies_removed": preview["copies_removed"], "source_sha256": batch["source_sha256"],
                     "destructive_confirmed": bool(confirm_destructive), "reason_code": reason_code,
                     "notes_present": bool(notes)}, separators=(",", ":")), now_text),
    )
    filename = f"DEX_TCGplayer_Update_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return {
        "filename": filename,
        "content_base64": base64.b64encode(body).decode("ascii"),
        "sha256": hashlib.sha256(body).hexdigest(),
        "row_count": exported_rows,
        "summary": preview,
    }


def summary(db: sqlite3.Connection, *, query: str = "", limit: int = 200) -> dict:
    latest = _latest_batch(db)
    pending = db.execute(
        """SELECT * FROM tcgplayer_import_batches WHERE status='PREVIEWED'
           ORDER BY source_export_timestamp DESC,id DESC LIMIT 1"""
    ).fetchone()
    clauses = ["active=1"]
    params: list[object] = []
    if query.strip():
        clauses.append("(product_name LIKE ? OR card_number LIKE ? OR tcgplayer_id LIKE ? OR set_name LIKE ?)")
        term = f"%{query.strip()[:100]}%"
        params.extend([term, term, term, term])
    rows = db.execute(
        f"SELECT * FROM inventory_pools WHERE {' AND '.join(clauses)} ORDER BY product_line,product_name,condition_name LIMIT ?",
        (*params, max(1, min(int(limit), 1000))),
    ).fetchall()
    pools = [_pool_payload(db, row) for row in rows]
    totals = db.execute(
        """SELECT COUNT(*) AS pool_count,
                  COALESCE((SELECT SUM(quantity_delta) FROM inventory_quantity_events),0) AS owned_quantity,
                  COALESCE(SUM(reserved_quantity),0) AS reserved_quantity
           FROM inventory_pools WHERE active=1"""
    ).fetchone()
    status_counts = {row["status"]: row["count"] for row in db.execute(
        "SELECT status,COUNT(*) AS count FROM tcgplayer_reconciliation_items GROUP BY status"
    )}
    games = [dict(row) for row in db.execute(
        """SELECT p.product_line,COUNT(*) AS pool_count,
                  COALESCE(SUM((SELECT SUM(e.quantity_delta) FROM inventory_quantity_events e WHERE e.pool_id=p.id)),0) AS owned_quantity
           FROM inventory_pools p WHERE p.active=1 GROUP BY p.product_line ORDER BY p.product_line"""
    )]
    export = export_preview(db)
    export.pop("_changes", None)
    export.pop("_batch", None)
    reconciliation_items = [
        _reconciliation_payload(db, item)
        for item in db.execute(
            """SELECT * FROM tcgplayer_reconciliation_items
               WHERE status='OPEN' ORDER BY created_at DESC,id DESC LIMIT 500"""
        )
    ]
    return {
        "calculation_version": CALCULATION_VERSION,
        "contract_version": CONTRACT_VERSION,
        "latest_snapshot": _batch_payload(db, latest) if latest else None,
        "pending_preview": _batch_payload(db, pending) if pending else None,
        "totals": {
            "pool_count": int(totals["pool_count"]),
            "owned_quantity": int(totals["owned_quantity"] or 0),
            "reserved_quantity": int(totals["reserved_quantity"] or 0),
            "available_quantity": int(totals["owned_quantity"] or 0) - int(totals["reserved_quantity"] or 0),
            "open_reconciliation_count": int(status_counts.get("OPEN", 0)),
        },
        "games": games,
        "pools": pools,
        "reconciliation_items": reconciliation_items,
        "export_preview": export,
    }


def private_source_summary(db: sqlite3.Connection, import_uuid: str) -> dict:
    """Return aggregate-only evidence suitable for operator reports."""
    batch = db.execute("SELECT * FROM tcgplayer_import_batches WHERE import_uuid=?", (import_uuid,)).fetchone()
    if not batch:
        raise ValueError("TCGplayer import was not found")
    one_piece = db.execute(
        """SELECT import_disposition,COUNT(*) AS row_count,SUM(total_quantity) AS total_quantity
           FROM tcgplayer_snapshot_rows WHERE import_batch_id=? AND product_line='One Piece Card Game'
           GROUP BY import_disposition""",
        (batch["id"],),
    ).fetchall()
    return {
        "source_sha256": batch["source_sha256"],
        "row_count": batch["row_count"],
        "positive_quantity_row_count": batch["positive_quantity_row_count"],
        "zero_quantity_row_count": batch["zero_quantity_row_count"],
        "source_total_quantity": batch["source_total_quantity"],
        "one_piece_dispositions": [dict(row) for row in one_piece],
        "games": _batch_payload(db, batch)["game_summary"],
    }
