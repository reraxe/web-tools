# DEX v2.2-test Patch Notes

Status: development checkpoint through Inbound 2.0 Phase 7 SAM Recognition + Human Review and controlled OCR Validation Pass 3; production not approved

## Phase 7 Controlled Validation Pass 3: OCR Latency Optimization

- Replace unconditional twelve-process OCR execution with a staged plan while retaining every Pass 2 crop, preprocessing, and page-segmentation recipe as a bounded fallback.
- Run the highest-yield primary grayscale `PSM 11` attempt first and a differently preprocessed primary binary `PSM 11` confirmation second. Exit only when two valid independent reads agree with no valid OCR conflict.
- Escalate unreadable or unconfirmed scans into bottom-band confirmation and then the remaining Pass 2 attempts. Any valid disagreement disables early exit and runs the complete fallback before applying the unchanged consensus rule.
- Prepare and serialize crops lazily, reuse a prepared crop across page-segmentation attempts, and record stage, region, preprocessing, per-attempt timing, leading-candidate effect, final-candidate support, and consensus-establishment evidence.
- Keep Tesseract as isolated local subprocesses. No shared OCR engine state, external image transmission, background worker, threshold, authority, visual-recognition, schema, migration, inventory, or economics change is introduced.
- Exact blind rerun of the unchanged nine references and five physical scans: 5/5 correct top candidates, 5/5 OCR success, 2/5 correct automatic matches, 3/5 Needs Review, 0 Unidentified, and 0 false automatic matches. Average attempts fell from 12.0 to 2.6; average recognition latency fell from 2,224.78 ms to 750.56 ms.
- Verification: 175 Python tests passed in 21.574 seconds; JavaScript syntax and all 12 self-contained frontend regressions passed; disposable health returned 200 with `v2.2-test` and queues reconciled to 2 Matched / 3 Needs Review / 0 Unidentified.
- Full results are recorded in [`SAM_REAL_WORLD_VALIDATION_OP16_OCR_PASS3_2026-08-15.md`](SAM_REAL_WORLD_VALIDATION_OP16_OCR_PASS3_2026-08-15.md).

## Phase 7 Controlled Validation Pass 2: Local Card-Number OCR

- Add optional, local-only Tesseract 5 reading of tightly bounded lower-right One Piece card-number regions. Original scans and derived crops never leave the DEX runtime; temporary crops are deleted after each attempt.
- Use deterministic grayscale, scale, contrast, sharpening, threshold, and page-segmentation attempts. OCR becomes evidence only when multiple valid reads reach a strict consensus.
- Accept explicit One Piece formats including `OP`, `EB`, `ST`, `PRB`, and `P`, with bounded `O/0` and `I/1` correction only in structurally valid positions. Arbitrary or malformed OCR text remains unreadable.
- Keep `sam-conservative-2026-08-15-v1` and the approved 90% overall / 86% visual thresholds unchanged. OCR/visual conflict, a missing reference, same-number variant ambiguity, and scan-quality warnings continue to prevent automatic authority.
- Keep OCR optional. An unavailable executable, timeout, processing error, or unreadable identifier records diagnostic evidence and falls back to the unchanged visual recognition path.
- Show a concise card-number agreement, conflict, or unreadable result in SAM review. Raw OCR, crop region, consensus, and timing remain behind an expandable diagnostics section.
- Package Tesseract and English language data in the Docker image and assert the executable at build time. Native development may supply `DEX_TESSERACT_CMD`; no migration or database-schema change is introduced.
- Exact blind rerun of the unchanged nine references and five physical OP16 scans: 5/5 correct top candidates, 5/5 valid OCR reads, 2/5 correct automatic matches, 3/5 Needs Review, and 0 false automatic matches. Average total recognition latency was 2,224.78 ms, including 1,844.36 ms of OCR execution.
- Add strict normalization, fallback, blurred/cropped/low-contrast failure, OCR/visual conflict, variant-protection, and frontend evidence regressions. Full results and hashes are recorded in [`SAM_REAL_WORLD_VALIDATION_OP16_OCR_PASS2_2026-08-15.md`](SAM_REAL_WORLD_VALIDATION_OP16_OCR_PASS2_2026-08-15.md).
- Verification: 174 Python tests passed in 22.136 seconds; JavaScript syntax passed; all 12 self-contained frontend regressions passed; disposable `/api/health` returned 200 with `v2.2-test` and the SAM queues reconciled to 2 Matched / 3 Needs Review / 0 Unidentified.

