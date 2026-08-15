# Dex v2.1-test Patch Notes

Status: v2.1-test development scope complete through Phase 7C; production deployment remains operator-controlled

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

### Phase 3 operator-smoke hotfix 1

- Prevent the batch detail view from crashing when an acquisition response omits the optional `receipt_group.batches` array.
- Default that presentation-only collection to an empty array; no economics calculation, schema, or acquisition rule changed.
- Bust the Phase 3 frontend asset cache so the corrected JavaScript loads immediately.
- Add a seeded OP16 batch-open regression covering all three batch-detail API payloads and the frontend fallback.

### Phase 3 operator-smoke hotfix 2

- Isolate the corrected Phase 3 frontend under a unique cache key after real-browser diagnostics found a paused Phase 4 frontend mixed with a Phase 3 backend on a reused disposable port.
- Confirm the exact stale expression was `rips.sessions.map(...)`; Phase 3 acquisition, receipt-group, card, and warning arrays were valid.
- Add a direct batch-detail renderer regression and preserve the corrected Phase 3 checkpoint as the known-good restore point.

## Phase 4: Rip Sessions, Bulk Reserves, and Immutable Basis

- Add explicit rip-session creation and activation. Creating a rip never assigns scanner intake automatically.
- Show a prominent active-rip banner and require confirmation before switching when the current batch has unprocessed scanner files.
- Associate browser/scanner intake with the one explicitly active rip while retaining `cards.batch_id` as the acquisition link.
- Allocate partial-rip cost from authoritative landed unit cost using deterministic exact-cent unit sequences.
- Support equal allocation, actual/manual per-card cost for known-cost singles, known-quantity bulk in the same equal allocation, and unknown-quantity bulk with an explicit manual reserve.
- Require a final `$0.00` reconciliation and two explicit confirmations before finalization.
- Lock finalized rips against ordinary intake and acquisition-fact edits.
- Store finalization and later basis corrections as append-only economic and basis events with immutable event IDs, duplicate-submission keys, effective/recorded timestamps, reason codes, and required correction notes.
- Retain basis and reconciliation when a participating card is recycled; active/excluded valuation presentation remains governed by the approved later reporting phases.
- Add defensive empty-array handling throughout the batch rip renderer and a Phase 4-specific asset cache key.
- Fix the Phase 4 intake-state regression found during operator QA: completing a batch now stops its active rip, and a completed batch cannot start scanner intake until it is explicitly reopened. Open batches with an active draft rip continue to accept repeated browser/scanner intake.
- Preserve the operator's logical viewport across same-batch button mutations by anchoring rerenders to stable rip, intake, card-list, and card identifiers. If the logical anchor was removed, restore the prior scroll position as a safe fallback.
- Polish the allocation modals without changing economics: show only the bulk quantity or manual reserve field applicable to the selected bulk mode, and align each final-confirmation checkbox with its wrapped, fully clickable confirmation sentence.
- Complete Phase 4 operator QA with slightly increased spacing between final-confirmation rows and before their action buttons; alignment, wrapping, label click targets, and native controls are unchanged.
- Package and import-check `dex_rip.py` in the runtime image.

## Approved Remaining Phases

- None within v2.1-test. Post-v2.1 work requires separate approval.

## Compatibility and Deployment

