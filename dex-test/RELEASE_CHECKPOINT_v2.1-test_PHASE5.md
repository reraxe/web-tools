# Dex v2.1-test Phase 5 Git-ready Checkpoint

Checkpoint scope: exact sealed-unit inventory, rip consumption of exact units, separate sealed-product outbound orders, sealed economics, reason-aware quantity adjustment, and atomic sale Undo. Phase 6 is not included.

Known-good restore point: preserve `DEX_v2.1-test_Phase4_GitHub_Checkpoint` unchanged with its matching pre-Phase-5 storage copy.

## Runtime Behavior

- A trustworthy homogeneous sealed acquisition owns one stable internal record per acquired unit.
- Final USD paid is divided across stable unit sequences with deterministic exact-cent allocation. Remainder cents always go to the lowest sequence.
- Unit states are `REMAINING`, `OPENED`, `SOLD`, and `ADJUSTED`.
- Creating a rip consumes exact lowest available units in the same SQLite write transaction. Existing activation, intake, allocation, completion, and label behavior remains unchanged.
- Sealed sales use a separate Outbound mode and cannot contain cards. The card-sale path remains separate.
- If exact identical unit IDs are not supplied, a sale consumes the lowest remaining stable sequences.
- Sealed order economics are backend-generated from merchandise revenue, shipping collected, marketplace fees, actual postage, and separately recorded marketplace-collected tax. Tax is excluded from revenue and P/L; packaging/supplies remain separate.
- Multi-unit orders retain exact unit IDs, deterministic merchandise-line cents, sold-basis snapshots, net proceeds, and realized P/L.
- Availability is checked under an immediate SQLite write transaction and each transition uses a conditional state update, preventing one unit from being opened/sold twice.
- Eligible Undo restores the exact units atomically and retains the canceled order, item links, and inverse unit events.
- Sales exposes an explicit sealed-order Details view with exact internal unit IDs/codes, recorded financial facts, canceled status, and current Undo eligibility. The order-specific action cannot target a different order, and the stable Sales row anchor preserves logical viewport context after Undo.
- Quantity adjustment requires a standardized reason, uses an immutable request/event ID, and moves only a remaining unit to `ADJUSTED`.
- Every batch reconciles acquired = opened + sold + remaining + corrected/adjusted.
- Receipt/Acquisition Groups remain informational and never change or allocate basis.

## Files Changed Since Phase 4

- `app.py`
- `dex_migrations.py`
- `dex_rip.py`
- `Dockerfile`
- `static/app.js`
- `static/index.html`
- `static/styles.css`
- `tests/test_app.py`
- `tests/test_phase3_acquisition.py`
- `tests/test_phase4_rip.py`
- `DEX_CURRENT_STATE.md`
- `DEX_OPERATING_MODEL.md`
- `MIGRATION_NOTES_v2.1-test.md`
- `PATCH_NOTES_v2.1-test.md`
- `PATCH_PLAN_ACQUISITION_RIP_BATCH.md`
- `README.md`
- `WEEKLY_ROADMAP.md`

New files:

