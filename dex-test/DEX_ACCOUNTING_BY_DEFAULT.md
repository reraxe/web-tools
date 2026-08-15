# DEX Accounting-by-Default UX Directive

Status: approved standing product/design contract. This document does not authorize Phase 3 or any later implementation phase.

Known-good restore baseline: preserved DEX v2.2-test Inbound 2.0 Phase 2 UX Revision checkpoint. The authorized Phase 2 Happy-Path Polish implements this directive for the current three-screen acquisition flow.

## Standing Product Rule

The operator provides business facts. DEX performs deterministic accounting. DEX asks for human attention only when reality is ambiguous, conflicting, incomplete, or materially exceptional.

The design test for future accounting features is:

- If DEX can determine it safely from authoritative facts, DEX should do it.
- If the operator merely needs visibility, show the result without creating another task.
- If DEX cannot determine it safely, request attention and preserve the unresolved state.

The desired normal experience is: operator records what happened → DEX handles the accounting → operator reviews the result → exceptions request attention.

## Decision Levels

Every new accounting-oriented workflow should use one of three levels:

1. **Automatic:** sufficient authoritative facts exist, so DEX completes the deterministic calculation or action.
2. **Automatic + Visible:** DEX completes the work and explains what it did without requiring a separate confirmation for the calculation.
3. **Needs Attention:** facts are ambiguous, conflicting, incomplete, or materially exceptional, so operator judgment is required.

## Backend Calculation Authority

Backend economics services remain the sole calculation authority. The frontend formats and displays backend results; it must not duplicate accounting formulas.

When sufficient authoritative source facts exist, DEX should automatically derive applicable values already governed by the Phase 3–7C economics architecture, including:

- purchase-component arithmetic and final landed cost;
- product-line and shared-cost allocation;
- per-unit basis and exact-cent reconciliation;
- recovery, effective proceeds, realized P/L, and operational loss;
- tax handling already established by DEX economics rules;
- remaining and derived inventory economics.

Every automatic result must be deterministic, explainable, versioned, auditable, reproducible, and exact to the cent.

## Never Invent Source Facts

Automation is calculation, not guessing. DEX may calculate from authoritative quantities and costs, but it must not silently classify an unexplained charge, unidentified product, unknown quantity, missing payment fact, conflicting UPC, or ambiguous transaction.

Missing source facts remain **Unknown** or **Unresolved**. Automation failure must degrade safely:

- unavailable extraction → manual entry remains available;
- unavailable document provider → acquisition continues and upload remains pending/retryable;
- unknown UPC → manual identification;
- impossible deterministic allocation → Needs Attention/manual allocation;
- missing final USD → acquisition remains incomplete.

## Inbound 2.0 Happy Path

The primary workflow remains three screens:

1. **What did you acquire?** One Single Cards, Pack Product, or Sealed Product line is created by default. Additional lines appear only through explicit add-line actions.
2. **Product & Purchase Details.** Collect business facts, not accounting mechanics. Purchase source, merchant, date, payment method, product identity, and quantities share this screen. Domestic purchases hide foreign-reference fields; International purchases reveal them. DEX performs no FX conversion.
3. **Review Acquisition.** Present the human-readable transaction, products, quantities, source-document status, components, final USD, backend-calculated landed costs, per-unit cost, reconciliation, and unresolved exceptions. The normal primary action is **Confirm Acquisition**.

Single Cards keeps TCG, set, and quantity on the happy path and defaults internally to Scan / Identify Now. Accounting implementation details stay hidden unless clarification is genuinely required.

## Allocation and Reconciliation

For one product line, DEX assigns 100% of authoritative landed cost automatically at acquisition confirmation. It records the method and source facts without showing per-line accounting controls.

For multiple lines, future receipt/catalog evidence should allow backend-generated deterministic allocation proposals using a disclosed approved method, such as direct receipt-line attribution or a specified proportional/equal method. DEX must never silently switch methods. Manual controls are an exception path for ambiguity, conflict, failed reconciliation, or explicit override.

When purchase components and line allocations reconcile, Review shows **Reconciled exactly** and requires no separate accounting task. When they do not, Review shows **Purchase needs attention** and exposes the established exception safeguards:

- `$5 OR 2%` material threshold;
- severe escalation at `50%+`;
- standardized reason and required explanatory note;
- exact final-USD re-entry;
- explicit material and severe confirmations.

## Future Receipt Intelligence Contract

Receipt/source documents are intended to become the normal economics input. Future approved phases should support multiple photos, images, screenshots, PDFs, invoices, and payment confirmations through a provider-neutral document abstraction.

Extraction may propose merchant, date, order reference, products, quantities, merchandise prices, subtotal, tax, shipping, fees, discounts, currency, and final paid. Extracted values remain proposed facts until acquisition confirmation. Manual entry remains a fallback and correction path; no mandatory Manual Economics screen returns.

Receipt lines retain explicit classifications: Inventory, Shipping/Fee, Business Noninventory, Personal/Nonbusiness, Duplicate Extraction, and Unresolved. Personal/nonbusiness and unrelated noninventory lines must never silently become inventory basis.

## Future Attention Center Contract

A future persistent **Attention Center** should centralize cases requiring judgment instead of interrupting routine work. Current exception contracts should remain compatible with later queue projection.

Suggested levels:

- **Critical:** authoritative inventory or economics integrity is blocked.
- **Review:** DEX has a probable answer but needs confirmation.
- **Advisory:** nothing is blocked, but operator awareness is useful.

Potential items include receipt/payment conflicts, unmatched products or quantities, unknown/conflicting UPC mappings, low-confidence extraction, unreadable documents, ambiguous allocation, SAM uncertainty, unmatched returns, or corrections that would create invalid negative economics.

The full Attention Center is not authorized by this directive.

## Automatic Audit Trail

Reducing operator work must not reduce traceability. DEX automatically records the source facts used, calculation/allocation method, calculation version, result values, timestamp, acquisition/product-line identity, acquisition confirmation, and later correction/reversal lineage. The operator should not have to construct this audit trail manually.

## Phase Boundary

This directive governs design across upcoming work. Its Phase 2 Happy-Path subset is implemented; Phase 3 Product Catalog + UPC, document storage, receipt extraction, SAM integration, downstream projection, and the Attention Center each remain separately gated.

All future work must preserve the accepted v2.2 acquisition state machine and Phase 3–7C economics compatibility.
