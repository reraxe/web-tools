"""Transactional, versioned SQLite migration support for Dex.

Migration callbacks must use ``connection.execute`` rather than ``executescript``;
SQLite's script helper can issue transaction boundaries that defeat savepoints.
"""

from __future__ import annotations

import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable


MigrationAction = Callable[[sqlite3.Connection], None]
MIGRATION_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")


@dataclass(frozen=True)
class Migration:
    migration_id: str
    description: str
    apply: MigrationAction


class MigrationError(RuntimeError):
    """Raised after a failed migration has been rolled back."""


def _phase3_acquisition_facts(connection: sqlite3.Connection) -> None:
    columns = {row[1] for row in connection.execute("PRAGMA table_info(batches)")}
    additions = (
        ("economics_mode", "TEXT NOT NULL DEFAULT 'LEGACY' CHECK (economics_mode IN ('LEGACY', 'SEALED_RIP', 'SINGLES_KNOWN_COST', 'SINGLES_LUMP_SUM'))"),
        ("economics_status", "TEXT NOT NULL DEFAULT 'ESTIMATED' CHECK (economics_status IN ('ESTIMATED', 'DRAFT', 'FINALIZED'))"),
        ("product_name", "TEXT NOT NULL DEFAULT ''"),
        ("product_code", "TEXT NOT NULL DEFAULT ''"),
        ("receipt_group_reference", "TEXT NOT NULL DEFAULT ''"),
        ("invoice_reference", "TEXT NOT NULL DEFAULT ''"),
        ("reporting_currency", "TEXT NOT NULL DEFAULT 'USD' CHECK (reporting_currency = 'USD')"),
        ("original_currency", "TEXT NOT NULL DEFAULT ''"),
        ("original_foreign_amount_minor", "INTEGER CHECK (original_foreign_amount_minor IS NULL OR original_foreign_amount_minor >= 0)"),
        ("final_usd_paid_cents", "INTEGER CHECK (final_usd_paid_cents IS NULL OR final_usd_paid_cents >= 0)"),
        ("units_acquired", "INTEGER CHECK (units_acquired IS NULL OR units_acquired >= 0)"),
        ("purchase_subtotal_cents", "INTEGER CHECK (purchase_subtotal_cents IS NULL OR purchase_subtotal_cents >= 0)"),
        ("acquisition_tax_cents", "INTEGER CHECK (acquisition_tax_cents IS NULL OR acquisition_tax_cents >= 0)"),
        ("inbound_shipping_cents", "INTEGER CHECK (inbound_shipping_cents IS NULL OR inbound_shipping_cents >= 0)"),
        ("acquisition_fees_cents", "INTEGER CHECK (acquisition_fees_cents IS NULL OR acquisition_fees_cents >= 0)"),
        ("acquisition_discount_cents", "INTEGER CHECK (acquisition_discount_cents IS NULL OR acquisition_discount_cents >= 0)"),
        ("cost_reconciliation_acknowledged", "INTEGER NOT NULL DEFAULT 0 CHECK (cost_reconciliation_acknowledged IN (0, 1))"),
        ("acquisition_updated_at", "TEXT"),
    )
    for name, declaration in additions:
        if name not in columns:
            connection.execute(f"ALTER TABLE batches ADD COLUMN {name} {declaration}")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_batches_receipt_group ON batches(receipt_group_reference)"
    )


