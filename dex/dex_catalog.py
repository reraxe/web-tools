"""DEX v2.2 Inbound 2.0 Phase 3 commercial product catalog and UPC intake.

This module identifies commercial products only. It never creates processing
batches, sealed-unit identities, card basis, receipt facts, or economics.
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Mapping

from dex_inbound import acquisition_payload


IDENTIFIER_TYPES = ("UPC_A", "EAN_13", "GTIN_14", "INTERNAL")
SCANNABLE_PRODUCT_CLASSES = ("PACK_PRODUCT", "SEALED_PRODUCT")
MAPPING_STATUSES = ("ACTIVE", "INACTIVE", "CONFLICT_REVIEW")
PRODUCT_PROVENANCE = ("OPERATOR_DEFINED", "OPERATOR_CONFIRMED", "MANUFACTURER", "IMPORT", "SEED_FIXTURE")
MAPPING_PROVENANCE = ("OPERATOR_CONFIRMED", "MANUFACTURER", "IMPORT", "SEED_FIXTURE")
CORRECTION_REASONS = ("WRONG_PRODUCT", "MANUFACTURER_CORRECTION", "DUPLICATE_ENTRY", "OTHER")
CATALOG_CALCULATION_VERSION = "product-catalog-v1"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _text(value: object, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _required_request_id(payload: Mapping[str, object]) -> str:
    request_id = _text(payload.get("request_id"), 120)
    if not request_id:
        raise ValueError("A unique request_id is required")
    return request_id


def _confirmed(value: object) -> bool:
    return value is True or value == 1 or str(value or "").strip().lower() in {"true", "yes", "on"}


def _require_revision(acquisition: sqlite3.Row, payload: Mapping[str, object]) -> None:
    supplied = payload.get("expected_revision")
    if isinstance(supplied, bool) or not isinstance(supplied, int):
        raise ValueError("expected_revision is required")
    if supplied != int(acquisition["revision"]):
        raise ValueError("Acquisition changed since it was loaded; reload before saving")


def _require_draft(acquisition: sqlite3.Row) -> None:
    if acquisition["state"] not in ("ACQUISITION_INCOMPLETE", "RECONCILIATION_REQUIRED"):
        raise ValueError("Product intake can change only an incomplete acquisition")


def _gtin_check_digit(data_digits: str) -> int:
    total = 0
    for index, digit in enumerate(reversed(data_digits)):
        total += int(digit) * (3 if index % 2 == 0 else 1)
    return (10 - total % 10) % 10


def normalize_identifier(raw_identifier: object, identifier_type: object = "") -> dict:
    """Normalize supported identifiers while preserving leading zeroes.

    Standard retail codes use their canonical zero-padded GTIN-14 value for
    uniqueness. The raw scanned representation and original symbology remain
    separate facts.
    """

    raw = _text(raw_identifier, 120)
    if not raw:
        raise ValueError("A product identifier is required")
    requested_type = _text(identifier_type, 20).upper().replace("-", "_")
    compact = re.sub(r"[\s-]+", "", raw)
    inferred = {12: "UPC_A", 13: "EAN_13", 14: "GTIN_14"}.get(len(compact)) if compact.isdigit() else None
    kind = requested_type or inferred or "INTERNAL"
    if kind not in IDENTIFIER_TYPES:
        raise ValueError("Identifier type must be UPC-A, EAN-13, GTIN-14, or Internal")
    if kind == "INTERNAL":
        normalized = raw.upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9._:/-]{1,79}", normalized):
            raise ValueError("Internal identifiers must be 2-80 letters, numbers, or . _ : / - characters")
        return {
            "raw_identifier": raw,
            "normalized_identifier": normalized,
            "identifier_type": kind,
            "valid_check_digit": None,
        }
    expected_length = {"UPC_A": 12, "EAN_13": 13, "GTIN_14": 14}[kind]
    if not compact.isdigit() or len(compact) != expected_length:
        raise ValueError(f"{kind.replace('_', '-')} must contain exactly {expected_length} digits")
    expected = _gtin_check_digit(compact[:-1])
    if int(compact[-1]) != expected:
        raise ValueError(f"Invalid {kind.replace('_', '-')} check digit")
    return {
        "raw_identifier": raw,
        "normalized_identifier": compact.zfill(14),
        "identifier_type": kind,
        "valid_check_digit": True,
    }


def _product_row(db: sqlite3.Connection, product_id: int, *, require_active: bool = True) -> sqlite3.Row:
    row = db.execute("SELECT * FROM catalog_products WHERE id=?", (product_id,)).fetchone()
    if not row:
        raise ValueError("Catalog product not found")
    if require_active and not row["active"]:
        raise ValueError("Catalog product is inactive")
    return row


def _identifier_row(db: sqlite3.Connection, identifier_id: int) -> sqlite3.Row:
    row = db.execute("SELECT * FROM product_identifiers WHERE id=?", (identifier_id,)).fetchone()
    if not row:
        raise ValueError("Product identifier mapping not found")
    return row


def catalog_product_payload(db: sqlite3.Connection, product_id: int) -> dict:
    product = dict(_product_row(db, product_id, require_active=False))
    product["identifiers"] = [
        dict(row)
        for row in db.execute(
            """SELECT id,identifier_uuid,normalized_identifier,raw_identifier,identifier_type,
                      mapping_status,provenance,created_at,verified_at,updated_at
                 FROM product_identifiers WHERE catalog_product_id=?
                 ORDER BY mapping_status='ACTIVE' DESC,identifier_type,normalized_identifier""",
            (product_id,),
        ).fetchall()
    ]
    return product


def search_catalog_products(
    db: sqlite3.Connection,
    query: str = "",
    product_class: str = "",
    *,
    include_inactive: bool = False,
    limit: int = 50,
) -> list[dict]:
    text = _text(query, 120)
    klass = _text(product_class, 40).upper()
    clauses: list[str] = []
    params: list[object] = []
    if not include_inactive:
        clauses.append("active=1")
    if klass:
        clauses.append("product_class=?")
        params.append(klass)
    if text:
        pattern = f"%{text}%"
        clauses.append(
            "(display_name LIKE ? COLLATE NOCASE OR game LIKE ? COLLATE NOCASE OR "
            "set_code LIKE ? COLLATE NOCASE OR set_name LIKE ? COLLATE NOCASE OR "
            "manufacturer_product_code LIKE ? COLLATE NOCASE)"
        )
        params.extend([pattern] * 5)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = db.execute(
        f"""SELECT id FROM catalog_products {where}
             ORDER BY active DESC,game,set_code,display_name,id LIMIT ?""",
        (*params, max(1, min(int(limit), 200))),
    ).fetchall()
    return [catalog_product_payload(db, int(row["id"])) for row in rows]


def _normalized_product_fields(payload: Mapping[str, object]) -> dict:
    game = _text(payload.get("game"), 80)
    name = _text(payload.get("display_name") or payload.get("product_name"), 180)
    product_class = _text(payload.get("product_class"), 40).upper()
    subtype = _text(payload.get("product_subtype") or payload.get("pack_type"), 80)
    provenance = _text(payload.get("provenance") or "OPERATOR_DEFINED", 40).upper()
    if not game:
        raise ValueError("Catalog product requires a TCG/game")
    if not name:
        raise ValueError("Catalog product requires a display name")
    if product_class not in SCANNABLE_PRODUCT_CLASSES:
        raise ValueError("Phase 3 catalog products must be Pack Product or Sealed Product")
    if not subtype:
        raise ValueError("Catalog product requires a product subtype")
    if provenance not in PRODUCT_PROVENANCE:
        raise ValueError("Catalog product provenance is not supported")
    return {
        "game": game,
        "display_name": name,
        "set_code": _text(payload.get("set_code"), 60),
        "set_name": _text(payload.get("set_name"), 120),
        "product_class": product_class,
        "product_subtype": subtype,
        "manufacturer_product_code": _text(payload.get("manufacturer_product_code"), 120),
        "provenance": provenance,
    }


def create_catalog_product(db: sqlite3.Connection, payload: Mapping[str, object]) -> dict:
    request_id = _required_request_id(payload)
    existing = db.execute(
        "SELECT id FROM catalog_products WHERE creation_request_id=?", (request_id,)
    ).fetchone()
    if existing:
        result = catalog_product_payload(db, int(existing["id"]))
        result["idempotent_replay"] = True
        return result
    values = _normalized_product_fields(payload)
    now = utcnow()
    cursor = db.execute(
        """INSERT INTO catalog_products
           (product_uuid,creation_request_id,game,display_name,set_code,set_name,product_class,
            product_subtype,manufacturer_product_code,active,provenance,created_at,verified_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,1,?,?,?,?)""",
        (
            f"CATPROD-{uuid.uuid4()}",
            request_id,
            values["game"],
            values["display_name"],
            values["set_code"],
            values["set_name"],
            values["product_class"],
            values["product_subtype"],
            values["manufacturer_product_code"],
            values["provenance"],
            now,
            now if _confirmed(payload.get("verified")) else None,
            now,
        ),
    )
    return catalog_product_payload(db, int(cursor.lastrowid))


def _event_payload(row: sqlite3.Row) -> dict:
    result = dict(row)
    result["payload"] = json.loads(result.pop("payload") or "{}")
    return result


def _event_by_request(db: sqlite3.Connection, request_id: str) -> dict | None:
    row = db.execute(
        "SELECT * FROM product_identifier_events WHERE request_id=?", (request_id,)
    ).fetchone()
    return _event_payload(row) if row else None


def _record_event(
    db: sqlite3.Connection,
    *,
    request_id: str,
    event_type: str,
    identifier_id: int | None = None,
    acquisition_id: int | None = None,
    acquisition_line_id: int | None = None,
    from_product_id: int | None = None,
    to_product_id: int | None = None,
    reason_code: str = "",
    notes: str = "",
    payload: Mapping[str, object] | None = None,
) -> str:
    event_id = f"CATALOGEVT-{uuid.uuid4()}"
    now = utcnow()
    db.execute(
        """INSERT INTO product_identifier_events
           (event_id,request_id,identifier_id,acquisition_id,acquisition_line_id,event_type,
            from_catalog_product_id,to_catalog_product_id,effective_at,recorded_at,
            reason_code,notes,payload)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            event_id,
            request_id,
            identifier_id,
            acquisition_id,
            acquisition_line_id,
            event_type,
            from_product_id,
            to_product_id,
            now,
            now,
            reason_code,
            notes,
            json.dumps(dict(payload or {}), separators=(",", ":"), sort_keys=True),
        ),
    )
    return event_id


