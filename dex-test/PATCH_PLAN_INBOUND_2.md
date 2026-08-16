# DEX v2.2-test — Inbound 2.0 Approved Plan

Status: architecture approved; Phases 1–6 accepted; Phase 7 SAM Recognition + Human Review implemented pending operator QA

Known-good baseline: immutable `v2.1-test` Phase 7C checkpoint

Known-good restore point: preserved `v2.2-test` Inbound 2.0 Phase 2 Happy-Path Polish checkpoint

Current checkpoint: `v2.2-test` Inbound 2.0 Phase 7 SAM Recognition + Human Review

## Approved Accounting-by-Default Contract

The operator supplies business facts; DEX performs deterministic accounting; ambiguity, conflict, incompleteness, and material exceptions require attention. Backend services are the sole accounting authority. Every automatic decision must be deterministic, explainable, versioned, auditable, reproducible, and exact to the cent.

Future UI/API work uses three decision levels: **Automatic**, **Automatic + Visible**, and **Needs Attention**. It must remain compatible with a later centralized Attention Center without implementing that center prematurely. See [`DEX_ACCOUNTING_BY_DEFAULT.md`](DEX_ACCOUNTING_BY_DEFAULT.md).

## Approved Architecture

An **Acquisition** is the purchase/receiving transaction and answers what entered the business. It may contain multiple product lines and product types. Existing product-specific **batches** remain the downstream processing and economics containers. Confirmed lines will project into the established Phase 3–7C batch model in a later approved phase; no existing economics service is replaced.

Approved product classes:

- `SINGLE_CARDS`
- `PACK_PRODUCT` — broad pack-format products, not booster-only
- `SEALED_PRODUCT` — broader non-pack sealed products

UPC identifies a commercial product, never a physical sealed unit. Receipt artifacts will live outside SQLite behind a provider-neutral, Google Drive-compatible abstraction. Manual entry must remain available during storage/extraction outages.

## Approved Safety Rules

- Draft Acquisition is the default safe state and receives an immutable ID immediately.
- Wizard autosave never confirms authoritative financial facts or reconciliation.
- Missing final USD stays Unknown; explicit `$0.00` requires an explicit zero-cost reason.
- Every product-line cost allocation discloses its method and remains non-authoritative until confirmed.
- Confirmed line costs reconcile exactly to final USD paid.
- Material discrepancy is `$5.00 OR 2%`; it requires reason, notes, exact final-USD re-entry, and stronger confirmation.
- A `50%+` difference receives severe escalation and a separate explicit confirmation.
- Receipt classifications are Inventory, Shipping/Fee, Business Noninventory, Personal/Nonbusiness, Duplicate Extraction, and Unresolved. Noninventory/personal lines never silently become inventory basis.
- Failed document uploads remain pending/retryable and never block manual acquisition entry.
- Incomplete acquisitions cannot create authoritative basis, economic rip allocation, authoritative sealed sales, or Finalized Economics portfolio totals.

## Lifecycle

1. `ACQUISITION_INCOMPLETE`
2. `RECONCILIATION_REQUIRED`
3. `READY_FOR_INTAKE`
4. `INTAKE_IN_PROGRESS`
5. `INTAKE_COMPLETE`
6. `CANCELED`

Ordinary autosave is permitted only while incomplete or reconciliation-required. Confirmation is an explicit request-safe event. Intake states are reserved for later approved downstream routing. Cancellation is durable history, not deletion.

## Phase 1: Foundation — Complete

- Additive `acquisitions`, `acquisition_lines`, and `acquisition_events` schema.
- Nullable `batches.acquisition_line_id` linkage.
- Immediate immutable acquisition UUID/code and idempotent creation.
- Optimistic revision checks for draft writes.
- Append-only lifecycle and allocation-confirmation events.
- Exact reconciliation and discrepancy severity service.
- Backend acquisition/line APIs and a machine-readable foundation contract.
- No current Inbound UI replacement, batch projection, UPC/catalog, documents, extraction, or SAM changes.

## Phase 2: Guided Wizard + Happy-Path Polish — Complete

- Three-screen resumable flow: product choice, combined Product & Purchase Details, and Review Acquisition.
- Single Cards asks only TCG, set, and quantity; hidden compatibility defaults route to Scan / Identify Now.
- Product lines remain independent, with explicit Add another product actions.
- Domestic/International progressive disclosure, merchant/date/payment facts, manual economics, and disabled future receipt controls share the details screen.
- A single product line receives an audited, versioned `SINGLE_LINE_100_PERCENT` allocation only during explicit authoritative confirmation; routine allocation controls are absent from the happy path.
- Multiple-line acquisitions remain exact to the cent. When DEX lacks safe allocation evidence, manual line allocation is exposed only inside the **Needs Attention → Resolve** exception path, leaving room for future receipt-derived deterministic proposals.
- Clean review says **Reconciled exactly** and presents one primary confirmation action. Missing cost, explicit zero, unresolved allocation, and purchase discrepancies publish `NEEDS_ATTENTION` metadata; detailed controls remain exception-only and retain every material/severe safeguard.
- Automatic allocation events preserve source facts, method, calculation version, resulting cents, per-unit result, affected acquisition/line, timestamp, and a link to final operator confirmation.
- Confirmation stops at `READY_FOR_INTAKE`; no downstream projection is performed.

## Phase 3: Product Catalog + UPC Intake — Complete