## Phase 7 Operator-QA Hotfix: Confirm Correction

- Replace the unsupported native `prompt()` used by Confirm Correction with visible, accessible correction-reason and operator-note fields inside the SAM review modal.
- Validate required correction details before submission and show an inline operator-visible error without losing the selected reference or closing the review.
- Guard the decision mutation with an in-flight lock so a click/double-click submits at most one request. Disable and mark the action busy while the request is pending.
- On backend validation, stale revision, rejection, or network failure, preserve the selected candidate and entered details, keep the modal open, and show both inline and toast errors.
- On success, show the selected authoritative card number, close the modal, and refresh queue counts. The original SAM suggestion, correction decision/provenance, and identity-only economics boundary remain unchanged.
- Add a frontend execution regression for OP16-034 → Find Match OP16-035 → Confirm Correction, including exact single-request payload and rejected-request visibility. Strengthen backend coverage for selected identity, immutable original suggestion, decision history, queue transition, stale revision, and unchanged batch economics.
- No schema, migration, API contract, recognition rule, confidence threshold, or economics change.
- Verification: 167 Python tests passed in 16.415 seconds; JavaScript syntax passed; 12 self-contained frontend regressions plus the live batch-detail regression passed; desktop/mobile visual rendering passed without console errors.

## Phase 7: SAM Recognition + Human Review

- Add migration `0014_v22_phase7_sam_recognition`. It introduces nullable card recognition links and empty provider-cache, reference-index, recognition-job, ranked-candidate, and operator-decision ledgers. It performs no historical identity backfill and changes no economics fact.
- Add `dex_sam.py` as the One Piece-only recognition service behind provider-neutral metadata and reference-library boundaries. The OPTCG adapter exchanges structured card metadata only; physical scans and local reference images are never transmitted.
- Cache normalized provider facts with provider/version/fetch provenance and active/stale/missing state. Provider failure falls back to cached metadata, local references, and manual Find Match without blocking scanner intake.
- Index the configured external reference library incrementally and resumably. Every file is checked by SHA-256, unchanged files are skipped, changed files are reindexed, duplicate hashes and near-duplicate visual families are recorded, and originals are never renamed, moved, rewritten, or stored as SQLite blobs.
- Use TCG/batch context, scan-quality observations, normalized card-number evidence, bounded candidate narrowing, rotation/crop-tolerant frame fingerprints, and visual comparison that masks the central SAMPLE-watermark region. Phase 7 never brute-forces the full library for each card.
- Apply versioned conservative rules: `AUTO_MATCHED` requires strong card-number and visual agreement with no meaningful ambiguity; conflicts and plausible variants become `NEEDS_REVIEW`; absent trustworthy evidence becomes `UNIDENTIFIED`. Thresholds live in the backend, not JavaScript.
- Add matched/review/unidentified queue lanes and a side-by-side human review modal. Operators can confirm SAM's suggestion, search the normalized local catalog, confirm a correction with reason/note, or leave the scan unidentified. The original suggestion, alternates, evidence, provider/reference provenance, engine/rules/index versions, and all decisions remain durable.
- Preserve physical identity and retries: request IDs and processed-scan identity prevent duplicate results, while two legitimate copies remain separate card/SKU records. Acquisition, acquisition-line, batch, rip, processed-scan, and source-image provenance remain attached.
- Preserve the economics boundary. SAM applies identity only and does not assign or change acquisition cost, card basis, rip allocation, sales economics, or portfolio calculations. Existing operator-confirmed/corrected identities cannot be silently overwritten by provider refresh or legacy SAM.
- Docker now includes and import-checks `dex_sam.py`; the One Piece reference root is externally configurable with `DEX_ONE_PIECE_REFERENCE_DIR` and defaults to the established source database mount.
- Verification: 167 Python tests passed; JavaScript syntax passed; 13 frontend contract/regression files passed; desktop/mobile visual rendering passed without console errors. The final hotfix run handled 5,000 references in 54.42 ms, exact reference search in 2.67 ms, 5,000 metadata-cache rows in 33.40 ms with a 0.05 ms lookup, and a 1,000-card review queue in 227.44 ms.

## Phase 6: Downstream Intake Bridge