def add_identifier_mapping(db: sqlite3.Connection, product_id: int, payload: Mapping[str, object]) -> dict:
    request_id = _required_request_id(payload)
    replay = _event_by_request(db, request_id)
    if replay:
        if replay["event_type"] != "MAPPING_CREATED" or replay["to_catalog_product_id"] != product_id:
            raise ValueError("request_id already belongs to a different catalog mutation")
        result = lookup_identifier(db, replay["payload"]["raw_identifier"], replay["payload"]["identifier_type"])
        result["idempotent_replay"] = True
        return result
    product = _product_row(db, product_id)
    normalized = normalize_identifier(payload.get("raw_identifier"), payload.get("identifier_type"))
    existing = db.execute(
        "SELECT * FROM product_identifiers WHERE normalized_identifier=?",
        (normalized["normalized_identifier"],),
    ).fetchone()
    if existing:
        if int(existing["catalog_product_id"]) != product_id:
            current = catalog_product_payload(db, int(existing["catalog_product_id"]))
            raise ValueError(
                f"Identifier is already mapped to {current['display_name']}; use the audited correction workflow"
            )
        result = lookup_identifier(db, normalized["raw_identifier"], normalized["identifier_type"])
        result["already_mapped"] = True
        return result
    provenance = _text(payload.get("provenance") or "OPERATOR_CONFIRMED", 40).upper()
    if provenance not in MAPPING_PROVENANCE:
        raise ValueError("Identifier mapping provenance is not supported")
    now = utcnow()
    cursor = db.execute(
        """INSERT INTO product_identifiers
           (identifier_uuid,normalized_identifier,raw_identifier,identifier_type,catalog_product_id,
            mapping_status,provenance,created_at,verified_at,updated_at)
           VALUES (?,?,?,?,?,'ACTIVE',?,?,?,?)""",
        (
            f"CATID-{uuid.uuid4()}",
            normalized["normalized_identifier"],
            normalized["raw_identifier"],
            normalized["identifier_type"],
            product_id,
            provenance,
            now,
            now if _confirmed(payload.get("verified", True)) else None,
            now,
        ),
    )
    identifier_id = int(cursor.lastrowid)
    event_id = _record_event(
        db,
        request_id=request_id,
        event_type="MAPPING_CREATED",
        identifier_id=identifier_id,
        to_product_id=product_id,
        reason_code="OPERATOR_CONFIRMED_MAPPING" if provenance == "OPERATOR_CONFIRMED" else provenance,
        payload={
            **normalized,
            "catalog_product_uuid": product["product_uuid"],
            "provenance": provenance,
            "calculation_version": CATALOG_CALCULATION_VERSION,
        },
    )
    result = lookup_identifier(db, normalized["raw_identifier"], normalized["identifier_type"])
    result["event_id"] = event_id
    return result


