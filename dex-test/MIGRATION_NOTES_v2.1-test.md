# Dex v2.1-test Migration Notes

Checkpoint: Phase 3 complete

## Migration Runner

`dex_migrations.py` owns a versioned `schema_migrations` ledger. Each registered migration runs inside a SQLite savepoint, so its schema changes and completion marker succeed together or roll back together. Startup still retains the older compatibility checks in `app.py`; unrelated schema code was not reorganized.

## Phase 3 Migration

Migration `0001_phase3_acquisition_facts` adds these nullable/defaulted columns to `batches`:

- `economics_mode`, `economics_status`
- `product_name`, `product_code`
- `receipt_group_reference`, `invoice_reference`
- `reporting_currency`
- `original_currency`, `original_foreign_amount_minor`
- `final_usd_paid_cents`, `units_acquired`
- `purchase_subtotal_cents`, `acquisition_tax_cents`, `inbound_shipping_cents`, `acquisition_fees_cents`, `acquisition_discount_cents`
- `cost_reconciliation_acknowledged`, `acquisition_updated_at`

It also adds index `idx_batches_receipt_group`. Existing rows become `economics_mode = LEGACY`, `economics_status = ESTIMATED`, and `reporting_currency = USD` through column defaults. The migration deliberately does **not** copy legacy `total_cost` into `final_usd_paid_cents`; old cost remains estimate-only until the operator explicitly enters authoritative acquisition facts.

For new or edited Phase 3 records, final USD paid is stored in integer cents and mirrored deterministically into legacy `total_cost` for compatibility. Optional original-currency fields are reference-only. DEX performs no currency conversion or FX accounting.

## Startup and Failure Behavior

- The migration runs once and records its ID only after success.
- A failed column or index change rolls back with no completion marker.
- A restart safely retries an unrecorded failed migration.
- Missing acquisition cost remains SQL `NULL` and is shown as Unknown/Incomplete.
- No Phase 3 migration creates rip sessions, card basis, sealed units, sales, or finalization records.

## Compatibility Verification

Automated tests migrate disposable copies of a v2.0-style database and confirm:

- the source fixture is never modified;
- the migration runs exactly once;
- legacy `total_cost` is preserved without permanent-basis backfill;
- legacy rows receive only the intended defaults;
- a forced index conflict rolls back every Phase 3 column and the ledger marker;
- all earlier application and migration tests still pass.

## Operator Safety

1. Preserve the Phase 2 checkpoint and make a timestamped copy of persistent storage before any approved upgrade.
2. First run this release against a disposable copy of the legacy database.
3. Confirm `/api/health`, inventory counts, inbound batches, Recycle Bin, Phase 2 estimates, and Phase 3 acquisition facts.
4. Compare the copied database before and after startup. Expected Phase 3 changes are the migration ledger entry, the listed `batches` columns, and `idx_batches_receipt_group`; inventory, card, and sale facts must not change.
5. Never manually insert ledger rows or experimentally migrate production data.

The older `scripts/preprod_phase2_gate.sh` is specifically a Phase 2 gate and expects ledger-only mutation. It is not a Phase 3 migration validator and will intentionally fail when it sees the approved Phase 3 schema additions.

## Rollback

If startup or validation fails, stop only the new test instance and return to the preserved Phase 2 application plus its pre-upgrade storage copy. Do not delete, rewrite, or downgrade the migrated database. The Phase 3 changes are additive, but rollback should use the captured database copy so application and schema remain a known-good pair.
