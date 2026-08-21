# Migration Notes — DEX v2.2-test RC3 HF3 Zero-Entry

No schema migration is added.

- Migration ledger remains 0001 through 0015.
- `dex_migrations.py` remains identical to HF2.
- No acquisition, receipt, inventory, card, sealed-unit, sale, or economic fact is backfilled or rewritten.
- Startup performs only the existing migration-ledger checks and does not create business facts.

Application-only rollback to HF2 is supported. Preserve database/storage; do not delete or edit migration records.