def lookup_identifier(db: sqlite3.Connection, raw_identifier: object, identifier_type: object = "") -> dict:
    normalized = normalize_identifier(raw_identifier, identifier_type)
    row = db.execute(
        """SELECT pi.*,cp.active AS product_active
             FROM product_identifiers pi JOIN catalog_products cp ON cp.id=pi.catalog_product_id
            WHERE pi.normalized_identifier=? AND pi.mapping_status='ACTIVE'""",
        (normalized["normalized_identifier"],),
    ).fetchone()
    if not row or not row["product_active"]:
        return {
            "status": "UNKNOWN",
            "decision_level": "NEEDS_ATTENTION",
            "identifier": normalized,
            "product": None,
            "message": "Product not recognized",
        }
    return {
        "status": "RECOGNIZED",
        "decision_level": "AUTOMATIC_VISIBLE",
        "identifier": {
            **normalized,
            "mapping_id": int(row["id"]),
            "mapping_status": row["mapping_status"],
            "mapping_provenance": row["provenance"],
            "mapping_verified_at": row["verified_at"],
        },
        "product": catalog_product_payload(db, int(row["catalog_product_id"])),
        "message": "Product recognized",
    }


def identifier_history(db: sqlite3.Connection, identifier_id: int) -> dict:
    identifier = dict(_identifier_row(db, identifier_id))
    identifier["product"] = catalog_product_payload(db, int(identifier["catalog_product_id"]))
    identifier["events"] = [
        _event_payload(row)
        for row in db.execute(
            "SELECT * FROM product_identifier_events WHERE identifier_id=? ORDER BY rowid",
            (identifier_id,),
        ).fetchall()
    ]
    return identifier


