# Migration Notes — v2.5-test TCGplayer Inventory Bootstrap V1

Migration: `0020_v25_tcgplayer_inventory_bootstrap_v1`

## Additive schema

- `tcgplayer_import_batches`: immutable source identity, export time, contract version, aggregate preview counts, and explicit preview/applied state.
- `tcgplayer_snapshot_rows`: immutable normalized snapshot rows plus preserved source JSON.
- `inventory_pools`: one structured product/condition pool per TCGplayer commercial identifier.
- `inventory_quantity_events`: append-only physical quantity deltas, idempotency keys, prior/resulting quantity, and linked reversals.
- `inventory_physical_reconciliation_events`: audited SAM decisions distinguishing existing bootstrapped copies from new intake.
- `tcgplayer_channel_observations`: immutable external quantity/price observations.
- `tcgplayer_reconciliation_items`: open/resolved/superseded channel differences.
- `tcgplayer_inventory_audit_events`: immutable preview, apply, and export audit records.

Indexes support latest-snapshot selection, pool search, event history, and open reconciliation. Triggers prevent updates/deletes of source snapshot rows, quantity events, physical-reconciliation events, channel observations, and audit events.

## Compatibility and migration behavior

The migration is transactional through the existing `schema_migrations` service. It does not read, rewrite, backfill, or reinterpret batches, serialized cards, acquisitions, sealed units, SAM facts, sales, WOLFF economics, or receipt intelligence. Existing v2.4 facts remain byte/logically unchanged. Startup creates only schema/ledger infrastructure; it creates no pools, quantities, cards, sales, or marketplace observations.

Rollback uses the preserved v2.4-test baseline and a pre-migration database copy. Application rollback alone must not be pointed at a database containing 0020 unless the older application has been verified to tolerate unknown additive tables. Do not delete 0020 tables from production as an ad-hoc rollback.