def _phase4_rip_sessions(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE rip_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rip_code TEXT NOT NULL UNIQUE,
            batch_id INTEGER NOT NULL REFERENCES batches(id),
            status TEXT NOT NULL DEFAULT 'DRAFT'
                CHECK (status IN ('DRAFT', 'ACTIVE', 'FINALIZED')),
            units_opened INTEGER NOT NULL DEFAULT 0 CHECK (units_opened >= 0),
            allocation_method TEXT NOT NULL DEFAULT 'EQUAL'
                CHECK (allocation_method IN ('EQUAL', 'MANUAL')),
            bulk_mode TEXT NOT NULL DEFAULT 'NONE'
                CHECK (bulk_mode IN ('NONE', 'KNOWN_QUANTITY', 'MANUAL_RESERVE')),
            bulk_quantity INTEGER CHECK (bulk_quantity IS NULL OR bulk_quantity >= 0),
            consumed_cost_cents INTEGER CHECK (consumed_cost_cents IS NULL OR consumed_cost_cents >= 0),
            scanned_basis_cents INTEGER CHECK (scanned_basis_cents IS NULL OR scanned_basis_cents >= 0),
            bulk_basis_cents INTEGER CHECK (bulk_basis_cents IS NULL OR bulk_basis_cents >= 0),
            total_allocated_cents INTEGER CHECK (total_allocated_cents IS NULL OR total_allocated_cents >= 0),
            difference_cents INTEGER,
            valuation_complete INTEGER NOT NULL DEFAULT 1 CHECK (valuation_complete IN (0, 1)),
            cards_accounted_confirmed INTEGER NOT NULL DEFAULT 0
                CHECK (cards_accounted_confirmed IN (0, 1)),
            unit_sequence_start INTEGER,
            unit_sequence_end INTEGER,
            created_at TEXT NOT NULL,
            started_at TEXT,
            finalized_at TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE rip_economic_events (
            event_id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL UNIQUE,
            rip_session_id INTEGER NOT NULL REFERENCES rip_sessions(id),
            event_type TEXT NOT NULL CHECK (event_type IN ('FINALIZATION', 'CORRECTION')),
            effective_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            reason_code TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            payload TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE rip_basis_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL REFERENCES rip_economic_events(event_id),
            rip_session_id INTEGER NOT NULL REFERENCES rip_sessions(id),
            target_type TEXT NOT NULL CHECK (target_type IN ('CARD', 'BULK')),
            card_id INTEGER REFERENCES cards(id),
            amount_delta_cents INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            CHECK ((target_type = 'CARD' AND card_id IS NOT NULL) OR
                   (target_type = 'BULK' AND card_id IS NULL))
        )
        """
    )
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    card_columns = {row[1] for row in connection.execute("PRAGMA table_info(cards)")}
    if "cards" in tables and "rip_session_id" not in card_columns:
        connection.execute(
            "ALTER TABLE cards ADD COLUMN rip_session_id INTEGER REFERENCES rip_sessions(id)"
        )
    scan_columns = {row[1] for row in connection.execute("PRAGMA table_info(processed_scans)")}
    if "processed_scans" in tables and "rip_session_id" not in scan_columns:
        connection.execute(
            "ALTER TABLE processed_scans ADD COLUMN rip_session_id INTEGER REFERENCES rip_sessions(id)"
        )
    connection.execute("CREATE INDEX idx_rip_sessions_batch ON rip_sessions(batch_id)")
    connection.execute(
        "CREATE UNIQUE INDEX idx_rip_sessions_active_batch ON rip_sessions(batch_id) WHERE status = 'ACTIVE'"
    )
    if "cards" in tables:
        connection.execute("CREATE INDEX idx_cards_rip_session ON cards(rip_session_id)")
    connection.execute("CREATE INDEX idx_rip_basis_session ON rip_basis_events(rip_session_id)")
    connection.execute("CREATE INDEX idx_rip_events_session ON rip_economic_events(rip_session_id)")


def _phase5_sealed_inventory(connection: sqlite3.Connection) -> None:
    """Add exact sealed-unit inventory and sealed-only sale facts.

    Existing card sales are explicitly classified as CARD orders. Trustworthy
    SEALED_RIP acquisitions are expanded into deterministic unit records. Any
    Phase 4 rip sessions already present consume the lowest unit sequences in
    stable rip-session order so an upgrade preserves their prior cost result.
    """

    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    if "sale_orders" in tables:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(sale_orders)")}
        additions = (
            ("order_type", "TEXT NOT NULL DEFAULT 'CARD' CHECK (order_type IN ('CARD', 'SEALED'))"),
            ("request_id", "TEXT"),
            ("merchandise_total_cents", "INTEGER CHECK (merchandise_total_cents IS NULL OR merchandise_total_cents >= 0)"),
            ("shipping_collected_cents", "INTEGER CHECK (shipping_collected_cents IS NULL OR shipping_collected_cents >= 0)"),
            ("marketplace_fees_cents", "INTEGER CHECK (marketplace_fees_cents IS NULL OR marketplace_fees_cents >= 0)"),
            ("actual_postage_cents", "INTEGER CHECK (actual_postage_cents IS NULL OR actual_postage_cents >= 0)"),
            ("marketplace_tax_cents", "INTEGER NOT NULL DEFAULT 0 CHECK (marketplace_tax_cents >= 0)"),
            ("canceled_at", "TEXT"),
            ("cancellation_reason", "TEXT NOT NULL DEFAULT ''"),
        )
        for name, declaration in additions:
            if name not in columns:
                connection.execute(f"ALTER TABLE sale_orders ADD COLUMN {name} {declaration}")
        connection.execute("UPDATE sale_orders SET order_type = 'CARD' WHERE order_type IS NULL OR order_type = ''")
        connection.execute(
            """UPDATE sale_orders SET
                   merchandise_total_cents = CAST(ROUND(subtotal * 100) AS INTEGER),
                   shipping_collected_cents = CAST(ROUND(shipping_collected * 100) AS INTEGER),
                   marketplace_fees_cents = CAST(ROUND(platform_fees * 100) AS INTEGER),
                   actual_postage_cents = CAST(ROUND(postage_cost * 100) AS INTEGER)
               WHERE merchandise_total_cents IS NULL"""
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_sale_orders_request_id "
            "ON sale_orders(request_id) WHERE request_id IS NOT NULL AND request_id <> ''"
        )

    connection.execute(
        """
        CREATE TABLE sealed_units (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_code TEXT NOT NULL UNIQUE,
            batch_id INTEGER NOT NULL REFERENCES batches(id),
            unit_sequence INTEGER NOT NULL CHECK (unit_sequence > 0),
            basis_cents INTEGER NOT NULL CHECK (basis_cents >= 0),
            status TEXT NOT NULL DEFAULT 'REMAINING'
                CHECK (status IN ('REMAINING', 'OPENED', 'SOLD', 'ADJUSTED')),
            rip_session_id INTEGER REFERENCES rip_sessions(id),
            current_order_id INTEGER REFERENCES sale_orders(id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(batch_id, unit_sequence)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE sealed_sale_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES sale_orders(id),
            sealed_unit_id INTEGER NOT NULL REFERENCES sealed_units(id),
            batch_id INTEGER NOT NULL REFERENCES batches(id),
            merchandise_amount_cents INTEGER NOT NULL CHECK (merchandise_amount_cents >= 0),
            basis_cents INTEGER NOT NULL CHECK (basis_cents >= 0)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE sealed_unit_events (
            event_id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL UNIQUE,
            sealed_unit_id INTEGER NOT NULL REFERENCES sealed_units(id),
            event_type TEXT NOT NULL
                CHECK (event_type IN ('CREATED', 'OPENED', 'SOLD', 'SALE_UNDONE', 'ADJUSTED')),
            from_status TEXT,
            to_status TEXT NOT NULL,
            rip_session_id INTEGER REFERENCES rip_sessions(id),
            order_id INTEGER REFERENCES sale_orders(id),
            reason_code TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            effective_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    connection.execute("CREATE INDEX idx_sealed_units_batch_status ON sealed_units(batch_id, status, unit_sequence)")
    connection.execute("CREATE INDEX idx_sealed_units_rip ON sealed_units(rip_session_id)")
    connection.execute("CREATE INDEX idx_sealed_units_order ON sealed_units(current_order_id)")
    connection.execute("CREATE INDEX idx_sealed_sale_items_order ON sealed_sale_items(order_id)")
    connection.execute("CREATE INDEX idx_sealed_events_unit ON sealed_unit_events(sealed_unit_id, recorded_at)")

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    batches = connection.execute(
        """SELECT id, batch_code, final_usd_paid_cents, units_acquired
           FROM batches
           WHERE economics_mode = 'SEALED_RIP'
             AND final_usd_paid_cents IS NOT NULL
             AND units_acquired IS NOT NULL AND units_acquired > 0
           ORDER BY id"""
    ).fetchall()
    for batch_id, batch_code, total_cents, unit_count in batches:
        base, remainder = divmod(int(total_cents), int(unit_count))
        unit_ids: list[int] = []
        for sequence in range(1, int(unit_count) + 1):
            basis = base + (1 if sequence <= remainder else 0)
            cursor = connection.execute(
                """INSERT INTO sealed_units
                   (unit_code, batch_id, unit_sequence, basis_cents, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (f"{batch_code}-UNIT-{sequence:04d}", batch_id, sequence, basis, now, now),
            )
            unit_ids.append(int(cursor.lastrowid))
            connection.execute(
                """INSERT INTO sealed_unit_events
                   (event_id, request_id, sealed_unit_id, event_type, from_status,
                    to_status, reason_code, effective_at, recorded_at, payload)
                   VALUES (?, ?, ?, 'CREATED', NULL, 'REMAINING', 'MIGRATION', ?, ?, '{}')""",
                (f"SEALED-{uuid.uuid4()}", f"MIGRATE-CREATE-{cursor.lastrowid}", cursor.lastrowid, now, now),
            )

        if "rip_sessions" not in tables:
            continue
        rips = connection.execute(
            "SELECT id, units_opened FROM rip_sessions WHERE batch_id = ? ORDER BY id",
            (batch_id,),
        ).fetchall()
        offset = 0
        for rip_id, units_opened in rips:
            claim = unit_ids[offset : offset + int(units_opened)]
            if len(claim) != int(units_opened):
                raise ValueError(f"Existing rip sessions exceed acquired units for {batch_code}")
            for unit_id in claim:
                connection.execute(
                    "UPDATE sealed_units SET status='OPENED', rip_session_id=?, updated_at=? WHERE id=?",
                    (rip_id, now, unit_id),
                )
                connection.execute(
                    """INSERT INTO sealed_unit_events
                       (event_id, request_id, sealed_unit_id, event_type, from_status,
                        to_status, rip_session_id, reason_code, effective_at, recorded_at, payload)
                       VALUES (?, ?, ?, 'OPENED', 'REMAINING', 'OPENED', ?, 'PHASE4_MIGRATION', ?, ?, '{}')""",
                    (f"SEALED-{uuid.uuid4()}", f"MIGRATE-OPEN-{rip_id}-{unit_id}", unit_id, rip_id, now, now),
                )
            if claim:
                sequences = connection.execute(
                    f"SELECT MIN(unit_sequence), MAX(unit_sequence) FROM sealed_units WHERE id IN ({','.join('?' for _ in claim)})",
                    claim,
                ).fetchone()
                connection.execute(
                    "UPDATE rip_sessions SET unit_sequence_start=?, unit_sequence_end=? WHERE id=?",
                    (sequences[0], sequences[1], rip_id),
                )
            offset += int(units_opened)


def _phase7a_corrections_dispositions(connection: sqlite3.Connection) -> None:
    """Add a unified append-only ledger for corrections and dispositions.

    Phase 7A does not rewrite any finalized acquisition, rip-basis, sealed-unit,
    card, or sale fact. Current corrected values are derived by adding these
    ledger entries to the preserved Phase 1–5 source facts.
    """

    connection.execute(
        """
        CREATE TABLE economic_events (
            event_id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL UNIQUE,
            batch_id INTEGER NOT NULL REFERENCES batches(id),
            event_type TEXT NOT NULL CHECK (event_type IN (
                'ACQUISITION_COST_CORRECTION',
                'BASIS_TRANSFER',
                'CARD_DISPOSITION',
                'SEALED_QUANTITY_CORRECTION',
                'REVERSAL'
            )),
            reason_code TEXT NOT NULL,
            effective_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            notes TEXT NOT NULL,
            reverses_event_id TEXT REFERENCES economic_events(event_id),
            payload TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE economic_event_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL REFERENCES economic_events(event_id),
            entry_type TEXT NOT NULL CHECK (entry_type IN (
                'ACQUISITION_COST', 'BASIS', 'OPERATIONAL_LOSS'
            )),
            target_type TEXT NOT NULL CHECK (target_type IN (
                'BATCH', 'CARD', 'RIP_BULK', 'SEALED_UNIT'
            )),
            target_id INTEGER NOT NULL,
            amount_delta_cents INTEGER NOT NULL CHECK (amount_delta_cents <> 0),
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE economic_tombstones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL REFERENCES economic_events(event_id),
            entity_type TEXT NOT NULL CHECK (entity_type IN ('CARD', 'SEALED_UNIT')),
            entity_id INTEGER NOT NULL,
            stable_identifier TEXT NOT NULL,
            batch_id INTEGER NOT NULL REFERENCES batches(id),
            reason_code TEXT NOT NULL,
            snapshot TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE UNIQUE INDEX idx_economic_events_one_reversal "
        "ON economic_events(reverses_event_id) WHERE reverses_event_id IS NOT NULL"
    )
    connection.execute(
        "CREATE INDEX idx_economic_events_batch_recorded "
        "ON economic_events(batch_id, recorded_at, event_id)"
    )
    connection.execute(
        "CREATE INDEX idx_economic_entries_target "
        "ON economic_event_entries(target_type, target_id, entry_type)"
    )
    connection.execute(
        "CREATE INDEX idx_economic_entries_event ON economic_event_entries(event_id)"
    )
    connection.execute(
        "CREATE INDEX idx_economic_tombstones_entity "
        "ON economic_tombstones(entity_type, entity_id, created_at)"
    )


def _phase7b_post_sale_events(connection: sqlite3.Connection) -> None:
    """Add immutable post-sale events and permit a returned card to sell again.

    The original order and item rows are preserved.  ``sale_items`` is rebuilt
    only to replace its legacy one-sale-per-card constraint with one item per
    card per order; current card state still prevents simultaneous sales.
    """

    columns = {row[1] for row in connection.execute("PRAGMA table_info(sale_items)")}
    if columns:
        connection.execute("ALTER TABLE sale_items RENAME TO sale_items_phase7b_legacy")
        connection.execute(
            """
            CREATE TABLE sale_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL REFERENCES sale_orders(id),
                card_id INTEGER NOT NULL REFERENCES cards(id),
                sale_price REAL NOT NULL DEFAULT 0,
                UNIQUE(order_id, card_id)
            )
            """
        )
        connection.execute(
            """INSERT INTO sale_items (id, order_id, card_id, sale_price)
               SELECT id, order_id, card_id, sale_price
                 FROM sale_items_phase7b_legacy ORDER BY id"""
        )
        connection.execute("DROP TABLE sale_items_phase7b_legacy")
    if columns:
        connection.execute("CREATE INDEX IF NOT EXISTS idx_sale_items_card ON sale_items(card_id, id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_sale_items_order ON sale_items(order_id, id)")

    connection.execute(
        """
        CREATE TABLE post_sale_events (
            event_id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL UNIQUE,
            order_id INTEGER NOT NULL REFERENCES sale_orders(id),
            event_type TEXT NOT NULL CHECK (event_type IN (
                'PARTIAL_REFUND', 'FULL_REFUND', 'CUSTOMER_RETURN',
                'CHARGEBACK', 'MARKETPLACE_FEE_CREDIT', 'POSTAGE_REFUND',
                'SALE_CORRECTION', 'REVERSAL'
            )),
            reason_code TEXT NOT NULL,
            effective_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            reverses_event_id TEXT REFERENCES post_sale_events(event_id),
            payload TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE post_sale_event_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL REFERENCES post_sale_events(event_id),
            component_type TEXT NOT NULL CHECK (component_type IN (
                'MERCHANDISE', 'SHIPPING', 'MARKETPLACE_FEES',
                'POSTAGE', 'OTHER_NET'
            )),
            amount_delta_cents INTEGER NOT NULL CHECK (amount_delta_cents <> 0),
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE post_sale_return_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL REFERENCES post_sale_events(event_id),
            item_type TEXT NOT NULL CHECK (item_type IN ('CARD', 'SEALED_UNIT')),
            sale_item_id INTEGER NOT NULL,
            entity_id INTEGER NOT NULL,
            stable_identifier TEXT NOT NULL,
            outcome TEXT NOT NULL CHECK (outcome IN ('RESTOCKED', 'DAMAGED_EXCLUDED')),
            basis_cents INTEGER,
            prior_state TEXT NOT NULL,
            restored_at TEXT NOT NULL,
            UNIQUE(event_id, item_type, sale_item_id)
        )
        """
    )
    connection.execute(
        "CREATE UNIQUE INDEX idx_post_sale_one_reversal "
        "ON post_sale_events(reverses_event_id) WHERE reverses_event_id IS NOT NULL"
    )
    connection.execute(
        "CREATE INDEX idx_post_sale_order_recorded "
        "ON post_sale_events(order_id, recorded_at, event_id)"
    )
    connection.execute(
        "CREATE INDEX idx_post_sale_entries_event ON post_sale_event_entries(event_id)"
    )
    connection.execute(
        "CREATE INDEX idx_post_sale_return_entity "
        "ON post_sale_return_items(item_type, entity_id, sale_item_id)"
    )


def _v22_phase1_inbound_acquisitions(connection: sqlite3.Connection) -> None:
    """Add the Inbound 2.0 parent acquisition and lifecycle foundation.

    The migration is deliberately additive. Existing Phase 3-7C batch facts are
    not backfilled, reclassified, or linked by inference.
    """

    connection.execute(
        """
        CREATE TABLE acquisitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            acquisition_uuid TEXT NOT NULL UNIQUE,
            acquisition_code TEXT NOT NULL UNIQUE,
            creation_request_id TEXT NOT NULL UNIQUE,
            state TEXT NOT NULL DEFAULT 'ACQUISITION_INCOMPLETE'
                CHECK (state IN (
                    'ACQUISITION_INCOMPLETE', 'RECONCILIATION_REQUIRED',
                    'READY_FOR_INTAKE', 'INTAKE_IN_PROGRESS',
                    'INTAKE_COMPLETE', 'CANCELED'
                )),
            revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
            source_scope TEXT CHECK (source_scope IS NULL OR source_scope IN ('DOMESTIC', 'INTERNATIONAL')),
            merchant_name TEXT NOT NULL DEFAULT '',
            merchant_country TEXT NOT NULL DEFAULT '',
            purchased_on TEXT,
            order_reference TEXT NOT NULL DEFAULT '',
            reporting_currency TEXT NOT NULL DEFAULT 'USD' CHECK (reporting_currency = 'USD'),
            original_currency TEXT NOT NULL DEFAULT '',
            original_foreign_amount_minor INTEGER
                CHECK (original_foreign_amount_minor IS NULL OR original_foreign_amount_minor >= 0),
            purchase_subtotal_cents INTEGER
                CHECK (purchase_subtotal_cents IS NULL OR purchase_subtotal_cents >= 0),
            acquisition_tax_cents INTEGER
                CHECK (acquisition_tax_cents IS NULL OR acquisition_tax_cents >= 0),
            inbound_shipping_cents INTEGER
                CHECK (inbound_shipping_cents IS NULL OR inbound_shipping_cents >= 0),
            acquisition_fees_cents INTEGER
                CHECK (acquisition_fees_cents IS NULL OR acquisition_fees_cents >= 0),
            import_duties_cents INTEGER
                CHECK (import_duties_cents IS NULL OR import_duties_cents >= 0),
            brokerage_cents INTEGER
                CHECK (brokerage_cents IS NULL OR brokerage_cents >= 0),
            acquisition_discount_cents INTEGER
                CHECK (acquisition_discount_cents IS NULL OR acquisition_discount_cents >= 0),
            final_usd_paid_cents INTEGER
                CHECK (final_usd_paid_cents IS NULL OR final_usd_paid_cents >= 0),
            discrepancy_reason_code TEXT NOT NULL DEFAULT '',
            discrepancy_notes TEXT NOT NULL DEFAULT '',
            financial_facts_confirmed INTEGER NOT NULL DEFAULT 0
                CHECK (financial_facts_confirmed IN (0, 1)),
            reconciliation_confirmed INTEGER NOT NULL DEFAULT 0
                CHECK (reconciliation_confirmed IN (0, 1)),
            confirmed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            canceled_at TEXT,
            cancel_reason_code TEXT NOT NULL DEFAULT '',
            cancel_notes TEXT NOT NULL DEFAULT ''
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE acquisition_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            line_uuid TEXT NOT NULL UNIQUE,
            acquisition_id INTEGER NOT NULL REFERENCES acquisitions(id),
            line_sequence INTEGER NOT NULL CHECK (line_sequence > 0),
            product_class TEXT NOT NULL
                CHECK (product_class IN ('SINGLE_CARDS', 'PACK_PRODUCT', 'SEALED_PRODUCT')),
            game TEXT NOT NULL DEFAULT '',
            product_name TEXT NOT NULL DEFAULT '',
            set_code TEXT NOT NULL DEFAULT '',
            pack_type TEXT NOT NULL DEFAULT '',
            quantity INTEGER CHECK (quantity IS NULL OR quantity > 0),
            quantity_certainty TEXT NOT NULL DEFAULT 'UNKNOWN'
                CHECK (quantity_certainty IN ('UNKNOWN', 'ESTIMATED', 'KNOWN')),
            singles_cost_mode TEXT NOT NULL DEFAULT ''
                CHECK (singles_cost_mode IN ('', 'KNOWN_LINE_COSTS', 'LUMP_SUM')),
            intended_action TEXT NOT NULL DEFAULT 'DECIDE_LATER'
                CHECK (intended_action IN ('DECIDE_LATER', 'KEEP_SEALED', 'RIP_OPEN', 'SCAN_IDENTIFY', 'INVENTORY_SINGLES')),
            assigned_landed_cost_cents INTEGER
                CHECK (assigned_landed_cost_cents IS NULL OR assigned_landed_cost_cents >= 0),
            allocation_method TEXT NOT NULL DEFAULT '',
            allocation_status TEXT NOT NULL DEFAULT 'UNALLOCATED'
                CHECK (allocation_status IN ('UNALLOCATED', 'SUGGESTED', 'CONFIRMED')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            canceled_at TEXT,
            UNIQUE(acquisition_id, line_sequence)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE acquisition_events (
            event_id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL UNIQUE,
            acquisition_id INTEGER NOT NULL REFERENCES acquisitions(id),
            acquisition_line_id INTEGER REFERENCES acquisition_lines(id),
            event_type TEXT NOT NULL CHECK (event_type IN (
                'CREATED', 'DRAFT_AUTOSAVED', 'LINE_ADDED', 'LINE_AUTOSAVED',
                'ALLOCATION_CONFIRMED', 'STATE_TRANSITION', 'AUTHORITATIVE_CONFIRMATION',
                'CANCELED'
            )),
            from_state TEXT,
            to_state TEXT,
            effective_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            reason_code TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            payload TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    batch_columns = {row[1] for row in connection.execute("PRAGMA table_info(batches)")}
    if "acquisition_line_id" not in batch_columns:
        connection.execute(
            "ALTER TABLE batches ADD COLUMN acquisition_line_id INTEGER REFERENCES acquisition_lines(id)"
        )
    connection.execute("CREATE INDEX idx_acquisitions_state_updated ON acquisitions(state, updated_at)")
    connection.execute("CREATE INDEX idx_acquisition_lines_parent ON acquisition_lines(acquisition_id, line_sequence)")
    connection.execute("CREATE INDEX idx_acquisition_events_parent ON acquisition_events(acquisition_id, recorded_at, event_id)")
    connection.execute("CREATE INDEX idx_batches_acquisition_line ON batches(acquisition_line_id)")


def _v22_phase2_manual_acquisition_wizard(connection: sqlite3.Connection) -> None:
    """Persist resumable manual-wizard progress without changing economics facts.

    The column is UI progress only. Existing Phase 1 drafts resume at the first
    screen and existing confirmed acquisitions remain confirmed.
    """

    columns = {row[1] for row in connection.execute("PRAGMA table_info(acquisitions)")}
    if "wizard_step" not in columns:
        connection.execute(
            """ALTER TABLE acquisitions ADD COLUMN wizard_step TEXT NOT NULL DEFAULT 'ACQUIRE'
               CHECK (wizard_step IN (
                   'ACQUIRE', 'PRODUCTS', 'SOURCE', 'ECONOMICS',
                   'RECONCILIATION', 'REVIEW'
               ))"""
        )


def _v22_phase2_ux_revision(connection: sqlite3.Connection) -> None:
    """Add human purchase method and map legacy wizard progress to three steps."""

    columns = {row[1] for row in connection.execute("PRAGMA table_info(acquisitions)")}
    if "payment_method" not in columns:
        connection.execute(
            """ALTER TABLE acquisitions ADD COLUMN payment_method TEXT NOT NULL DEFAULT ''
               CHECK (payment_method IN ('', 'CREDIT_DEBIT_CARD', 'CASH', 'PAYPAL', 'STORE_CREDIT', 'OTHER'))"""
        )
    connection.execute(
        """UPDATE acquisitions
              SET wizard_step = CASE
                    WHEN wizard_step IN ('SOURCE', 'ECONOMICS') THEN 'PRODUCTS'
                    WHEN wizard_step = 'RECONCILIATION' THEN 'REVIEW'
                    ELSE wizard_step
                  END
            WHERE wizard_step IN ('SOURCE', 'ECONOMICS', 'RECONCILIATION')"""
    )


def _v22_phase3_product_catalog_upc(connection: sqlite3.Connection) -> None:
    """Add reusable commercial-product identity and audited identifier mappings.

    Product classes and subtypes intentionally remain TEXT rather than schema
    enums so later catalog classes do not require replacing these tables.
    No existing batches, cards, sealed units, or acquisition lines are inferred.
    """

    connection.execute(
        """
        CREATE TABLE catalog_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_uuid TEXT NOT NULL UNIQUE,
            creation_request_id TEXT NOT NULL UNIQUE,
            game TEXT NOT NULL,
            display_name TEXT NOT NULL,
            set_code TEXT NOT NULL DEFAULT '',
            set_name TEXT NOT NULL DEFAULT '',
            product_class TEXT NOT NULL,
            product_subtype TEXT NOT NULL DEFAULT '',
            manufacturer_product_code TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
            provenance TEXT NOT NULL,
            created_at TEXT NOT NULL,
            verified_at TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE product_identifiers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identifier_uuid TEXT NOT NULL UNIQUE,
            normalized_identifier TEXT NOT NULL UNIQUE,
            raw_identifier TEXT NOT NULL,
            identifier_type TEXT NOT NULL,
            catalog_product_id INTEGER NOT NULL REFERENCES catalog_products(id),
            mapping_status TEXT NOT NULL DEFAULT 'ACTIVE',
            provenance TEXT NOT NULL,
            created_at TEXT NOT NULL,
            verified_at TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE product_identifier_events (
            event_id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL UNIQUE,
            identifier_id INTEGER REFERENCES product_identifiers(id),
            acquisition_id INTEGER REFERENCES acquisitions(id),
            acquisition_line_id INTEGER REFERENCES acquisition_lines(id),
            event_type TEXT NOT NULL,
            from_catalog_product_id INTEGER REFERENCES catalog_products(id),
            to_catalog_product_id INTEGER REFERENCES catalog_products(id),
            effective_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            reason_code TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            payload TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    line_columns = {row[1] for row in connection.execute("PRAGMA table_info(acquisition_lines)")}
    if "catalog_product_id" not in line_columns:
        connection.execute(
            "ALTER TABLE acquisition_lines ADD COLUMN catalog_product_id INTEGER REFERENCES catalog_products(id)"
        )
    connection.execute(
        "CREATE INDEX idx_catalog_products_search ON catalog_products(active, game, set_code, display_name)"
    )
    connection.execute(
        "CREATE INDEX idx_product_identifiers_product ON product_identifiers(catalog_product_id, mapping_status)"
    )
    connection.execute(
        "CREATE INDEX idx_product_identifier_events_identifier ON product_identifier_events(identifier_id, recorded_at, event_id)"
    )
    connection.execute(
        "CREATE INDEX idx_product_identifier_events_acquisition ON product_identifier_events(acquisition_id, recorded_at, event_id)"
    )
    connection.execute(
        "CREATE INDEX idx_acquisition_lines_catalog_product ON acquisition_lines(catalog_product_id)"
    )


def _v22_phase4_source_documents(connection: sqlite3.Connection) -> None:
    """Add provider-neutral source-document metadata; binary artifacts stay outside SQLite."""

    connection.execute(
        """
        CREATE TABLE acquisition_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_uuid TEXT NOT NULL UNIQUE,
            acquisition_id INTEGER NOT NULL REFERENCES acquisitions(id),
            upload_request_id TEXT NOT NULL UNIQUE,
            provider_name TEXT NOT NULL,
            provider_resource_id TEXT NOT NULL DEFAULT '',
            original_filename TEXT NOT NULL,
            safe_filename TEXT NOT NULL,
            declared_mime_type TEXT NOT NULL DEFAULT '',
            detected_mime_type TEXT NOT NULL DEFAULT '',
            byte_size INTEGER NOT NULL DEFAULT 0 CHECK (byte_size >= 0),
            sha256 TEXT NOT NULL DEFAULT '',
            document_role TEXT NOT NULL DEFAULT 'RECEIPT',
            capture_method TEXT NOT NULL DEFAULT 'FILE_UPLOAD',
            storage_status TEXT NOT NULL DEFAULT 'PENDING'
                CHECK (storage_status IN ('PENDING','STORED','FAILED','TOMBSTONED')),
            extraction_status TEXT NOT NULL DEFAULT 'NOT_REQUESTED'
                CHECK (extraction_status = 'NOT_REQUESTED'),
            integrity_status TEXT NOT NULL DEFAULT 'UNVERIFIED'
                CHECK (integrity_status IN ('UNVERIFIED','VERIFIED','FAILED','NOT_AVAILABLE')),
            error_code TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            duplicate_of_document_id INTEGER REFERENCES acquisition_documents(id),
            replaced_by_document_id INTEGER REFERENCES acquisition_documents(id),
            captured_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_verified_at TEXT,
            tombstoned_at TEXT,
            tombstone_reason TEXT NOT NULL DEFAULT ''
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE acquisition_document_events (
            event_id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL UNIQUE,
            acquisition_id INTEGER NOT NULL REFERENCES acquisitions(id),
            document_id INTEGER REFERENCES acquisition_documents(id),
            event_type TEXT NOT NULL,
            effective_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            reason_code TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            payload TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    connection.execute(
        "CREATE INDEX idx_acquisition_documents_acquisition ON acquisition_documents(acquisition_id, created_at, id)"
    )
    connection.execute(
        "CREATE INDEX idx_acquisition_documents_hash ON acquisition_documents(acquisition_id, sha256, storage_status)"
    )
    connection.execute(
        "CREATE INDEX idx_acquisition_document_events_acquisition ON acquisition_document_events(acquisition_id, recorded_at, event_id)"
    )


def _v22_phase5_receipt_intelligence(connection: sqlite3.Connection) -> None:
    """Add versioned receipt candidates and proposal history without changing source facts."""

    connection.execute(
        """
        CREATE TABLE receipt_extraction_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_uuid TEXT NOT NULL UNIQUE,
            request_id TEXT NOT NULL UNIQUE,
            acquisition_id INTEGER NOT NULL REFERENCES acquisitions(id),
            document_id INTEGER NOT NULL REFERENCES acquisition_documents(id),
            retry_of_job_id INTEGER REFERENCES receipt_extraction_jobs(id),
            provider_name TEXT NOT NULL,
            provider_version TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('QUEUED','PROCESSING','COMPLETED','FAILED','NO_FACTS')),
            disposition TEXT NOT NULL DEFAULT 'PENDING'
                CHECK (disposition IN ('PENDING','ACCEPTED','REJECTED','SUPERSEDED')),
            queued_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            failed_at TEXT,
            error_code TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE receipt_candidate_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_uuid TEXT NOT NULL UNIQUE,
            job_id INTEGER NOT NULL REFERENCES receipt_extraction_jobs(id),
            acquisition_id INTEGER NOT NULL REFERENCES acquisitions(id),
            field_name TEXT NOT NULL,
            normalized_value TEXT NOT NULL,
            value_type TEXT NOT NULL CHECK (value_type IN ('TEXT','DATE','CURRENCY','INTEGER','CENTS','SCOPE')),
            confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
            confidence_band TEXT NOT NULL CHECK (confidence_band IN ('HIGH','MEDIUM','LOW')),
            source_page INTEGER,
            source_location TEXT NOT NULL DEFAULT '',
            disposition TEXT NOT NULL DEFAULT 'PENDING'
                CHECK (disposition IN ('PENDING','ACCEPTED','REJECTED','SUPERSEDED')),
            accepted_value TEXT,
            disposition_reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(job_id, field_name)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE receipt_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            line_uuid TEXT NOT NULL UNIQUE,
            job_id INTEGER NOT NULL REFERENCES receipt_extraction_jobs(id),
            acquisition_id INTEGER NOT NULL REFERENCES acquisitions(id),
            document_id INTEGER NOT NULL REFERENCES acquisition_documents(id),
            line_sequence INTEGER NOT NULL,
            description TEXT NOT NULL,
            quantity INTEGER,
            unit_price_cents INTEGER,
            line_total_cents INTEGER,
            currency TEXT NOT NULL DEFAULT '',
            extracted_identifier TEXT NOT NULL DEFAULT '',
            manufacturer_product_code TEXT NOT NULL DEFAULT '',
            confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
            confidence_band TEXT NOT NULL CHECK (confidence_band IN ('HIGH','MEDIUM','LOW')),
            source_page INTEGER,
            source_location TEXT NOT NULL DEFAULT '',
            classification TEXT NOT NULL DEFAULT 'UNRESOLVED'
                CHECK (classification IN ('INVENTORY','SHIPPING_FEE','BUSINESS_NONINVENTORY','PERSONAL_NONBUSINESS','DUPLICATE_EXTRACTION','UNRESOLVED')),
            classification_source TEXT NOT NULL DEFAULT 'EXTRACTOR',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(job_id, line_sequence)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE receipt_line_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_uuid TEXT NOT NULL UNIQUE,
            receipt_line_id INTEGER NOT NULL REFERENCES receipt_lines(id),
            acquisition_line_id INTEGER NOT NULL REFERENCES acquisition_lines(id),
            match_method TEXT NOT NULL CHECK (match_method IN ('EXACT_IDENTIFIER','EXACT_MANUFACTURER_CODE','EXACT_NAME_SET','FUZZY_TEXT')),
            confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
            status TEXT NOT NULL DEFAULT 'PROPOSED'
                CHECK (status IN ('PROPOSED','ACCEPTED','REJECTED','SUPERSEDED')),
            authoritative_identity INTEGER NOT NULL DEFAULT 0 CHECK (authoritative_identity IN (0,1)),
            rationale TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE receipt_allocation_proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_uuid TEXT NOT NULL UNIQUE,
            request_id TEXT NOT NULL UNIQUE,
            acquisition_id INTEGER NOT NULL REFERENCES acquisitions(id),
            method TEXT NOT NULL,
            calculation_version TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PROPOSED'
                CHECK (status IN ('PROPOSED','APPLIED','ACCEPTED','REJECTED','SUPERSEDED')),
            input_facts TEXT NOT NULL DEFAULT '{}',
            allocations TEXT NOT NULL DEFAULT '[]',
            total_allocated_cents INTEGER NOT NULL,
            difference_cents INTEGER NOT NULL,
            explanation TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            accepted_at TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE acquisition_field_provenance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            acquisition_id INTEGER NOT NULL REFERENCES acquisitions(id),
            field_name TEXT NOT NULL,
            candidate_id INTEGER NOT NULL REFERENCES receipt_candidate_facts(id),
            proposed_value TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PROPOSED'
                CHECK (status IN ('PROPOSED','OPERATOR_REPLACED','ACCEPTED','REJECTED','SUPERSEDED')),
            operator_value TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(acquisition_id, field_name, candidate_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE receipt_extraction_events (
            event_id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL UNIQUE,
            acquisition_id INTEGER NOT NULL REFERENCES acquisitions(id),
            job_id INTEGER REFERENCES receipt_extraction_jobs(id),
            candidate_id INTEGER REFERENCES receipt_candidate_facts(id),
            receipt_line_id INTEGER REFERENCES receipt_lines(id),
            event_type TEXT NOT NULL,
            effective_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            reason_code TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            payload TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    connection.execute("CREATE INDEX idx_receipt_jobs_acquisition ON receipt_extraction_jobs(acquisition_id, created_at, id)")
    connection.execute("CREATE INDEX idx_receipt_candidates_acquisition ON receipt_candidate_facts(acquisition_id, field_name, created_at)")
    connection.execute("CREATE INDEX idx_receipt_lines_acquisition ON receipt_lines(acquisition_id, classification, line_sequence)")
    connection.execute("CREATE INDEX idx_receipt_matches_line ON receipt_line_matches(receipt_line_id, status, confidence)")
    connection.execute("CREATE INDEX idx_receipt_allocations_acquisition ON receipt_allocation_proposals(acquisition_id, status, created_at)")
    connection.execute("CREATE INDEX idx_receipt_events_acquisition ON receipt_extraction_events(acquisition_id, recorded_at, event_id)")


def _v22_prephase_ux_safety_hotfix(connection: sqlite3.Connection) -> None:
    """Add recoverable acquisition tombstone facts without deleting source history."""

    columns = {row[1] for row in connection.execute("PRAGMA table_info(acquisitions)")}
    additions = (
        ("recycled_at", "TEXT"),
        ("recycle_reason_code", "TEXT NOT NULL DEFAULT ''"),
        ("recycle_notes", "TEXT NOT NULL DEFAULT ''"),
        ("pre_recycle_state", "TEXT"),
    )
    for name, definition in additions:
        if name not in columns:
            connection.execute(f"ALTER TABLE acquisitions ADD COLUMN {name} {definition}")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_acquisitions_recycled_updated "
        "ON acquisitions(recycled_at, updated_at)"
    )


def _v22_phase6_downstream_intake_bridge(connection: sqlite3.Connection) -> None:
    """Add an append-only routing ledger between acquisitions and batches.

    Historical batches and sealed units are deliberately left unlinked.  The
    disposition default keeps every existing remaining sealed unit available,
    while Phase 6 projections explicitly mark new units pending until routed.
    """

    sealed_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(sealed_units)")
    }
    if "intake_disposition" not in sealed_columns:
        connection.execute(
            "ALTER TABLE sealed_units ADD COLUMN intake_disposition TEXT NOT NULL "
            "DEFAULT 'LEGACY_AVAILABLE' CHECK (intake_disposition IN "
            "('LEGACY_AVAILABLE','PENDING','KEEP_SEALED','RIP_OPEN'))"
        )
    connection.execute(
        """
        CREATE TABLE acquisition_intake_operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_uuid TEXT NOT NULL UNIQUE,
            request_id TEXT NOT NULL UNIQUE,
            acquisition_id INTEGER NOT NULL REFERENCES acquisitions(id),
            from_state TEXT NOT NULL,
            to_state TEXT NOT NULL,
            effective_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE acquisition_line_projections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            projection_uuid TEXT NOT NULL UNIQUE,
            acquisition_id INTEGER NOT NULL REFERENCES acquisitions(id),
            acquisition_line_id INTEGER NOT NULL UNIQUE REFERENCES acquisition_lines(id),
            batch_id INTEGER NOT NULL UNIQUE REFERENCES batches(id),
            product_class TEXT NOT NULL CHECK (product_class IN ('SINGLE_CARDS','PACK_PRODUCT','SEALED_PRODUCT')),
            quantity_acquired INTEGER NOT NULL CHECK (quantity_acquired > 0),
            landed_cost_cents INTEGER NOT NULL CHECK (landed_cost_cents >= 0),
            catalog_product_id INTEGER REFERENCES catalog_products(id),
            created_by_operation_id INTEGER NOT NULL REFERENCES acquisition_intake_operations(id),
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE acquisition_intake_route_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_event_uuid TEXT NOT NULL UNIQUE,
            operation_id INTEGER NOT NULL REFERENCES acquisition_intake_operations(id),
            acquisition_line_id INTEGER NOT NULL REFERENCES acquisition_lines(id),
            batch_id INTEGER NOT NULL REFERENCES batches(id),
            route_action TEXT NOT NULL CHECK (route_action IN ('KEEP_SEALED','RIP_OPEN','SCAN_IDENTIFY')),
            quantity INTEGER NOT NULL CHECK (quantity > 0),
            basis_cents INTEGER NOT NULL CHECK (basis_cents >= 0),
            rip_session_id INTEGER REFERENCES rip_sessions(id),
            created_at TEXT NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    connection.execute(
        "CREATE UNIQUE INDEX idx_batches_one_acquisition_line "
        "ON batches(acquisition_line_id) WHERE acquisition_line_id IS NOT NULL"
    )
    connection.execute(
        "CREATE INDEX idx_intake_operations_acquisition "
        "ON acquisition_intake_operations(acquisition_id, recorded_at, id)"
    )
    connection.execute(
        "CREATE INDEX idx_intake_routes_line "
        "ON acquisition_intake_route_events(acquisition_line_id, id)"
    )
    connection.execute(
        "CREATE INDEX idx_intake_routes_batch "
        "ON acquisition_intake_route_events(batch_id, id)"
    )
    connection.execute(
        "CREATE INDEX idx_sealed_units_intake_disposition "
        "ON sealed_units(batch_id, intake_disposition, status, unit_sequence)"
    )


def _v22_phase7_sam_recognition(connection: sqlite3.Connection) -> None:
    """Add provider-neutral SAM metadata, reference, recognition, and review facts."""

    cards_exist = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='cards'"
    ).fetchone()
    if cards_exist:
        card_columns = {row[1] for row in connection.execute("PRAGMA table_info(cards)")}
        for name, definition in (
            ("sam_recognition_state", "TEXT"),
            ("sam_recognition_job_id", "INTEGER"),
        ):
            if name not in card_columns:
                connection.execute(f"ALTER TABLE cards ADD COLUMN {name} {definition}")

    connection.execute(
        """
        CREATE TABLE sam_metadata_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            source_key TEXT NOT NULL,
            card_number TEXT NOT NULL DEFAULT '',
            normalized_metadata TEXT NOT NULL DEFAULT '{}',
            provider_version TEXT NOT NULL DEFAULT '',
            fetched_at TEXT,
            refreshed_at TEXT NOT NULL,
            cache_state TEXT NOT NULL
                CHECK (cache_state IN ('ACTIVE','STALE','MISSING')),
            error_code TEXT NOT NULL DEFAULT '',
            UNIQUE(provider, source_key)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE sam_metadata_refresh_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_uuid TEXT NOT NULL UNIQUE,
            request_id TEXT NOT NULL UNIQUE,
            provider TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('COMPLETED','PARTIAL','FAILED')),
            requested_keys INTEGER NOT NULL DEFAULT 0,
            refreshed_keys INTEGER NOT NULL DEFAULT 0,
            missing_keys INTEGER NOT NULL DEFAULT 0,
            duration_ms REAL NOT NULL DEFAULT 0,
            started_at TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            error_code TEXT NOT NULL DEFAULT '',
            payload TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE sam_reference_index_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_uuid TEXT NOT NULL UNIQUE,
            request_id TEXT NOT NULL UNIQUE,
            library_root TEXT NOT NULL,
            index_version TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('COMPLETED','PARTIAL','FAILED')),
            files_seen INTEGER NOT NULL DEFAULT 0,
            indexed INTEGER NOT NULL DEFAULT 0,
            unchanged INTEGER NOT NULL DEFAULT 0,
            changed INTEGER NOT NULL DEFAULT 0,
            duplicate_hashes INTEGER NOT NULL DEFAULT 0,
            near_duplicates INTEGER NOT NULL DEFAULT 0,
            missing_marked INTEGER NOT NULL DEFAULT 0,
            duration_ms REAL NOT NULL DEFAULT 0,
            started_at TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            error_code TEXT NOT NULL DEFAULT '',
            payload TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE sam_reference_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference_uuid TEXT NOT NULL UNIQUE,
            game TEXT NOT NULL,
            card_number TEXT NOT NULL DEFAULT '',
            set_code TEXT NOT NULL DEFAULT '',
            card_name TEXT NOT NULL DEFAULT '',
            rarity TEXT NOT NULL DEFAULT '',
            card_type TEXT NOT NULL DEFAULT '',
            color TEXT NOT NULL DEFAULT '',
            language TEXT NOT NULL DEFAULT 'Unknown',
            variant TEXT NOT NULL DEFAULT 'Unknown',
            printing TEXT NOT NULL DEFAULT 'Unknown',
            source_filename TEXT NOT NULL,
            source_reference TEXT NOT NULL,
            width INTEGER,
            height INTEGER,
            file_size INTEGER NOT NULL,
            mtime_ns INTEGER NOT NULL,
            sha256 TEXT NOT NULL,
            perceptual_hash TEXT NOT NULL DEFAULT '',
            visual_bucket TEXT NOT NULL DEFAULT '',
            metadata_provider TEXT NOT NULL DEFAULT '',
            metadata_source_key TEXT NOT NULL DEFAULT '',
            library_provenance TEXT NOT NULL DEFAULT 'LOCAL_OPERATOR_LIBRARY',
            index_version TEXT NOT NULL,
            indexed_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
            duplicate_of_reference_id INTEGER REFERENCES sam_reference_records(id),
            UNIQUE(game, source_reference)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE sam_recognition_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_uuid TEXT NOT NULL UNIQUE,
            request_id TEXT NOT NULL UNIQUE,
            recognition_key TEXT NOT NULL UNIQUE,
            card_id INTEGER NOT NULL REFERENCES cards(id),
            batch_id INTEGER NOT NULL REFERENCES batches(id),
            rip_session_id INTEGER REFERENCES rip_sessions(id),
            acquisition_line_id INTEGER REFERENCES acquisition_lines(id),
            game TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('QUEUED','COMPLETED','FAILED')),
            revision INTEGER NOT NULL DEFAULT 1,
            engine_version TEXT NOT NULL,
            rules_version TEXT NOT NULL,
            scan_sha256 TEXT NOT NULL DEFAULT '',
            raw_ocr_candidate TEXT NOT NULL DEFAULT '',
            normalized_card_number TEXT NOT NULL DEFAULT '',
            card_number_confidence REAL NOT NULL DEFAULT 0,
            top_reference_id INTEGER REFERENCES sam_reference_records(id),
            confidence REAL NOT NULL DEFAULT 0,
            recognition_state TEXT NOT NULL
                CHECK (recognition_state IN ('AUTO_MATCHED','NEEDS_REVIEW','UNIDENTIFIED')),
            identity_applied INTEGER NOT NULL DEFAULT 0 CHECK (identity_applied IN (0,1)),
            scan_quality TEXT NOT NULL DEFAULT '{}',
            exception_codes TEXT NOT NULL DEFAULT '[]',
            evidence TEXT NOT NULL DEFAULT '{}',
            submitted_at TEXT NOT NULL,
            completed_at TEXT,
            error_code TEXT NOT NULL DEFAULT ''
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE sam_recognition_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL REFERENCES sam_recognition_jobs(id),
            rank INTEGER NOT NULL,
            reference_id INTEGER NOT NULL REFERENCES sam_reference_records(id),
            confidence REAL NOT NULL,
            card_number_score REAL NOT NULL DEFAULT 0,
            visual_score REAL NOT NULL DEFAULT 0,
            context_score REAL NOT NULL DEFAULT 0,
            evidence TEXT NOT NULL DEFAULT '{}',
            UNIQUE(job_id, rank),
            UNIQUE(job_id, reference_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE sam_recognition_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_uuid TEXT NOT NULL UNIQUE,
            request_id TEXT NOT NULL UNIQUE,
            job_id INTEGER NOT NULL REFERENCES sam_recognition_jobs(id),
            card_id INTEGER NOT NULL REFERENCES cards(id),
            decision_type TEXT NOT NULL
                CHECK (decision_type IN ('OPERATOR_CONFIRMED','OPERATOR_CORRECTED','LEFT_UNIDENTIFIED')),
            original_top_reference_id INTEGER REFERENCES sam_reference_records(id),
            selected_reference_id INTEGER REFERENCES sam_reference_records(id),
            expected_revision INTEGER NOT NULL,
            effective_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            reason_code TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            evidence TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    connection.execute(
        "CREATE INDEX idx_sam_metadata_number ON sam_metadata_cache(card_number, cache_state)"
    )
    connection.execute(
        "CREATE INDEX idx_sam_reference_number ON sam_reference_records(game, card_number, active)"
    )
    connection.execute(
        "CREATE INDEX idx_sam_reference_search ON sam_reference_records(game, set_code, card_name, active)"
    )
    connection.execute(
        "CREATE INDEX idx_sam_reference_hash ON sam_reference_records(sha256, active)"
    )
    connection.execute(
        "CREATE INDEX idx_sam_reference_bucket ON sam_reference_records(game, visual_bucket, active)"
    )
    connection.execute(
        "CREATE INDEX idx_sam_jobs_queue ON sam_recognition_jobs(batch_id, recognition_state, submitted_at)"
    )
    connection.execute(
        "CREATE INDEX idx_sam_jobs_card ON sam_recognition_jobs(card_id, submitted_at, id)"
    )
    connection.execute(
        "CREATE INDEX idx_sam_decisions_job ON sam_recognition_decisions(job_id, recorded_at, id)"
    )


def _v24_sam_phase1_family_printing(connection: sqlite3.Connection) -> None:
    """Separate stable card-family truth from exact commercial-printing truth.

    The migration is deliberately additive. Existing card identity text is left
    untouched and receives no inferred family or printing foreign key.
    """

    certainty = (
        "CHECK (certainty IN ('AUTHORITATIVE','OPERATOR_CONFIRMED',"
        "'HIGH_CONFIDENCE_SUGGESTION','UNRESOLVED','CONFLICTING','LEGACY_RECORDED'))"
    )
    connection.execute(
        """
        CREATE TABLE sam_card_families (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            family_uuid TEXT NOT NULL UNIQUE,
            game TEXT NOT NULL,
            family_key TEXT NOT NULL,
            normalized_set_code TEXT NOT NULL DEFAULT '',
            card_number TEXT NOT NULL DEFAULT '',
            canonical_name TEXT NOT NULL DEFAULT '',
            normalized_name TEXT NOT NULL DEFAULT '',
            external_descriptors TEXT NOT NULL DEFAULT '{}',
            active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(game, family_key)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE sam_commercial_printings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            printing_uuid TEXT NOT NULL UNIQUE,
            family_id INTEGER NOT NULL REFERENCES sam_card_families(id),
            printing_key TEXT NOT NULL,
            artwork_identity TEXT NOT NULL DEFAULT '',
            variant_label TEXT NOT NULL DEFAULT '',
            rarity_treatment TEXT NOT NULL DEFAULT '',
            finish TEXT NOT NULL DEFAULT '',
            language TEXT NOT NULL DEFAULT 'Unknown',
            special_designation TEXT NOT NULL DEFAULT '',
            stamp_marking TEXT NOT NULL DEFAULT '',
            promo_release TEXT NOT NULL DEFAULT '',
            operator_description TEXT NOT NULL DEFAULT '',
            catalog_source TEXT NOT NULL DEFAULT '',
            evidence_requirements TEXT NOT NULL DEFAULT '{}',
            authority_state TEXT NOT NULL DEFAULT 'DESCRIPTIVE'
                CHECK (authority_state IN ('DESCRIPTIVE','OPERATOR_CONFIRMED','INACTIVE')),
            active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(family_id, printing_key)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE sam_printing_external_ids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            printing_id INTEGER NOT NULL REFERENCES sam_commercial_printings(id),
            provider TEXT NOT NULL,
            external_id TEXT NOT NULL,
            descriptive_metadata TEXT NOT NULL DEFAULT '{}',
            authority_granted INTEGER NOT NULL DEFAULT 0 CHECK (authority_granted=0),
            created_at TEXT NOT NULL,
            UNIQUE(provider, external_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE sam_reference_asset_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference_id INTEGER NOT NULL UNIQUE REFERENCES sam_reference_records(id),
            family_id INTEGER NOT NULL REFERENCES sam_card_families(id),
            printing_id INTEGER REFERENCES sam_commercial_printings(id),
            asset_scope TEXT NOT NULL CHECK (asset_scope IN ('FAMILY','PRINTING')),
            certainty TEXT NOT NULL DEFAULT 'HIGH_CONFIDENCE_SUGGESTION'
                CHECK (certainty IN ('AUTHORITATIVE','OPERATOR_CONFIRMED',
                    'HIGH_CONFIDENCE_SUGGESTION','UNRESOLVED','CONFLICTING','LEGACY_RECORDED')),
            provenance TEXT NOT NULL DEFAULT 'LOCAL_REFERENCE_DESCRIPTION',
            evidence TEXT NOT NULL DEFAULT '{}',
            linked_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE sam_identity_assertions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assertion_uuid TEXT NOT NULL UNIQUE,
            card_id INTEGER NOT NULL REFERENCES cards(id),
            job_id INTEGER REFERENCES sam_recognition_jobs(id),
            legacy_decision_id INTEGER REFERENCES sam_recognition_decisions(id),
            field_scope TEXT NOT NULL
                CHECK (field_scope IN ('FAMILY','PRINTING','LANGUAGE','FINISH','REFERENCE_ASSET')),
            family_id INTEGER REFERENCES sam_card_families(id),
            printing_id INTEGER REFERENCES sam_commercial_printings(id),
            reference_id INTEGER REFERENCES sam_reference_records(id),
            proposed_value TEXT NOT NULL DEFAULT '',
            certainty TEXT NOT NULL {certainty},
            numeric_confidence REAL,
            authority_granted INTEGER NOT NULL DEFAULT 0 CHECK (authority_granted IN (0,1)),
            actor TEXT NOT NULL CHECK (actor IN ('SYSTEM','OPERATOR','LEGACY')),
            reason_code TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            evidence TEXT NOT NULL DEFAULT '{{}}',
            supersedes_assertion_id INTEGER REFERENCES sam_identity_assertions(id),
            created_at TEXT NOT NULL,
            CHECK (field_scope!='PRINTING' OR authority_granted=0 OR
                   (actor='OPERATOR' AND certainty='OPERATOR_CONFIRMED'))
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE sam_identity_decision_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_uuid TEXT NOT NULL UNIQUE,
            request_id TEXT NOT NULL UNIQUE,
            job_id INTEGER REFERENCES sam_recognition_jobs(id),
            card_id INTEGER NOT NULL REFERENCES cards(id),
            event_type TEXT NOT NULL CHECK (event_type IN (
                'FAMILY_AUTO_APPLIED','FAMILY_CONFIRMED','FAMILY_CORRECTED',
                'PRINTING_CONFIRMED','PRINTING_CORRECTED','PRINTING_LEFT_UNRESOLVED',
                'PRINTING_CONFLICT','REFERENCE_ATTACHED','MANUAL_IDENTITY_EDIT')),
            family_id INTEGER REFERENCES sam_card_families(id),
            printing_id INTEGER REFERENCES sam_commercial_printings(id),
            reference_id INTEGER REFERENCES sam_reference_records(id),
            prior_family_id INTEGER REFERENCES sam_card_families(id),
            prior_printing_id INTEGER REFERENCES sam_commercial_printings(id),
            certainty TEXT NOT NULL {certainty},
            actor TEXT NOT NULL CHECK (actor IN ('SYSTEM','OPERATOR','LEGACY')),
            effective_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            reason_code TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            evidence TEXT NOT NULL DEFAULT '{{}}',
            CHECK (event_type NOT IN ('PRINTING_CONFIRMED','PRINTING_CORRECTED') OR
                   (actor='OPERATOR' AND certainty='OPERATOR_CONFIRMED'))
        )
        """
    )

    card_columns = {row[1] for row in connection.execute("PRAGMA table_info(cards)")}
    for name, definition in (
        ("sam_family_id", "INTEGER REFERENCES sam_card_families(id)"),
        ("sam_printing_id", "INTEGER REFERENCES sam_commercial_printings(id)"),
        ("sam_family_certainty", "TEXT NOT NULL DEFAULT 'UNRESOLVED'"),
        ("sam_printing_certainty", "TEXT NOT NULL DEFAULT 'UNRESOLVED'"),
        ("sam_language_certainty", "TEXT NOT NULL DEFAULT 'LEGACY_RECORDED'"),
        ("sam_finish_certainty", "TEXT NOT NULL DEFAULT 'LEGACY_RECORDED'"),
        ("sam_legacy_identity_provenance", "TEXT NOT NULL DEFAULT 'LEGACY_RECORDED'"),
    ):
        if name not in card_columns:
            connection.execute(f"ALTER TABLE cards ADD COLUMN {name} {definition}")

    job_columns = {row[1] for row in connection.execute("PRAGMA table_info(sam_recognition_jobs)")}
    for name, definition in (
        ("family_id", "INTEGER REFERENCES sam_card_families(id)"),
        ("family_confidence", "REAL NOT NULL DEFAULT 0"),
        ("family_certainty", "TEXT NOT NULL DEFAULT 'UNRESOLVED'"),
        ("printing_id", "INTEGER REFERENCES sam_commercial_printings(id)"),
        ("printing_confidence", "REAL NOT NULL DEFAULT 0"),
        ("printing_certainty", "TEXT NOT NULL DEFAULT 'UNRESOLVED'"),
        ("printing_unresolved_reason", "TEXT NOT NULL DEFAULT ''"),
        ("printing_evidence", "TEXT NOT NULL DEFAULT '{}'"),
    ):
        if name not in job_columns:
            connection.execute(f"ALTER TABLE sam_recognition_jobs ADD COLUMN {name} {definition}")

    connection.execute("CREATE INDEX idx_sam_families_number ON sam_card_families(game, card_number, active)")
    connection.execute("CREATE INDEX idx_sam_printings_family ON sam_commercial_printings(family_id, active, id)")
    connection.execute("CREATE INDEX idx_sam_reference_family ON sam_reference_asset_links(family_id, printing_id)")
    connection.execute("CREATE INDEX idx_sam_assertions_card ON sam_identity_assertions(card_id, created_at, id)")
    connection.execute("CREATE INDEX idx_sam_identity_events_card ON sam_identity_decision_events(card_id, recorded_at, id)")
    connection.execute(
        "CREATE TRIGGER sam_identity_assertions_no_update BEFORE UPDATE ON sam_identity_assertions "
        "BEGIN SELECT RAISE(ABORT, 'SAM identity assertions are append-only'); END"
    )
    connection.execute(
        "CREATE TRIGGER sam_identity_assertions_no_delete BEFORE DELETE ON sam_identity_assertions "
        "BEGIN SELECT RAISE(ABORT, 'SAM identity assertions are append-only'); END"
    )
    connection.execute(
        "CREATE TRIGGER sam_identity_events_no_update BEFORE UPDATE ON sam_identity_decision_events "
        "BEGIN SELECT RAISE(ABORT, 'SAM identity decisions are append-only'); END"
    )
    connection.execute(
        "CREATE TRIGGER sam_identity_events_no_delete BEFORE DELETE ON sam_identity_decision_events "
        "BEGIN SELECT RAISE(ABORT, 'SAM identity decisions are append-only'); END"
    )


def _v24_jarvis_economics_sam_phase2(connection: sqlite3.Connection) -> None:
    """Add evidence completeness and append-only printing observations.

    JARVIS calculations remain read-only and are never stored as dashboard
    totals.  The sale evidence row records whether a zero fee/postage value was
    explicitly supplied; it does not change the sale itself.  SAM observations
    are evidence only and cannot grant commercial-printing authority.
    """

    connection.execute(
        """
        CREATE TABLE jarvis_sale_input_evidence (
            order_id INTEGER PRIMARY KEY REFERENCES sale_orders(id),
            merchandise_proceeds_known INTEGER
                CHECK (merchandise_proceeds_known IS NULL OR merchandise_proceeds_known IN (0,1)),
            shipping_collected_known INTEGER
                CHECK (shipping_collected_known IS NULL OR shipping_collected_known IN (0,1)),
            marketplace_fees_known INTEGER
                CHECK (marketplace_fees_known IS NULL OR marketplace_fees_known IN (0,1)),
            actual_shipping_cost_known INTEGER
                CHECK (actual_shipping_cost_known IS NULL OR actual_shipping_cost_known IN (0,1)),
            captured_at TEXT NOT NULL,
            provenance TEXT NOT NULL DEFAULT 'SALE_ENTRY_PRESENCE_FLAGS'
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE sam_printing_evidence_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            observation_uuid TEXT NOT NULL UNIQUE,
            job_id INTEGER NOT NULL REFERENCES sam_recognition_jobs(id),
            family_id INTEGER NOT NULL REFERENCES sam_card_families(id),
            printing_id INTEGER REFERENCES sam_commercial_printings(id),
            reference_id INTEGER REFERENCES sam_reference_records(id),
            evidence_type TEXT NOT NULL,
            observed_state TEXT NOT NULL
                CHECK (observed_state IN ('PRESENT','ABSENT_CONFIDENT','UNRESOLVED')),
            numeric_confidence REAL
                CHECK (numeric_confidence IS NULL OR
                       (numeric_confidence >= 0 AND numeric_confidence <= 1)),
            source_kind TEXT NOT NULL CHECK (source_kind IN (
                'SYSTEM_VISUAL','SYSTEM_OCR','REFERENCE_METADATA',
                'CHALLENGER_SHADOW','OPERATOR'
            )),
            explanation TEXT NOT NULL DEFAULT '',
            evidence TEXT NOT NULL DEFAULT '{}',
            observed_at TEXT NOT NULL,
            CHECK (source_kind!='CHALLENGER_SHADOW' OR observed_state!='PRESENT'
                   OR numeric_confidence IS NOT NULL)
        )
        """
    )
    connection.execute(
        "CREATE INDEX idx_sam_printing_observations_job "
        "ON sam_printing_evidence_observations(job_id, printing_id, evidence_type, id)"
    )
    connection.execute(
        "CREATE INDEX idx_sam_printing_observations_family "
        "ON sam_printing_evidence_observations(family_id, printing_id, observed_at, id)"
    )
    connection.execute(
        "CREATE TRIGGER sam_printing_observations_no_update "
        "BEFORE UPDATE ON sam_printing_evidence_observations "
        "BEGIN SELECT RAISE(ABORT, 'SAM printing evidence is append-only'); END"
    )
    connection.execute(
        "CREATE TRIGGER sam_printing_observations_no_delete "
        "BEFORE DELETE ON sam_printing_evidence_observations "
        "BEGIN SELECT RAISE(ABORT, 'SAM printing evidence is append-only'); END"
    )


def _v22_rc3_hf1_mixed_purchase_reconciliation(connection: sqlite3.Connection) -> None:
    """Add an explicit, nullable noninventory partition to acquisition facts.

    Existing rows are deliberately left NULL.  The migration does not infer an
    excluded amount from a discrepancy reason, receipt line, or allocation gap.
    """

    columns = {row[1] for row in connection.execute("PRAGMA table_info(acquisitions)")}
    additions = {
        "excluded_noninventory_cents": (
            "INTEGER CHECK (excluded_noninventory_cents IS NULL "
            "OR excluded_noninventory_cents >= 0)"
        ),
        "noninventory_treatment_code": (
            "TEXT CHECK (noninventory_treatment_code IS NULL OR "
            "noninventory_treatment_code IN ("
            "'BUSINESS_NONINVENTORY','PERSONAL_NONBUSINESS',"
            "'MIXED_NONINVENTORY','OTHER'))"
        ),
        "noninventory_notes": "TEXT",
    }
    for name, definition in additions.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE acquisitions ADD COLUMN {name} {definition}")


def _v23_inventory_intelligence_phase1_receipt_semantics(
    connection: sqlite3.Connection,
) -> None:
    """Add non-authoritative, append-only receipt semantic evidence.

    Existing HF3 receipt facts are intentionally not backfilled. Historical
    extraction jobs retain their established behavior until explicitly
    reprocessed by the new semantic engine.
    """

    connection.execute(
        """
        CREATE TABLE receipt_semantic_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            semantic_uuid TEXT NOT NULL UNIQUE,
            job_id INTEGER NOT NULL REFERENCES receipt_extraction_jobs(id),
            acquisition_id INTEGER NOT NULL REFERENCES acquisitions(id),
            document_id INTEGER NOT NULL REFERENCES acquisition_documents(id),
            receipt_line_id INTEGER REFERENCES receipt_lines(id),
            source_line_index INTEGER NOT NULL CHECK (source_line_index > 0),
            source_page INTEGER,
            source_location TEXT NOT NULL DEFAULT '',
            normalized_text TEXT NOT NULL,
            source_line_sha256 TEXT NOT NULL,
            signed_amount_cents INTEGER,
            semantic_class TEXT NOT NULL CHECK (semantic_class IN (
                'MERCHANDISE','DISCOUNT_CREDIT','FEE_SURCHARGE','TAX','SHIPPING',
                'SUBTOTAL','TOTAL','TENDER_PAYMENT_METHOD','PAYMENT_SUMMARY',
                'INFORMATIONAL_FOOTER','STRUCTURAL','UNKNOWN'
            )),
            numeric_confidence REAL CHECK (
                numeric_confidence IS NULL OR
                (numeric_confidence >= 0 AND numeric_confidence <= 1)
            ),
            confidence_state TEXT NOT NULL CHECK (confidence_state IN (
                'HIGH_CONFIDENCE_SUGGESTION','UNRESOLVED','CONFLICTING',
                'OPERATOR_CONFIRMED'
            )),
            parser_version TEXT NOT NULL,
            rules_version TEXT NOT NULL,
            engine_version TEXT NOT NULL,
            operator_confirmation_required INTEGER NOT NULL DEFAULT 1
                CHECK (operator_confirmation_required IN (0,1)),
            semantic_status TEXT NOT NULL CHECK (semantic_status IN (
                'PROPOSED','CONFIRMED','UNRESOLVED','CONFLICTING','SUPERSEDED'
            )),
            recorded_at TEXT NOT NULL,
            supersedes_semantic_line_id INTEGER REFERENCES receipt_semantic_lines(id),
            evidence TEXT NOT NULL DEFAULT '{}',
            UNIQUE(job_id, source_line_index, supersedes_semantic_line_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE receipt_semantic_events (
            event_id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL UNIQUE,
            semantic_line_id INTEGER NOT NULL REFERENCES receipt_semantic_lines(id),
            successor_semantic_line_id INTEGER REFERENCES receipt_semantic_lines(id),
            job_id INTEGER NOT NULL REFERENCES receipt_extraction_jobs(id),
            acquisition_id INTEGER NOT NULL REFERENCES acquisitions(id),
            event_type TEXT NOT NULL CHECK (event_type IN (
                'CLASSIFIED','OPERATOR_CONFIRMED','OPERATOR_CORRECTED',
                'MARKED_UNRESOLVED'
            )),
            from_semantic_class TEXT,
            to_semantic_class TEXT NOT NULL,
            effective_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            reason_code TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            payload TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    connection.execute(
        "CREATE INDEX idx_receipt_semantic_acquisition "
        "ON receipt_semantic_lines(acquisition_id, job_id, source_line_index, id)"
    )
    connection.execute(
        "CREATE INDEX idx_receipt_semantic_receipt_line "
        "ON receipt_semantic_lines(receipt_line_id, semantic_status, id)"
    )
    connection.execute(
        "CREATE UNIQUE INDEX idx_receipt_semantic_one_successor "
        "ON receipt_semantic_lines(supersedes_semantic_line_id) "
        "WHERE supersedes_semantic_line_id IS NOT NULL"
    )
    connection.execute(
        "CREATE INDEX idx_receipt_semantic_events_acquisition "
        "ON receipt_semantic_events(acquisition_id, recorded_at, event_id)"
    )


def _v24_sam_multi_evidence_operator_trial_v1a(connection: sqlite3.Connection) -> None:
    """Add passive, append-only audited SAM operator-trial records.

    These records deliberately sit beside the established SAM tables. The frozen
    recognizer writes only its immutable suggestion here. A later, explicit
    operator decision is the sole path that may grant card-family authority.
    """

    script = (
        """
        CREATE TABLE sam_audited_recognition_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            result_uuid TEXT NOT NULL UNIQUE,
            request_id TEXT NOT NULL UNIQUE,
            card_id INTEGER NOT NULL REFERENCES cards(id),
            source_sha256 TEXT NOT NULL,
            build_identifier TEXT NOT NULL,
            build_fingerprint TEXT NOT NULL,
            suggested_family TEXT,
            suggested_name TEXT,
            evidence_state TEXT NOT NULL,
            review_state TEXT NOT NULL CHECK (review_state IN (
                'SUGGESTION','NEEDS_REVIEW','UNIDENTIFIED','FAILED'
            )),
            result_json TEXT NOT NULL,
            result_sha256 TEXT NOT NULL,
            suggestion_only INTEGER NOT NULL DEFAULT 1 CHECK (suggestion_only=1),
            identity_applied INTEGER NOT NULL DEFAULT 0 CHECK (identity_applied=0),
            exact_printing_authority INTEGER NOT NULL DEFAULT 0 CHECK (exact_printing_authority=0),
            recorded_at TEXT NOT NULL
        );

        CREATE TABLE sam_audited_operator_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_uuid TEXT NOT NULL UNIQUE,
            request_id TEXT NOT NULL UNIQUE,
            result_id INTEGER NOT NULL UNIQUE REFERENCES sam_audited_recognition_results(id),
            card_id INTEGER NOT NULL REFERENCES cards(id),
            action TEXT NOT NULL CHECK (action IN (
                'CONFIRMED_UNCHANGED','CORRECTED_FAMILY','CORRECTED_CARD_NUMBER',
                'CORRECTED_NAME','MARKED_UNIDENTIFIED','ESCALATED_REVIEW','RESCAN_REQUESTED'
            )),
            original_suggested_family TEXT,
            selected_family TEXT,
            selected_name TEXT,
            selected_candidate_rank INTEGER,
            identity_applied INTEGER NOT NULL CHECK (identity_applied IN (0,1)),
            reason_code TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            recognition_result_sha256 TEXT NOT NULL,
            effective_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        );

        CREATE TABLE sam_audited_verified_truth (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            truth_uuid TEXT NOT NULL UNIQUE,
            request_id TEXT NOT NULL UNIQUE,
            result_id INTEGER NOT NULL REFERENCES sam_audited_recognition_results(id),
            decision_id INTEGER REFERENCES sam_audited_operator_decisions(id),
            disposition TEXT NOT NULL CHECK (disposition IN (
                'SAM_CORRECT','OPERATOR_CORRECT','BOTH_UNRESOLVED',
                'OPERATOR_CORRECTION_LATER_REVERSED'
            )),
            verified_family TEXT,
            verified_name TEXT,
            reason_code TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            supersedes_truth_id INTEGER REFERENCES sam_audited_verified_truth(id),
            used_as_training_label INTEGER NOT NULL DEFAULT 0 CHECK (used_as_training_label=0),
            effective_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        );

        CREATE TABLE sam_audited_recognition_deltas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            delta_uuid TEXT NOT NULL UNIQUE,
            result_id INTEGER NOT NULL REFERENCES sam_audited_recognition_results(id),
            decision_id INTEGER REFERENCES sam_audited_operator_decisions(id),
            truth_id INTEGER REFERENCES sam_audited_verified_truth(id),
            verification_state TEXT NOT NULL CHECK (verification_state IN ('UNVERIFIED','VERIFIED')),
            before_json TEXT NOT NULL,
            after_json TEXT NOT NULL,
            forensic_json TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        );

        CREATE INDEX idx_sam_audited_results_card
            ON sam_audited_recognition_results(card_id, recorded_at, id);
        CREATE INDEX idx_sam_audited_decisions_result
            ON sam_audited_operator_decisions(result_id, recorded_at, id);
        CREATE INDEX idx_sam_audited_truth_result
            ON sam_audited_verified_truth(result_id, recorded_at, id);
        CREATE INDEX idx_sam_audited_deltas_result
            ON sam_audited_recognition_deltas(result_id, recorded_at, id);

        CREATE TRIGGER sam_audited_results_no_update
        BEFORE UPDATE ON sam_audited_recognition_results
        BEGIN SELECT RAISE(ABORT, 'Audited SAM original results are immutable'); END;
        CREATE TRIGGER sam_audited_results_no_delete
        BEFORE DELETE ON sam_audited_recognition_results
        BEGIN SELECT RAISE(ABORT, 'Audited SAM original results are durable'); END;
        CREATE TRIGGER sam_audited_decisions_no_update
        BEFORE UPDATE ON sam_audited_operator_decisions
        BEGIN SELECT RAISE(ABORT, 'Audited SAM decisions are append-only'); END;
        CREATE TRIGGER sam_audited_decisions_no_delete
        BEFORE DELETE ON sam_audited_operator_decisions
        BEGIN SELECT RAISE(ABORT, 'Audited SAM decisions are durable'); END;
        CREATE TRIGGER sam_audited_truth_no_update
        BEFORE UPDATE ON sam_audited_verified_truth
        BEGIN SELECT RAISE(ABORT, 'Audited SAM verified truth is append-only'); END;
        CREATE TRIGGER sam_audited_truth_no_delete
        BEFORE DELETE ON sam_audited_verified_truth
        BEGIN SELECT RAISE(ABORT, 'Audited SAM verified truth is durable'); END;
        CREATE TRIGGER sam_audited_deltas_no_update
        BEFORE UPDATE ON sam_audited_recognition_deltas
        BEGIN SELECT RAISE(ABORT, 'Audited SAM deltas are append-only'); END;
        CREATE TRIGGER sam_audited_deltas_no_delete
        BEFORE DELETE ON sam_audited_recognition_deltas
        BEGIN SELECT RAISE(ABORT, 'Audited SAM deltas are durable'); END;
        """
    )
    # sqlite3.Connection.executescript() commits implicitly and would destroy
    # apply_migrations()' per-migration savepoint. Execute complete statements
    # one at a time so a failed migration remains transactionally reversible.
    statement = ""
    for line in script.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            connection.execute(statement)
            statement = ""
    if statement.strip():
        raise RuntimeError("Incomplete SQL statement in audited SAM migration")


DEFAULT_MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        "0001_phase3_acquisition_facts",
        "add Phase 3 acquisition facts and receipt group references",
        _phase3_acquisition_facts,
    ),
    Migration(
        "0002_phase4_rip_sessions",
        "add Phase 4 rip sessions, immutable basis events, and intake association",
        _phase4_rip_sessions,
    ),
    Migration(
        "0003_phase5_sealed_inventory",
        "add exact sealed units, sealed-only sale facts, and sealed event history",
        _phase5_sealed_inventory,
    ),
    Migration(
        "0004_phase7a_corrections_dispositions",
        "add append-only correction, disposition, reversal, and tombstone history",
        _phase7a_corrections_dispositions,
    ),
    Migration(
        "0005_phase7b_post_sale_events",
        "add immutable post-sale events, exact returns, and repeat card-sale history",
        _phase7b_post_sale_events,
    ),
    Migration(
        "0006_v22_phase1_inbound_acquisitions",
        "add draft acquisitions, product lines, lifecycle events, and nullable batch linkage",
        _v22_phase1_inbound_acquisitions,
    ),
    Migration(
        "0007_v22_phase2_manual_acquisition_wizard",
        "add resumable manual acquisition wizard progress",
        _v22_phase2_manual_acquisition_wizard,
    ),
    Migration(
        "0008_v22_phase2_ux_revision",
        "add payment method and map resumable wizard progress to the three-step receiving flow",
        _v22_phase2_ux_revision,
    ),
    Migration(
        "0009_v22_phase3_product_catalog_upc",
        "add commercial product catalog, validated identifiers, audit history, and nullable acquisition-line linkage",
        _v22_phase3_product_catalog_upc,
    ),
    Migration(
        "0010_v22_phase4_source_documents",
        "add private provider-neutral source-document metadata, integrity state, and audit history",
        _v22_phase4_source_documents,
    ),
    Migration(
        "0011_v22_phase5_receipt_intelligence",
        "add provider-neutral extraction jobs, normalized candidates, receipt lines, matches, allocations, and provenance",
        _v22_phase5_receipt_intelligence,
    ),
    Migration(
        "0012_v22_prephase_ux_safety_hotfix",
        "add recoverable acquisition recycle tombstones and removal-state metadata",
        _v22_prephase_ux_safety_hotfix,
    ),
    Migration(
        "0013_v22_phase6_downstream_intake_bridge",
        "add idempotent acquisition-line routing, batch projection, and sealed intake disposition",
        _v22_phase6_downstream_intake_bridge,
    ),
    Migration(
        "0014_v22_phase7_sam_recognition",
        "add provider-neutral SAM metadata, reference indexing, recognition, evidence, and review history",
        _v22_phase7_sam_recognition,
    ),
    Migration(
        "0015_v22_rc3_hf1_mixed_purchase_reconciliation",
        "add an explicit nullable noninventory partition for mixed acquisitions",
        _v22_rc3_hf1_mixed_purchase_reconciliation,
    ),
    Migration(
        "0016_v23_inventory_intelligence_phase1_receipt_semantics",
        "add non-authoritative receipt semantic evidence, confidence, and correction history",
        _v23_inventory_intelligence_phase1_receipt_semantics,
    ),
    Migration(
        "0017_v24_sam_phase1_family_printing",
        "separate SAM card-family authority from commercial-printing authority and evidence",
        _v24_sam_phase1_family_printing,
    ),
    Migration(
        "0018_v24_jarvis_economics_sam_phase2",
        "add JARVIS sale input completeness and append-only SAM printing evidence observations",
        _v24_jarvis_economics_sam_phase2,
    ),
    Migration(
        "0019_v24_sam_multi_evidence_operator_trial_v1a",
        "add immutable multi-evidence suggestions and append-only operator audit records",
        _v24_sam_multi_evidence_operator_trial_v1a,
    ),
)


def _create_ledger(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_id TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )


def apply_migrations(
    connection: sqlite3.Connection,
    migrations: Iterable[Migration] = DEFAULT_MIGRATIONS,
) -> tuple[str, ...]:
    """Apply pending migrations once, with each migration protected by a savepoint.

    A completion marker is written inside the same savepoint as the schema changes.
    If the callback fails, both its changes and marker are rolled back before the
    exception is surfaced.
    """

    _create_ledger(connection)
    migration_list = tuple(migrations)
    ids = [migration.migration_id for migration in migration_list]
    if len(set(ids)) != len(ids):
        raise ValueError("Migration IDs must be unique")
    for migration_id in ids:
        if not MIGRATION_ID_RE.fullmatch(migration_id):
            raise ValueError(f"Invalid migration ID: {migration_id!r}")

    already_applied = {
        row[0] for row in connection.execute("SELECT migration_id FROM schema_migrations")
    }
    applied_now: list[str] = []
    for index, migration in enumerate(migration_list):
        if migration.migration_id in already_applied:
            continue
        savepoint = f"dex_migration_{index}"
        connection.execute(f"SAVEPOINT {savepoint}")
        try:
            migration.apply(connection)
            connection.execute(
                """
                INSERT INTO schema_migrations (migration_id, description, applied_at)
                VALUES (?, ?, ?)
                """,
                (
                    migration.migration_id,
                    migration.description,
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )
            connection.execute(f"RELEASE SAVEPOINT {savepoint}")
        except Exception as exc:
            connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            connection.execute(f"RELEASE SAVEPOINT {savepoint}")
            raise MigrationError(
                f"Migration {migration.migration_id!r} failed and was rolled back"
            ) from exc
        applied_now.append(migration.migration_id)
    return tuple(applied_now)
