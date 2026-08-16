# DEX v2.2-test — Inbound 2.0 Phase 6 Checkpoint

Status: implementation complete; operator QA required; production deployment **NOT APPROVED**  
Scope cutoff: Downstream Intake Bridge only  
Runtime identity: `v2.2-test`  
Known-good predecessors: accepted Phase 5 Receipt Intelligence and Pre-Phase UX Hotfix checkpoints

## Included Scope

- Continue Intake from confirmed acquisitions without replacing the Phase 3–7C batch/economics architecture.
- Partial, resumable line routing for Keep Sealed, Rip/Open, Scan & Identify, and Decide Later.
- One homogeneous batch per acquisition line through `batches.acquisition_line_id`.
- Automatic transfer of confirmed line landed cost and deterministic exact-cent unit basis.
- Exact sealed-unit creation, pending-unit protection, existing rip preparation, and existing card-intake continuation.
- `READY_FOR_INTAKE` → `INTAKE_IN_PROGRESS` → `INTAKE_COMPLETE` from derived quantity reconciliation.
- Append-only routing operations/events, unique request IDs, preview tokens, optimistic revisions, and transactional projection.
- Operator-facing status, preview, confirmation, additional-routing, downstream-link, and continue APIs/UI.

Not included: SAM recognition, new accounting formulas, marketplace integrations, global Attention Center, authentication, production deployment, or production-data work.

## Migration Ledger

Latest migration: `0013_v22_phase6_downstream_intake_bridge`

It adds:

- `acquisition_intake_operations`
- `acquisition_line_projections`
- `acquisition_intake_route_events`
- `sealed_units.intake_disposition`
- uniqueness and lookup indexes for one projection per line and stable routing

The migration is additive and performs no historical acquisition inference or batch linkage. Existing sealed units receive the compatibility value `LEGACY_AVAILABLE`. Startup creates no acquisition, batch, card, sealed unit, rip, or route. A forced-conflict regression verifies that schema changes and the migration marker roll back together.

## Routing and Reconciliation

- Sealed/Pack lines: `acquired = kept sealed + rip/opened + undecided`.
- Singles lines: `acquired = scan/identify + undecided`.
- Every line retains `confirmed landed cost = routed basis + undecided basis`, with exact `$0.00` difference.
- Remainder cents follow immutable unit/quantity ordinals. UI sorting, labels, names, and scan order cannot change allocation.
- Pending sealed units cannot be sold or opened. Rip/Open consumes the lowest stable unit explicitly routed to Rip/Open.
- Singles receive no invented per-card basis. Their line cost remains pending in the existing rip allocation workflow until all intended quantity is routed and finalization is explicitly confirmed.

## Compatibility and Safety

- Existing unlinked batches and sealed units retain prior behavior.
- Existing rip activation remains explicit; routing never activates scanner intake.
- Batch completion, labels, card intake, sealed sales, Undo, corrections, dispositions, returns, receipt groups, portfolio economics, catalog, documents, and receipt intelligence remain in their established services.
- Projected acquisitions immediately become protected dependencies; draft recycle/confirmed cancellation cannot erase linked inventory history.
- Retry/double-click uses request replay. Concurrent stale routing fails before duplicate batch, sealed-unit, or rip creation.
- Receipt/source-document and catalog provenance remain attached through the unchanged acquisition line; blobs and extraction rows are not copied into batches.

## Verification

- Python suite: **153 passed**, including 8 new Phase 6 service/API/migration/concurrency/performance tests.
- JavaScript syntax: **passed**. Eleven frontend regressions passed, including the server-backed batch-detail rendering contract.
- Docker build context includes and import-checks `dex_intake_bridge.py` beside `app.py`; direct packaged-module imports passed.
- Disposable startup: `/api/health` returned HTTP 200 with version `v2.2-test`.
- Phase 6 performance: 75 acquisition lines / 150 exact sealed units routed in **43.83 ms** in the final full-suite run (limit: five seconds).
- Browser QA: acquisition list states, partial-route resume, backend preview (`$24.00`, stable ordinals 3–4, `$0.00` difference), Intake Complete transition, linked batch, `$330.00` three-unit basis, and draft rip navigation all passed.

## Disposable Operator QA

Create new disposable storage with:

`python scripts/seed_v22_phase6_intake_bridge_demo.py --output <new-empty-path>`

Launch DEX with every data/database/document/scanner/source path pointed at that new directory and scanner watching disabled. Never point this checkpoint at production or real ShonenRiot storage for QA.

- Scenario A `ACQ-P6-A-SPLIT`: verify three OP16 Booster Boxes at `$330.00` reconcile as one exact opened unit at `$110.00` plus two available sealed units totaling `$220.00`; quantity and basis differences are `$0.00`.
- Scenario B `ACQ-P6-B-PARTIAL`: verify the Pack Product line is complete, the four-unit sealed line has two routed and two undecided, and acquisition state is Intake in Progress. Route the final two and verify Intake Complete.
- Scenario C `ACQ-P6-C-SINGLES`: open Continue Scanning, verify the existing batch/card intake surface and acquisition provenance, and confirm no per-card basis was invented.
- Scenario D `ACQ-P6-D-RETRY`: verify the same request was replayed without duplicate batch, units, or route quantity.

## Rollback

Do not manually unlink projected batches, delete route rows, reset unit dispositions, drop tables, or remove migration-ledger entries.

- Before any Phase 6 route exists: restore the preserved Pre-Phase/Phase 5 application checkpoint and its matching pre-`0013` disposable database copy.
- After routing exists: restore the matching pre-route database copy together with the prior application checkpoint. Older code cannot safely expose Phase 6 pending-unit semantics.
- Production rollback remains an operator-approved deployment action and is not authorized by this checkpoint.

## Approval Gate

Phase 6 requires the disposable operator QA above. Production remains operator-controlled. SAM or any next phase requires separate explicit approval.