- Add a local commercial-product catalog and text identifiers for UPC-A, EAN-13, GTIN-14, and internal codes. Product class/subtype storage remains extensible without a replacement migration.
- Validate barcode check digits, preserve raw scans and leading zeroes, and use canonical 14-digit normalized text for collision-safe lookup.
- Recognized scans are **Automatic + Visible**. Repeat scans increment one product line; different products create independent lines; request-level idempotency and optimistic revisions prevent retry duplicates.
- Unknown scans are never guessed. Operators can search, identify locally, or remember an operator-confirmed mapping for future automatic recognition.
- Silent reassignment is blocked. Explicit corrections require reason/note and append audit history without rewriting earlier mapping events or acquisition facts.
- UPC identifies only a commercial product. Phase 3 creates no physical sealed-unit identity, batch, card, basis, receipt fact, or portfolio result.

## Phase 4: Source Documents — Complete

- Replace the receipt placeholders with camera/file capture for multiple JPG/JPEG/PNG/PDF artifacts. HEIC/HEIF remains visible but is rejected clearly unless the runtime has a verified safe decoder.
- Keep raw artifacts outside SQLite behind `DocumentStore`; activate only private local filesystem storage and retain an unconfigured Google Drive-compatible boundary without credentials or public links.
- Store provider metadata, SHA-256, detected MIME, byte size, integrity/storage state, acquisition linkage, tombstones, and append-only events in migration `0010_v22_phase4_source_documents`.
- Validate size, signatures, decoded image safety, lightweight PDF structure/page limits, filenames/path containment, duplicates, request IDs, and optimistic acquisition revisions.
- Let failed uploads remain visible and retryable without blocking manual facts. Draft removal deletes the local artifact but retains audit metadata; confirmed evidence becomes a durable tombstone and preserves the artifact outside normal view.
- Provide server-mediated private viewing with no-store/nosniff headers. No extraction, suggested facts, receipt-line matching, or downstream projection occurs.

## Implemented Phases

### Phase 5: Receipt extraction and matching — Complete

- Provider-neutral extraction jobs use immutable IDs, provider/version/timestamps, retry state, normalized candidates, confidence, and page/line provenance.
- The operational provider is private local PDF text extraction. Image OCR and external providers remain unconfigured; no document is transmitted externally.
- Empty draft fields may receive visible high-confidence proposals. Manual/confirmed facts are never silently overwritten, and operator replacements preserve the original candidate.
- Receipt lines support the approved classifications and deterministic matching priority. Fuzzy matches remain non-authoritative suggestions.
- Multi-line landed cost uses `receipt-landed-allocation-v1`: direct receipt merchandise plus shared components allocated proportionally by merchandise value, with exact-cent remainder assignment by immutable acquisition-line ID.
- Review keeps details collapsible, exposes Needs Attention exceptions, and preserves the final acquisition confirmation as the authority gate.

Versioned candidates, field-level confidence, receipt-line classifications, and product/quantity reconciliation. Candidate facts populate Review but remain non-authoritative until acquisition confirmation. Deterministic calculations may be Automatic + Visible; ambiguous classification, matching, or allocation becomes Needs Attention. No mandatory Manual Economics or Reconciliation screen returns.

### Phase 6: Downstream projection and routing — Complete

- Route confirmed lines partially through backend-generated preview and explicit confirmation. Decide Later remains resumable.
- Project one homogeneous existing-style batch per acquisition line with exact confirmed landed cost and durable line linkage.
- Create stable sealed units for Pack/Sealed lines; pending units are unavailable, Keep Sealed units become sellable inventory, and Rip/Open opens exact lowest eligible stable units into a draft rip.
- Route acquired singles into one existing singles batch/allocation session without SAM or premature per-card basis.
- Record append-only, idempotent operation and route events; use optimistic revisions and transactional locking to prevent duplicate projection or double claims.
- Transition `READY_FOR_INTAKE` to `INTAKE_IN_PROGRESS` or `INTAKE_COMPLETE` only from exact quantity reconciliation.

### Phase 7: SAM Recognition + Human Review — Implemented, pending operator QA

- Restrict recognition to One Piece while keeping provider-neutral metadata and reference interfaces for later TCGs.
- Combine structured cached OPTCG facts, a non-destructive incremental local reference index, physical scan/card-number evidence, scan-quality observations, and bounded visual comparison.
- Require strong multi-source agreement for `AUTO_MATCHED`; route ambiguity to `NEEDS_REVIEW` and absent trustworthy evidence to `UNIDENTIFIED`.
- Preserve append-only recognition jobs, ranked candidates, evidence, engine/rules/index versions, operator confirmation/correction/unidentified decisions, and original suggestions.
- Keep intake non-blocking with batch review queues and local Find Match. Only approved automatic or operator decisions become authoritative identity.
- Preserve acquisition/batch/rip/processed-scan provenance and the strict identity-only economics boundary.

## Later Phases — Not Authorized

JANA pricing, listing automation, cross-TCG recognition, autonomous retraining, production cutover, and authentication changes require separate approval.

### Future: Attention Center — Not Scheduled or Authorized

Centralize Critical, Review, and Advisory items that genuinely require operator judgment. Earlier exception APIs/events should project into this queue without architectural replacement.

## Global Gates

- Each phase requires explicit operator approval.
- All existing tests plus phase-specific regressions must pass.
- Migrations run transactionally and are tested only on disposable/copied Phase 7C fixtures.
- Every phase produces a Git-ready checkpoint with exclusions, migration notes, and rollback instructions.
- No production data or deployment configuration changes without a separate approved release step.
