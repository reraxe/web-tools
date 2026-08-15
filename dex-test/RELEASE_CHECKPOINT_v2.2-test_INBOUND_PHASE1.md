# DEX v2.2-test Inbound 2.0 Phase 1 Git-ready Checkpoint

Scope: backend-only Inbound 2.0 acquisition foundation. The immutable `DEX_v2.1-test_Phase7C_GitHub_Checkpoint` remains the known-good restore point. Phase 2, production deployment, and server-side actions are not authorized.

## Runtime Behavior

- Runtime version is `v2.2-test`.
- Existing economics calculation version remains `acquisition-rip-v3` because no Phase 3–7C formula changed.
- The existing New Inbound Batch UI remains active and unchanged except version/cache metadata.
- New acquisitions start as `ACQUISITION_INCOMPLETE` and receive an immutable UUID/code immediately.
- Draft autosave cannot set authoritative confirmation, reconciliation confirmation, state, reporting currency, or immutable identity.
- All mutations require unique request IDs; updates use optimistic acquisition revisions.
- Phase 1 creates no processing batches, sealed units, basis, rips, sales, UPC mappings, documents, extraction facts, SAM facts, or portfolio totals.

## Migration and Schema

Migration `0006_v22_phase1_inbound_acquisitions` adds:

1. `acquisitions`
2. `acquisition_lines`
3. `acquisition_events`
4. nullable `batches.acquisition_line_id`
5. state, line-order, event-history, and linkage indexes

No historical rows are inferred or backfilled. Existing batch linkage remains `NULL`.

## State Rules

- `ACQUISITION_INCOMPLETE` is the only creation state.
- Draft facts and lines may be autosaved while incomplete or reconciliation-required.
- Autosave returns the acquisition to incomplete and invalidates prior confirmations.
- `RECONCILIATION_REQUIRED` requires at least one active line.
- `READY_FOR_INTAKE` requires explicit financial and reconciliation confirmations, final USD, valid product lines, individually confirmed allocation methods/costs, and an exact `$0.00` line-cost difference.
- Intake-in-progress and complete are reserved for later routing phases.
- Cancellation is allowed only before readiness, requires a reason, and remains immutable event history.

## APIs

- `GET /api/inbound/foundation`
- `GET /api/acquisitions`
- `GET /api/acquisitions/{id}`
- `POST /api/acquisitions`
- `PATCH /api/acquisitions/{id}`
- `POST /api/acquisitions/{id}/lines`
- `PATCH /api/acquisition-lines/{id}`
- `POST /api/acquisition-lines/{id}/confirm-allocation`
- `POST /api/acquisitions/{id}/reconciliation`
- `POST /api/acquisitions/{id}/confirm`
- `POST /api/acquisitions/{id}/cancel`

## Test Results

- Full Python suite: 94 tests passed in 7.184 seconds in the final workspace regression run.
- All 86 Phase 1–7C tests pass unchanged in behavior.
- Eight new tests cover additive migration, forced rollback, immutable/idempotent draft creation, autosave restrictions, broad product classes, allocation confirmation, exact reconciliation, missing cost, severe discrepancy escalation, API contract, unchanged UI, version, and Docker packaging.
- JavaScript syntax and direct Phase 4 viewport/batch rendering, Phase 5 sealed Sales, Phase 7B post-sale, and Phase 7C Operational Economics regressions passed.
- Disposable startup returned `/api/health` 200 as `v2.2-test`; migration `0006` was present, existing batch linkage remained entirely `NULL`, and no acquisition was inferred.

## Known Limitations

- The guided wizard is absent; the current all-at-once New Inbound Batch form remains the operator interface in Phase 1.
- Therefore the legacy New Batch route still has its older compatibility behavior. The safe missing-cost and discrepancy rules apply to the new acquisition APIs until the later approved wizard cutover.
- Confirmed Phase 1 lines do not project into batches; `READY_FOR_INTAKE` records wait for a later approved routing phase.
- No UPC/catalog or receipt/document/extraction infrastructure exists yet.
- Receipt/document outage behavior is contractual only in Phase 1: manual entry stays available, and later failed uploads must be retryable.
- No SAM integration changed.