- Add migration `0013_v22_phase6_downstream_intake_bridge` with append-only intake operations, one projection per acquisition line, route events, and explicit sealed-unit intake disposition. Historical batches remain unlinked and historical sealed units remain available without inferred backfill.
- Let confirmed `READY_FOR_INTAKE` lines route partially and resumably. Sealed/Pack lines support **Keep Sealed**, **Rip / Open**, and **Decide Later**; Single Cards support **Scan & Identify** and **Decide Later**.
- Project each confirmed product line into one established homogeneous batch linked by `batches.acquisition_line_id`. Receipt, catalog, and source-document provenance remain reachable through that line.
- Carry confirmed line landed cost into the batch automatically. Exact per-unit cents use immutable unit/quantity ordinals; no operator cost re-entry or frontend financial calculation is added.
- Create exact sealed-unit identities before routing. Pending/undecided units cannot be sold or opened; Keep Sealed units enter sealed inventory; Rip/Open claims the lowest eligible stable unit and creates a draft rip without activating scanner intake.
- Route acquired singles into the existing batch/rip intake surface without SAM. Per-card basis remains pending until the established allocation workflow is finalized, and finalization is blocked while line quantity remains undecided.
- Transition acquisitions to `INTAKE_IN_PROGRESS` after any route and to `INTAKE_COMPLETE` only when every active line quantity is accounted for. Additional routing uses the same preview/confirm endpoints and optimistic revision protection.
- Require a backend-generated preview token before confirmation. Unique request IDs make retries idempotent; `BEGIN IMMEDIATE`, stable selection, and revision checks prevent duplicate projection or double consumption.
- Preserve existing rip activation, batch completion, label printing, card intake, sealed sales, economics, receipt groups, catalog, and receipt intelligence. Linked acquisitions are protected from recycle/cancel and require existing correction/reversal workflows.
- Add status, preview, confirm, additional-routing, links, and continue APIs; a full acquisition Review routing surface; backend/API/migration/concurrency/frontend regressions; and four disposable operator scenarios.
- Verification: 153 Python tests passed; JavaScript syntax and 11 frontend regressions passed; the server-backed batch-detail regression passed; `/api/health` returned 200 with `v2.2-test`; 75 lines / 150 exact units routed in 43.83 ms in the final full run.

## Pre-Phase UX Consistency and Acquisition Safety Hotfix

- Add one session-scoped disclosure-state registry for DEX `<details>` sections. Operator-expanded and operator-collapsed state now survives searches, autosaves, mutations, and rerenders; dynamic summary counts do not define identity. Critical/Needs Attention sections may force themselves open.
- Keep Product Catalog manual search expanded after Search and render results immediately in the open section. Preserve its query, logical viewport, and search focus across the result refresh.
- Convert Purchase Details and Purchase Amounts into consistent disclosures. Missing/blocked facts or retryable receipt/document failures force the relevant section open; clean sections may start collapsed. Presentation state never changes receipt-derived or manual facts.
- Add migration `0012_v22_prephase_ux_safety_hotfix` with recoverable acquisition recycle metadata only. No acquisition, batch, inventory, document, receipt, catalog, or economics fact is backfilled or rewritten.
- Allow an unprotected incomplete acquisition to move to Recycle Bin with a standardized reason, confirmation, durable lifecycle event, and restore action. Permanent acquisition purge is intentionally unavailable.
- Allow an unlinked `READY_FOR_INTAKE` acquisition to be canceled with a standardized reason and operator note. Authoritative facts, product lines, documents, receipt/catalog provenance, allocations, and events remain immutable and visible.
- Block acquisition recycle/cancel when a downstream batch, inventory identity, sale, rip, correction, or economic event is linked. Confirmed draft allocations must be reversed or invalidated before draft recycling.
- Add backend, API, and frontend regressions for disclosure preservation, attention-forced opening, draft recycle/restore, confirmed cancellation, protected-history blocking, and Recycle Bin rendering.

## Phase 5: Receipt Intelligence + Auto-Populated Economics

