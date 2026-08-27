# Migration Notes — DEX v2.5-live

## Migration

`0020_v25_tcgplayer_inventory_bootstrap_v1`

The migration is additive. It introduces TCGplayer snapshot/import, quantity-pool, inventory-event, reconciliation, and export audit structures required by v2.5. Existing migrations `0001` through `0019` remain unchanged.

## LIVE upgrade behavior

- DEX starts against the existing persistent LIVE `/data` storage.
- The migration runner detects migrations `0001–0019` and applies `0020` once.
- A failed migration must not be marked complete or leave a partially committed migration.
- Existing acquisitions, batches, cards, sales, economics, receipt, SAM, and WOLFF facts are preserved.
- No opening inventory is created merely by startup or migration.
- A TCGplayer import requires preview, review where applicable, and explicit operator confirmation.

## Verification

Before cutover, test migration against a disposable v2.4-live-like database. After cutover, verify migration 0020 is present, SQLite integrity is `ok`, foreign-key violations are zero, and existing inventory counts remain unchanged until an operator intentionally applies an import or records an event.

## Rollback boundary

Application rollback may return to the prior v2.4-live image while retaining the same storage. Do not delete the 0020 ledger row or manually remove its tables. A data restore is a separate operator-authorized action and is not the normal startup-failure response.

