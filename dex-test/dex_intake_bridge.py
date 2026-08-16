"""Inbound 2.0 Phase 6 acquisition-to-inventory routing bridge.

Confirmed acquisition lines project into the established batch, sealed-unit,
and rip-session architecture.  Routing facts are append-only and every write is
expected to run inside the caller's ``BEGIN IMMEDIATE`` transaction.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Mapping

from dex_economics import allocate_cents
from dex_rip import create_rip_session
from dex_sealed import synchronize_sealed_units


CALCULATION_VERSION = "inbound-intake-bridge-v1"
ROUTE_ACTIONS = ("KEEP_SEALED", "RIP_OPEN", "SCAN_IDENTIFY")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _text(value: object, limit: int = 500) -> str:
    return str(value or "").strip()[:limit]


def _integer(value: object, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a whole number")
    try:
        result = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a whole number") from None
    if result < minimum:
        raise ValueError(f"{label} must be at least {minimum}")
    return result


def _acquisition(db: sqlite3.Connection, acquisition_id: int) -> sqlite3.Row:
    row = db.execute(
        "SELECT * FROM acquisitions WHERE id=?", (acquisition_id,)
    ).fetchone()
    if not row:
        raise ValueError("Acquisition not found")
    return row


def _active_lines(db: sqlite3.Connection, acquisition_id: int) -> list[sqlite3.Row]:
    return db.execute(
        """SELECT * FROM acquisition_lines
             WHERE acquisition_id=? AND canceled_at IS NULL
             ORDER BY line_sequence,id""",
        (acquisition_id,),
    ).fetchall()


def _allowed_actions(product_class: str) -> tuple[str, ...]:
    if product_class == "SINGLE_CARDS":
        return ("SCAN_IDENTIFY",)
    return ("KEEP_SEALED", "RIP_OPEN")


def _routed(db: sqlite3.Connection, line_id: int) -> dict[str, int]:
    totals = {action: 0 for action in ROUTE_ACTIONS}
    basis = {action: 0 for action in ROUTE_ACTIONS}
    for row in db.execute(
        """SELECT route_action,COALESCE(SUM(quantity),0) AS quantity,
                  COALESCE(SUM(basis_cents),0) AS basis_cents
             FROM acquisition_intake_route_events
            WHERE acquisition_line_id=? GROUP BY route_action""",
        (line_id,),
    ).fetchall():
        totals[row["route_action"]] = int(row["quantity"])
        basis[row["route_action"]] = int(row["basis_cents"])
    return {**{f"{key}_quantity": value for key, value in totals.items()},
            **{f"{key}_basis_cents": value for key, value in basis.items()}}


def _projection(db: sqlite3.Connection, line_id: int) -> sqlite3.Row | None:
    return db.execute(
        """SELECT p.*,b.batch_code,b.status AS batch_status,b.economics_status
             FROM acquisition_line_projections p JOIN batches b ON b.id=p.batch_id
            WHERE p.acquisition_line_id=?""",
        (line_id,),
    ).fetchone()


def _line_unit_allocations(line: sqlite3.Row) -> list[int]:
    if line["assigned_landed_cost_cents"] is None or not line["quantity"]:
        return []
    return [
        item.cents
        for item in allocate_cents(
            int(line["assigned_landed_cost_cents"]),
            range(1, int(line["quantity"]) + 1),
        )
    ]


def _line_status(db: sqlite3.Connection, line: sqlite3.Row) -> dict:
    routed = _routed(db, int(line["id"]))
    projection = _projection(db, int(line["id"]))
    quantity = int(line["quantity"] or 0)
    routed_quantity = sum(
        int(routed[f"{action}_quantity"]) for action in ROUTE_ACTIONS
    )
    routed_basis = sum(int(routed[f"{action}_basis_cents"]) for action in ROUTE_ACTIONS)
    cost_value = line["assigned_landed_cost_cents"]
    cost = int(cost_value or 0)
    links: list[dict] = []
    if projection:
        rip_rows = db.execute(
            """SELECT id,rip_code,status,units_opened FROM rip_sessions
                 WHERE batch_id=? ORDER BY id""",
            (projection["batch_id"],),
        ).fetchall()
        links.append({
            "kind": "BATCH",
            "id": int(projection["batch_id"]),
            "label": projection["batch_code"],
            "status": projection["batch_status"],
        })
        links.extend({
            "kind": "RIP_SESSION",
            "id": int(rip["id"]),
            "label": rip["rip_code"],
            "status": rip["status"],
            "units_opened": int(rip["units_opened"]),
        } for rip in rip_rows)
    per_unit = _line_unit_allocations(line)
    return {
        "line_id": int(line["id"]),
        "line_uuid": line["line_uuid"],
        "line_sequence": int(line["line_sequence"]),
        "product_class": line["product_class"],
        "game": line["game"],
        "product_name": line["product_name"],
        "set_code": line["set_code"],
        "pack_type": line["pack_type"],
        "catalog_product_id": line["catalog_product_id"],
        "quantity_acquired": quantity,
        "landed_cost_cents": cost,
        "landed_cost_known": cost_value is not None,
        "allocation_method": line["allocation_method"],
        "allowed_actions": list(_allowed_actions(line["product_class"])),
        "routed": {
            "keep_sealed_quantity": routed["KEEP_SEALED_quantity"],
            "rip_open_quantity": routed["RIP_OPEN_quantity"],
            "scan_identify_quantity": routed["SCAN_IDENTIFY_quantity"],
            "total_quantity": routed_quantity,
        },
        "basis": {
            "keep_sealed_cents": routed["KEEP_SEALED_basis_cents"],
            "rip_open_cents": routed["RIP_OPEN_basis_cents"],
            "scan_identify_reserved_cents": routed["SCAN_IDENTIFY_basis_cents"],
            "undecided_cents": cost - routed_basis,
            "total_cents": cost,
            "difference_cents": cost - (routed_basis + cost - routed_basis),
        },
        "undecided_quantity": quantity - routed_quantity,
        "projected": projection is not None,
        "batch_id": int(projection["batch_id"]) if projection else None,
        "batch_code": projection["batch_code"] if projection else "",
        "per_unit_basis": {
            "minimum_cents": min(per_unit) if per_unit else None,
            "maximum_cents": max(per_unit) if per_unit else None,
            "remainder_units": (sum(1 for value in per_unit if value == max(per_unit)) if min(per_unit) != max(per_unit) else 0) if per_unit else None,
            "deterministic_order": "Immutable unit sequence / acquisition-line quantity ordinal",
        },
        "links": links,
    }


def intake_status(db: sqlite3.Connection, acquisition_id: int) -> dict:
    acquisition = _acquisition(db, acquisition_id)
    lines = _active_lines(db, acquisition_id)
    statuses = [_line_status(db, line) for line in lines]
    total = sum(item["quantity_acquired"] for item in statuses)
    routed = sum(item["routed"]["total_quantity"] for item in statuses)
    all_costs_known = all(item["landed_cost_known"] for item in statuses)
    authoritative_cost = sum(item["landed_cost_cents"] for item in statuses) if all_costs_known else None
    accounted_basis = sum(
        item["basis"]["keep_sealed_cents"]
        + item["basis"]["rip_open_cents"]
        + item["basis"]["scan_identify_reserved_cents"]
        + item["basis"]["undecided_cents"]
        for item in statuses
    )
    return {
        "calculation_version": CALCULATION_VERSION,
        "acquisition_id": acquisition_id,
        "acquisition_code": acquisition["acquisition_code"],
        "state": acquisition["state"],
        "revision": int(acquisition["revision"]),
        "eligible": acquisition["state"] in ("READY_FOR_INTAKE", "INTAKE_IN_PROGRESS"),
        "lines": statuses,
        "summary": {
            "quantity_acquired": total,
            "quantity_routed": routed,
            "quantity_undecided": total - routed,
            "authoritative_cost_cents": authoritative_cost,
            "authoritative_cost_known": all_costs_known,
            "accounted_basis_cents": accounted_basis,
            "difference_cents": authoritative_cost - accounted_basis if authoritative_cost is not None else None,
            "complete": bool(statuses) and routed == total,
        },
        "notices": [
            "Confirmed line costs project into existing batches; no new accounting model is created.",
            "Singles basis remains pending until the existing rip allocation workflow is finalized.",
            "Receipt and catalog provenance remain linked through the acquisition line.",
        ],
    }


def _normalized_request(db: sqlite3.Connection, acquisition_id: int, payload: Mapping[str, object]) -> list[dict]:
    raw_lines = payload.get("lines")
    if not isinstance(raw_lines, list) or not raw_lines:
        raise ValueError("Choose at least one intake quantity")
    active = {int(row["id"]): row for row in _active_lines(db, acquisition_id)}
    seen: set[int] = set()
    normalized: list[dict] = []
    for item in raw_lines:
        if not isinstance(item, Mapping):
            raise ValueError("Each intake choice must identify a product line")
        line_id = _integer(item.get("line_id"), "Product line", 1)
        if line_id in seen or line_id not in active:
            raise ValueError("Intake product lines must be active, unique, and belong to this acquisition")
        seen.add(line_id)
        line = active[line_id]
        values = {
            "KEEP_SEALED": _integer(item.get("keep_sealed_quantity", 0), "Keep sealed quantity"),
            "RIP_OPEN": _integer(item.get("rip_open_quantity", 0), "Rip/open quantity"),
            "SCAN_IDENTIFY": _integer(item.get("scan_identify_quantity", 0), "Scan and identify quantity"),
        }
        allowed = _allowed_actions(line["product_class"])
        if any(values[action] for action in ROUTE_ACTIONS if action not in allowed):
            raise ValueError("That intake action does not apply to this product type")
        already = _routed(db, line_id)
        available = int(line["quantity"]) - sum(
            int(already[f"{action}_quantity"]) for action in ROUTE_ACTIONS
        )
        requested = sum(values.values())
        if requested > available:
            raise ValueError("Intake quantities cannot exceed the line's undecided quantity")
        if requested:
            normalized.append({"line": line, "values": values, "available": available})
    if not normalized:
        raise ValueError("Choose at least one quantity to route; Decide Later needs no entry")
    return normalized


def _action_preview(line: sqlite3.Row, already_count: int, values: dict[str, int]) -> dict:
    allocations = _line_unit_allocations(line)
    cursor = already_count
    actions: dict[str, dict] = {}
    # Stable action order makes the same request consume the same immutable ordinals.
    for action in ("RIP_OPEN", "KEEP_SEALED", "SCAN_IDENTIFY"):
        quantity = int(values[action])
        basis = sum(allocations[cursor:cursor + quantity])
        actions[action] = {
            "quantity": quantity,
            "basis_cents": basis,
            "ordinal_start": cursor + 1 if quantity else None,
            "ordinal_end": cursor + quantity if quantity else None,
        }
        cursor += quantity
    return actions


def intake_preview(db: sqlite3.Connection, acquisition_id: int, payload: Mapping[str, object]) -> dict:
    acquisition = _acquisition(db, acquisition_id)
    if acquisition["state"] not in ("READY_FOR_INTAKE", "INTAKE_IN_PROGRESS"):
        raise ValueError("Only a confirmed Ready for Intake acquisition can be routed")
    if payload.get("expected_revision") is not None and int(payload["expected_revision"]) != int(acquisition["revision"]):
        raise ValueError("This acquisition changed in another view; reload before continuing")
    normalized = _normalized_request(db, acquisition_id, payload)
    result_lines = []
    for item in normalized:
        line = item["line"]
        already = _routed(db, int(line["id"]))
        already_count = sum(int(already[f"{action}_quantity"]) for action in ROUTE_ACTIONS)
        actions = _action_preview(line, already_count, item["values"])
        requested_quantity = sum(action["quantity"] for action in actions.values())
        requested_basis = sum(action["basis_cents"] for action in actions.values())
        result_lines.append({
            "line_id": int(line["id"]),
            "line_sequence": int(line["line_sequence"]),
            "product_class": line["product_class"],
            "product_name": line["product_name"],
            "actions": actions,
            "requested_quantity": requested_quantity,
            "requested_basis_cents": requested_basis,
            "undecided_after_quantity": item["available"] - requested_quantity,
            "undecided_after_basis_cents": int(line["assigned_landed_cost_cents"]) - sum(
                int(already[f"{action}_basis_cents"]) for action in ROUTE_ACTIONS
            ) - requested_basis,
        })
    canonical = {
        "acquisition_id": acquisition_id,
        "revision": int(acquisition["revision"]),
        "lines": result_lines,
        "calculation_version": CALCULATION_VERSION,
    }
    preview_token = hashlib.sha256(
        json.dumps(canonical, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        **canonical,
        "preview_token": preview_token,
        "confirmation_required": True,
        "summary": {
            "requested_quantity": sum(line["requested_quantity"] for line in result_lines),
            "requested_basis_cents": sum(line["requested_basis_cents"] for line in result_lines),
            "undecided_after_quantity": sum(line["undecided_after_quantity"] for line in result_lines),
            "difference_cents": 0,
        },
        "basis_notice": "Amounts use deterministic exact-cent allocation. Singles amounts are reserved pending the existing card-allocation finalization workflow.",
    }


def _batch_code(db: sqlite3.Connection, acquisition: sqlite3.Row, line: sqlite3.Row) -> str:
    stem = re.sub(r"[^A-Z0-9]+", "-", str(acquisition["acquisition_code"]).upper()).strip("-")
    candidate = f"{stem}-L{int(line['line_sequence']):02d}"
    suffix = 1
    while db.execute("SELECT 1 FROM batches WHERE batch_code=?", (candidate,)).fetchone():
        suffix += 1
        candidate = f"{stem}-L{int(line['line_sequence']):02d}-{suffix}"
    return candidate


def _create_projection(db: sqlite3.Connection, acquisition: sqlite3.Row, line: sqlite3.Row, operation_id: int) -> sqlite3.Row:
    existing = _projection(db, int(line["id"]))
    if existing:
        return existing
    now = utcnow()
    batch_code = _batch_code(db, acquisition, line)
    sealed = line["product_class"] in ("PACK_PRODUCT", "SEALED_PRODUCT")
    mode = "SEALED_RIP" if sealed else (
        "SINGLES_KNOWN_COST" if line["singles_cost_mode"] == "KNOWN_LINE_COSTS" else "SINGLES_LUMP_SUM"
    )
    product_name = line["product_name"] or line["pack_type"] or f"{line['set_code']} singles"
    cursor = db.execute(
        """INSERT INTO batches
           (batch_code,created_at,game,set_code,set_name,color,finish_group,default_condition,
            acquisition_type,total_cost,location,notes,scan_order,scan_mode,economics_mode,
            economics_status,product_name,product_code,receipt_group_reference,invoice_reference,
            reporting_currency,original_currency,original_foreign_amount_minor,final_usd_paid_cents,
            units_acquired,cost_reconciliation_acknowledged,acquisition_updated_at,acquisition_line_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            batch_code, now, line["game"] or "One Piece", line["set_code"] or "MIXED", "", "",
            "Non-Foil", "Near Mint", "Pack Product" if line["product_class"] == "PACK_PRODUCT" else (
                "Sealed Product" if sealed else "Purchased Singles"
            ), int(line["assigned_landed_cost_cents"]) / 100, line["set_code"] or "Inbound",
            f"Projected from {acquisition['acquisition_code']} product line {line['line_sequence']}.",
            "FRONT_FIRST", "FRONT_BACK", mode, "FINALIZED" if sealed else "DRAFT", product_name,
            "", acquisition["acquisition_code"], acquisition["order_reference"], "USD",
            acquisition["original_currency"], acquisition["original_foreign_amount_minor"],
            int(line["assigned_landed_cost_cents"]), int(line["quantity"]), 1, now, int(line["id"]),
        ),
    )
    batch_id = int(cursor.lastrowid)
    db.execute(
        """INSERT INTO acquisition_line_projections
           (projection_uuid,acquisition_id,acquisition_line_id,batch_id,product_class,
            quantity_acquired,landed_cost_cents,catalog_product_id,created_by_operation_id,created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (f"PROJ-{uuid.uuid4()}", acquisition["id"], line["id"], batch_id, line["product_class"],
         line["quantity"], line["assigned_landed_cost_cents"], line["catalog_product_id"], operation_id, now),
    )
    if sealed:
        synchronize_sealed_units(db, batch_id)
        db.execute(
            "UPDATE sealed_units SET intake_disposition='PENDING',updated_at=? WHERE batch_id=?",
            (now, batch_id),
        )
    return _projection(db, int(line["id"]))


def confirm_intake_routing(db: sqlite3.Connection, acquisition_id: int, payload: Mapping[str, object]) -> dict:
    request_id = _text(payload.get("request_id"), 120)
    if not request_id:
        raise ValueError("A unique request ID is required")
    duplicate = db.execute(
        "SELECT acquisition_id FROM acquisition_intake_operations WHERE request_id=?", (request_id,)
    ).fetchone()
    if duplicate:
        if int(duplicate["acquisition_id"]) != acquisition_id:
            raise ValueError("That request ID belongs to another acquisition")
        return intake_status(db, acquisition_id)
    acquisition = _acquisition(db, acquisition_id)
    if acquisition["state"] not in ("READY_FOR_INTAKE", "INTAKE_IN_PROGRESS"):
        raise ValueError("Only a confirmed Ready for Intake acquisition can be routed")
    if int(payload.get("expected_revision", 0)) != int(acquisition["revision"]):
        raise ValueError("This acquisition changed in another view; reload before continuing")
    preview = intake_preview(db, acquisition_id, payload)
    if not payload.get("confirm_routing"):
        raise ValueError("Explicit intake-routing confirmation is required")
    if _text(payload.get("preview_token"), 80) != preview["preview_token"]:
        raise ValueError("The routing preview changed; review it again before confirming")
    now = utcnow()
    operation_uuid = f"INTAKE-{uuid.uuid4()}"
    op_cursor = db.execute(
        """INSERT INTO acquisition_intake_operations
           (operation_uuid,request_id,acquisition_id,from_state,to_state,effective_at,recorded_at,payload)
           VALUES (?,?,?,?,?,?,?,?)""",
        (operation_uuid, request_id, acquisition_id, acquisition["state"], acquisition["state"],
         _text(payload.get("effective_at"), 40) or now, now, "{}"),
    )
    operation_id = int(op_cursor.lastrowid)
    normalized = _normalized_request(db, acquisition_id, payload)
    preview_by_line = {int(item["line_id"]): item for item in preview["lines"]}
    created_links: list[dict] = []
    for item in normalized:
        line = item["line"]
        line_id = int(line["id"])
        projection = _create_projection(db, acquisition, line, operation_id)
        batch_id = int(projection["batch_id"])
        for action in ("RIP_OPEN", "KEEP_SEALED", "SCAN_IDENTIFY"):
            action_preview = preview_by_line[line_id]["actions"][action]
            quantity = int(action_preview["quantity"])
            if not quantity:
                continue
            rip_id = None
            if action in ("RIP_OPEN", "KEEP_SEALED"):
                rows = db.execute(
                    """SELECT id,unit_code,unit_sequence,basis_cents FROM sealed_units
                         WHERE batch_id=? AND status='REMAINING' AND intake_disposition='PENDING'
                         ORDER BY unit_sequence LIMIT ?""",
                    (batch_id, quantity),
                ).fetchall()
                if len(rows) != quantity:
                    raise sqlite3.IntegrityError("Exact pending sealed units were not available")
                unit_ids = [int(row["id"]) for row in rows]
                placeholders = ",".join("?" for _ in unit_ids)
                db.execute(
                    f"UPDATE sealed_units SET intake_disposition=?,updated_at=? WHERE id IN ({placeholders})",
                    (action, now, *unit_ids),
                )
                if action == "RIP_OPEN":
                    rip = create_rip_session(db, batch_id, {"units_opened": quantity})
                    rip_id = int(rip["id"])
            else:
                rip_row = db.execute(
                    "SELECT id FROM rip_sessions WHERE batch_id=? ORDER BY id LIMIT 1", (batch_id,)
                ).fetchone()
                if rip_row:
                    rip_id = int(rip_row["id"])
                else:
                    rip = create_rip_session(db, batch_id, {})
                    rip_id = int(rip["id"])
                unit_ids = []
            event_uuid = f"ROUTE-{uuid.uuid4()}"
            db.execute(
                """INSERT INTO acquisition_intake_route_events
                   (route_event_uuid,operation_id,acquisition_line_id,batch_id,route_action,
                    quantity,basis_cents,rip_session_id,created_at,payload)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (event_uuid, operation_id, line_id, batch_id, action, quantity,
                 action_preview["basis_cents"], rip_id, now,
                 json.dumps({"unit_ids": unit_ids, "ordinal_start": action_preview["ordinal_start"],
                             "ordinal_end": action_preview["ordinal_end"]}, separators=(",", ":"), sort_keys=True)),
            )
            created_links.append({"line_id": line_id, "batch_id": batch_id, "rip_session_id": rip_id,
                                  "action": action, "quantity": quantity, "unit_ids": unit_ids})
    status = intake_status(db, acquisition_id)
    new_state = "INTAKE_COMPLETE" if status["summary"]["complete"] else "INTAKE_IN_PROGRESS"
    db.execute(
        "UPDATE acquisitions SET state=?,revision=revision+1,updated_at=? WHERE id=?",
        (new_state, now, acquisition_id),
    )
    operation_payload = {
        "calculation_version": CALCULATION_VERSION,
        "preview_token": preview["preview_token"],
        "links": created_links,
    }
    db.execute(
        "UPDATE acquisition_intake_operations SET to_state=?,payload=? WHERE id=?",
        (new_state, json.dumps(operation_payload, separators=(",", ":"), sort_keys=True), operation_id),
    )
    db.execute(
        """INSERT INTO activity_log (created_at,action_type,description,payload)
           VALUES (?,?,?,?)""",
        (now, "ACQUISITION_INTAKE_ROUTE", f"Routed intake for {acquisition['acquisition_code']}",
         json.dumps({"operation_uuid": operation_uuid, **operation_payload}, separators=(",", ":"), sort_keys=True)),
    )
    return intake_status(db, acquisition_id)
