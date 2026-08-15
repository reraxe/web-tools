# Dex v2.1-test Phase 4 Git-ready Checkpoint

Checkpoint scope: explicit rip sessions, intake association, bulk reserves, exact allocation finalization, and immutable card-basis history. Phase 5 is not included.

Known-good restore point: preserve the corrected `DEX_v2.1-test_Phase3_GitHub_Checkpoint` package unchanged with its matching pre-Phase-4 storage copy.

## Runtime Behavior

- Creating a rip session never activates scanner intake. The operator must explicitly start it.
- One global active rip receives new scanner/browser cards only for its own acquisition batch. A prominent banner identifies it.
- Switching with unprocessed scanner files requires explicit confirmation.
- Completing a batch transactionally stops any active rip for that batch. Completed batches cannot start rip intake until the operator uses the existing reopen workflow.
- An open batch with an active draft rip continues accepting repeated browser/scanner intake; intake does not disappear merely because a card was added.
- Same-batch mutations preserve the operator's logical viewport using stable section, rip, and card anchors instead of returning to the top. Removed anchors fall back to the prior scroll position.
- Allocation modal polish shows only the field relevant to the selected unscanned-bulk mode. Final-confirmation checkboxes are native required controls aligned to the first line of fully clickable, wrapping labels.
- Phase 4 operator QA passed; the completed checkpoint includes final confirmation-group spacing polish with no workflow or economics changes.
- Sealed rip cost uses authoritative final USD paid and deterministic acquired-unit cent allocation. Pending/finalized openings cannot exceed acquired units.
- Equal allocation uses immutable internal card IDs and stable bulk-slot IDs. Known bulk quantity participates in the same per-card allocation.
- Unknown-quantity bulk requires an explicit manual reserve and marks valuation coverage incomplete.
- Known-cost singles require an actual cost for every participating card; ripped product and lump-sum singles default to equal allocation.
- Finalization requires all-cards confirmation, lock confirmation, and an exact `$0.00` difference.
- Finalized rips reject ordinary intake. Later basis changes append audited correction events and never overwrite the original finalization payload.
- Existing batch completion, labels, inventory, card sales, recycle, SAM, and legacy estimates remain available.
- No sealed-unit sale, mixed order, refund/return, portfolio, or Phase 5 behavior is included.

## Files Changed Since Corrected Phase 3

- `app.py`
- `dex_migrations.py`
- `Dockerfile`
- `static/app.js`
- `static/index.html`
- `static/styles.css`
- `tests/test_phase3_acquisition.py`
- `DEX_CURRENT_STATE.md`
- `DEX_OPERATING_MODEL.md`
- `MIGRATION_NOTES_v2.1-test.md`
- `PATCH_NOTES_v2.1-test.md`
- `PATCH_PLAN_ACQUISITION_RIP_BATCH.md`
- `README.md`
- `WEEKLY_ROADMAP.md`

New files:

