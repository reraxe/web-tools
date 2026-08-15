# DEX v2.2-test — Inbound 2.0 Approved Plan

Status: architecture approved; Phases 1–3 complete; Phase 4 not authorized

Known-good baseline: immutable `v2.1-test` Phase 7C checkpoint

Known-good restore point: preserved `v2.2-test` Inbound 2.0 Phase 2 Happy-Path Polish checkpoint

Current checkpoint: `v2.2-test` Inbound 2.0 Phase 3 Product Catalog + UPC Intake

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

## Later Phases — Not Authorized

### Phase 4: Source documents

Provider-neutral external storage, protected multi-document upload/capture, metadata/hash tracking, retryable failures, and Google Drive-compatible adapter contract. Provider failure must not block manual acquisition entry.

### Phase 5: Receipt extraction and matching

Versioned candidates, field-level confidence, receipt-line classifications, and product/quantity reconciliation. Candidate facts populate Review but remain non-authoritative until acquisition confirmation. Deterministic calculations may be Automatic + Visible; ambiguous classification, matching, or allocation becomes Needs Attention. No mandatory Manual Economics or Reconciliation screen returns.

### Phase 6: Downstream projection and routing

Transactional projection of confirmed lines into established homogeneous batches, sealed units, rip/open, scans, and acquired-singles workflows.

### Phase 7: Operator cutover and hardening

Make New Acquisition primary only after full compatibility, accessibility, performance, security, rollback, and operator QA gates pass.

### Future: Attention Center — Not Scheduled or Authorized

Centralize Critical, Review, and Advisory items that genuinely require operator judgment. Earlier exception APIs/events should project into this queue without architectural replacement.

## Global Gates

- Each phase requires explicit operator approval.
- All existing tests plus phase-specific regressions must pass.
- Migrations run transactionally and are tested only on disposable/copied Phase 7C fixtures.
- Every phase produces a Git-ready checkpoint with exclusions, migration notes, and rollback instructions.
- No production data or deployment configuration changes without a separate approved release step.
