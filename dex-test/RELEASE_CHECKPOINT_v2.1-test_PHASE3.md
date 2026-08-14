# Dex v2.1-test Phase 3 Git-ready Checkpoint

Checkpoint scope: Acquisition Cost Facts and Receipt/Acquisition Groups. Phase 4 is not included.

Known-good restore point: the existing `DEX_v2.1-test_Phase2_GitHub_Checkpoint` package remains unchanged. Keep it together with a pre-upgrade copy of storage for rollback.

## Runtime Behavior

- Existing inventory, scanner, labels, sales, recycle, SAM, and Phase 2 estimate workflows remain available.
- Operators may create or edit draft acquisition facts on a homogeneous product batch.
- `final_usd_paid_cents` is authoritative. Original currency and amount are reference-only; no FX math occurs.
- Cost components must reconcile exactly or carry an explicit mismatch acknowledgement.
- Receipt/Acquisition Groups link batches informationally and never allocate shared charges.
- Material changes create activity records. Ordinary editing is blocked after economics status becomes `FINALIZED`.
- Phase 3 does not add rip sessions, basis assignment/finalization, sealed-unit sales, refunds, or portfolio economics.

## Files Changed Since the Phase 2 Restore Point

- `app.py`
- `dex_migrations.py`
- `Dockerfile` — packaging metadata and required-module copy/import assertion only; no port, volume, tag, Compose, Jenkins, or deployment workflow change
- `static/app.js`
- `static/index.html`
- `static/styles.css`
- `tests/test_app.py`
- `DEX_CURRENT_STATE.md`
- `DEX_OPERATING_MODEL.md`
- `MIGRATION_NOTES_v2.1-test.md`
- `PATCH_NOTES_v2.1-test.md`
- `PATCH_PLAN_ACQUISITION_RIP_BATCH.md`
- `README.md`
- `WEEKLY_ROADMAP.md`

New files:

