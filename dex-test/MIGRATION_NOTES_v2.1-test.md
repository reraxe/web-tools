# Dex v2.1-test Migration Notes

Checkpoint: Phase 2 complete

## Migration Scope

Phase 1 introduced `dex_migrations.py`, a versioned SQLite migration runner with a `schema_migrations` ledger. Each registered migration runs inside a savepoint. Its schema/data changes and completion marker succeed together or roll back together.

There are no registered acquisition-economics migrations through Phase 2. `DEFAULT_MIGRATIONS` is empty. Phase 2 adds no columns, tables, indexes, permanent card basis, or legacy conversion records.

On startup, the migration runner may create the internal `schema_migrations` table. Existing legacy startup schema checks in `app.py` remain in place and have not been reorganized.

## Safety Rules

- Test experimental migrations only against disposable copies or generated legacy fixtures.
- Never use a production/server database or irreplaceable inventory database for migration development.
- Back up the complete persistent storage before any future deployment that registers a real migration.
- A failed migration must not leave its changes or completion marker behind.
- Do not manually insert migration-ledger rows.

## Phase 2 Read-only Guarantee

The legacy economics endpoint opens a separate SQLite connection in URI `mode=ro` and enables `PRAGMA query_only=ON`. Loading an estimate does not run conversion, assign basis, repair legacy rows, or write allocation decisions.

## Rollback Impact

Rolling application files back to the preserved v2.0-test baseline does not require an economics-schema downgrade because Phase 2 creates no economics schema. The internal `schema_migrations` table is harmless to older application code and should not be manually deleted from real data.
