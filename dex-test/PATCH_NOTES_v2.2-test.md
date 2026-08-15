# DEX v2.2-test Patch Notes

Status: release candidate packaged through Inbound 2.0 Phase 3; production not approved pending physical barcode-scanner QA; receipt/document work not authorized

## Phase 3: Product Catalog + UPC Intake

- Add a reusable local commercial-product catalog with immutable IDs, flexible game/class/subtype facts, provenance, active state, verification timestamps, manufacturer codes, and no dependency on the UI's current game suggestions.
- Store UPC-A, EAN-13, GTIN-14, and internal identifiers as text. Standard barcodes are check-digit validated and normalized to canonical 14-digit text while retaining the raw representation and leading zeroes.
- Add prominent keyboard-scanner intake for Pack Product and Sealed Product lines. Enter submits a scan; recognized products populate catalog facts with an **Automatic + Visible** result.
- Aggregate repeated scans of one catalog product into one acquisition line and quantity. Request IDs and optimistic revisions prevent frontend retries from duplicating quantities or lines; different products remain separate lines.
- Keep unknown barcodes at **Needs Attention** with Search catalog, Identify manually, and Cancel actions. Local-only identification creates no global mapping; Remember Mapping creates an operator-confirmed catalog record and identifier mapping that resolves automatically later.
- Block silent identifier reassignment. Corrections require a standardized reason and note, update only the future active mapping, and append immutable mapping history that preserves the earlier product relationship.
- Preserve manual Pack Product, Sealed Product, and Single Cards workflows. Product recognition supplies commercial facts only and creates no cost, basis, batch, sealed unit, card, rip, sale, or portfolio fact.
- Add migration `0009_v22_phase3_product_catalog_upc`, catalog/scan/history APIs, Docker packaging for `dex_catalog.py`, and a disposable catalog QA seeder.
- Verify 117 Python tests, JavaScript syntax, all self-contained frontend regressions, `/api/health` 200, and the complete disposable browser flow. Searching a 1,000-product fixture completed in under 1 ms in the regression run.

## Phase 2 Happy-Path Polish

- Apply Accounting-by-Default to the existing three-screen wizard. A clean one-line purchase now reaches Review without routine allocation inputs, allocation confirmation, or a separate reconciliation task.
- Keep the backend as the only calculation authority. At final acquisition confirmation it assigns 100% of authoritative final USD to the sole active product line, calculates deterministic per-unit cents, and records a versioned `SINGLE_LINE_100_PERCENT` event linked from the final `AUTHORITATIVE_CONFIRMATION` event.
- Add the lightweight presentation contract `AUTOMATIC`, `AUTOMATIC_VISIBLE`, and `NEEDS_ATTENTION`. This metadata is compatible with a later Attention Center, but no notification bell or global queue is implemented.
- Make unresolved multi-line allocation, missing authoritative cost, explicit zero cost, and purchase discrepancies visible as **Purchase needs attention**. Detailed controls stay collapsed under **Resolve** until operator judgment is required.
- Preserve the `$5 OR 2%` material threshold, stronger `50%+` escalation, standardized reason, required note, exact final-USD re-entry, material confirmation, and severe confirmation.
- Keep missing authoritative cost Unknown and confirmation-blocking. Explicit `$0.00` remains an exception requiring its approved reason and confirmation.
- Keep autosave non-authoritative and confirmation bounded at `READY_FOR_INTAKE`, with zero processing batches, cards, sealed units, or rip sessions created.
- Add no schema migration. Runtime remains `v2.2-test`; inbound calculation/audit payloads use `inbound-acquisition-v1`.

## Post-Checkpoint Design Directive — Documentation Only

- Adopt the standing **Accounting-by-Default** rule: operators provide authoritative business facts; backend services perform deterministic accounting; only ambiguous, conflicting, incomplete, or materially exceptional reality requires attention.
- Standardize future accounting UX around **Automatic**, **Automatic + Visible**, and **Needs Attention**.
- Define receipt-driven economics and a future Critical/Review/Advisory Attention Center as forward-compatible design contracts.
- Preserve backend-only calculation authority, exact-cent/versioned auditability, graceful manual fallback, and all existing phase gates.
- No application code, schema, runtime behavior, or Phase 3 feature is authorized or changed by this documentation amendment. See [`DEX_ACCOUNTING_BY_DEFAULT.md`](DEX_ACCOUNTING_BY_DEFAULT.md).

## Phase 2 UX Revision

- Collapse the primary acquisition flow from six screens to three: **What did you acquire?**, **Product & Purchase Details**, and **Review Acquisition**.
- Keep one product line by default; additional Single Cards, Pack Product, or Sealed Product lines appear only when the operator explicitly adds them.
- Simplify Single Cards to TCG, set, and quantity. Hidden compatibility defaults use Scan / Identify Now without exposing lot naming, quantity confidence, identification-plan, or singles-accounting controls.
- Combine purchase source, merchant/date/payment, manual economics, and the future receipt placeholder on one progressively disclosed screen. Domestic purchases hide foreign-reference fields; International purchases reveal them.
- Add human payment methods: Credit / Debit Card, Cash, PayPal, Store Credit, and Other.
- Keep receipt actions visibly unavailable as **Coming Soon** while manual entry and an optional advanced receipt/order reference remain usable.
- Assign a one-line acquisition 100% of authoritative final landed cost only at confirmation. The backend records a disclosed `SINGLE_LINE_100_PERCENT` allocation event and deterministic per-unit preview; JavaScript performs no financial calculation.
- Preserve exact multi-line reconciliation while moving manual line allocation into the exception-only **Resolve** workflow when DEX lacks sufficient evidence to allocate safely.
- Make reconciliation exception-only: clean purchases show **Reconciled exactly** and one confirmation action; differences reveal the existing `$5 OR 2%`, note/reason, final-USD re-entry, and 50%+ severe controls.
- Preserve Unknown cost and explicit `$0.00` handling, resumable drafts, legacy New Batch access, and the no-downstream-projection boundary.
- Add migration `0008_v22_phase2_ux_revision` for payment method and safe three-screen resume mapping.

