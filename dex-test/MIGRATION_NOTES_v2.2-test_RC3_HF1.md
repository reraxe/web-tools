# DEX v2.2-test RC3 Hotfix 1 Migration Notes

Migration: `0015_v22_rc3_hf1_mixed_purchase_reconciliation`

## Additive schema

`acquisitions` receives nullable `excluded_noninventory_cents`, `noninventory_treatment_code`, and `noninventory_notes` fields. The amount is integer cents and nonnegative when present. Treatment is bounded to Business Noninventory, Personal/Nonbusiness, Mixed Noninventory, or Other.

`NULL` remains Unknown/unconfirmed and is never displayed or calculated as authoritative `$0.00`. Migration 0015 does not inspect reasons, receipt lines, allocations, or purchase gaps and performs no backfill.

## Runtime behavior

Startup applies pending migrations transactionally through the existing savepoint/ledger mechanism. The only automatic database change for an RC3-era database is the three nullable columns and the `0015` ledger row. No acquisition, batch, card, sealed unit, allocation, or economic fact is created.

## Compatibility verification

- Fresh disposable database: migrations 0001–0015 ordered and `PRAGMA integrity_check = ok`.
- Disposable RC3-era fixture: 0015 applied once; existing facts unchanged.
- Existing confirmed acquisition fixture: state, final USD, and confirmation flags unchanged; new fields `NULL`.
- Existing incomplete Mom and Pop-style fixture: identity, merchant, final USD, and incomplete state unchanged; new fields `NULL` and resumable.
- Re-run: no-op.

## Rollback boundary

RC3-r4 code does not understand the three new facts. If Hotfix 1 startup or operation fails, do not delete migration rows or columns. Restore the RC3-r4 image and the matching pre-0015 storage backup. If new mixed-purchase facts were confirmed after migration, preserve the Hotfix 1 database for audit and restore only a verified matching backup for rollback.
