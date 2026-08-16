# DEX v2.2-test Migration Notes

## `0014_v22_phase7_sam_recognition`

This additive migration introduces the Phase 7 recognition ledger without guessing historical identities or touching economics:

- nullable `cards.sam_recognition_state` and `cards.sam_recognition_job_id` compatibility columns;
- `sam_metadata_cache` and `sam_metadata_refresh_runs` for normalized provider facts, state, version, timestamps, and refresh provenance;
- `sam_reference_index_runs` and `sam_reference_records` for externally stored local references, SHA-256/perceptual features, duplicate relationships, provenance, and incremental-index state;
- `sam_recognition_jobs` and `sam_recognition_candidates` for immutable scan context, evidence, confidence, exception codes, ranked suggestions, engine/rules/index versions, and request de-duplication;
- `sam_recognition_decisions` for append-only operator confirmation, correction, and unidentified decisions.

No image blob is stored in SQLite. No historical card receives a recognition job, candidate, state, or identity. Existing authoritative card identity fields and all Phase 3–7C economics data remain unchanged.

The migration runs inside the existing savepoint/transaction mechanism and records its ledger marker only after every required table, column, and index succeeds. The forced-failure regression verifies that the marker and partial schema roll back together. Re-running the migration is a no-op.

Rollback requires the matching pre-`0014` disposable/production-approved database copy and the preserved Phase 6 application checkpoint. Once Phase 7 recognition evidence exists, do not drop tables, null card links, or delete migration markers by hand; doing so would discard audit provenance. Production migration remains an explicit operator-approved release action and must first be rehearsed on a disposable copied legacy fixture.

Checkpoint: Inbound 2.0 Phase 7 SAM Recognition + Human Review

## `0013_v22_phase6_downstream_intake_bridge`

This additive migration creates `acquisition_intake_operations`, `acquisition_line_projections`, and `acquisition_intake_route_events`. It adds `sealed_units.intake_disposition` with a legacy-safe `LEGACY_AVAILABLE` default, a one-batch-per-acquisition-line uniqueness guard, and routing lookup indexes.

No historical acquisition or batch is linked by inference. No historical batch, card, rip, sale, cost, basis, sealed status, receipt, or catalog fact is changed. Existing sealed units receive only the compatibility disposition that preserves their prior availability. The new operation/projection/route tables start empty, and startup alone creates no batch, card, sealed unit, rip, or route.

The schema work and `0013` ledger marker share the established savepoint. A forced conflict rolls back the sealed-unit column, new tables, indexes, and marker together. Re-running is a no-op. Runtime routing is separately transactional under `BEGIN IMMEDIATE`; a failed projection does not leave a partial batch, sealed-unit claim, route event, or lifecycle transition.

Rollback before any Phase 6 route requires the matching pre-`0013` database copy and the prior application checkpoint. After routing exists, restore the matching pre-route database copy if reverting to older code; do not drop the routing tables, unlink batches, reset sealed dispositions, or delete migration-ledger rows by hand.

Checkpoint: Inbound 2.0 Phase 6 Downstream Intake Bridge

## `0012_v22_prephase_ux_safety_hotfix`

- Adds nullable `recycled_at` and `pre_recycle_state` fields plus non-null reason/note fields to `acquisitions`.
- Adds an index for acquisition Recycle Bin listing.
- Performs no backfill and creates no acquisition, line, document, receipt, catalog, batch, card, sealed-unit, sale, or economics fact.
- Draft recycle and restore reuse append-only `acquisition_events`; records are tombstoned, never hard-deleted. Confirmed cancellation preserves authoritative financial flags and all dependent records.
- Existing databases apply the migration transactionally through the normal ledger. On failure, the migration marker and schema changes roll back together where SQLite permits.
- Rollback requires the matching pre-migration database copy plus the previous application checkpoint. Do not point older code at a database after `0012` and assume the new recycle metadata will be understood.

Checkpoint: Inbound 2.0 Phase 5 Receipt Intelligence + Auto-Populated Economics

## Migration `0011_v22_phase5_receipt_intelligence`

This additive migration creates empty receipt-intelligence tables and indexes for extraction jobs, normalized candidate facts, receipt lines and classifications, product-line match proposals, versioned allocation proposals, acquisition-field provenance, and append-only receipt events.

It performs no historical receipt inference or backfill and changes no existing acquisition, batch, card, sealed-unit, rip, sale, catalog, correction, or portfolio fact. Startup adds only the empty structures and the `0011` migration-ledger row. Receipt artifacts remain outside SQLite; raw OCR/text is not persisted.

The migration and ledger marker run in the established savepoint. A forced conflict rolls back all Phase 5 schema work and leaves no `0011` marker. Re-running is a no-op. Rollback of application code requires restoring the matching pre-Phase-5 database copy; older code must not be pointed at a database after an unapproved partial deployment.

Operational provider status is separate from migration success. The included local provider supports text-layer PDFs. JPG/PNG remain attachable Phase 4 evidence but require a future reviewed OCR provider for extraction. No external provider, credential, billing integration, or document transmission is configured.

## Migration `0010_v22_phase4_source_documents`

Creates two empty additive metadata tables: `acquisition_documents` and `acquisition_document_events`. The first records immutable document identity, acquisition linkage, provider/resource metadata, safe/original filenames, declared/detected MIME, byte size, SHA-256, role/capture method, storage/integrity state, retry/replacement linkage, and tombstone facts. The second records append-only attachment, failure, duplicate suppression, retry, integrity verification/failure, and tombstone events with unique request IDs.

Raw JPG/PNG/PDF bytes are never stored in SQLite. Existing acquisitions are not backfilled, and existing batches, cards, sealed units, economics facts, sale history, catalog mappings, and acquisition state remain unchanged. Startup creates only empty metadata/history tables, indexes, and the `0010` ledger row.

The migration and completion marker share the established savepoint. A forced table conflict rolls back all Phase 4 schema work and leaves no `0010` marker. Re-running is a no-op. Local artifacts default to the private `source-documents` directory beneath `DEX_DATA_DIR`; deployment must persist and back up that directory together with its matching database metadata.

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
- All 126 Python regression tests pass; JavaScript syntax and nine direct frontend regressions pass.
- A Phase 1-style draft fixture receives `wizard_step = 'ACQUIRE'`; its identity, state, and facts remain unchanged.

## Deployment Assumption

Production remains operator-controlled. Before an approved deployment, run the v2.2 image against a timestamped disposable copy and confirm migrations `0006`–`0009` retain their documented behavior and `0010` adds only empty document metadata/history infrastructure and indexes. Confirm the configured private document directory is persistent, writable only by the DEX runtime/operator, backed up with the database, and never served directly by a public web server.

## Rollback

If startup fails before any v2.2 acquisition is created, stop only the failed runtime and restore the Phase 7C application checkpoint with its matching pre-migration storage copy. Do not drop tables or remove ledger rows manually.

After v2.2 acquisition, catalog, or document facts exist, restore the matching pre-upgrade database **and** private document-storage copy when rolling back to software that predates those facts. Older code cannot expose or preserve the new metadata and artifact relationships. Do not manually drop tables, delete artifacts, or remove migration-ledger rows.