- `dex_rip.py`
- `tests/test_phase4_rip.py`
- `tests/test_phase4_batch_detail_render.cjs`
- `tests/test_phase4_viewport_context.cjs`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE4.md`

`VERSION` remains the approved `v2.1-test` value and is included in the package.

## Schema and Migration

Registered migration: `0002_phase4_rip_sessions`.

It adds `rip_sessions`, `rip_economic_events`, and `rip_basis_events`; nullable rip provenance on cards and processed scans; and lookup indexes. Migration execution and its ledger marker share one SQLite savepoint. It creates no rip records, assigns no legacy card basis, changes no sale fact, and performs no Phase 5 sealed migration.

See `MIGRATION_NOTES_v2.1-test.md` for exact behavior and rollback.

## Tests and Results

- Full suite: 48 tests passed (`python -m unittest discover -s tests -v`) in 2.340 seconds after the Phase 4 modal polish.
- Frontend syntax: `node --check static/app.js` passed.
- Direct seeded batch renderer: `node tests/test_phase4_batch_detail_render.cjs` is part of the disposable local smoke gate.
- Logical viewport regression: `node tests/test_phase4_viewport_context.cjs` passed stable-anchor restoration and removed-anchor fallback coverage.
- Coverage includes migration one-time/rollback behavior, explicit and repeated intake, completion-time intake shutdown, reopen recovery, pending-file switch confirmation, browser/scanner association, deterministic partial-unit and bulk allocation, known-cost singles, unknown bulk, finalization locks, idempotent append-only corrections, recycled basis retention, UI contracts, and Docker module packaging.

## Deployment Assumptions and Warnings

- Production remains operator-controlled. No production server, credentials, container, storage, or real inventory database is accessed by this checkpoint.
- Test only against disposable or copied legacy data before any operator-approved deployment.
- The Dockerfile copies and import-checks `dex_rip.py` beside all existing runtime modules.
- Compose, Jenkins, production tags, ports, volumes, and deployment workflow are unchanged.
- `scripts/preprod_phase2_gate.sh` is not a Phase 4 validator and will fail closed on the additive schema.
- Keep DEX private; application authentication is still absent.

## Known Limitations

- Phase 4 stores one aggregate bulk reserve per rip. Bulk sales/dispositions and richer bulk-lot states remain later approved work.
- Sealed-unit identity, sealed sales, and sold/corrected sealed-quantity facts do not exist until Phase 5; their Phase 4 availability deductions are therefore zero.
- Draft rip sessions have no cancel/delete workflow in this phase. Incorrect drafts should not be finalized and require a future audited lifecycle action.
- Correction UI supports card-to-card or card-to-bulk reallocation; reason-aware loss/disposition workflows remain Phase 7A.
- Legacy batches stay estimate-only unless authoritative Phase 3 facts are entered. Phase 4 performs no guided legacy conversion.

## Rollback

1. Stop only the failed/new test runtime.
2. Restore the corrected Phase 3 application package.
3. Attach its matching pre-Phase-4 storage copy.
4. Verify health, inventory, batches, labels, sales, Recycle Bin, acquisition facts, and Estimated Economics.

Do not attempt an in-place schema downgrade or delete migrated storage.

## Exact Upload Manifest

Upload these source paths:

- `VERSION`
- `app.py`
- `dex_acquisition.py`
- `dex_economics.py`
- `dex_legacy_economics.py`
- `dex_migrations.py`
- `dex_rip.py`
- `requirements.txt`
- `Dockerfile`
- `static/`
- `tests/fixtures/phase1_economics_scenarios.json`
- `tests/test_app.py`
- `tests/test_phase1_economics.py`
- `tests/test_phase1_migrations.py`
- `tests/test_phase2_legacy_economics.py`
- `tests/test_phase3_acquisition.py`
- `tests/test_phase4_rip.py`
- `tests/test_phase4_batch_detail_render.cjs`
- `tests/test_phase4_viewport_context.cjs`
- `DEX_CURRENT_STATE.md`
- `DEX_OPERATING_MODEL.md`
- `MIGRATION_NOTES_v2.1-test.md`
- `PATCH_NOTES_v2.1-test.md`
- `PATCH_PLAN_ACQUISITION_RIP_BATCH.md`
- `README.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE2.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE3.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE4.md`
- `WEEKLY_ROADMAP.md`
- `WHATS_NEW_HUB_PLAN.md`
- `scripts/preprod_phase2_gate.sh` as retained Phase 2 history only

## Do Not Upload

- `__pycache__/`, `*.pyc`, `.pytest_cache/`, or test caches
- `data/`, `storage/`, scanner folders, source databases, card images, labels, exports, logs, screenshots, or backups
- `*.db`, `*.sqlite`, SQLite WAL/SHM files, or any real inventory data
- `.env`, credentials, passwords, keys, tokens, Jenkins/Portainer secrets
- temporary/demo folders, local virtual environments, or machine-specific files
- a checkpoint-package directory nested inside the repository

## Disposable Local Validation

Use `DEX_SEED_DEMO=1`, `DEX_WATCH_INBOUND=0`, and a new temporary `DEX_DATA_DIR`. Open the seeded OP16 batch, create a one-unit rip, explicitly start intake, add disposable cards, preview/finalize with known or unknown bulk, and confirm the exact reconciliation and intake lock. See the completion report for the short operator sequence.
