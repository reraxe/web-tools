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


DEFAULT_MIGRATIONS: tuple[Migration, ...] = ()


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