def correct_identifier_mapping(db: sqlite3.Connection, identifier_id: int, payload: Mapping[str, object]) -> dict:
    request_id = _required_request_id(payload)
    replay = _event_by_request(db, request_id)
    if replay:
        if replay["event_type"] != "MAPPING_CORRECTED" or replay["identifier_id"] != identifier_id:
            raise ValueError("request_id already belongs to a different catalog mutation")
        result = identifier_history(db, identifier_id)
        result["idempotent_replay"] = True
        return result
    identifier = _identifier_row(db, identifier_id)
    new_product_id = payload.get("catalog_product_id")
    if isinstance(new_product_id, bool) or not isinstance(new_product_id, int):
        raise ValueError("Corrected catalog_product_id is required")
    new_product = _product_row(db, new_product_id)
    old_product_id = int(identifier["catalog_product_id"])
    if old_product_id == new_product_id:
        raise ValueError("Identifier already maps to that catalog product")
    reason = _text(payload.get("reason_code"), 50).upper()
    notes = _text(payload.get("notes"), 1000)
    if reason not in CORRECTION_REASONS:
        raise ValueError("A standardized mapping-correction reason is required")
    if not notes:
        raise ValueError("Mapping corrections require an explanatory note")
    now = utcnow()
    db.execute(
        """UPDATE product_identifiers
              SET catalog_product_id=?,provenance='OPERATOR_CONFIRMED',verified_at=?,updated_at=?
            WHERE id=?""",
        (new_product_id, now, now, identifier_id),
    )
    event_id = _record_event(
        db,
        request_id=request_id,
        event_type="MAPPING_CORRECTED",
        identifier_id=identifier_id,
        from_product_id=old_product_id,
        to_product_id=new_product_id,
        reason_code=reason,
        notes=notes,
        payload={
            "normalized_identifier": identifier["normalized_identifier"],
            "old_product_uuid": _product_row(db, old_product_id, require_active=False)["product_uuid"],
            "new_product_uuid": new_product["product_uuid"],
            "calculation_version": CATALOG_CALCULATION_VERSION,
        },
    )
    result = identifier_history(db, identifier_id)
    result["event_id"] = event_id
    return result


