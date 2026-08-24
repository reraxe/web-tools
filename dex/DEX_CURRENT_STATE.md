# Dex Current State

Baseline date: 2026-08-24  
Known-good restore baseline: `v2.2-test RC3 HF3 ZERO ENTRY`  
Active promotion candidate: `v2.4-live`; package only, not deployed  
Accepted TEST source: `v2.4-test-sam-multi-evidence-operator-trial-v1a`, fingerprint `dd899b6f73891252395ae9b8d09b43906ad15c656f0a0c739bd15a916c012493`

`v2.4-live` is the one-time creation of DEX LIVE with clean business state and a permanent, separately writable storage lineage. Existing TEST storage remains the development archive. Future LIVE releases reuse the LIVE lineage and preserve inventory, acquisitions, receipts, sales, SAM audit history, WOLFF records, and future intelligence history. No normal version promotion authorizes a reset.

The accepted audited multi-evidence build is integrated as a suggestion-only One Piece intake workflow. DEX freezes its original result before catalog lookup or operator action, preserves decisions and optional verified truth separately, and grants family authority only through an explicit operator confirm/correct action. Exact printing remains manual. WOLFF, receipt intelligence, established SAM, production configuration, and all earlier economics rules remain unchanged.

HF3 remains frozen and is the immediate rollback checkpoint. Phase 1 adds a non-authoritative semantic layer before product matching, with migration 0016 and an operator review surface. It does not change receipt allocation, mixed-purchase `POLICY_REQUIRED`, SAM, inventory authority, economics formulas, or production deployment configuration.

The accepted Remediation 2 candidate remains unchanged and is the immediate v2.3 predecessor. Remediation 3 closes the Fantasy Bay allocation-safety defect: a single merchandise line no longer makes 100% allocation eligible when receipt financial semantics, receipt arithmetic, or mixed-purchase policy remain unresolved. The backend is authoritative; the UI only displays its eligibility result. Every future operator deployment must still verify the exact committed GitHub build context against the accepted DEPLOY SHA-256 ledger before Jenkins runs, then reconcile backend version, visible UI version, immutable image identity, and deployed runtime hashes after deployment.

This document is the handoff baseline for future Dex development. It describes the observed implementation; plans and patch notes may describe broader intent.

## Architecture

Dex is a private, single-user TCG inventory system organized as a compact monolith:

- `app.py`: threaded Python HTTP server, JSON API, SQLite access and startup migrations, scanner-folder watcher, image storage, SAM matching, QR generation, CSV exports, and recycle maintenance.
- `dex_migrations.py`: versioned transactional migrations and `schema_migrations` ledger.
- `dex_acquisition.py`: Phase 3 acquisition validation, exact-cent facts, authoritative USD reconciliation, and informational receipt-group payloads.
- `dex_rip.py`: Phase 4 explicit rip intake, partial-unit cost, allocation previews, finalization, and append-only card/bulk basis events.
- `dex_sealed.py`: Phase 5 exact sealed-unit ledger, deterministic unit basis, rip/sale claims, sealed-order economics, quantity adjustment, and atomic sale Undo.
- `dex_receipts.py`: provider-neutral private receipt extraction, normalized non-authoritative candidates, receipt-line matching/classification, field provenance, and versioned exact-cent allocation proposals.
- `dex_receipt_semantics.py`: deterministic source-line semantics, confidence/provenance, merchandise-only matching eligibility, and append-only confirmation/correction history.
- `dex_batch_economics.py`: Phase 6 query-only authoritative batch/group calculations, stable sale attribution, valuation coverage/freshness, reconciliation, and export rows.
- `dex_corrections.py`: Phase 7A append-only correction/disposition ledger service, current corrected values, operational-loss treatment, durable tombstones, and linked inverse reversals.
- `dex_post_sale.py`: Phase 7B immutable sale-adjustment ledger, effective financial facts, exact return/restoration state transitions, de-duplication, and linked inverses.
- `dex_portfolio_economics.py`: Phase 7C read-only Finalized Economics portfolio totals, stable per-item order attribution, valuation coverage/freshness, reconciliation, and CSV rows.
- `dex_inbound.py`: v2.2 Draft Acquisition identity, three-screen guided wizard facts, Accounting-by-Default reconciliation, explicit confirmation, append-only lifecycle events, recoverable draft recycle, confirmed-acquisition cancellation, and downstream dependency protection.
- `dex_intake_bridge.py`: Phase 6 transactional/idempotent routing of confirmed acquisition lines into the established batch, sealed-unit, rip, and scanning architecture with exact quantity/basis reconciliation.
- `dex_catalog.py`: v2.2 local commercial-product catalog, validated text identifiers, request-safe scan aggregation, learned mappings, and append-only mapping corrections.
- `dex_sam.py`: v2.2 One Piece-only recognition service with provider-neutral metadata/cache and reference interfaces, incremental local reference indexing, conservative versioned confidence rules, review queues, request idempotency, and append-only evidence/decisions.
- `dex_sam_audited.py` and `dex_sam_audited_worker.py`: v2.4 frozen multi-evidence integration boundary, runtime component verification, suggestion-only isolated inference, post-inference catalog verification, explicit family-write gate, and append-only recognition/decision/truth/delta audit history.
- `dex_legacy_economics.py`: query-only Phase 2 estimated economics for legacy batches.
- `static/index.html`, `static/app.js`, and `static/styles.css`: vanilla-JavaScript single-page operator interface.
- SQLite: source of truth for batches, physical cards, source cards, sales, settings, processed scans, and activity history.
- Persistent folders: inventory database/images, scanner inbox, and SAM source database are separately mounted by Docker Compose.
- Deployment: version-isolated `v2.0-test` container, port, storage, scanner inbox, and source folder. Jenkins builds an image and health-checks `/api/health`.