- Dex v2.0-test remains the documented baseline.
- Phase 1 added no operator-visible behavior; Phase 2 remained strictly read-only.
- Phase 3 adds the registered `0001_phase3_acquisition_facts` migration. It adds batch columns and a receipt-group index but does not backfill legacy cost into finalized economics.
- Phase 4 adds registered migration `0002_phase4_rip_sessions`. It adds rip/event tables and nullable intake links without assigning basis to legacy cards.
- Phase 5 adds registered migration `0003_phase5_sealed_inventory`. It classifies historical orders as `CARD`, mirrors their existing money facts into exact-cent compatibility fields, creates exact unit records only for trustworthy sealed acquisitions, and maps existing Phase 4 rips to stable lowest sequences.
- Phase 6 adds no schema migration or stored calculated totals. It derives every report/export value from existing Phase 1–5 source facts.
- Phase 7A adds registered migration `0004_phase7a_corrections_dispositions`. It creates empty append-only event, ledger-entry, and tombstone infrastructure without rewriting or backfilling acquisition, card, rip, sealed-unit, sale, or legacy facts.
- Phase 7B adds registered migration `0005_phase7b_post_sale_events`. It creates empty append-only post-sale event/entry/return-item tables and preserves historical sale rows/IDs while permitting a physically returned card to appear in a later order. It backfills no refund, return, chargeback, or correction.
- Phase 7C adds no migration, schema change, index, backfill, or stored calculated total. Its API and export are read-only.
- Docker packaging includes every Python module imported by `app.py`, including `dex_sealed.py`, `dex_batch_economics.py`, and `dex_portfolio_economics.py`. Compose, Jenkins, ports, volumes, containers, and server credentials remain unchanged and operator-controlled.

## Phase 3 Checkpoint Test Results

- `python -m unittest discover -s tests -q`: 35 tests passed in 1.411 seconds in the development workspace.
- `node --check static/app.js`: passed with the bundled Node runtime.
- Phase 3 validation, receipt-group, API, audit, CSV, finalized-lock, runtime-packaging, one-time migration, rollback, and UI-contract tests passed.
- All Phase 1 and Phase 2 regression tests passed, including the existing 2,500-card performance guard.
- Disposable migration tests confirmed the legacy source fixture remains unchanged and no permanent cost is backfilled.
- A disposable seeded API smoke test confirmed 6 OP16 boxes at $660.00 plus 2 ST27 decks at $86.40 reconcile to $746.40 under one informational receipt group.

## Phase 4 Checkpoint Test Results

- `python -m unittest discover -s tests -v`: 48 tests passed in 2.340 seconds after the Phase 4 modal polish.
- `node --check static/app.js`: passed with the bundled Node runtime.
- `node tests/test_phase4_viewport_context.cjs`: passed logical-anchor restoration and removed-anchor fallback coverage.
- New tests cover transactional migration rollback, one-time migration, explicit and repeated intake, completion-time intake shutdown, reopen recovery, pending-file switch confirmation, browser intake association, partial-unit cost, deterministic bulk/card allocation, known-cost singles, unknown bulk, finalization locks, correction idempotency/history, recycled basis retention, UI contracts, and runtime packaging.

## Phase 5: Sealed Inventory and Separate Sealed Sales

- Add stable unit records beneath each authoritative sealed acquisition with deterministic exact-cent basis and `REMAINING`, `OPENED`, `SOLD`, or `ADJUSTED` state.
- Make rip creation claim the exact lowest available unit sequences inside the same write transaction. Final rip cost now sums those exact records.
- Add a separate sealed-product Outbound mode and reject mixed card/sealed orders. Multi-unit orders retain exact unit IDs, basis, and deterministic merchandise-line cents.
- Record gross merchandise revenue, shipping collected, marketplace fees, actual postage, and marketplace-collected tax separately. Backend net proceeds exclude tax and equal merchandise + shipping - fees - postage; realized P/L equals net proceeds - sold basis.
- Prevent overselling with immediate SQLite write transactions plus conditional state updates. Specific unit IDs are supported by the API; otherwise the lowest available sequence is consumed.
- Add reason-aware quantity adjustment to the `ADJUSTED` state with immutable event/request IDs and retained notes.
- Make eligible sealed-sale Undo restore the exact units and mark the order canceled while preserving sale items and event history. Refunds/returns remain separate later work.
- Add a sealed-order **Details** action to Sales showing exact internal unit IDs/codes, recorded financial facts, status, and Undo eligibility. The order-specific Undo action reuses the atomic exact-unit restoration and keeps canceled history visible; card-order behavior is unchanged.
- Show exact sealed-unit reconciliation on the batch page and keep Receipt/Acquisition Groups informational only.
- Append Phase 5 sealed columns to the sales CSV without changing prior column meanings.

