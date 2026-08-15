# Dex v2.1-test Phase 7C Git-ready Checkpoint

Checkpoint scope: read-only portfolio **Operational Economics**, effective Phase 7B recovery, exact Finalized Economics attribution, valuation coverage/freshness, reconciliation, and CSV export. This completes the approved v2.1-test development scope. Production deployment and post-v2.1 work are not authorized.

Known-good restore point: preserve `DEX_v2.1-test_Phase7B_GitHub_Checkpoint` unchanged. This Phase 7C package is a new additive checkpoint.

## Runtime and Calculation Behavior

- `VERSION` remains `v2.1-test`; economics APIs and exports identify Phase 7C rules as `acquisition-rip-v3`.
- `dex_portfolio_economics.py` is the sole portfolio calculation source. The frontend formats returned facts and contains no portfolio financial formulas.
- Portfolio totals include only authoritative batches whose economics status is `FINALIZED`. Legacy estimates and authoritative-but-unfinalized batches are listed separately and never blended.
- Effective realized proceeds use immutable sale facts plus active Phase 7B events. Canceled orders and reversed events follow their effective state. Marketplace-collected tax remains excluded.
- Immutable card sale-item IDs and exact sealed sale-item IDs are attributed once. Cross-batch card orders reuse their original stable weighting; group and portfolio aggregation do not duplicate revenue, fees, postage, proceeds, or basis.
- Realized Economics and Unrealized/Remaining Value remain separate. Market and listed values never substitute for one another, and remaining sealed value is Unknown without an authoritative valuation fact.
- Receipt/Acquisition Groups remain informational and never allocate shared charges automatically.
- Calculated portfolio totals are not stored. API and CSV requests open SQLite read-only and derive the result from source facts.

## Exact Calculation Definitions

- **Authoritative acquisition cost:** current authoritative acquisition cost of all non-recycled Finalized Economics batches, including active Phase 7A acquisition corrections.
- **Effective realized net proceeds:** merchandise revenue + shipping collected − marketplace fees − actual postage + other active sale adjustments, allocated once to included exact sale items. Marketplace-collected tax is excluded.
- **Active sold basis:** current known basis of sold card/sealed identities not currently restored by an active return. If any active sold item lacks trustworthy basis, the total and Realized P/L are Unknown/Incomplete.
- **Realized P/L:** effective realized net proceeds − active sold basis.
- **Operational loss/disposition:** active Phase 7A operational-loss entries for included finalized batches; it is reported separately and carries no tax conclusion.
- **Remaining known market/listed value:** the sum of known values for active remaining cards/bulk facts only. Missing prices and unopened sealed values stay Unknown and reduce coverage.
- **Cost Recovery %:** effective realized net proceeds ÷ authoritative acquisition cost × 100. It is uncapped and Unknown when acquisition cost is zero.
- **Current Economic Position:** effective realized net proceeds + known remaining market value − authoritative acquisition cost. It is explicitly incomplete when market coverage is incomplete.
- **Projected Listed Position:** effective realized net proceeds + known remaining listed value − authoritative acquisition cost. It is explicitly incomplete when listed coverage is incomplete.
- **Freshness:** oldest known underlying timestamp only when every valued fact has known freshness; otherwise **Freshness Unknown**.

## Schema and Migration

Phase 7C adds no migration, table, column, index, constraint, backfill, or stored calculated total. The ledger remains at `0001` through `0005_phase7b_post_sale_events`. Loading the portfolio API, page, or CSV must not write or repair any database fact.

## APIs, UI, and Export

- `GET /api/portfolio/economics`
- `GET /api/export/portfolio-economics.csv`
- Main navigation adds **Economics** and renders the four first-look answers: cost, recovered proceeds, known remaining market value, and current position.
- Additional sections show Realized Economics, Unrealized/Remaining Value, inventory and valuation coverage, scope/groups, per-batch reconciliation, and warnings.
- The CSV serializes the same backend payload and includes calculation version and generated timestamp.

## Test Summary

- Full Python suite: 86 tests passed.
- JavaScript syntax check: passed.
- Direct JavaScript Phase 4 viewport, Phase 5 sealed Sales details/Undo, Phase 7B event/detail, and Phase 7C backend-only rendering regressions: passed.
- Python compilation/import checks: passed for `app.py`, all runtime modules, and the Phase 7C seed helper.
- Correctness tests cover Finalized Economics scope, cost/recovery/P&L, active returns, refunds/chargebacks/credits/reversals, operational dispositions/reversals, canceled orders, marketplace-tax exclusion, card/sealed coverage, unknown valuations, and read-only API/export behavior.
- Reconciliation tests prove portfolio cost equals included batch cost and fully scoped order attribution equals each order's effective net exactly; duplicate attributed-item count remains zero.
- Performance fixture: the final run with 40 finalized batches and 4,000 cards calculated in 295.57 ms on the development workstation, below the 5-second regression guard.
- Disposable startup and `/api/health` returned 200 as `v2.1-test`; API and CSV both reported `acquisition-rip-v3`.

