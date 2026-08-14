# Dex v2.1-test Patch Notes

Status: active development; Phase 3 complete

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

## Phase 3: Acquisition Cost Facts and Receipt/Acquisition Groups

- Add authoritative acquisition facts to each batch without assigning permanent card basis.
- Support `SEALED_RIP`, `SINGLES_KNOWN_COST`, and `SINGLES_LUMP_SUM` modes while keeping legacy batches estimate-only.
- Store final USD paid and cost components in exact integer cents. Final USD paid is the sole authoritative amount; optional original currency and amount are reference-only.
- Require correction or an explicit acknowledgement when entered components do not reconcile to final USD paid.
- Preserve legacy `total_cost` compatibility by deterministically mirroring operator-entered final USD paid.
- Link separate homogeneous product batches with an informational Receipt/Acquisition Group reference. DEX reports each batch's assigned cost and never allocates shared transaction charges automatically.
- Add a batch acquisition editor, read API, audited material updates, finalized-edit protection, and backwards-compatible appended inventory CSV fields.
- Add a transactional migration for acquisition columns and the receipt-group index. Existing legacy costs are not backfilled into permanent economics.
- Expand the disposable demo with six OP16 booster boxes and two ST27 starter decks on one $746.40 receipt group.
- Do not add rip sessions, card basis, sealed-unit inventory/sales, or economics finalization.

## Approved Remaining Phases

- Phase 4: explicit rip sessions, unscanned-bulk reserves, and immutable card basis.
- Phase 5: sealed-unit inventory and separate sealed-product sales.
- Phase 6: batch economics UI and versioned exports.
- Phase 7A: corrections and dispositions.
- Phase 7B: refunds, returns, chargebacks, and post-sale corrections.
- Phase 7C: portfolio Operational Economics.

## Compatibility and Deployment

- Dex v2.0-test remains the documented baseline.
- Phase 1 added no operator-visible behavior; Phase 2 remained strictly read-only.
- Phase 3 adds the registered `0001_phase3_acquisition_facts` migration. It adds batch columns and a receipt-group index but does not backfill legacy cost into finalized economics.
- Docker packaging includes every Python module imported by `app.py`. Compose, Jenkins, ports, volumes, containers, and server credentials remain unchanged and operator-controlled.

## Phase 3 Checkpoint Test Results

- `python -m unittest discover -s tests -q`: 35 tests passed in 1.411 seconds in the development workspace.
- `node --check static/app.js`: passed with the bundled Node runtime.
- Phase 3 validation, receipt-group, API, audit, CSV, finalized-lock, runtime-packaging, one-time migration, rollback, and UI-contract tests passed.
- All Phase 1 and Phase 2 regression tests passed, including the existing 2,500-card performance guard.
- Disposable migration tests confirmed the legacy source fixture remains unchanged and no permanent cost is backfilled.
- A disposable seeded API smoke test confirmed 6 OP16 boxes at $660.00 plus 2 ST27 decks at $86.40 reconcile to $746.40 under one informational receipt group.

## Deployment Packaging Fix

- Correct the Docker build so `dex_migrations.py`, `dex_economics.py`, and `dex_legacy_economics.py` are copied beside `/app/app.py`.
- Add a build-time import assertion so an image build fails immediately if any required v2.1-test Python module is missing.
- No application behavior, economics logic, database schema, or Phase 3 work is included in this fix.
- Add `scripts/preprod_phase2_gate.sh`, an operator-confirmed, fail-closed pre-production gate that builds the dynamically resolved Compose image and validates it only against a timestamped SQLite/storage copy on a loopback-only temporary port.

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