Each physical card receives an immutable SKU. Card identity, physical SKU, grouped listing identity, and drawer location are separate concepts.

## Confirmed Working Workflows

The complete automated suite passes and confirms the core paths below.

- Create and edit inbound batches for supported games and acquisition types.
- Add one card or bulk-import cards with unique physical SKUs.
- Pair explicit `_front`/`_back` files and sequential scanner files in front-first or back-first order.
- Reopen completed batches and add cards without reusing existing SKUs.
- Complete batches and queue labels only after completion; requeue and mark labels printed.
- Review grouped inventory, edit card details and pricing, search sold cards by order number, and export inventory/sales CSVs.
- Complete multi-card eBay or TCGplayer sales and retain protected financial history.
- Move cards or batches to the Recycle Bin, restore them, purge eligible unsold cards, and undo supported recent actions.
- Configure timezone, TCGplayer capacity, and recycle retention settings.
- Index local One Piece references incrementally without modifying originals; unchanged hashes are skipped and duplicate/near-duplicate relationships remain visible.
- Refresh/cache normalized OPTCG structured metadata or continue with stale/missing cache state, local references, and Find Match during provider outages.
- Recognize one card or a batch with TCG/context narrowing, card-number evidence, scan-quality observations, bounded candidates, and rotation/crop/SAMPLE-tolerant visual evidence.
- Confirm SAM's suggestion, correct it through local Find Match, or leave a scan unidentified while retaining the original suggestion, alternates, evidence, and decision history.
- Upgrade a legacy v1.x database with SAM columns before creating the related index.
- Open any existing batch to view a strictly read-only **Estimated Economics** preview with valuation coverage, warnings, separate recycled value, and estimated historical sale attribution. No permanent cost basis is assigned.
- Create or edit Phase 3 acquisition facts for one homogeneous product batch: acquisition mode, product identity, units acquired, final USD paid, cost breakdown, optional foreign-currency reference, invoice, and receipt group.
- Link multiple product-specific batches from one transaction without merging their inventory or automatically distributing shared charges. The batch view reports group coverage and total explicitly assigned USD cost.
- Reject unacknowledged cost-component differences, preserve unknown cost as unknown, mirror authoritative final USD paid to legacy `total_cost`, audit material edits, and block ordinary rewrites after economics is finalized.
- Create rip sessions without activating scanner intake; explicitly start/stop intake and show which rip currently receives new scanner/browser cards.
- Require confirmation before switching away from an active rip that has unprocessed scanner files.
- Preview and finalize equal or manual card allocation with known-quantity bulk or an explicit unknown-quantity reserve, requiring exact-cent reconciliation and all-cards confirmation.
- Consume partial-rip cost from deterministic authoritative landed-unit sequences, lock finalized sessions against ordinary intake, and append audited corrections without rewriting original basis events.
- Materialize stable sealed units only for batches with trustworthy authoritative USD cost and units acquired; preserve exact basis down to the cent.
- Open exact sealed units through rip creation, sell the lowest remaining stable sequences by default, or accept explicit exact unit IDs through the API.
- Complete separate multi-unit sealed-product orders with backend-calculated net proceeds, sold basis, and realized P/L; marketplace-collected tax is recorded but excluded.
- Prevent the same unit from being opened/sold twice, reject overselling and mixed card/sealed orders, retain canceled order history, and restore exact units through eligible Undo.
- Reconcile every sealed batch as acquired = opened + sold + remaining + corrected/adjusted, with reason-aware adjustment events.
- Open an authoritative batch into a collapsible economics interface whose first screen answers cost, recovered proceeds, known remaining value, and current ahead/behind position.
- Keep realized proceeds/P&L visually and mathematically separate from remaining market/listed value; show unknown prices as incomplete coverage with known or explicitly unknown freshness.
- Calculate uncapped Cost Recovery, Current Economic Position, and Projected Listed Position exclusively in the backend from source facts; the browser formats returned values only.
- Attribute cross-batch card orders once using stable historical sale-item weighting and aggregate Receipt/Acquisition Groups without duplicating order-level proceeds or allocating shared costs.
- Export versioned batch economics and append Phase 6 provenance fields to inventory/sales CSVs without changing existing column meanings.
- Correct authoritative acquisition cost without rewriting `batches.final_usd_paid_cents`; deterministically reconcile the change across stable sealed-unit IDs or an explicit singles target.
- Transfer exact basis between finalized cards and rip bulk while preserving the original allocation and a zero-sum audit trail.
- Distinguish duplicate/entry errors from physical damage, loss, and disposal. Duplicate basis is reallocated; physical basis moves to separately labeled Operational Loss.
- Preserve disposed card/sealed records as durable tombstones, block normal hard purge, and restore state/basis only through a linked inverse event while keeping the original event visible.
- Inspect card and sealed orders from Sales with original facts, backend-derived effective economics, exact sold identities, and complete append-only event history.
- Record partial/full refunds and chargebacks without restoring inventory; record fee credits and actual postage refunds separately without rewriting the original sale.
- Restore exact returned card or sealed identities only after physical receipt and condition confirmation, at most once under concurrent requests; route damaged returns to Excluded and require linked reversal for restoration.
- Preserve returned-card sale history while permitting a later new sale row for that same physical identity; current inventory and batch economics count the physical card once.
- Reuse original stable sale-item weighting when post-sale adjustments affect a cross-batch order, so batch portions and group totals reconcile without duplicate proceeds.
- Open **Operational Economics** to see Finalized Economics acquisition cost, effective recovered proceeds, active sold basis, realized P/L, operational loss, remaining known market/listed value, uncapped recovery, and current/projected positions from backend source facts only.
- Keep legacy estimates and authoritative-but-unfinalized batches separate from portfolio totals; show explicit card/sealed coverage, freshness, and incomplete states. Remaining sealed value stays Unknown without an authoritative value fact.
- Reconcile portfolio cost to batch facts and effective proceeds to stable exact sale-item attribution, counting cross-batch orders once while excluding canceled orders and neutralizing linked reversals.
- Export the same read-only `acquisition-rip-v3` portfolio payload as CSV without storing dashboard totals.
- Create an immutable Draft Acquisition ID immediately, autosave only non-authoritative facts and wizard position, and preserve every lifecycle mutation as an immutable request-safe event.
- Keep `PACK_PRODUCT` and `SEALED_PRODUCT` distinct, require every suggested line allocation to disclose its method, and prevent suggestions from becoming authoritative without explicit confirmation.
- Require exact product-line landed-cost reconciliation, `$5 OR 2%` material-discrepancy confirmation, and severe `50%+` escalation. Missing final USD stays Unknown rather than becoming `$0.00`.
- Use the focused three-screen **New Acquisition** wizard while retaining Advanced / Legacy New Batch compatibility and all Phase 3–7C batch economics.
- Scan validated UPC-A, EAN-13, and GTIN-14 identifiers for Pack/Sealed lines; known products populate visibly, repeat scans increment one line, and different products stay economically independent.
- Keep unknown identifiers unguessed, support acquisition-local identification or explicit operator-confirmed Remember Mapping, block silent collisions, and preserve reasoned mapping-correction history.
- Preserve manual Pack Product, Sealed Product, and Single Cards entry. Product recognition creates no batch, card, sealed unit, basis, document, receipt extraction, SAM match, or portfolio fact.
- Attach multiple private JPG/JPEG/PNG/PDF source artifacts to an acquisition, verify SHA-256 integrity, retry failed uploads, and preserve removal/tombstone history. These artifacts never auto-populate financial facts and create no inventory or economics records.