- Add migration `0011_v22_phase5_receipt_intelligence` for provider-neutral extraction jobs, normalized candidate facts, receipt lines/classifications, proposed matches, versioned allocation proposals, field provenance, and append-only receipt events. No receipt blob or raw OCR text is stored in SQLite.
- Add `dex_receipts.py` with a private local text-PDF provider, explicit provider/privacy status, retryable image-provider failure, field-level confidence/provenance, conflict-preserving draft proposals, exact identifier/manufacturer/name matching, fuzzy suggestions, and deterministic exact-cent allocation.
- Add queue/status/retry, candidate apply/disposition, line classification, match disposition, and allocation proposal APIs with request IDs and optimistic acquisition revision checks.
- Add compact extraction actions/status to Product & Purchase Details and a calm, collapsible Receipt Intelligence review surface. Frontend code formats backend facts only; it does not calculate allocation or reconciliation.
- Preserve Accounting-by-Default safeguards: Unknown is never zero, no automatic FX, $5 OR 2% material handling, 50%+ severe escalation, explicit zero rules, and final acquisition confirmation as the only authority gate.
- Add five-scenario disposable QA seeding plus backend/API/frontend regression coverage. No batch, card, sealed unit, rip, sale, SAM, or portfolio fact is created by extraction.

## Phase 4: Receipt / Source Document Infrastructure

- Replace disabled receipt actions with camera capture and multiple-file upload for JPG/JPEG, PNG, and PDF. HEIC/HEIF is rejected with a clear retryable status until a verified safe decoder is available.
- Add provider-neutral `DocumentStore` behavior and private local-filesystem storage outside SQLite. A Google Drive-compatible provider boundary is present but intentionally unconfigured; no credentials, public URLs, or provider-specific schema are introduced.
- Add migration `0010_v22_phase4_source_documents` for document metadata, SHA-256 integrity state, storage status, acquisition linkage, durable tombstones, and append-only attach/failure/retry/verify/tombstone history. SQLite contains no document blobs.
- Validate signatures, decoded images, lightweight PDF structure/page limits, maximum size, MIME/extension agreement, safe filenames/path containment, duplicate SHA-256 values, unique request IDs, and optimistic acquisition revisions.
- Keep manual acquisition entry available during every document failure. Failed uploads remain visible and retryable; no missing or failed artifact becomes a financial fact or `$0.00` cost.
- Show compact attachment status on Product & Purchase Details and Step 3 Review. Private view/download is server-mediated with no-store, no-sniff, and sandbox response controls.
- Preserve draft removal versus confirmed-evidence retention: both keep audit metadata; confirmed evidence also preserves the private artifact under a durable tombstone.
- Add disposable Phase 4 QA seeding and focused backend/frontend regressions. No OCR, AI extraction, candidate fact population, receipt-line matching, SAM work, downstream batch projection, or economics change is included.

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

## Still Explicitly Not Included After Phase 6

- No image OCR provider or external OCR/AI service. Text-layer PDF extraction is the only operational provider.
- No SAM change.
- No acquisition-aware SAM identification or global Attention Center.
- No new accounting formula, marketplace integration, deployment change, or production-data action.

## Verification

- Full suite: 153 Python tests passed, including all prior v2.1 and v2.2 regressions plus focused receipt-intelligence, disclosure-state, acquisition-removal, automatic-allocation, Needs Attention, and downstream-routing coverage.
- Migration tests cover additive one-time execution, source-row preservation, nullable linkage, and transactional rollback after a forced conflict.
- Service tests cover immediate draft identity, idempotency, autosave restrictions, broad product classes, exact allocations, unknown cost, severe discrepancy escalation, transactional downstream projection, partial routing, and exact unit claims.
- API/packaging tests cover the foundation contract, draft create/list/detail routes, guided Inbound UI, legacy compatibility entry, runtime version, and Docker module inclusion.
- A direct JavaScript wizard test covers the three-screen contract, progressive disclosure, multiple lines, payment method, receipt placeholder, domestic/international behavior, autosave serialization, clean/exception reconciliation, explicit zero, incomplete recovery, keyboard/focus semantics, and logical viewport hooks.
- JavaScript syntax and 10 direct frontend regressions passed, including receipt extraction/review actions plus all prior viewport, batch, Sales, post-sale, and Operational Economics contracts.
- Receipt performance coverage processed 25 matched product lines and produced an exact proposal in approximately 24 ms on the development workstation.
- Disposable browser QA verified clean single-line, exact multi-line, manual conflict, and retryable failure paths without console errors.
- Disposable startup returned `/api/health` 200 as `v2.2-test`; migration `0006` was present, all existing batch links remained `NULL`, and no draft acquisition was inferred.
- Disposable browser QA passed the required one-line `$120 / 3 = $40` happy path, a 90% severe discrepancy, and a resumable missing-cost draft. The confirmed happy path created one automatic allocation event and no downstream inventory.
