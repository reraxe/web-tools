# Dex v2.1-test Patch Notes

Status: active development; Phase 2 complete

## Focus

Dex v2.1-test adds Acquisition and Rip Batch Economics while preserving v2.0-test as the documented implementation baseline. The approved work connects acquisition cost to sealed units, rip sessions, resulting card inventory, realized sales, remaining value, cost recovery, and operational profit/loss.

This release is implemented in gated phases. Each phase must pass its complete test set before the next begins.

## Phase 1: Foundations

- Add a dedicated versioned SQLite migration runner and migration ledger.
- Run migrations transactionally where SQLite permits; failed migrations roll back and are not recorded as complete.
- Add deterministic exact-cent allocation based on immutable stable identifiers.
- Add disposable legacy-database migration fixtures and approved-rule tests.
- Preserve all existing operator workflows and API behavior.

## Phase 2: Read-only Legacy Batch Economics

- Add a query-only estimated-economics API for existing acquisition batches.
- Add an unmistakable **Estimated Economics** panel to batch detail with the statement **“Estimate only. Cost basis not finalized.”**
- Separate realized economics from unrealized/remaining value.
- Show valuation coverage and freshness beside value-dependent totals; unknown prices remain unknown.
- Show material-understatement warnings for detectable open batches, unscanned bulk, missing values, and incomplete sale history.
- Show recoverable recycled cards separately and exclude them from active remaining value.
- Attribute historical multi-batch orders once using their existing sale-item split and label the result estimated.
- Keep the endpoint enforced read-only; it assigns no permanent basis and performs no legacy conversion or repair.
- Include calculation version `acquisition-rip-v1` in the response and panel.
- Local app health metadata, footer, and frontend cache tags report `v2.1-test`; production deployment configuration remains unchanged.

## Approved Remaining Phases

- Phase 3: acquisition cost facts and Receipt/Acquisition Groups.
- Phase 4: explicit rip sessions, unscanned-bulk reserves, and immutable card basis.
- Phase 5: sealed-unit inventory and separate sealed-product sales.
- Phase 6: batch economics UI and versioned exports.
- Phase 7A: corrections and dispositions.
- Phase 7B: refunds, returns, chargebacks, and post-sale corrections.
- Phase 7C: portfolio Operational Economics.

## Compatibility and Deployment

- Dex v2.0-test remains the documented baseline.
- Phase 1 adds no acquisition-economics fields, screens, routes, or operator-visible workflow changes.
- Existing databases gain only the internal `schema_migrations` ledger; Phase 2 adds no schema migration.
- Production/server Docker, Compose, Jenkins, ports, volumes, containers, and tags are unchanged during Phase 1.

## Phase 2 Checkpoint Test Results

- `python -m unittest discover -s tests -q`: 26 tests passed in 1.385 seconds in the isolated checkpoint package.
- `node --check static/app.js`: passed.
- A 2,500-card legacy batch preview averaged 11.37 ms over five runs; maximum 12.58 ms.
- Read-only integration tests confirmed that preview requests do not mutate batches, cards, activity, or migration records.

## Deployment Packaging Fix

- Correct the Docker build so `dex_migrations.py`, `dex_economics.py`, and `dex_legacy_economics.py` are copied beside `/app/app.py`.
- Add a build-time import assertion so an image build fails immediately if any required v2.1-test Python module is missing.
- No application behavior, economics logic, database schema, or Phase 3 work is included in this fix.

## Verification

- Existing v2.0-test API/integration tests pass unchanged.
- DEX initialization creates the internal migration ledger.
- Disposable legacy-copy tests verify one-time migration execution and source-fixture isolation.
- Forced-failure testing verifies schema changes and completion markers roll back together.
- Deterministic cent-allocation tests verify stable remainder assignment and exact reconciliation.
- Approved-rule fixtures cover the planned acquisition, rip, bulk, sale, recycle, legacy, and receipt-group scenarios.
- Phase 2 read-only, valuation, cross-batch allocation, warning, UI-contract, and performance tests pass.
- A 2,500-card legacy preview averaged 11.37 ms over five measured runs; maximum was 12.58 ms in the Phase 2 workspace benchmark.

## Documentation

- `DEX_OPERATING_MODEL.md` assigns Acquisition and Rip Batch Economics to v2.1-test.
- `WEEKLY_ROADMAP.md` moves the What's New hub and displaced future work to later version slots without deleting it.
- `PATCH_PLAN_ACQUISITION_RIP_BATCH.md` remains the approved implementation authority.