- `dex_sealed.py`
- `tests/test_phase5_sealed.py`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE5.md`

`VERSION` remains the approved `v2.1-test` value and is included in the package.

## Schema and Migration

Registered migration: `0003_phase5_sealed_inventory`.

It adds `sealed_units`, `sealed_sale_items`, and `sealed_unit_events`; exact-cent and order-type compatibility columns to `sale_orders`; cancellation/tombstone fields; and sealed lookup indexes. Existing sale orders become `CARD` without changing their dollar facts. Trustworthy sealed acquisitions receive deterministic unit records. Existing Phase 4 rips consume matching lowest unit sequences in stable rip ID order. Unknown-cost and legacy batches receive no sealed basis.

Migration execution and its ledger marker share one SQLite savepoint. Forced-failure coverage confirms sale columns, sealed tables, and the marker roll back together.

See `MIGRATION_NOTES_v2.1-test.md` for exact behavior and rollback.

## API and UI

Added read APIs:

- `GET /api/sealed-inventory`
- `GET /api/batches/{id}/sealed-units`
- `GET /api/sealed-sales/{id}`

Added mutation/preview APIs:

- `POST /api/sealed-sales/preview`
- `POST /api/sealed-sales`
- `POST /api/sealed-sales/{id}/undo`
- `POST /api/sealed-units/{id}/adjust`

Extended `GET /api/sales`, `GET /api/sealed-sales/{id}`, sales CSV, rip payloads, rip creation, and existing Undo. The Sales page now provides sealed-order Details and eligible order-specific Undo while leaving card rows unchanged. The batch page shows Sealed Unit Inventory and reconciliation. Outbound offers clearly separate Card Sale and Sealed-Product Sale modes.

## Tests and Results

- Full Python suite: 58 tests passed (`python -m unittest discover -s tests -v`).
- Frontend syntax: `node --check static/app.js` passed.
- Direct Sales UI execution: `node tests/test_phase5_sales_details.cjs` passed details opening, exact unit ID display, targeted Undo request, stable viewport anchor, and retained canceled history.
- Seeded batch-detail renderer passed against the disposable Phase 5 server.
- Logical viewport regression passed.
- Disposable real-browser smoke passed for the OP16 sealed ledger, sealed Outbound form, backend preview, and return to the unchanged card form.
- Concurrency test: two simultaneous immediate transactions attempted to sell one final unit; exactly one committed and one was rejected.
- Reconciliation tests cover `$10.00 / 3 = $3.34 / $3.33 / $3.33`, exact multi-unit sold basis, tax exclusion, net/P&L, rip claims, adjustments, overselling, idempotency, and atomic Undo.

## Known Limitations and Deferred Work

- Phase 5 supports homogeneous whole sealed units only. Nested box-to-pack/component transformations are deferred.
- The operator UI chooses batch and quantity; explicit exact unit selection is available through the API but not yet exposed as a unit-picker UI.
- Sealed quantity adjustment is a one-way audited `ADJUSTED` state in this phase. Linked reversal/disposition accounting is Phase 7A.
- Refunds, returns, chargebacks, fee credits, postage refunds, and post-sale corrections are Phase 7B.
- Batch/portfolio economics dashboards, remaining sealed market/listed values, valuation coverage, freshness, and versioned economics exports are Phase 6/7C.
- Legacy card orders retain the existing equal per-card `sale_price` split. Phase 5 does not reinterpret historical card-line facts.
- Draft rip sessions still have no cancel/delete workflow; creating a sealed rip means those exact units are considered opened.
- Authentication remains absent; keep DEX private.

## Deployment Warnings

- Production remains operator-controlled. This checkpoint accessed no server, credentials, production storage, or real inventory database.
- Migration `0003` changes schema and creates deterministic unit rows for trustworthy sealed acquisitions. Test only against a disposable copy before any operator-approved deployment.
- The old Phase 2 pre-production script expects ledger-only mutation and is not a valid Phase 5 gate.
- `Dockerfile` now copies and import-checks `dex_sealed.py`. Compose, Jenkins, ports, volumes, and production tags were not changed.
- Rebuilding the image should replace application code only, but application startup will apply pending migrations to whichever storage is mounted. Verify the mount before starting a Phase 5 image.

## Rollback

1. Stop only the failed/new Phase 5 runtime.
2. Restore the Phase 4 application checkpoint.
3. Attach the matching timestamped pre-Phase-5 storage copy.
4. Verify health, inventory, batches, labels, card sales, Recycle Bin, acquisition facts, and rip sessions.

Do not attempt an in-place schema downgrade and do not delete or rewrite migrated storage.

## Exact Upload Manifest

Upload these source paths:

- `VERSION`
- `app.py`
- `dex_acquisition.py`
- `dex_economics.py`
- `dex_legacy_economics.py`
- `dex_migrations.py`
- `dex_rip.py`
- `dex_sealed.py`
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
- `tests/test_phase5_sealed.py`
- `tests/test_phase5_sales_details.cjs`
- `DEX_CURRENT_STATE.md`
- `DEX_OPERATING_MODEL.md`
- `MIGRATION_NOTES_v2.1-test.md`
- `PATCH_NOTES_v2.1-test.md`
- `PATCH_PLAN_ACQUISITION_RIP_BATCH.md`
- `README.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE2.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE3.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE4.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE5.md`
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

Use a new temporary data directory with `DEX_SEED_DEMO=1` and `DEX_WATCH_INBOUND=0`. Open OP16 batch `OP-B20260814-01`, verify six `$110.00` remaining unit records and exact `6 = 0 + 0 + 6 + 0` reconciliation, then create a disposable multi-unit sealed sale from the Outbound page. In Sales, open **Details**, verify exact unit IDs and financial facts, use **Undo sealed sale**, and confirm the same row remains visible as canceled while the exact units return to remaining inventory. Do not use real inventory data.
