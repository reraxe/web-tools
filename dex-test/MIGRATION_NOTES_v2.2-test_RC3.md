# RC3 Migration Notes

RC3 adds no database migration. It carries the already accepted `0001` through `0014` migration chain in `dex_migrations.py`.

On a new database, DEX creates the migration ledger and applies all fourteen migrations in order. On an existing compatible database, only unapplied migrations run. A migration must not be marked complete if its transaction fails.

Before any operator trial using real data:

1. Stop no production service merely to inspect this checkpoint.
2. Make a timestamped, verified copy of the matching database and storage.
3. Test RC3 against disposable or copied storage first.
4. Confirm `/api/health`, runtime version, migration ledger, inventory counts, Inbound, Sales, and Operational Economics before cutover.

Rollback must restore a matching application checkpoint and matching database/storage backup. Do not manually remove ledger rows, columns, tables, or authoritative records.

