# Dex v2.1-test Phase 2 Checkpoint

Status: Git-ready checkpoint for manual upload; Phase 3 not started

## Release Contents

This checkpoint contains all approved documentation/version housekeeping, Phase 1 foundations, and Phase 2 read-only legacy batch economics. It includes source, browser assets, migrations, tests, plans, and operator documentation only.

## Test Summary

- Full suite: `python -m unittest discover -s tests -q`
- Result: 26 tests passed in 1.385 seconds in the isolated checkpoint package.
- JavaScript syntax: `node --check static/app.js` passed.
- Performance fixture: 2,500 cards; five-run average 11.37 ms, maximum 12.58 ms.
- Read-only tests compare database state before and after preview requests and verify direct mutation is rejected.

## Known Limitations and Technical Debt

- Estimates are not permanent cost basis and must never be mixed with finalized economics.
- A legacy zero `total_cost` is shown as unknown/incomplete because it cannot be distinguished reliably from missing data.
- Unrecorded or historically purged inventory cannot be discovered unless another legacy signal exposes the gap.
- Historical cross-batch order attribution is estimated from the stable existing sale-item split.
- The migration framework exists, but older conditional startup alterations have not yet been converted to registered migrations.
- `app.py` and `static/app.js` remain large and coupled; Phase 1 intentionally avoided unrelated reorganization.
- There is no authentication. Keep Dex restricted to a trusted private network.
- Browser visual verification remains an operator checkpoint.

## Deployment Warnings

- This is a test checkpoint, not approval to deploy against production inventory.
- Do not replace or migrate a production/server database during manual GitHub upload validation.
- Dockerfile, Compose, Jenkins, server ports, volumes, container names, and image tags were deliberately not changed.
- Existing deployment files still describe the preserved v2.0-test server lane. Do not infer a v2.1-test production deployment from the application version.
- Never commit `.env` files, credentials, database files, card images, scanner intake, source-image libraries, logs, backups, or machine-specific paths.

## Rollback Notes

1. Keep the preserved v2.0-test commit/tag and its storage backup available.
2. If the checkpoint fails validation, restore the prior application files or redeploy the preserved v2.0-test image.
3. Do not delete or edit real inventory rows to roll back this checkpoint.
4. Phase 2 has no economics-schema migration to reverse. The internal migration ledger may remain present.
5. Validate the restored `/api/health`, inbound workflow, inventory, labels, and outbound flow before reopening operator access.

## Upload Manifest

Upload these paths while preserving their repository-relative locations:

```text
VERSION
app.py
Dockerfile
dex_migrations.py
dex_economics.py
dex_legacy_economics.py
static/index.html
static/app.js
static/styles.css
tests/test_app.py
tests/test_phase1_migrations.py
tests/test_phase1_economics.py
tests/fixtures/phase1_economics_scenarios.json
tests/test_phase2_legacy_economics.py
README.md
DEX_OPERATING_MODEL.md
DEX_CURRENT_STATE.md
WEEKLY_ROADMAP.md
WHATS_NEW_HUB_PLAN.md
PATCH_PLAN_ACQUISITION_RIP_BATCH.md
PATCH_NOTES_v2.1-test.md
MIGRATION_NOTES_v2.1-test.md
RELEASE_CHECKPOINT_v2.1-test_PHASE2.md
```

## Paths That Must Not Be Uploaded

Do not upload any of the following, including nested copies:

```text
.git/
.env
.env.*
__pycache__/
*.pyc
*.pyo
*.db
*.db-*
*.sqlite
*.sqlite3
data/
storage/
scanner-inbox/
inbound/
images/
backups/
logs/
*.log
source-database/
source-database-v2.0-test/
node_modules/
.pytest_cache/
.mypy_cache/
.coverage
coverage/
dist/
build/
tmp/
temp/
*.zip
*.tar
*.gz
```

Also exclude editor settings, OS metadata, secrets, credentials, exported inventory/sales files, generated labels, scanner output, temporary demo databases, and any real ShonenRiot inventory data.

## Operator Validation After Upload

1. Clone or download the uploaded checkpoint into a new directory.
2. Confirm `VERSION` contains `v2.1-test`.
3. Install dependencies with `python -m pip install -r requirements.txt`.
4. Run `python -m unittest discover -s tests -q`; require all 26 tests to pass.
5. Run `node --check static/app.js`; require success.
6. Start Dex with a fresh disposable `DEX_DATA_DIR`, `DEX_SEED_DEMO=1`, and `DEX_WATCH_INBOUND=0`.
7. Open `/api/health`; confirm version `v2.1-test`.
8. Open seeded batch `OP-B...` and verify the prominent estimate-only panel, realized/unrealized separation, valuation coverage/freshness, warnings, recycled section, and calculation version.
9. Confirm normal inbound, batch completion, labels, inventory, outbound, and recycle workflows remain available.
10. Stop the disposable instance and remove only its temporary data directory. Do not point this checkpoint at production storage without separate deployment approval and a verified backup.
