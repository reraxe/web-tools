# Dex v2.1-test Migration Notes

Checkpoint: Phase 7C complete; no Phase 7C migration

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

## Phase 4 Migration

Migration `0002_phase4_rip_sessions` adds:

- `rip_sessions`: draft/active/finalized opening sessions, units opened, allocation mode, aggregate bulk facts, immutable final reconciliation snapshot, stable acquired-unit sequence, and timestamps.
- `rip_economic_events`: append-only finalization/correction events with unique event and request IDs, effective date, recorded timestamp, standardized reason, notes, and immutable payload snapshots.
- `rip_basis_events`: append-only card or aggregate-bulk basis deltas linked to an economic event.
- nullable `cards.rip_session_id` and `processed_scans.rip_session_id` provenance links.
- indexes for batch sessions, active sessions, card/session lookup, and event lookup.

The migration assigns no existing card to a rip, creates no finalized basis, changes no inventory or sale fact, and performs no sealed-unit or sealed-sale migration. Existing legacy and Phase 3 batches retain their prior economics status. The active-rip setting is written only after an operator explicitly starts intake.

Unscanned bulk is represented as one aggregate reserve per rip plus append-only bulk basis events, not fake card SKUs. Known physical quantity is preserved when supplied; unknown quantity requires a manual reserve and remains valuation-incomplete.

## Phase 5 Migration

Migration `0003_phase5_sealed_inventory` adds:

- `sealed_units`: one stable internal record and sequence per authoritative acquired unit, exact deterministic basis cents, state, rip link, and current sealed-order link.
- `sealed_sale_items`: exact sealed units, batch provenance, merchandise-line cents, and sold-basis snapshots retained beneath a sealed order.
- `sealed_unit_events`: immutable event/request IDs, state transition, rip/order reference, reason, notes, effective date, recorded timestamp, and payload.
- `sale_orders.order_type`, duplicate-submission request ID, exact-cent merchandise/shipping/fee/postage/tax facts, and cancellation/tombstone fields.
- indexes for unit availability, rip/order lookup, sale items, event history, and non-empty order request IDs.

Existing sale orders are explicitly classified as `CARD`; their existing dollar facts are preserved and mirrored into the new exact-cent compatibility columns. No historical card sale becomes a sealed sale.

For a batch already carrying trustworthy `SEALED_RIP` facts, the migration creates `units_acquired` records and divides final USD paid deterministically by stable sequence. Example: `$10.00` over three units is always `$3.34`, `$3.33`, `$3.33`. Existing Phase 4 rip sessions claim the lowest sequences in stable rip-session order, preserving the prior partial-rip result. Legacy/unknown-cost batches receive no sealed records or permanent basis.

## Phase 6 Migration Impact

Phase 6 adds **no migration, table, column, index, backfill, or stored calculated total**. The migration ledger remains at the three approved entries through `0003_phase5_sealed_inventory`. `dex_batch_economics.py` reads existing Phase 1–5 facts and recalculates batch/group/export values on request.

Loading a Phase 6 economics report may update no card, batch, rip, sealed unit, sale, activity, or migration record. Automated API and service tests compare source rows and activity counts before and after report/export calls.

## Phase 7A Migration

Migration `0004_phase7a_corrections_dispositions` adds:

- `economic_events`: immutable event/request IDs, batch, event type, standardized reason, effective date, recorded timestamp, required notes, optional reversed-event link, and immutable payload.
- `economic_event_entries`: signed acquisition-cost, basis, or operational-loss deltas against a typed batch/card/rip-bulk/sealed-unit target.
- `economic_tombstones`: durable card or sealed-unit identity, reason, batch, source snapshot, and originating event.
- indexes for batch/event history, typed target lookup, tombstone lookup, and a unique one-reversal-per-original-event constraint.

The migration creates empty infrastructure only. It does **not** copy legacy cost, assign card basis, convert a batch, dispose inventory, alter sealed quantities, rewrite a sale, or create a correction event. Runtime corrections derive current values by adding immutable entries to preserved Phase 3–5 source facts.

Each migration callback and its completion marker remain within one SQLite savepoint. A forced conflicting-table test confirms a failed Phase 7A migration leaves no marker or partial entry/tombstone tables.

## Phase 7B Migration

Migration `0005_phase7b_post_sale_events` adds:

- `post_sale_events`: immutable event/request IDs, order link, distinct event type, standardized reason, effective date, recorded timestamp, notes, payload, and optional reversed-event link.
- `post_sale_event_entries`: signed merchandise, shipping, marketplace-fee, postage, or other-net deltas. Current order economics are derived and never stored as dashboard totals.
- `post_sale_return_items`: exact original sale-item ID, exact physical card/sealed identity, stable identifier, confirmed outcome, preserved basis, prior-state snapshot, and restoration timestamp.
- indexes for order history, event entries, returned identities, and one linked reversal per original event.

