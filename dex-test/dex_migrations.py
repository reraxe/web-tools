"""Transactional, versioned SQLite migration support for Dex.

Migration callbacks must use ``connection.execute`` rather than ``executescript``;
SQLite's script helper can issue transaction boundaries that defeat savepoints.
"""

from __future__ import annotations

import re
import sqlite3
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


DEFAULT_MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        "0001_phase3_acquisition_facts",
        "add Phase 3 acquisition facts and receipt group references",
        _phase3_acquisition_facts,
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
