# Dex Weekly Roadmap

Last updated: 2026-06-23

## Release Cadence

Dex should move in weekly, low-drama steps.

- Weekdays, 9-5: testing, bug logging, docs, source database prep, API planning, and small quality-of-life improvements.
- Evenings: scanner/server checks, SAM matching tests, labels, outbound sales, and physical workflow validation.
- End of week: decide whether the active test version is stable enough to promote.
- Stable versions are used for real inventory work.
- Test versions are where we add new features and shake them down.
- Every release package should ship with patch notes and a short README/docs summary so the GitHub push explains both what changed in Dex and what changed in the operator instructions.

## Promotion Rule

A test version can become stable after:

- core tests pass
- no active blocker bugs remain
- scanner/import flow works
- labels print correctly
- outbound flow works
- Recycle Bin/undo behavior works
- user has run at least one real inventory session without major pain

## Preserved Baseline

### v2.0-test: SAM One Piece Recognition

Goal: reduce manual card entry by matching One Piece scans against a local source database.

Weekday focus:

- Build and refine the source database folder.
- Run API/backend tests.
- Improve docs and test scripts.
- Log SAM mismatch patterns.
- Decide what confidence scores feel trustworthy.

Home/server focus:

- Load OP16 source images.
- Rescan SAM source.
- Import a small OP16 batch.
- Run SAM Match All.
- Check label queue after matching.

Potential promotion:

- `v2.0-test` can become `v2.1-stable` if SAM is useful enough and does not disrupt the stable inventory workflow.

See `DEX_OPERATING_MODEL.md` for the full Dex, SAM, Janna, and Project: Goose workflow.

## Preserved Known-good Lane

### v2.1-test: Acquisition and Rip Batch Economics

Goal: connect acquisition cost to sealed inventory, partial rips, resulting physical cards, realized sales, remaining value, cost recovery, and operational profit/loss.

Implementation gates:

- Phase 1: complete — transactional migration foundation, deterministic exact-cent allocation, and approved-rule fixtures.
- Phase 2: complete — read-only estimated legacy economics.
- Phase 3: complete — acquisition cost facts and informational Receipt/Acquisition Groups.
- Phase 4: complete — explicit rip sessions, bulk reserves, immutable basis, and audited corrections.
- Phase 5: complete — sealed-unit inventory, exact rip/sale consumption, separate sealed-product sales, adjustments, and atomic Undo.
- Phase 6: complete — backend-calculated batch economics UI, reconciliation/history drill-downs, group rollups, coverage/freshness, and versioned exports.
- Phase 7A: complete — append-only corrections, reason-aware dispositions, durable tombstones, operational-loss treatment, and linked inverse reversals.
- Phase 7B: complete — immutable refunds, returns, chargebacks, fee/postage credits, sale corrections, and exact confirmed return restoration.
- Phase 7C: complete — read-only portfolio Operational Economics, Finalized Economics scope, effective Phase 7B proceeds, exact stable attribution, coverage/freshness, reconciliation, and versioned CSV.

Rules:

- Finish and test each phase before starting the next.
- Keep v2.0-test as the implementation baseline.
- Keep production/server deployment configuration unchanged until an explicitly approved deployment step.
- Treat DEX economics as operational reporting, not tax-accounting conclusions.

See `PATCH_PLAN_ACQUISITION_RIP_BATCH.md` for the approved design and safeguards.

## Current Active Lane

### v2.2-test: Inbound 2.0

Goal: separate purchase/acquisition creation from later inventory processing while preserving the Phase 3–7C economics model.

Implementation gates:

- Phase 1: complete — additive Draft Acquisition, product-line, lifecycle-event, state-machine, API, migration, and compatibility foundation. No operator-facing replacement yet.
- Phase 2: complete — focused three-screen New Acquisition wizard, resumable drafts, Accounting-by-Default one-line allocation, backend per-unit cents and audit evidence, exception-only multi-line/manual resolution, lightweight Needs Attention metadata, and legacy New Batch compatibility. No downstream projection.
- Phase 3: complete — local commercial-product catalog, validated UPC/EAN/GTIN/internal identifiers, keyboard-scanner intake, quantity aggregation, unknown/manual/remember flows, and audited mapping correction. No downstream projection.
- Phase 4: complete — private provider-neutral source-document storage, hashes/integrity, retry/tombstone history, and Google Drive-compatible boundary. No extraction in this phase.
- Phase 5: complete — local text-PDF receipt extraction, normalized non-authoritative candidates, receipt-line matching/classification, and deterministic exact-cent accounting proposals.
- Phase 6: accepted — partial/resumable routing of confirmed lines into established homogeneous batches, exact sealed units, rip/open, and acquired-singles intake.
- Phase 7: implemented, operator QA pending — One Piece-only conservative SAM recognition, OPTCG structured metadata cache, incremental local reference index, non-blocking review queues, local Find Match, and durable suggestion/decision evidence.
- Cross-TCG SAM, JANA, global Attention Center, autonomous retraining, and production deployment: not authorized.