The migration transactionally rebuilds `sale_items` with the same columns and preserved primary keys, replacing legacy `UNIQUE(card_id)` with `UNIQUE(order_id, card_id)`. This is required so a confirmed returned physical card can be sold in a later order while every original sale item remains visible. Current inventory state plus transactional conditional updates prevent one card from being actively sold twice.

No existing order, sale item, sealed item, card status, sealed-unit status, financial amount, or basis is changed. No historical event is inferred or backfilled. The new tables begin empty. A migration fixture confirms legacy sale-item IDs and values survive exactly and the migration runs once.

## Phase 7C Migration Impact

Phase 7C adds **no migration, table, column, index, constraint, backfill, or stored dashboard total**. The migration ledger remains at the five approved entries through `0005_phase7b_post_sale_events`.

`dex_portfolio_economics.py` opens the database read-only and derives portfolio results from Phase 3–7B source facts. Loading the Operational Economics page or CSV must not change batches, cards, rips, sealed units, orders, correction events, post-sale events, activity, or migration rows. Automated API/export tests compare database files and logical row counts before and after reads.

## Startup and Failure Behavior

- The migration runs once and records its ID only after success.
- A failed column or index change rolls back with no completion marker.
- A restart safely retries an unrecorded failed migration.
- Missing acquisition cost remains SQL `NULL` and is shown as Unknown/Incomplete.
- Phase 4 migration creates empty rip infrastructure only. Phase 5 then creates sealed units only for trustworthy sealed facts and never assigns permanent basis to legacy cards.
- Phase 7A migration creates empty correction infrastructure only. The first data mutation occurs only after an operator explicitly submits a correction/disposition.
- Phase 7B migration creates empty post-sale infrastructure only. Original financial facts remain immutable; effective facts change only after an operator submits a post-sale event.

## Compatibility Verification

Automated tests migrate disposable copies of a v2.0-style database and confirm:

- the source fixture is never modified;
- the migration runs exactly once;
- legacy `total_cost` is preserved without permanent-basis backfill;
- legacy rows receive only the intended defaults;
- a forced index conflict rolls back every Phase 3 column and the ledger marker;
- a forced mid-Phase-4 table conflict rolls back newly created rip schema and leaves the Phase 4 marker unrecorded;
- a forced Phase 5 table conflict rolls back sale-order columns, new tables, and the Phase 5 marker together;
- a forced Phase 7A table conflict rolls back its new tables and marker together;
- historical `sale_items` primary keys, order links, card links, and prices survive the Phase 7B table rebuild exactly;
- the Phase 7B uniqueness change permits the same returned card in a later order but still rejects duplicate card lines inside one order;
- historical card orders retain their facts and become `order_type = CARD`;
- `$10.00 / 3` produces stable `$3.34 / $3.33 / $3.33` unit basis and exact reconciliation;
- existing Phase 4 rips claim exact lowest sequences without exceeding acquired quantity;
- concurrent sale attempts against one remaining unit yield one sale and one rejection;
- Phase 4 runs once against current and reduced legacy fixtures without modifying source copies;
- finalized source acquisition, rip-basis, sealed-unit, and sale rows remain unchanged while corrections and linked inverse events reconcile through signed entries;
- all earlier application and migration tests still pass.

## Operator Safety

1. Preserve the Phase 7A checkpoint and make a timestamped copy of persistent storage before any approved upgrade.
2. First run this release against a disposable copy of the legacy database.
3. Confirm `/api/health`, inventory counts, inbound batches, Recycle Bin, Phase 2 estimates, Phase 3 acquisition facts, Phase 4 rips, sealed-unit counts/basis, existing card and sealed sales, Phase 6 Batch Economics, and Phase 7A correction/reversal history.
4. Compare the copied database before and after startup. Upgrading from Phase 7A to Phase 7B should add migration `0005`, the three empty post-sale tables/indexes, and the compatible `sale_items` constraint rebuild. Existing row IDs and values must compare exactly; no refund, return, financial adjustment, or inventory-state change occurs until an operator submits a Phase 7B event.
5. Never manually insert ledger rows or experimentally migrate production data.

The older `scripts/preprod_phase2_gate.sh` is specifically a Phase 2 gate and expects ledger-only mutation. It is not a Phase 3/4/5/6/7A/7B release validator and will intentionally fail when it sees the approved additive schema.

## Rollback

If Phase 7B startup or validation fails, stop only the failed/new runtime and restore the preserved Phase 7A application **with its matching timestamped pre-Phase-7B storage copy**. Phase 7A code does not understand the new post-sale ledger or repeat-sale constraint semantically, so application-only rollback is not the approved database rollback. Do not delete, rewrite, or downgrade a migrated database in place. No post-sale event data should be copied backwards manually.