## Known Gaps

- Phase 7 recognition is intentionally One Piece-only. Other games require later adapters, rules, and representative fixtures.
- The bundled runtime does not require an OCR engine. Without optional local OCR, strong printed-number evidence comes from existing intake fields or filenames; visual/context evidence still works but more cards may require review.
- The visual engine uses conservative perceptual/frame fingerprints rather than a trained embedding model. It tolerates ordinary rotation/crop and SAMPLE artifacts but is not a grading or counterfeit-detection system.
- OPTCG refresh is operator-triggered for requested card numbers; no scheduled whole-catalog synchronization or live provider dependency is introduced.
- Local reference quality, filenames, and variant coverage materially affect candidate narrowing. Unknown metadata stays Unknown, and new/provider-missing cards need local references or manual review.
- Pokemon, Riftbound, live catalog synchronization, marketplace synchronization, automatic pricing, Janna, Goose, and DPS remain outside this Phase 7 scope.
- The Phase 3 commercial-product catalog is local only; manufacturer/import synchronization and authoritative external provenance are not implemented.
- HEIC/HEIF needs a verified decoder and is currently rejected with a retryable failure. PDF validation is intentionally lightweight and bounded; OCR/AI extraction and receipt-line matching are not implemented.
- Physical keyboard-emulating barcode-scanner operator QA remains outstanding. Automated keyboard submission and browser simulation have passed, but production approval requires real-device confirmation.
- The mapping-correction dialog uses a bounded product list; a large future catalog may need search within that dialog.
- The global Attention Center, cross-TCG SAM, autonomous learning/retraining, JANA pricing, and listing automation remain later approval gates. Receipt image OCR/external extraction providers remain unconfigured.