Rules:

- Preserve the immutable v2.1-test Phase 7C checkpoint.
- Preserve every accepted Phase 1–6 checkpoint; SAM Recognition + Human Review Phase 7 is the current development checkpoint.
- Project confirmed acquisition lines only through the accepted Phase 6 bridge; do not replace established economics services.
- Keep SAM identity-only. Do not let recognition assign basis, change economics, or feed later pricing/listing automation without a separate phase.
- Apply the approved Accounting-by-Default rule to future phases: backend deterministic automation, visible results without repetitive tasks, and Needs Attention only for ambiguous or exceptional reality.
- Keep the future Attention Center at design-contract status until separately authorized.
- Test all migrations on disposable Phase 7C copies before any operator-authorized deployment.

See `PATCH_PLAN_INBOUND_2.md` for the approved architecture and phase gates, and `DEX_ACCOUNTING_BY_DEFAULT.md` for the standing automation/attention design contract.

## Next Planned Versions

### v2.3-test: What's New Hub

Goal: put Dex updates, daily agenda, roadmap, and known issues inside the app.

Scope:

- Add **What's New** to the sidebar near the lower-left utility area.
- Show current version.
- Show patch notes.
- Show daily agenda.
- Show roadmap cards.
- Keep Market Watch as a placeholder tab for now.

Why next:

- It helps us test weekly without losing track of what changed.
- It makes Dex feel more like an operating system for the business.

### v2.4-test: One Piece API Cache + Manual Market Watch

Goal: start Janna, the Market Watch layer, and turn Dex into a card knowledge and market awareness tool.

Scope:

- Add OPTCG API cache planning or first adapter.
- Add local/manual Market Watch posts for Janna.
- Store Market Watch notes in SQLite.
- Tag posts by game, set, marketplace, and watchlist.
- Summarize market notes into hold, watch, list, and research signals.

### v2.5-test: Inventory Signals

Goal: start Project: Goose as recommendation-only inventory and sales support.

Scope:

- Show cards missing prices.
- Show TCGplayer candidates under $20.
- Show eBay candidates at $20+.
- Show cards with low SAM confidence.
- Show sell, hold, watch, and review recommendations from Janna signals.
- Begin CardDex/MTGJSON source planning.

### v2.5-test: Pricing Recommendations

Goal: let Goose suggest price changes without silently changing business-critical fields.

Scope:

- Add suggested price fields.
- Add suggested platform fields.
- Add recommendation reasons.
- Add one-click apply after user review.
- Keep automatic price adjustment out of scope until the algorithm is proven.

### v2.6-test: Portfolio Analytics

Goal: add stock-portfolio-style inventory value tracking.

Scope:

- Add price snapshot storage.
- Add total inventory market value graph.
- Add daily, weekly, monthly, quarterly, and yearly time frame controls.
- Show top 3 positive movers.
- Show top 3 negative movers.
- Keep realized sales separate from unrealized inventory value.

See `PORTFOLIO_ANALYTICS_PLAN.md` for the full value graph, snapshot, and top-movers plan.

### v2.7-test: Marketplace Connector Prep

Goal: prepare eBay connection once developer approval and HTTPS are ready.

Scope:

- eBay credentials checklist.
- OAuth connection screen.
- Server-only token storage plan.
- Listing/order mapping table.
- No auto-posting until the flow is proven.

### v2.8-test: Broader Card Knowledge Sources

Goal: expand source data planning beyond One Piece.

Scope:

- CardDex adapter research for Pokemon TCG.
- PokeAPI support metadata plan.
- MTGJSON import size and useful-field review.
- Decide what belongs in Dex now versus later.

### v3.0-test or Later: DPS

Goal: Dex Pre-grading System for high-value cards.

Scope:

- Flatbed scan workflow.
- Centering measurements.
- edge/corner review.
- surface scan report.
- score summary and confidence notes.

See `DPS_PLAN.md` for the full DPS capture, measurement, validation, and safety plan.

## Weekday Work Menu

Good tasks while away from the scanner:

- Run automated tests.
- Update patch notes.
- Review screenshots.
- Write test checklists.
- Build small UI improvements.
- Prepare card/source metadata.
- Plan API credentials and storage.
- Document bugs from server testing.

Tasks that need home/scanner/server time:

- actual scan imports
- source image uploads to the server
- SAM matching against real scans
- label printing
- outbound phone scan tests
- HTTPS/camera tests
- Docker/Jenkins deployment checks

## Daily Question

Each morning, answer:

```text
What version are we testing today, and what is the one thing that would make it better?
```

If there is no clear upgrade needed, we stabilize instead of adding noise.