def _acquisition_row(db: sqlite3.Connection, acquisition_id: int) -> sqlite3.Row:
    row = db.execute("SELECT * FROM acquisitions WHERE id=?", (acquisition_id,)).fetchone()
    if not row:
        raise ValueError("Acquisition not found")
    return row


def _line_identity(product: sqlite3.Row) -> dict:
    return {
        "product_class": product["product_class"],
        "game": product["game"],
        "product_name": product["display_name"],
        "set_code": product["set_code"],
        "pack_type": product["product_subtype"] if product["product_class"] == "PACK_PRODUCT" else "",
        "quantity_certainty": "KNOWN",
        "catalog_product_id": int(product["id"]),
    }


def _blank_catalog_line(db: sqlite3.Connection, acquisition_id: int) -> sqlite3.Row | None:
    return db.execute(
        """SELECT * FROM acquisition_lines
            WHERE acquisition_id=? AND canceled_at IS NULL AND catalog_product_id IS NULL
              AND product_class IN ('PACK_PRODUCT','SEALED_PRODUCT')
              AND game='' AND product_name='' AND set_code='' AND quantity IS NULL
            ORDER BY line_sequence,id LIMIT 1""",
        (acquisition_id,),
    ).fetchone()


def _apply_product_quantity(
    db: sqlite3.Connection,
    acquisition: sqlite3.Row,
    product: sqlite3.Row,
    *,
    request_id: str,
    identifier_id: int | None,
    normalized: Mapping[str, object] | None,
    local_only: bool = False,
    local_fields: Mapping[str, object] | None = None,
) -> tuple[int, int, str, str]:
    acquisition_id = int(acquisition["id"])
    line = None
    if not local_only:
        line = db.execute(
            """SELECT * FROM acquisition_lines
                WHERE acquisition_id=? AND catalog_product_id=? AND canceled_at IS NULL
                ORDER BY line_sequence,id LIMIT 1""",
            (acquisition_id, int(product["id"])),
        ).fetchone()
    if line:
        before = int(line["quantity"] or 0)
        after = before + 1
        db.execute(
            "UPDATE acquisition_lines SET quantity=?,quantity_certainty='KNOWN',updated_at=? WHERE id=?",
            (after, utcnow(), int(line["id"])),
        )
        line_id = int(line["id"])
        action = "QUANTITY_INCREMENTED"
    else:
        line = _blank_catalog_line(db, acquisition_id)
        fields = dict(local_fields or _line_identity(product))
        before = int(line["quantity"] or 0) if line else 0
        after = before + 1
        now = utcnow()
        if line:
            assignments = {
                **fields,
                "quantity": after,
                "quantity_certainty": "KNOWN",
                "allocation_status": "UNALLOCATED",
                "assigned_landed_cost_cents": None,
                "allocation_method": "",
                "updated_at": now,
            }
            db.execute(
                f"UPDATE acquisition_lines SET {','.join(f'{key}=?' for key in assignments)} WHERE id=?",
                (*assignments.values(), int(line["id"])),
            )
            line_id = int(line["id"])
            action = "LINE_POPULATED"
        else:
            sequence = int(
                db.execute(
                    "SELECT COALESCE(MAX(line_sequence),0)+1 FROM acquisition_lines WHERE acquisition_id=?",
                    (acquisition_id,),
                ).fetchone()[0]
            )
            values = {
                "line_uuid": f"ACQLINE-{uuid.uuid4()}",
                "acquisition_id": acquisition_id,
                "line_sequence": sequence,
                **fields,
                "quantity": 1,
                "quantity_certainty": "KNOWN",
                "created_at": now,
                "updated_at": now,
            }
            cursor = db.execute(
                f"INSERT INTO acquisition_lines ({','.join(values)}) VALUES ({','.join('?' for _ in values)})",
                tuple(values.values()),
            )
            line_id = int(cursor.lastrowid)
            action = "LINE_CREATED"
    now = utcnow()
    db.execute(
        """UPDATE acquisitions SET state='ACQUISITION_INCOMPLETE',financial_facts_confirmed=0,
                  reconciliation_confirmed=0,confirmed_at=NULL,revision=revision+1,updated_at=? WHERE id=?""",
        (now, acquisition_id),
    )
    event_id = _record_event(
        db,
        request_id=request_id,
        event_type="LOCAL_IDENTIFICATION_APPLIED" if local_only else "SCAN_APPLIED",
        identifier_id=identifier_id,
        acquisition_id=acquisition_id,
        acquisition_line_id=line_id,
        to_product_id=None if local_only else int(product["id"]),
        reason_code="ACQUISITION_LOCAL_ONLY" if local_only else "RECOGNIZED_IDENTIFIER",
        payload={
            "calculation_version": CATALOG_CALCULATION_VERSION,
            "identifier": dict(normalized or {}),
            "action": action,
            "quantity_before": before,
            "quantity_after": after,
            "catalog_mapping_remembered": not local_only,
        },
    )
    return line_id, after, action, event_id


