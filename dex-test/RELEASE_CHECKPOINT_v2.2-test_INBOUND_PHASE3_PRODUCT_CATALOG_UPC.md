# DEX v2.2-test — Inbound 2.0 Phase 3 Checkpoint

Checkpoint: Product Catalog + UPC Intake  
Status: development complete; receipt/document work is not authorized  
Prior restore point: preserved Inbound 2.0 Phase 2 Happy-Path Polish checkpoint

## Delivered Scope

- Reusable local commercial-product catalog with immutable IDs, provenance, active state, verification timestamps, and extensible text product classes/subtypes.
- Text identifiers for UPC-A, EAN-13, GTIN-14, and internal codes. Standard codes are check-digit validated, canonicalized for lookup, and retain the raw scan plus leading zeroes.
- Prominent keyboard-emulating scanner input for Pack Product and Sealed Product acquisition lines; manual entry and catalog search remain first-class.
- Automatic visible product recognition, repeat-scan quantity aggregation, separate lines for different products, request de-duplication, and optimistic revision checks.
- Unknown-product Search, Identify manually, Cancel, acquisition-local identification, and optional operator-confirmed learned mappings.
- Collision blocking and explicit reason/note correction with append-only mapping history. Corrections affect future lookup without rewriting earlier acquisition or scan history.
- Resume-safe catalog linkage. UPC supplies product facts only and creates no batch, sealed unit, card, basis, rip, sale, receipt fact, SAM match, or portfolio result.

## Schema and Migration

Migration `0009_v22_phase3_product_catalog_upc` creates:

- `catalog_products`
- `product_identifiers`
- `product_identifier_events`
- nullable `acquisition_lines.catalog_product_id`
- supporting catalog, identifier, event-history, and acquisition-line indexes

The migration is additive, runs with its completion marker inside the existing savepoint, guesses no historical mapping, and leaves every existing acquisition line unlinked. Forced-failure coverage confirms the schema changes and ledger marker roll back together.

## APIs

Read-only:

- `GET /api/catalog/contract`
- `GET /api/catalog/products`
- `GET /api/catalog/products/{id}`
- `GET /api/catalog/identifiers/lookup`
- `GET /api/catalog/identifiers/{id}/history`

Mutating, request-ID protected where applicable:

- `POST /api/catalog/products`
- `POST /api/catalog/products/{id}/identifiers`
- `POST /api/catalog/identifiers/{id}/correct`
- `POST /api/acquisitions/{id}/product-scan`
- `POST /api/acquisitions/{id}/identify-product`
- `POST /api/acquisition-lines/{id}/catalog-product`

## Verification

- Python: 117 tests passed.
- Frontend: JavaScript syntax plus Phase 2 wizard, Phase 3 catalog, viewport, sealed Sales, post-sale Sales, and Operational Economics direct regressions passed.
- Migration: additive legacy compatibility, no guessed backfill, repeat no-op, and forced-failure rollback passed.
- Performance: indexed search across 1,000 catalog products completed in under 1 ms in the automated fixture.
- Disposable runtime: `/api/health` returned HTTP 200 and `v2.2-test`.
- Browser QA: known UPC quantity reached 3 on one line; a different EAN created a second line; an unknown valid UPC was not guessed; operator-confirmed Remember Mapping resolved automatically in a second acquisition; refresh/exit/resume preserved identity and quantity.
- Boundary check after browser QA: 0 batches, 0 sealed units, and 0 cards.

## Known Limits

- The catalog is local to this DEX database; no manufacturer or external catalog synchronization exists.
- Scanner support assumes normal keyboard-emulation and a trailing Enter. No scanner-specific driver/protocol is added.
- Product search is text-based and the mapping-correction dialog currently loads a bounded result list; large catalogs may require a search-within-dialog improvement later.
- Mapping corrections change future identifier lookup only. Existing acquisition lines intentionally retain the product identity captured at the time.
- Receipt/document storage, extraction/OCR, receipt-derived product/cost matching, SAM, global Attention Center, downstream batch projection, and sealed-unit creation remain out of scope.

## Rollback

Do not manually drop catalog tables or delete migration-ledger rows. Stop the v2.2 runtime and restore the preserved Phase 2 application checkpoint together with the matching pre-Phase-3 storage copy. If Phase 3 catalog/acquisition facts must be retained, export/reconcile them before rollback because Phase 2 cannot expose the new mapping records.

## Git Upload Manifest

Upload the entire packaged checkpoint. The Phase 3 delta includes:

- `app.py`
- `dex_catalog.py`
- `dex_inbound.py`
- `dex_migrations.py`
- `Dockerfile`
- `static/app.js`
- `static/index.html`
- `static/styles.css`
- `scripts/seed_v22_phase3_catalog_demo.py`
- `tests/test_v22_phase3_catalog.py`
- `tests/test_v22_phase3_catalog_ui.cjs`
- migration/cache compatibility updates in the existing Phase 1–7C and v2.2 tests
- `README.md`, `DEX_OPERATING_MODEL.md`, `PATCH_PLAN_INBOUND_2.md`, `PATCH_NOTES_v2.2-test.md`, `MIGRATION_NOTES_v2.2-test.md`, `WEEKLY_ROADMAP.md`, and this checkpoint file

Do not upload databases, storage folders, inventory/scanner/source images, credentials, secrets, logs, caches, `__pycache__`, `.pyc`, disposable QA data, generated labels/exports, or machine-specific files.
