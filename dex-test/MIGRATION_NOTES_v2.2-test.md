# DEX v2.2-test Migration Notes

Checkpoint: Inbound 2.0 Phase 3 Product Catalog + UPC Intake

## Migration `0009_v22_phase3_product_catalog_upc`

Creates three empty additive tables:

- `catalog_products` for immutable local commercial-product identity and descriptive facts;
- `product_identifiers` for unique normalized text identifiers and their current product mapping;
- `product_identifier_events` for immutable mapping, scan, local-identification, catalog-application, and correction history.

Adds nullable `acquisition_lines.catalog_product_id` plus catalog search, identifier lookup, mapping-event, and acquisition-line linkage indexes. Product class and subtype are stored as flexible text so future commercial categories do not require schema replacement.

The migration does not infer or backfill any catalog product or identifier. Existing acquisition lines receive `catalog_product_id = NULL`. It does not inspect card/batch product codes, create batches or sealed units, assign cost or basis, or alter any Phase 3–7C economics fact.

The migration and its ledger marker run within the established migration savepoint. A forced conflicting catalog table rolls back the new tables, nullable column, indexes, and marker together. Re-running the migration is a no-op.

## Happy-Path Polish Schema Impact

The Happy-Path Polish adds **no database migration and no schema change**. It reuses the Phase 1/2 acquisition, line, and append-only event tables. New automatic-allocation and confirmation evidence is stored in the existing event JSON payload using calculation version `inbound-acquisition-v1`.

Existing `0006`, `0007`, and `0008` migration behavior is unchanged. A database already migrated through `0008_v22_phase2_ux_revision` receives only the `0009` ledger row and empty catalog infrastructure when this checkpoint starts.

## Migration `0008_v22_phase2_ux_revision`

Adds `acquisitions.payment_method` with an empty draft-safe default and constrained human choices: Credit / Debit Card, Cash, PayPal, Store Credit, or Other.

For resumability, existing draft progress is mapped without changing acquisition facts:

- `SOURCE` and `ECONOMICS` resume at `PRODUCTS` (Product & Purchase Details).
- `RECONCILIATION` resumes at `REVIEW`.
- `ACQUIRE`, `PRODUCTS`, and `REVIEW` remain unchanged.

The migration does not confirm a payment method, acquisition cost, line allocation, reconciliation, or lifecycle state. It does not create batches, sealed units, cards, receipt documents, UPC mappings, or SAM data.

## Migration `0007_v22_phase2_manual_acquisition_wizard`

Adds one non-null `acquisitions.wizard_step` column with a safe `ACQUIRE` default and an allowed-value constraint covering the six Phase 2 screens. The field stores resumable UI progress only; it is not an economics fact and cannot confirm an acquisition.

Existing Phase 1 drafts resume at the first screen. Existing `READY_FOR_INTAKE` acquisitions remain confirmed and open directly on Review. The migration does not touch existing batches, cards, sealed units, sales, basis, corrections, dispositions, returns, or portfolio facts.

## Migration `0006_v22_phase1_inbound_acquisitions`

Creates empty additive tables:

- `acquisitions`
- `acquisition_lines`
- `acquisition_events`

Adds nullable `batches.acquisition_line_id` and indexes for acquisition state/listing, line order, event history, and batch linkage.

The migration does not:

- create or infer historical acquisitions;
- link an existing batch;
- alter existing acquisition cost, basis, economics status, receipt group, card, rip, sealed unit, sale, correction, return, or portfolio fact;
- add UPC/catalog or receipt/document data;
- create authoritative allocations or downstream inventory.

Every Phase 7C batch receives `acquisition_line_id = NULL` by default. The established Phase 3–7C model remains the only economics model.

## Transaction and Compatibility Results

- The migration and completion marker execute within the existing migration savepoint.
- A forced conflicting `acquisition_lines` table rolls back the earlier `acquisitions` creation, nullable batch column, indexes, and ledger marker.
- A disposable Phase 7C-style fixture preserves existing batch/card values exactly.
- Re-running migrations is a no-op.
- All 117 Python regression tests pass; JavaScript syntax and direct wizard/catalog plus prior frontend regressions also pass.
- A Phase 1-style draft fixture receives `wizard_step = 'ACQUIRE'`; its identity, state, and facts remain unchanged.

## Deployment Assumption

Production remains operator-controlled. Before an approved deployment, run the v2.2 image against a timestamped disposable copy and confirm migrations `0006`–`0008` retain their documented behavior and `0009` adds only empty catalog infrastructure plus nullable acquisition-line linkage.

## Rollback

If startup fails before any v2.2 acquisition is created, stop only the failed runtime and restore the Phase 7C application checkpoint with its matching pre-migration storage copy. Do not drop tables or remove ledger rows manually.

After v2.2 acquisition or catalog facts exist, always restore the matching pre-upgrade storage copy when rolling back to software that predates those facts. Older code cannot expose or preserve catalog mappings even though the additive tables are syntactically harmless. Do not manually drop tables or delete migration-ledger rows.