def scan_apply_product(db: sqlite3.Connection, acquisition_id: int, payload: Mapping[str, object]) -> dict:
    request_id = _required_request_id(payload)
    normalized = normalize_identifier(payload.get("raw_identifier"), payload.get("identifier_type"))
    replay = _event_by_request(db, request_id)
    if replay:
        if replay["event_type"] != "SCAN_APPLIED" or replay["acquisition_id"] != acquisition_id:
            raise ValueError("request_id already belongs to a different catalog mutation")
        if replay["payload"].get("identifier", {}).get("normalized_identifier") != normalized["normalized_identifier"]:
            raise ValueError("request_id already belongs to a different scanned identifier")
        replay_payload = replay["payload"]
        result = acquisition_payload(db, acquisition_id)
        return {
            "status": "RECOGNIZED",
            "decision_level": "AUTOMATIC_VISIBLE",
            "idempotent_replay": True,
            "scan": {
                "action": replay_payload.get("action"),
                "line_id": replay["acquisition_line_id"],
                "quantity": replay_payload.get("quantity_after"),
                "event_id": replay["event_id"],
            },
            "acquisition": result,
        }
    lookup = lookup_identifier(db, normalized["raw_identifier"], normalized["identifier_type"])
    if lookup["status"] == "UNKNOWN":
        return {**lookup, "acquisition": acquisition_payload(db, acquisition_id)}
    acquisition = _acquisition_row(db, acquisition_id)
    _require_revision(acquisition, payload)
    _require_draft(acquisition)
    identifier_id = int(lookup["identifier"]["mapping_id"])
    product = _product_row(db, int(lookup["product"]["id"]))
    line_id, quantity, action, event_id = _apply_product_quantity(
        db,
        acquisition,
        product,
        request_id=request_id,
        identifier_id=identifier_id,
        normalized=normalized,
    )
    return {
        "status": "RECOGNIZED",
        "decision_level": "AUTOMATIC_VISIBLE",
        "identifier": lookup["identifier"],
        "product": catalog_product_payload(db, int(product["id"])),
        "scan": {"action": action, "line_id": line_id, "quantity": quantity, "event_id": event_id},
        "acquisition": acquisition_payload(db, acquisition_id),
    }


