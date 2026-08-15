# Dex v2.1-test Phase 6 Git-ready Checkpoint

Checkpoint scope: backend-calculated authoritative Batch Economics, Receipt/Acquisition Group rollups, valuation coverage/freshness, rip/sale/reconciliation drill-downs, and versioned backwards-compatible exports. Phase 7 is not included.

Known-good restore point: preserve `DEX_v2.1-test_Phase5_GitHub_Checkpoint` unchanged. Phase 6 is additive application/reporting work and adds no database migration.

## Runtime and Behavior

- `VERSION` remains `v2.1-test`.
- `dex_batch_economics.py` is the sole Phase 6 calculation source. The frontend formats backend results and contains no Phase 6 financial formulas.
- Authoritative batch reports are recalculated from acquisition, card/rip basis, sealed-unit, and sale facts on every request. No dashboard totals are stored.
- Legacy batches remain on the Phase 2 **Estimate only. Cost basis not finalized.** path and are not converted.
- Realized net proceeds/P&L remain distinct from current market and projected listed positions.
- Cross-batch card orders reuse stable sale-item attribution; group rollups count unique orders once.
- Receipt/Acquisition Groups remain informational and never allocate shared costs automatically.

## APIs and Exports

- `GET /api/batches/{id}/economics/report`
- `GET /api/acquisition-groups/{reference}/economics`
- `GET /api/export/batch-economics.csv` with optional `batch_id`
- Inventory CSV appends calculation version, authoritative card-basis status/value, rip code, and rip finalization timestamp.
- Sales CSV appends economics inclusion, stable attribution method, and attributable batch IDs.
- Every economics response/export identifies calculation version `acquisition-rip-v1`.

## Database and Migration Impact

Phase 6 adds no migration, schema object, index, backfill, or stored calculated total. The registered ledger remains:

1. `0001_phase3_acquisition_facts`
2. `0002_phase4_rip_sessions`
3. `0003_phase5_sealed_inventory`

Starting Phase 6 on a valid Phase 5 database should not change schema or data. Starting it on an older database may still apply those previously approved migrations; use only disposable/copied legacy fixtures before an operator-approved release.

## Test Summary

- Full Python suite: 64 tests passed in 2.882 seconds.
- JavaScript syntax check: passed.
- Direct JavaScript regressions passed for authoritative batch rendering, logical viewport preservation, and sealed Sales details/Undo.
- Python compilation/import check: passed for `app.py` and every packaged runtime module.
- Phase 6 coverage includes backend-only calculations, exact recovery/P&L, uncapped recovery above 100%, market/listed separation, valuation coverage/freshness, excluded inventory, read-only behavior, cost/quantity reconciliation, stable cross-batch order attribution, group de-duplication, API/export contracts, UI hierarchy, and packaging.
- A 2,500-card authoritative report remained inside the 2.0-second guard; the entire five-test Phase 6 module completed in about 0.06 seconds locally.
- Disposable browser QA passed against `OP-B20260814-01`, including the approved first-screen answers, expandable history, 1/2 valuation coverage, exact zero-difference reconciliations, and unchanged intake/label controls.

## Known Limitations and Technical Debt

- Unopened sealed units have no market/listed price fact in this release, so their value remains Unknown and makes coverage incomplete.
- Market/listing entry remains manual; no marketplace synchronization or automatic pricing is included.
- Listed-value freshness has no dedicated source timestamp and therefore reports **Freshness Unknown**.
- Legacy batches remain estimate-only until the future optional guided conversion workflow.
- Shared receipt shipping, tax, discounts, and fees are not automatically allocated.
- Phase 7A corrections/dispositions, Phase 7B refunds/returns/chargebacks, and Phase 7C portfolio Operational Economics are not included.
- `app.py` and `static/app.js` remain large and coupled; Phase 6 avoids unrelated reorganization.
- The server remains private-network software without authentication. Do not expose its port publicly.

## Deployment Warnings

- Production remains operator-controlled. This checkpoint accessed no server, production database, credentials, scanner folders, or real inventory.
- Verify the Compose image/tag and mounted storage before any operator-run deployment.
- Rebuilding replaces application code, but startup applies any still-pending registered Phase 3–5 migrations to the mounted database.
- `scripts/preprod_phase2_gate.sh` is not a Phase 6 release validator; it intentionally expects the earlier Phase 2 ledger-only state.
- Do not infer approval for Phase 7 from deploying or accepting this checkpoint.

## Rollback

If a Phase 6 runtime fails against an already valid Phase 5 database:

1. Stop only the failed/new Phase 6 runtime.
2. Restore the preserved Phase 5 application checkpoint.
3. Reuse the database only if inspection confirms no older pending migration ran; Phase 6 itself writes no schema/data.
4. If an older Phase 3–5 migration ran during the same deployment, restore the timestamped pre-upgrade storage copy with the matching older application.
5. Never delete, rewrite, or downgrade production storage merely because application startup failed.

## Exact Upload Manifest

Upload these files/folders from the packaged checkpoint:

- `app.py`
- `dex_acquisition.py`
- `dex_batch_economics.py`
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
- `WEEKLY_ROADMAP.md`
- `WHATS_NEW_HUB_PLAN.md`
- `scripts/preprod_phase2_gate.sh`
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
- `tests/fixtures/phase1_economics_scenarios.json`

## Exact Exclusion Manifest

Do **not** upload:

- `.git/`, `.agents/`, `.codex/`, IDE settings, or machine-specific metadata
- `__pycache__/`, `*.pyc`, `.pytest_cache/`, coverage output, test logs, or temporary files
- `data/`, `storage/`, `storage-v2.0-test/`, `storage-v2.1-test/`, `*.db`, `*.sqlite`, SQLite journal/WAL/SHM files, or database backups
- inventory/card images, generated labels, generated CSV exports, screenshots, or browser downloads
- `scanner-inbox/`, inbound scan folders, source-database contents, or real inventory data
- `.env`, credentials, passwords, private keys, tokens, cookies, or secrets
- the disposable local Phase 6 demo database/folders
- the checkpoint-package directory nested inside the repository

## Operator Validation After Upload

1. Confirm `VERSION` is `v2.1-test` and all eight runtime Python files listed above are beside `app.py`.
2. Run `python -m unittest discover -s tests -q`; expect 64 passing tests.
3. Run `node --check static/app.js`; expect no output and exit code 0.
4. Start Dex against disposable storage and confirm `/api/health` returns 200 with `v2.1-test`.
5. Confirm existing Inventory, Inbound, Recycle Bin, card sales, sealed sales/details/Undo, rip intake, batch completion, and labels still work.
6. Open an authoritative acquisition batch and verify the seven Phase 6 sections appear in the approved order.
7. Confirm the Summary answers cost, recovered proceeds, remaining value with coverage, and ahead/behind position.
8. Expand Recovery, Remaining, Sales, and Reconciliation; confirm realized/unrealized separation, freshness, warnings, stable attributable sale portions, and exact quantity/basis reconciliation.
9. Download Batch Economics, Inventory, and Sales CSVs and confirm calculation/provenance columns are appended.
10. Open a legacy batch and confirm it still says **Estimate only. Cost basis not finalized.**