## Deployment Warnings

- Production remains operator-controlled. No production data, server, secrets, Jenkins, Compose, ports, or live configuration were accessed or changed.
- Validate migration `0006` only against a disposable timestamped Phase 7C storage copy before any operator-approved deployment.
- `scripts/preprod_phase2_gate.sh` is not a v2.2 validator.
- Deployment does not authorize Phase 2.

## Rollback

1. Stop only the failed/new v2.2 runtime.
2. Restore the immutable Phase 7C application checkpoint.
3. Restore the matching pre-v2.2 storage copy; do not drop acquisition tables or delete ledger entries manually.
4. Never discard Draft Acquisition history by pairing Phase 7C code with actively used v2.2 storage.

## Exact Upload Manifest

Upload these 64 files from the checkpoint:

- `app.py`
- `dex_acquisition.py`
- `dex_batch_economics.py`
- `dex_corrections.py`
- `dex_economics.py`
- `dex_inbound.py`
- `dex_legacy_economics.py`
- `dex_migrations.py`
- `dex_portfolio_economics.py`
- `dex_post_sale.py`
- `dex_rip.py`
- `dex_sealed.py`
- `Dockerfile`
- `requirements.txt`
- `VERSION`
- `README.md`
- `DEX_CURRENT_STATE.md`
- `DEX_OPERATING_MODEL.md`
- `MIGRATION_NOTES_v2.1-test.md`
- `MIGRATION_NOTES_v2.2-test.md`
- `PATCH_NOTES_v2.1-test.md`
- `PATCH_NOTES_v2.2-test.md`
- `PATCH_PLAN_ACQUISITION_RIP_BATCH.md`
- `PATCH_PLAN_INBOUND_2.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE2.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE3.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE4.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE5.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE6.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE7A.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE7B.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE7C.md`
- `RELEASE_CHECKPOINT_v2.2-test_INBOUND_PHASE1.md`
- `WEEKLY_ROADMAP.md`
- `WHATS_NEW_HUB_PLAN.md`
- `scripts/backup.py`
- `scripts/preprod_phase2_gate.sh`
- `scripts/seed_phase7a_demo.py`
- `scripts/seed_phase7b_demo.py`
- `scripts/seed_phase7c_demo.py`
- `static/app.js`
- `static/favicon.svg`
- `static/index.html`
- `static/styles.css`
- `static/vendor/LUCIDE_LICENSE.txt`
- `static/vendor/lucide.min.js`
- `tests/test_app.py`
- `tests/test_phase1_economics.py`
- `tests/test_phase1_migrations.py`
- `tests/test_phase2_legacy_economics.py`
- `tests/test_phase3_acquisition.py`
- `tests/test_phase4_batch_detail_render.cjs`
- `tests/test_phase4_rip.py`
- `tests/test_phase4_viewport_context.cjs`
- `tests/test_phase5_sales_details.cjs`
- `tests/test_phase5_sealed.py`
- `tests/test_phase6_batch_economics.py`
- `tests/test_phase7a_corrections.py`
- `tests/test_phase7b_post_sale.py`
- `tests/test_phase7b_sales_events.cjs`
- `tests/test_phase7c_portfolio.cjs`
- `tests/test_phase7c_portfolio.py`
- `tests/test_v22_phase1_inbound.py`
- `tests/fixtures/phase1_economics_scenarios.json`

## Exact Exclusion Manifest

Do **not** upload:

- `.git/`, `.agents/`, `.codex/`, IDE settings, or machine-specific metadata
- `__pycache__/`, `*.pyc`, `.pytest_cache/`, coverage output, logs, or temporary files
- `data/`, `storage/`, `storage-v2.0-test/`, `storage-v2.1-test/`, `storage-v2.2-test/`, `*.db`, `*.sqlite`, WAL/SHM/journal files, or backups
- inventory/card images, generated labels, CSV exports, screenshots, browser downloads, or `outputs/`
- scanner/inbound folders, source-database contents, or real inventory data
- `.env`, credentials, passwords, keys, tokens, cookies, or secrets
- disposable Phase 7C/v2.2 fixture directories
- the checkpoint directory nested inside the repository