## Phase 5 Checkpoint Test Results

- `python -m unittest discover -s tests -v`: 58 tests passed.
- `node --check static/app.js`: passed.
- Existing direct JavaScript regressions passed for authoritative batch rendering, logical viewport preservation, and sealed Sales details/Undo.
- `node tests/test_phase5_sales_details.cjs`: passed direct Sales detail rendering, exact-unit display, targeted Undo integration, stable viewport anchor, and canceled-history rendering.
- Direct seeded batch rendering and logical viewport regressions passed against the disposable Phase 5 server.
- Real-browser smoke testing confirmed the OP16 batch renders six stable units, the sealed Outbound form renders backend-calculated exact unit/basis/net/P/L facts, and switching back to Card Sale removes the sealed form while preserving the existing card workflow.
- Concurrency coverage confirmed two simultaneous writers cannot sell the same final unit: one commits and one is rejected.

## Phase 6: Batch Economics Interface and Exports

- Add `dex_batch_economics.py` as the sole calculation service for authoritative batch reports, Receipt/Acquisition Group rollups, and batch-economics export rows. Calculated totals are derived per request and never stored.
- Add `GET /api/batches/{id}/economics/report` and `GET /api/acquisition-groups/{reference}/economics`; both include calculation version `acquisition-rip-v1` and perform no writes.
- Add a collapsible batch interface in the approved order: Summary, Acquisition, Recovery & P/L, Remaining Inventory, Rip Sessions, Sales, and Reconciliation / Warnings.
- Make the Summary answer authoritative cost, realized recovery, known remaining market value, and current ahead/behind position in the first screenful.
- Keep Realized Economics distinct from Unrealized/Remaining Value. Cost Recovery is realized net proceeds divided by authoritative acquisition cost and is not capped. Current and Projected positions use market and listed values independently and never substitute one for the other.
- Show coverage beside price-dependent values, mark positions incomplete when values are unknown, and display the oldest known underlying market timestamp or **Freshness Unknown**.
- Show recycled cards and adjusted sealed units separately so their known basis/value does not inflate active remaining inventory.
- Reuse one stable sale-item allocation for historical cross-batch card orders. Batch reports show attributable portions; group rollups count unique orders once and do not duplicate revenue, fees, postage, or proceeds.
- Label Receipt/Acquisition Group rollups as informational and state that shared costs were not allocated automatically.
- Add `GET /api/export/batch-economics.csv`. Append calculation/basis provenance to Inventory CSV and inclusion/attribution provenance to Sales CSV without changing earlier columns or meanings.
- Keep legacy batches on the existing visually unmistakable read-only estimate path; Phase 6 does not convert or finalize them.

## Phase 6 Checkpoint Test Results

- `python -m unittest discover -s tests -q`: 64 tests passed in 2.882 seconds.
- `node --check static/app.js`: passed.
- Python compilation/import checks passed for `app.py` and every packaged v2.1-test module.
- A 2,500-card authoritative batch report completed inside the 2.0-second regression guard; the complete five-test Phase 6 module, including setup and assertions, completed in about 0.06 seconds on the development workstation.
- Disposable browser QA confirmed the approved section hierarchy, first-screen answers, 102.5% uncapped recovery, realized P/L, 1/2 coverage, timestamp/unknown freshness, incomplete positions, exact basis/quantity reconciliation, rip/sale history, informational group notice, and unchanged intake/label controls.

## Phase 7A: Corrections and Dispositions