def identify_unknown_product(db: sqlite3.Connection, acquisition_id: int, payload: Mapping[str, object]) -> dict:
    """Apply operator identification locally, optionally remembering a mapping."""

    request_id = _required_request_id(payload)
    normalized = normalize_identifier(payload.get("raw_identifier"), payload.get("identifier_type"))
    replay = _event_by_request(db, request_id)
    if replay:
        if replay["acquisition_id"] != acquisition_id:
            raise ValueError("request_id already belongs to a different acquisition")
        replay_payload = replay["payload"]
        return {
            "status": "IDENTIFIED",
            "decision_level": "AUTOMATIC_VISIBLE",
            "idempotent_replay": True,
            "scan": {
                "action": replay_payload.get("action"),
                "line_id": replay["acquisition_line_id"],
                "quantity": replay_payload.get("quantity_after"),
                "event_id": replay["event_id"],
            },
            "acquisition": acquisition_payload(db, acquisition_id),
        }
    acquisition = _acquisition_row(db, acquisition_id)
    _require_revision(acquisition, payload)
    _require_draft(acquisition)
    remember = _confirmed(payload.get("remember_mapping"))
    product_id = payload.get("catalog_product_id")
    if product_id is not None and (isinstance(product_id, bool) or not isinstance(product_id, int)):
        raise ValueError("catalog_product_id must be a whole number")
    if product_id is None:
        fields = _normalized_product_fields(payload)
        if remember:
            product = create_catalog_product(
                db,
                {**fields, "request_id": f"{request_id}:product", "verified": True},
            )
            product_id = int(product["id"])
        else:
            local_fields = {
                "product_class": fields["product_class"],
                "game": fields["game"],
                "product_name": fields["display_name"],
                "set_code": fields["set_code"],
                "pack_type": fields["product_subtype"] if fields["product_class"] == "PACK_PRODUCT" else "",
                "catalog_product_id": None,
            }
            placeholder = {
                "id": 0,
                "product_uuid": "",
                "product_class": fields["product_class"],
                "game": fields["game"],
                "display_name": fields["display_name"],
                "set_code": fields["set_code"],
                "product_subtype": fields["product_subtype"],
            }
            line_id, quantity, action, event_id = _apply_product_quantity(
                db,
                acquisition,
                placeholder,  # type: ignore[arg-type]
                request_id=request_id,
                identifier_id=None,
                normalized=normalized,
                local_only=True,
                local_fields=local_fields,
            )
            return {
                "status": "IDENTIFIED_LOCAL",
                "decision_level": "AUTOMATIC_VISIBLE",
                "identifier": normalized,
                "product": {**fields, "catalog_product_id": None},
                "scan": {"action": action, "line_id": line_id, "quantity": quantity, "event_id": event_id},
                "mapping_remembered": False,
                "acquisition": acquisition_payload(db, acquisition_id),
            }
    product = _product_row(db, int(product_id))
    if remember:
        add_identifier_mapping(
            db,
            int(product_id),
            {
                "request_id": f"{request_id}:mapping",
                "raw_identifier": normalized["raw_identifier"],
                "identifier_type": normalized["identifier_type"],
                "provenance": "OPERATOR_CONFIRMED",
                "verified": True,
            },
        )
        lookup = lookup_identifier(db, normalized["raw_identifier"], normalized["identifier_type"])
        identifier_id = int(lookup["identifier"]["mapping_id"])
    else:
        identifier_id = None
    line_id, quantity, action, event_id = _apply_product_quantity(
        db,
        acquisition,
        product,
        request_id=request_id,
        identifier_id=identifier_id,
        normalized=normalized,
        local_only=not remember,
        local_fields=(
            {
                **_line_identity(product),
                "catalog_product_id": int(product["id"]),
            }
            if not remember
            else None
        ),
    )
    return {
        "status": "IDENTIFIED_AND_REMEMBERED" if remember else "IDENTIFIED_LOCAL",
        "decision_level": "AUTOMATIC_VISIBLE",
        "identifier": normalized,
        "product": catalog_product_payload(db, int(product["id"])),
        "scan": {"action": action, "line_id": line_id, "quantity": quantity, "event_id": event_id},
        "mapping_remembered": remember,
        "acquisition": acquisition_payload(db, acquisition_id),
    }