## Known Limitations and Technical Debt

- Unopened sealed market/listed valuation has no authoritative source field and therefore remains Unknown.
- Listed-value facts have no independent observed-at timestamp, so listed freshness is normally **Freshness Unknown**.
- Legacy estimated portfolio totals are intentionally not blended or synthesized; legacy estimates remain available per batch, with only their excluded scope shown at portfolio level.
- Card orders retain their stable historical equal-item allocation; explicit per-card sale prices remain future work.
- Receipt groups do not automatically allocate shared shipping, tax, discounts, or fees.
- Portfolio reporting recalculates on each request. The 4,000-card guard passes comfortably, but significantly larger inventories should be profiled before production promotion.
- `app.py` and `static/app.js` remain large; unrelated refactoring was deliberately avoided.
- The private-network runtime has no application authentication and must not be exposed publicly.

## Deployment Warnings and Rollback

- Production remains operator-controlled. Development used disposable local storage only; no live server, database, inventory, scanner folder, secrets, or credentials were accessed.
- Phase 7C has no schema mutation, but a runtime upgrading from an older phase may still apply the previously approved migrations. First validate the complete image against a timestamped disposable storage copy.
- Verify the exact Compose image/tag and storage mount before any operator-run deployment. Compose, Jenkins, ports, volumes, containers, and production settings were not changed.
- `scripts/preprod_phase2_gate.sh` is specific to Phase 2 and is not a Phase 7C validator.
- If startup or validation fails, stop only the failed/new runtime and restore the preserved Phase 7B application checkpoint. Because Phase 7C adds no migration, the same unchanged Phase 7B-compatible storage may be reused only if validation confirms no writes occurred. If an older runtime applied migrations during the attempt, restore its matching timestamped storage copy instead. Never downgrade or rewrite a database in place.

## Exact Upload Manifest

Upload these files/folders from the packaged checkpoint:

- `app.py`
- `dex_acquisition.py`
- `dex_batch_economics.py`
- `dex_corrections.py`
- `dex_economics.py`
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
- `PATCH_NOTES_v2.1-test.md`
- `PATCH_PLAN_ACQUISITION_RIP_BATCH.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE2.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE3.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE4.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE5.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE6.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE7A.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE7B.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE7C.md`
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
- `tests/fixtures/phase1_economics_scenarios.json`

## Exact Exclusion Manifest

Do **not** upload:

- `.git/`, `.agents/`, `.codex/`, IDE settings, or machine-specific metadata
- `__pycache__/`, `*.pyc`, `.pytest_cache/`, coverage output, test logs, or temporary files
- `data/`, `storage/`, `storage-v2.0-test/`, `storage-v2.1-test/`, `*.db`, `*.sqlite`, SQLite journal/WAL/SHM files, or database backups
- inventory/card images, generated labels, generated CSV exports, screenshots, browser downloads, or `outputs/`
- `scanner-inbox/`, inbound scan folders, source-database contents, or real inventory data
- `.env`, credentials, passwords, private keys, tokens, cookies, or secrets
- disposable Phase 7A/7B/7C storage/database folders
- the checkpoint-package directory nested inside the repository

## Disposable Operator Validation

1. Create new disposable storage: `python scripts/seed_phase7c_demo.py --output <new-empty-path>`.
2. Point `DEX_DATA_DIR`, `DEX_DB_PATH`, `DEX_IMAGE_DIR`, `DEX_INBOUND_DIR`, and `DEX_SOURCE_DB_DIR` at that path; set `DEX_WATCH_INBOUND=0`, choose a loopback-only non-production port, and run `python app.py`.
3. Confirm `/api/health` returns 200, runtime is `v2.1-test`, and normal Inventory, Inbound, Sales, Recycle Bin, rip, sealed, and Phase 7A/7B details still load.
4. Open **Economics**. Confirm the first screen shows cost, recovery, known remaining market value, and current position; legacy/unfinished batches remain separate.
5. Confirm Realized Economics uses the effective refund facts and marketplace tax is excluded. Open Sales to compare original and effective order facts.
6. Confirm the shared receipt reference is informational, the cross-batch order contributes once, duplicate attribution is zero, and portfolio-vs-batch cost/proceeds differences equal `$0.00`.
7. Confirm market/listed coverage and freshness are explicit, positions show incomplete when prices are missing, and remaining sealed value is Unknown.
8. Export Portfolio Economics CSV and confirm `acquisition-rip-v3` plus the displayed backend totals are present.
9. Compare the disposable database before/after these read-only views. No Phase 7C row, activity, event, or migration change is expected.