- Add `dex_corrections.py` as the dedicated append-only service for acquisition-cost corrections, finalized card/rip-bulk basis transfers, card dispositions, sealed-quantity corrections, and linked reversals.
- Preserve finalized source facts. Current authoritative cost and basis equal preserved source facts plus immutable signed ledger entries; no correction overwrites original batch, rip-basis, sealed-unit, or sale facts.
- Give every economic event an immutable `ECO7A-*` ID, unique request/de-duplication ID, standardized reason, effective date, separately recorded timestamp, required operator notes, payload snapshot, and calculation version.
- Allocate sealed acquisition-cost changes deterministically across stable internal unit IDs with exact-cent reconciliation. Singles corrections require an explicit finalized card or rip-bulk target.
- Treat Duplicate/Entry Error as reallocation, Correction Hold as excluded basis retention, and physical Damaged/Missing-Lost/Disposed/Other as operational loss. DEX explicitly makes no tax conclusion.
- Preserve durable card/sealed tombstones and block normal hard purge or auto-purge when economic history exists. Card restoration from an active disposition is available only through the event's linked inverse reversal.
- Keep sealed quantity reconciliation exact while an adjusted unit remains represented in the stable unit ledger.
- Recalculate Phase 6 batch/group economics and exports from source facts plus Phase 7A entries; no dashboard total is stored and frontend JavaScript performs formatting only.
- Add a disposable Phase 7A seed helper that refuses existing output paths and creates one finalized OP16 rip with four allocated cards and five remaining sealed units.
- Package and build-time import-check `dex_corrections.py`; production/Compose/Jenkins settings remain unchanged.

## Phase 7A Checkpoint Test Results

- `python -m unittest discover -s tests -q`: 72 tests passed.
- `node --check static/app.js`: passed.
- Direct JavaScript regressions passed for authoritative batch rendering, logical viewport preservation, and sealed Sales details/Undo.
- New coverage verifies one-time/rollback-safe migration, deterministic cent corrections, de-duplication, card/bulk transfers, duplicate reallocation, physical loss, exact sealed disposition, tombstones, purge protection, linked inverse events, API/UI contracts, and current economics reconciliation.
- A 1,000-card finalized corrections payload stayed inside the 2.0-second performance guard.
- Disposable browser QA verified acquisition correction/reversal, exact `$0.00` reconciliation, sealed damage to Operational Loss, card disposition, protected Recycle Bin history, and linked restoration.

## Phase 7B: Post-Sale Events

- Add `dex_post_sale.py` as the dedicated service for immutable `PARTIAL_REFUND`, `FULL_REFUND`, `CUSTOMER_RETURN`, `CHARGEBACK`, `MARKETPLACE_FEE_CREDIT`, `POSTAGE_REFUND`, `SALE_CORRECTION`, and linked `REVERSAL` events.
- Keep original `sale_orders`, `sale_items`, and `sealed_sale_items` visible and unchanged. Effective merchandise, shipping, fees, postage, other net adjustments, net proceeds, active sold basis, and realized P/L are recalculated from original facts plus signed event entries.
- Require a unique request ID, standardized reason, effective date, separately recorded timestamp, and durable immutable event ID for every event. Material manual corrections and every reversal require notes.
- Keep refunds, returns, and chargebacks distinct. Refunds and chargebacks never restore inventory. Marketplace fee credits and actual carrier/postage refunds are separate events.
- Require explicit physical-receipt and condition confirmation before a return. Restore exact card/sealed identities at most once; sellable returns become active inventory and damaged returns become Damaged/Excluded.
- Preserve the basis of returned items. Active returned items leave sold basis and return to active or excluded basis; no financial refund is inferred from a physical return.
- Make return reversals atomic and state-aware. If an identity was edited, sold, opened, or otherwise changed after restoration, DEX refuses an unsafe reversal.
- Preserve damaged-return history in Recycle Bin. Ordinary Restore is blocked; the operator opens the originating Sales order and creates a linked inverse event.
- Replace the legacy one-lifetime-sale-per-card constraint with `UNIQUE(order_id, card_id)`, preserving all historical item IDs and allowing a confirmed returned card to be sold again. Current card state and immediate transactions still prevent simultaneous sales.
- Reuse the original immutable sale-item weights for every later cross-batch adjustment. Batch views show attributable effective portions and Receipt/Acquisition Group totals count the order once.
- Add a Sales detail view for card and sealed orders with original facts, effective Realized Economics, exact item identities, return state, immutable event history, event actions, and linked reversal controls.
- Append post-sale/effective fields to Sales CSV without changing prior column meanings. Batch economics and group rollups automatically serialize the backend effective facts.
- Advance economics calculation version to `acquisition-rip-v2` so reports identify the Phase 7B ruleset.
- Package and build-time import-check `dex_post_sale.py`; production/Compose/Jenkins settings remain unchanged.