## Technical Debt and Risks

- No authentication or authorization: any client that can reach the service can read exports and call mutation, sale, recycle, purge, settings, SAM, and undo endpoints. The port must remain private.
- The threaded server, scanner watcher, SAM, and recycle maintenance do not use one consistent SQLite write-serialization policy.
- Requests may contain up to 250 MB of base64 JSON; concurrent imports can create high memory pressure.
- Legacy startup-time conditional `ALTER TABLE` statements still exist alongside the new Phase 1 migration framework. The framework provides a ledger and transactional rollback for registered migrations, but the legacy alterations have not yet been converted into registered migrations.
- Broad exception handlers can expose internal error and path details through API responses.
- Activity history is not a complete system-wide audit trail. Phase 7 recognition suggestions and decisions are durable, but several older non-SAM mutations and automatic purge still lack equivalent comprehensive history.
- Multi-card sale subtotal is divided evenly instead of retaining explicit item-level sale prices.
- Receipt/Acquisition Groups are reference strings rather than a separate transaction table in Phase 3. This is intentional for the approved first release, but richer shared-charge reconciliation will require an audited model later.
- Phase 4 stores one aggregate bulk reserve per rip rather than individual fake bulk-card SKUs. Resolution into later scanned cards uses audited basis transfers; richer bulk sale/disposition states remain later work.
- Phase 5 uses one stable unit record per homogeneous acquired unit. Nested box/pack/component models and mixed-product batches remain deferred.
- Sealed Sales rows retain exact consumed IDs and eligible Undo. Once immutable post-sale history exists, ordinary sealed Undo is disabled and corrections use linked events.
- The legacy Phase 5 `/adjust` API remains for backwards compatibility, but the operator UI now routes sealed corrections/dispositions through the Phase 7A immutable event workflow.
- Inbound receipt extraction currently operates only on text-layer PDFs through the local provider. JPG/PNG receipt OCR is intentionally provider-ready but unavailable; failure is retryable and manual entry remains usable.
- Receipt-derived draft values and allocation proposals become authoritative only through the existing acquisition confirmation gate. No Phase 5 extraction operation creates downstream inventory.
- Card orders retain the legacy equal item split; Undo now retains the canceled order/item history instead of deleting it. Explicit operator-entered per-card sale lines remain future work.
- Phase 6 has no market/listed price fact for unopened sealed units, so those units correctly produce unknown valuation coverage rather than a guessed value. Marketplace pricing remains manual.
- Phase 6 group rollups aggregate only explicitly assigned batch costs. Shared receipt shipping, tax, discounts, and fees remain informational until an audited allocation workflow exists.
- Phase 7C completes the approved v2.1-test development scope; production deployment and any post-v2.1 work remain separately operator-approved.
- A confirmed sellable return restores to `IN_STOCK`/`REMAINING`; richer condition grading, exchanges, replacement shipments, and refund-to-payment-provider integration remain outside this phase.
- Event-ledger targets use typed integer IDs without database foreign keys to every polymorphic target table; service validation and immutable event/tombstone relationships enforce target scope.
- The Phase 2 pre-production gate script expects ledger-only schema mutation and is intentionally not valid for Phase 3's approved additive migration.
- `app.py` and `static/app.js` are large single files, increasing coupling and regression risk.
- Automated SAM coverage includes high/ambiguous/unknown decisions, provider failure, watermark/crop/rotation variation, history, and 5,000 reference rows; physical scanner accuracy and false-positive rates still require operator QA with representative cards and variants.
- Jenkins runs a health smoke test but not the full automated suite. The visual test is machine-specific and not part of CI.
- Reference libraries are private operator data outside Git. A large or poorly curated mixed tree can add indexing time and ambiguous duplicates; use a dedicated read-only One Piece root.
- Root `index.html` coexists with the served `static/index.html`, creating ambiguity about which interface file is authoritative.
- Operational backups cover SQLite through `scripts/backup.py`; a complete recovery plan must also preserve inventory images and configuration.

## Recommended Development Order

1. **Preserve the gate:** retain the immutable Phase 7C and prior v2.2 Git-ready checkpoints; test v2.2 migrations only against disposable Phase 7C copies before any operator-authorized deployment.
2. **Complete the Phase 7 gate:** run the disposable One Piece scenarios and representative physical scanner QA before promotion. Do not begin cross-TCG SAM, JANA, the global Attention Center, or production deployment without separate approval.
3. **Keep reporting derived:** extend the backend event/source-fact model rather than storing dashboard totals or duplicating formulas in the frontend.
4. **Secure private operation:** add authentication/authorization or an enforced trusted-proxy boundary, safer error responses, request limits, and consistent write serialization when separately approved.
5. **Measure SAM conservatism:** record physical false positives, variant confusion, OCR misses, poor-scan warnings, and reference gaps before changing versioned thresholds or methods.
6. **Reduce coupling:** continue extracting dedicated economics/migration modules without reorganizing unrelated code; later separate persistence, scanner, sales, and frontend views.

## Baseline Rule

Future work should preserve physical SKUs, sale/audit history, review-first matching, recoverable deletion, stable/test data isolation, and manual fallback. Update this document whenever architecture, workflow guarantees, known gaps, or development priorities materially change.