## Phase 2: Guided Manual Acquisition Wizard

- Replace the primary New Batch entry with **New Acquisition** while preserving the existing form under **Advanced / Legacy batch workflow**.
- Add the original full-page resumable guided acquisition foundation, subsequently refined by the three-screen UX revision above.
- Persist wizard position through additive migration `0007_v22_phase2_manual_acquisition_wizard`; progress-only autosave never confirms financial facts or resets reconciliation state.
- Keep `ACQUISITION_INCOMPLETE` unmistakable and resumable. Missing final USD displays **Unknown / Setup incomplete**, never `$0.00`.
- Support multiple independent Single Cards, Pack Product, and Sealed Product lines in one acquisition, including provisional singles and identify-later setup.
- Disclose every allocation method. Multiple lines require explicit line-cost confirmation; a single line receives the documented automatic 100% allocation only with authoritative acquisition confirmation.
- Show component total, final USD, difference, `$5 OR 2%` material escalation, and a severe 50%+ warning. Material confirmation requires a reason, note, final-USD re-entry, and explicit acceptance.
- Support intentional `$0.00` acquisitions only with `EXPLICIT_ZERO_COST` and normal authoritative confirmation.
- Add backend-generated readiness warnings and deterministic per-unit cost previews.
- Confirmation produces `READY_FOR_INTAKE` only. Phase 2 creates no downstream batch, card, basis, sealed unit, UPC/catalog, document, extraction, or SAM record.
- Add durable draft-line removal and preserve its lifecycle event rather than silently deleting draft history.

## Phase 1: Foundation

- Add immediate immutable Draft Acquisition identity with `ACQUISITION_INCOMPLETE` as the safe default.
- Add multi-line acquisition facts using broad `SINGLE_CARDS`, `PACK_PRODUCT`, and `SEALED_PRODUCT` classifications.
- Add append-only lifecycle events, immutable event IDs, unique request de-duplication, and optimistic revision checks.
- Make autosave draft-only. Autosave cannot set state, identity, authoritative confirmation, or reconciliation confirmation.
- Keep missing final USD as `NULL`/Unknown. An explicit zero-dollar acquisition requires `EXPLICIT_ZERO_COST`.
- Require allocation-method disclosure and an explicit allocation-confirmation call before any line cost is authoritative.
- Require confirmed line landed costs to equal final USD paid exactly.
- Enforce `$5 OR 2%` material-discrepancy rules and separate severe confirmation for `50%+` differences.
- Publish the approved receipt-line classification vocabulary for later receipt intelligence without adding receipt/document tables yet.
- Add nullable batch linkage for later projection while leaving every existing batch unlinked and unchanged.
- Add backend acquisition, product-line, reconciliation, confirmation, cancellation, and contract APIs.
- Package and build-time import-check `dex_inbound.py`.
- Advance application/runtime metadata to `v2.2-test`; keep economics calculation version `acquisition-rip-v3` because Phase 3–7C formulas did not change.

## Still Explicitly Not Included After Phase 3

- No receipt upload, camera capture, document storage, or extraction.
- No SAM change.
- No processing-batch or sealed-unit projection.
- No economics, rip, sale, portfolio, deployment, or production-data change.

## Verification

- Full suite: 104 Python tests passed, including all prior v2.1 and v2.2 regressions plus focused automatic-allocation and Needs Attention coverage.
- Migration tests cover additive one-time execution, source-row preservation, nullable linkage, and transactional rollback after a forced conflict.
- Service tests cover immediate draft identity, idempotency, autosave restrictions, broad product classes, exact allocations, unknown cost, severe discrepancy escalation, and no downstream projection.
- API/packaging tests cover the foundation contract, draft create/list/detail routes, guided Inbound UI, legacy compatibility entry, runtime version, and Docker module inclusion.
- A direct JavaScript wizard test covers the three-screen contract, progressive disclosure, multiple lines, payment method, receipt placeholder, domestic/international behavior, autosave serialization, clean/exception reconciliation, explicit zero, incomplete recovery, keyboard/focus semantics, and logical viewport hooks.
- JavaScript syntax and direct Phase 4 viewport/batch rendering, Phase 5 sealed Sales, Phase 7B post-sale, and Phase 7C Operational Economics regressions passed.
- Disposable startup returned `/api/health` 200 as `v2.2-test`; migration `0006` was present, all existing batch links remained `NULL`, and no draft acquisition was inferred.
- Disposable browser QA passed the required one-line `$120 / 3 = $40` happy path, a 90% severe discrepancy, and a resumable missing-cost draft. The confirmed happy path created one automatic allocation event and no downstream inventory.
