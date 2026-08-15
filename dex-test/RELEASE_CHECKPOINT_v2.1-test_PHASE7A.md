# Dex v2.1-test Phase 7A Git-ready Checkpoint

Checkpoint scope: append-only acquisition/basis corrections, reason-aware card and sealed dispositions, operational-loss treatment, durable tombstones, and linked inverse reversals. Phase 7B refunds/returns/chargebacks and Phase 7C portfolio Operational Economics are not included.

Known-good restore point: preserve `DEX_v2.1-test_Phase6_GitHub_Checkpoint` unchanged. This Phase 7A package is a new additive checkpoint.

## Runtime and Behavior

- `VERSION` remains `v2.1-test`.
- `dex_corrections.py` owns Phase 7A validation, immutable event creation, current corrected values, tombstones, dispositions, and reversals.
- Finalized source acquisition, rip-basis, sealed-unit, and sale facts are never overwritten by a correction. Current values are derived from preserved source facts plus signed event entries.
- Duplicate/Entry Error reallocates basis and does not create operational loss. Correction Hold retains basis while excluding the item. Damaged, Missing/Lost, Disposed, and Other physical dispositions move basis to Operational Loss.
- Operational Loss is operational economics only; DEX makes no tax/accounting or deduction conclusion.
- A reversal creates one linked inverse event and restores eligible entity state atomically. The original event and tombstone remain durable history.
- Cards with economic history cannot be hard-purged or auto-purged. An active disposition is restored from Recycle Bin only through its linked reversal workflow.
- All write routes use the existing process lock plus `BEGIN IMMEDIATE`; request IDs prevent duplicate submissions.

## Schema and Migration

Registered migration `0004_phase7a_corrections_dispositions` creates:

1. `economic_events`
2. `economic_event_entries`
3. `economic_tombstones`

It also creates indexes for batch/event history, typed target lookup, tombstone lookup, and one linked reversal per original event. The migration is transactional through the existing savepoint runner and performs no data backfill or source-fact rewrite.

## Event Types

- `ACQUISITION_COST_CORRECTION`
- `BASIS_TRANSFER`
- `CARD_DISPOSITION`
- `SEALED_QUANTITY_CORRECTION`
- `REVERSAL`

Every event has an immutable event ID, unique request ID, standardized reason, effective date, recorded timestamp, required notes, payload snapshot, and calculation version in API responses.

## APIs and UI

- `GET /api/batches/{id}/corrections`
- `GET /api/economic-events/{event_id}`
- `POST /api/batches/{id}/corrections/acquisition`
- `POST /api/batches/{id}/corrections/basis-transfer`
- `POST /api/cards/{sku}/disposition`
- `POST /api/sealed-units/{id}/disposition`
- `POST /api/economic-events/{event_id}/reverse`
- Batch Economics adds **Corrections & Dispositions** inside Reconciliation / Warnings.
- Card detail exposes **Audited disposition** for eligible finalized-basis cards.
- Remaining sealed units expose **Correct / dispose**.
- Recycle Bin identifies protected economic/tombstone records, disables hard purge, and offers **Reverse disposition** for active tombstones.
- Batch and inventory CSVs append current/source correction and operational-loss fields without changing existing column meanings.

## Test Summary

- Full Python suite: 72 tests passed.
- JavaScript syntax check: passed.
- Direct JavaScript batch-render, logical-viewport, and sealed Sales details/Undo regressions: passed.
- Python compile/import checks: passed for `app.py` and all packaged runtime modules.
- New tests cover migration rollback/no-backfill, event/request IDs, de-duplication, deterministic exact-cent acquisition correction, explicit card/bulk transfer, duplicate/error reallocation, physical damage/loss, exact sealed-unit disposition, operational-loss reconciliation, tombstones, hard-purge protection, linked inverse events, HTTP APIs, UI/runtime packaging, and current report integration.
- A 1,000-card finalized corrections payload passed the 2.0-second performance guard.
- Disposable browser QA passed acquisition correction/reversal, exact reconciliation, sealed damage, card damage, protected Recycle Bin history, and linked restoration.

## Known Limitations and Technical Debt

- Phase 7B post-sale events are absent: no refunds, returns, chargebacks, fee credits, carrier refunds, or post-sale money corrections.
- Phase 7C portfolio Operational Economics is absent.
- Reversal-of-reversal is intentionally unsupported in Phase 7A; a reviewed future workflow is required.
- Card/bulk transfers are limited to targets in finalized rip/allocation sessions.
- The older Phase 4 rip-correction API and Phase 5 sealed-adjust API remain for compatibility; the current operator UI routes covered dispositions through Phase 7A.
- Unopened sealed market/listed values remain Unknown, and manual pricing remains unchanged.
- Receipt/Acquisition Groups remain informational and never allocate shared costs automatically.
- Polymorphic event-entry target IDs are service-validated rather than foreign-keyed to every target table.
- `app.py` and `static/app.js` remain large; unrelated refactoring was deliberately avoided.
- The private-network runtime still has no authentication and must not be exposed publicly.