- `dex_acquisition.py`
- `tests/test_phase3_acquisition.py`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE3.md`

`VERSION` remains the approved `v2.1-test` value and is included in the package.

## Schema and Migration

Registered migration: `0001_phase3_acquisition_facts`.

It adds acquisition mode/status, product identity, receipt/invoice references, USD and optional foreign-reference amounts, acquired quantity, cost components, reconciliation acknowledgement, and update timestamp to `batches`, plus `idx_batches_receipt_group`. Monetary facts are integer cents. Legacy `total_cost` remains unchanged during migration and is not promoted into permanent economics.

See `MIGRATION_NOTES_v2.1-test.md` for the exact columns, transaction behavior, disposable-copy procedure, expected mutations, and rollback.

## Tests and Results

- Full development suite: 35 tests passed (`python -m unittest discover -s tests -q`) in 1.411 seconds.
- Isolated checkpoint package: 35 tests passed; no forbidden runtime/private artifacts were present.
- Earlier Phase 1/2 tests all pass, including the 2,500-card legacy-preview performance guard.
- New coverage verifies validation, exact reconciliation, optional foreign references, unknown cost, mismatch acknowledgement, receipt grouping without allocation, audit history, CSV compatibility, finalized-edit protection, runtime image module packaging, one-time legacy migration, source-copy isolation, and rollback on forced migration failure.
- Disposable seeded API smoke: health `200`, runtime `v2.1-test`; 6 OP16 boxes cost $660.00 and 2 ST27 decks cost $86.40 under `DEMO-RECEIPT-001`; group assigned-cost total is $746.40 with 2/2 batch coverage.
- Frontend syntax: `node --check static/app.js` passed with the bundled Node runtime.
- Automated browser control could not launch because its sandboxed runtime could not access its own machine-local runtime path. Visual verification remains an operator acceptance step; this did not affect the app or disposable database.

## Deployment Assumptions and Warnings

- Production remains operator-controlled. No production server, credentials, live container, production storage, or real inventory database was accessed.
- This checkpoint is source only. It is not authorization to deploy or begin Phase 4.
- The Dockerfile now copies and import-checks `dex_acquisition.py` beside `app.py`, in addition to all Phase 1/2 modules.
- Do not run the old `scripts/preprod_phase2_gate.sh` as a Phase 3 validator; it expects only a migration ledger and will fail closed on the approved Phase 3 columns.
- Before an operator-approved upgrade, back up complete storage and validate the image against a disposable copied legacy database.
- Never treat `total_cost` alone as finalized Phase 3 basis. Legacy records remain estimate-only until authoritative facts are entered.
- Keep the service private; DEX still has no application authentication.

## Rollback

1. Stop only the failed/new test container or process.
2. Restore the Phase 2 application package.
3. Attach the pre-upgrade Phase 2 storage copy, not the newly migrated database.
4. Start the Phase 2 runtime and verify health, inventory, batches, sales, and Recycle Bin.

Do not delete production storage or attempt an in-place schema downgrade. The safe rollback unit is application plus its matching captured storage copy.

## Exact Upload Manifest

Upload these paths from the Phase 3 checkpoint package:

- `VERSION`
- `app.py`
- `dex_acquisition.py`
- `dex_economics.py`
- `dex_legacy_economics.py`
- `dex_migrations.py`
- `requirements.txt`
- `Dockerfile`
- `static/`
- `tests/fixtures/phase1_economics_scenarios.json`
- `tests/test_app.py`
- `tests/test_phase1_economics.py`
- `tests/test_phase1_migrations.py`
- `tests/test_phase2_legacy_economics.py`
- `tests/test_phase3_acquisition.py`
- `DEX_CURRENT_STATE.md`
- `DEX_OPERATING_MODEL.md`
- `MIGRATION_NOTES_v2.1-test.md`
- `PATCH_NOTES_v2.1-test.md`
- `PATCH_PLAN_ACQUISITION_RIP_BATCH.md`
- `README.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE2.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE3.md`
- `WEEKLY_ROADMAP.md`
- `WHATS_NEW_HUB_PLAN.md`
- `scripts/preprod_phase2_gate.sh` (retained historical Phase 2 tool; not a Phase 3 validator)

## Do Not Upload

- `__pycache__/`, `*.pyc`, `.pytest_cache/`, test caches
- `data/`, `storage/`, `storage-v2.0-test/`, `storage-v2.1-test/`, `*.db`, `*.sqlite`, SQLite WAL/SHM files
- real inventory exports, card images, source databases, `source-database-v2.0-test/`
- scanner folders, scanner inboxes, pending scans, generated labels, backups, logs, screenshots, or audit output
- `.env`, credentials, passwords, keys, tokens, Jenkins/Portainer secrets
- machine-specific IDE files, temporary folders, disposable demo data, or local virtual environments
- the checkpoint package itself nested inside the Git repository

## Local Operator Validation

1. Create a disposable empty folder outside the repository.
2. Set `DEX_DATA_DIR` to that folder, `DEX_WATCH_INBOUND=0`, and `DEX_SEED_DEMO=1`.
3. Start `python app.py` and open `http://127.0.0.1:8080`.
4. Confirm `/api/health` reports `v2.1-test`.
5. Open Inbound and select the OP16 booster-box demo batch.
6. Confirm Acquisition Cost Facts shows 6 units, $660.00 final USD, a $0.00 reconciliation difference, CAD 900.00 as reference only, and receipt group `DEMO-RECEIPT-001`.
7. Confirm the group shows the separate ST27 batch at $86.40 and a $746.40 assigned-cost total, with the no-automatic-allocation notice.
8. Edit a disposable batch with a mismatched component total and confirm DEX requires correction or explicit acknowledgement.
9. Confirm existing inventory, Estimated Economics, batch completion/labels, sales, and Recycle Bin still load.
10. Stop DEX and delete only the disposable test folder when finished.