## Phase 7B Checkpoint Test Results

- Full Python suite: 82 tests passed, including all Phase 1–7A regressions.
- JavaScript syntax, authoritative batch-detail rendering, logical viewport preservation, sealed Sales details/Undo, and direct Phase 7B Sales event/detail regressions passed.
- Python compile/import checks passed for `app.py`, every packaged runtime module, and the disposable seed helper.
- New coverage verifies transactional legacy sale-item migration, preserved row IDs, partial/full refunds, chargebacks, fee credits, postage refunds, sale corrections, exact card/sealed returns, damaged Excluded routing, linked inverses, request de-duplication, immutable originals, concurrent at-most-once restoration, stable cross-batch attribution, HTTP APIs, and backend effective P/L.
- The disposable Phase 7B seed helper passed and created only new local test storage with one finalized batch, a two-card order, and an exact sealed-unit order. Startup and `/api/health` returned `v2.1-test` from that storage.

## Phase 7C: Portfolio Operational Economics

- Add `dex_portfolio_economics.py` as the read-only portfolio calculation service. It includes Finalized Economics batches only and keeps legacy estimates and unfinished authoritative batches outside every authoritative total.
- Add **Operational Economics** to the main navigation. The first view answers acquisition cost, recovered net proceeds, known remaining market value, and current position; realized and remaining-value sections stay visually separate.
- Derive effective proceeds from original orders plus Phase 7B events. Canceled orders and reversed event deltas follow their effective state; marketplace-collected tax remains excluded.
- Count immutable card sale-item IDs and exact sealed sale-item IDs once. Cross-batch orders retain their original stable weights, and only the finalized-batch portion enters portfolio totals when an order spans excluded scope.
- Report active sold basis, realized P/L, operational loss/dispositions, remaining known market/listed values, uncapped Cost Recovery, Current Economic Position, and Projected Listed Position from backend source facts only.
- Show card, sealed-unit, and bulk counts with explicit coverage, incomplete/unknown states, and valuation freshness. Market and listed value never substitute for one another; unopened sealed valuation remains Unknown without an authoritative fact.
- Keep Receipt/Acquisition Group rollups informational and explicitly state that shared costs were not allocated automatically.
- Add `GET /api/portfolio/economics` and a read-only `GET /api/export/portfolio-economics.csv`; both serialize calculation version `acquisition-rip-v3`. No calculated total is stored.
- Add a disposable Phase 7C seed helper covering finalized sealed/singles batches, a shared receipt reference, cross-batch sale attribution, effective refund history, sealed sales, an operational disposition, a legacy estimate, and unfinished authoritative batches.
- Package and build-time import-check `dex_portfolio_economics.py`; production/Compose/Jenkins settings remain unchanged.

## Phase 7C Checkpoint Test Results

- Full Python suite: 86 tests passed, including every Phase 1–7B regression.
- JavaScript syntax and all direct frontend regressions passed, including backend-only Operational Economics rendering.
- Python compile/import checks passed for the application, all runtime modules, and the Phase 7C seed helper.
- Tests prove exact cost/proceeds reconciliation, stable cross-batch attribution, no duplicate item/order contribution, canceled-order exclusion, Phase 7B effective refunds/reversals, active-return basis, Phase 7A dispositions/reversals, marketplace-tax exclusion, unknown sealed valuation, API/CSV parity, and read-only database behavior.
- The final portfolio performance run with 40 finalized batches and 4,000 cards calculated in 295.57 ms on the development workstation, below the 5-second regression guard.
- Disposable startup returned `/api/health` 200 as `v2.1-test`; Operational Economics reported calculation version `acquisition-rip-v3`, exact batch/portfolio reconciliation, and the versioned CSV from the same copied facts.

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