## Deployment Warnings

- Production remains operator-controlled. Development used only disposable local storage and no server credentials, live database, scanner folder, or real inventory.
- Startup against a Phase 6 database applies migration `0004`; first validate against a timestamped disposable copy.
- Verify the exact Compose image/tag and storage mount before any operator-run deployment. No Compose, Jenkins, port, volume, or production configuration changed in Phase 7A.
- `scripts/preprod_phase2_gate.sh` is not a Phase 7A validator and will reject the expected newer schema.
- Deploying Phase 7A does not authorize Phase 7B.

## Rollback

If Phase 7A startup or validation fails:

1. Stop only the failed/new Phase 7A runtime.
2. Restore the preserved Phase 6 application checkpoint.
3. Restore the matching timestamped pre-Phase-7A storage copy; do not pair Phase 6 code with a database containing new Phase 7A events.
4. Do not delete, rewrite, manually reverse, or downgrade the migrated production database in place.

## Exact Upload Manifest

Upload these files/folders from the packaged checkpoint:

- `app.py`
- `dex_acquisition.py`
- `dex_batch_economics.py`
- `dex_corrections.py`
- `dex_economics.py`
- `dex_legacy_economics.py`
- `dex_migrations.py`
- `dex_rip.py`
- `dex_sealed.py`
- `Dockerfile`
- `requirements.txt`
- `VERSION`
- `README.md`
- `DEX_CURRENT_STATE.md`
- `DEX_OPERATING_MODEL.md`
- `MIGRATION_NOTES_v2.1-test.md`
- `PATCH_NOTES_v2.1-test.md`
- `PATCH_PLAN_ACQUISITION_RIP_BATCH.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE2.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE3.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE4.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE5.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE6.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE7A.md`
- `WEEKLY_ROADMAP.md`
- `WHATS_NEW_HUB_PLAN.md`
- `scripts/backup.py`
- `scripts/preprod_phase2_gate.sh`
- `scripts/seed_phase7a_demo.py`
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
- `tests/fixtures/phase1_economics_scenarios.json`

## Exact Exclusion Manifest

Do **not** upload:

- `.git/`, `.agents/`, `.codex/`, IDE settings, or machine-specific metadata
- `__pycache__/`, `*.pyc`, `.pytest_cache/`, coverage output, test logs, or temporary files
- `data/`, `storage/`, `storage-v2.0-test/`, `storage-v2.1-test/`, `*.db`, `*.sqlite`, SQLite journal/WAL/SHM files, or database backups
- inventory/card images, generated labels, generated CSV exports, screenshots, or browser downloads
- `scanner-inbox/`, inbound scan folders, source-database contents, or real inventory data
- `.env`, credentials, passwords, private keys, tokens, cookies, or secrets
- disposable Phase 7A storage/database folders
- the checkpoint-package directory nested inside the repository

## Disposable Operator Validation

1. Create new disposable storage: `python scripts/seed_phase7a_demo.py --output <new-empty-path>`.
2. Point `DEX_DATA_DIR`, `DEX_DB_PATH`, `DEX_IMAGE_DIR`, `DEX_INBOUND_DIR`, and `DEX_SOURCE_DB_DIR` at that new path; set `DEX_WATCH_INBOUND=0`, choose a loopback-only non-production port, and run `python app.py`.
3. Open Inbound → `OP-B20260814-01`. Confirm the batch is Finalized, one unit is opened, five remain, four cards have basis, and both basis/quantity differences are zero.
4. Under Reconciliation / Warnings → Corrections & Dispositions, change acquisition cost from `$660.00` to `$660.02`. Confirm preserved source remains `$660.00`, current cost becomes `$660.02`, and basis still reconciles to `$0.00` difference.
5. Reverse that event. Confirm both original and inverse events remain visible and current cost returns to `$660.00`.
6. Expand Remaining Inventory → exact sealed units; mark one remaining unit Damaged. Confirm adjusted quantity becomes one, Operational Loss becomes `$110.00`, and both reconciliations remain exact. Reverse if desired.
7. Edit a batch card → Audited disposition. Test Duplicate/Entry Error with another card destination or Damaged. Confirm the card enters Recycle Bin as Protected Record, cannot be purged, and basis is reallocated or moved to Operational Loss as appropriate.
8. Use Reverse disposition in Recycle Bin. Confirm a linked inverse event is created and the exact card returns with basis/value restored.
9. Confirm normal intake, batch completion/labels, card sales, sealed sales/details/Undo, and Phase 2 legacy estimates remain usable.