def apply_catalog_product_to_line(db: sqlite3.Connection, line_id: int, payload: Mapping[str, object]) -> dict:
    request_id = _required_request_id(payload)
    replay = _event_by_request(db, request_id)
    line = db.execute("SELECT * FROM acquisition_lines WHERE id=?", (line_id,)).fetchone()
    if not line:
        raise ValueError("Acquisition line not found")
    acquisition_id = int(line["acquisition_id"])
    if replay:
        if replay["event_type"] != "CATALOG_PRODUCT_APPLIED" or replay["acquisition_line_id"] != line_id:
            raise ValueError("request_id already belongs to a different catalog mutation")
        result = acquisition_payload(db, acquisition_id)
        result["idempotent_replay"] = True
        return result
    acquisition = _acquisition_row(db, acquisition_id)
    _require_revision(acquisition, payload)
    _require_draft(acquisition)
    product_id = payload.get("catalog_product_id")
    if isinstance(product_id, bool) or not isinstance(product_id, int):
        raise ValueError("catalog_product_id is required")
    product = _product_row(db, product_id)
    identity = _line_identity(product)
    now = utcnow()
    db.execute(
        """UPDATE acquisition_lines
              SET product_class=?,game=?,product_name=?,set_code=?,pack_type=?,catalog_product_id=?,
                  allocation_status='UNALLOCATED',assigned_landed_cost_cents=NULL,allocation_method='',updated_at=?
            WHERE id=? AND canceled_at IS NULL""",
        (
            identity["product_class"], identity["game"], identity["product_name"],
            identity["set_code"], identity["pack_type"], identity["catalog_product_id"], now, line_id,
        ),
    )
    db.execute(
        """UPDATE acquisitions SET state='ACQUISITION_INCOMPLETE',financial_facts_confirmed=0,
                  reconciliation_confirmed=0,confirmed_at=NULL,revision=revision+1,updated_at=? WHERE id=?""",
        (now, acquisition_id),
    )
    _record_event(
        db,
        request_id=request_id,
        event_type="CATALOG_PRODUCT_APPLIED",
        acquisition_id=acquisition_id,
        acquisition_line_id=line_id,
        from_product_id=int(line["catalog_product_id"]) if line["catalog_product_id"] else None,
        to_product_id=product_id,
        reason_code="MANUAL_CATALOG_SELECTION",
        payload={"calculation_version": CATALOG_CALCULATION_VERSION},
    )
    return acquisition_payload(db, acquisition_id)


def catalog_contract() -> dict:
    return {
        "phase": "INBOUND_2_PHASE_3_PRODUCT_CATALOG_UPC",
        "calculation_version": CATALOG_CALCULATION_VERSION,
        "identifier_types": list(IDENTIFIER_TYPES),
        "scannable_product_classes": list(SCANNABLE_PRODUCT_CLASSES),
        "mapping_statuses": list(MAPPING_STATUSES),
        "decision_levels": ["AUTOMATIC_VISIBLE", "NEEDS_ATTENTION"],
        "boundaries": {
            "commercial_product_identity_only": True,
            "single_cards_use_upc": False,
            "sealed_unit_identity": False,
            "receipt_documents": False,
            "receipt_extraction": False,
            "sam": False,
            "batch_projection": False,
            "economics": False,
            "global_attention_center": False,
        },
    }
