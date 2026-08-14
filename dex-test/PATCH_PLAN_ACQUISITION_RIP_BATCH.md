# Patch Plan: Acquisition and Rip Batch Economics

Status: design decisions approved; phase implementation pending  
Baseline: Dex `v2.0-test` and `DEX_CURRENT_STATE.md`

## Objective

Extend the existing inbound batch model so Dex can answer, for each acquisition and rip:

- What was acquired, in what quantity, and at what landed cost?
- How much remains sealed, how much was opened, and which cards resulted?
- What are the current market and listed values of remaining sealed product and cards?
- What gross and net proceeds have been realized?
- How much acquisition cost has been recovered?
- What realized profit/loss and current total economic position remain?

This is operational inventory economics, not tax accounting. Values must remain reviewable and must not imply precision when market data or cost basis is missing.

## Approved Decisions

The following rules were approved before implementation and are requirements for this plan.

1. **One product type per batch, with transaction grouping.** Each acquisition batch represents one homogeneous product type. Multiple product-specific batches from the same receipt or order may share a Receipt/Acquisition Group reference. The group shows their common origin and supports later reconciliation of shared shipping, tax, discounts, and fees without weakening the one-product-type-per-batch rule.
2. **USD-only reporting with foreign-currency references.** USD is the only reporting and accounting currency in the first release. A batch may optionally preserve original currency, original foreign-currency amount, and final USD amount actually paid. Only the final USD amount is used for cost basis, recovery, and profit/loss. DEX will not calculate exchange rates, automatic conversions, or FX gains/losses.
3. **Acquisition-type cost allocation.** Ripped sealed product uses equal allocation by default. Purchased singles with known line-item costs use actual per-card acquisition cost. Lump-sum singles lots without individual costs use equal allocation by default. Manual override is allowed before finalization. Finalized per-card basis is immutable except through an explicit audited correction. A rip cannot finalize until the operator confirms that every participating card is accounted for. Intentionally unscanned or unidentified bulk must retain a reserved portion of basis instead of pushing the entire rip cost onto scanned cards.
4. **Scoped sealed sales in the first release.** DEX supports selling unopened units from an acquisition batch. A sealed sale reduces remaining quantity, recognizes correct per-unit basis, records sale price, marketplace, order number, fees, shipping, net proceeds, and realized profit/loss, prevents overselling, and permits multiple units from the same batch in one order. Card and sealed-product orders remain separate first-release workflows. Quantity reconciliation is: acquired = opened + sold sealed + remaining sealed + corrected/adjusted.
5. **Reason-aware Recycle Bin economics.** Recoverable recycled cards appear on a separate Excluded/Recycled line, retain assigned basis, and are excluded from active market/listed totals. Restore returns basis and value to active inventory. Recycling captures a categorized reason: Duplicate/Entry Error, Correction Hold, Damaged, Missing/Lost, or Other. Purge alone never determines accounting treatment. Erroneous records use audited basis correction/reallocation; real damage, loss, or disposal may use an audited loss/disposition adjustment. Recycle, restore, correction, purge, and permanent disposition history must be preserved.
6. **Optional guided legacy conversion.** Legacy batches remain estimate-only by default and may show a clearly labeled estimated economics preview. Estimated values must not be mixed with finalized totals without clear labeling, and no historical card receives permanent basis automatically. Conversion is optional and prioritizable per batch. The guided workflow confirms total acquisition cost, acquisition type, cards present, previously sold cards, recycled/missing/disposed cards, unscanned bulk, and allocation method; shows a reconciliation preview; and requires explicit confirmation. Finalization records a timestamp and audit entry and thereafter uses the same correction rules as new economics batches.

## Design Principles

1. Keep `batches` as the acquisition boundary. Do not create a separate acquisition system.
2. Keep `cards.batch_id` as the permanent link from every physical card to its acquisition.
3. Add rip/opening records only where a batch can be opened in stages or needs card-level cost allocation.
4. Reuse card market, listing, status, sale-order, and sale-item data.
5. Store source facts and immutable allocation snapshots; calculate dashboards and reports from those facts.
6. Never silently treat unknown cost or unknown market value as zero. Show valuation coverage and incomplete states.
7. Preserve physical SKUs, sale history, recycle protections, test/stable isolation, and manual fallback.
8. Use decimal-safe integer cents for new money fields and deterministic remainder allocation.

## Proposed Domain Model

### Acquisition Batch

An existing `batches` row becomes the economic container for one acquired lot. Examples:

- one booster box purchased for a rip;
- six identical sealed boxes, opened over several dates;
- purchased singles;
- a trade or inherited/existing inventory lot with an entered fair-value basis.

For the first release, a sealed-product batch represents one homogeneous product. Mixed purchases are split into product-specific batches linked by a shared Receipt/Acquisition Group reference. This keeps the current set/game workflow and avoids premature invoice and product-catalog subsystems while preserving transaction-level provenance.

### Rip Session

A `rip_sessions` row records one opening event against a batch. It consumes one or more sealed units and groups the resulting cards. A batch may have zero, one, or many rip sessions.

`cards.batch_id` remains authoritative. A nullable `cards.rip_session_id` adds provenance for cards produced by a specific opening. Cards purchased as singles remain directly attached to the batch with no rip session.

### Sealed Inventory

Sealed inventory is a batch-level quantity, not a fake card SKU:

`sealed remaining = acquired - opened - sold sealed - disposed sealed + returned sealed adjustments`

The first implementation should support homogeneous whole units. Nested box-to-pack-to-card transformations and mixed sealed SKUs are deferred until real workflows require a product-component model.

## Proposed Schema Changes

Names are provisional and should be finalized during migration design.

### Extend `batches`

Add:

| Field | Purpose |
| --- | --- |
| `economics_mode` | `LEGACY`, `SINGLES`, or `SEALED_RIP`; defaults to `LEGACY` for existing rows. |
| `product_name` | Operator-facing sealed product or acquired lot name. |
| `product_code` | Optional set/product/catalog code. |
| `receipt_group_reference` | Shared Receipt/Acquisition Group identifier linking product-specific batches from one transaction. |
| `invoice_reference` | Optional receipt, trade, or purchase reference. |
| `reporting_currency` | Constrained to `USD`. |
| `original_currency` | Optional reference currency; never used for calculations. |
| `original_foreign_amount` | Optional reference amount in the original currency. |
| `final_usd_paid_cents` | Final USD amount actually paid and the authoritative basis input. |
| `units_acquired` | Whole sealed units acquired; normally `0` for singles. |
| `purchase_subtotal_cents` | Product price before acquisition adjustments. |
| `acquisition_tax_cents` | Tax included in landed cost. |
| `inbound_shipping_cents` | Shipping paid to acquire the lot. |
| `acquisition_fees_cents` | Buyer fees or other capitalizable acquisition costs. |
| `acquisition_discount_cents` | Discounts/refunds reducing cost. |
| `sealed_market_unit_cents` | Current reviewed market value per unopened unit. |
| `sealed_market_updated_at` | Timestamp for sealed market value. |
| `sealed_listing_unit_cents` | Current asking price per listed unopened unit. |
| `sealed_listed_units` | Number of remaining sealed units currently listed. |
| `economics_status` | `ESTIMATED`, `DRAFT`, or `FINALIZED`; keeps legacy estimates separate from finalized totals. |
| `economics_finalized_at` | Explicit confirmation timestamp. |

Retain `total_cost` during transition for API compatibility. The canonical landed acquisition cost is denominated only in USD and becomes:

`purchase subtotal + tax + inbound shipping + acquisition fees - acquisition discount`

During compatibility phases, write the calculated landed total back to `total_cost` as dollars. Remove or rename it only in a later versioned migration after all consumers use integer cents.

Receipt/Acquisition Group reporting may show combined source amounts and unreconciled shared charges, but first-release batch economics uses only amounts explicitly assigned to each product-specific batch. DEX must not guess a cross-batch allocation.

### Add `rip_sessions`

| Field | Purpose |
| --- | --- |
| `id` | Primary key. |
| `batch_id` | Required reference to `batches`. |
| `opened_at` | Business timestamp/date of the rip. |
| `units_opened` | Whole sealed units consumed. |
| `allocated_cost_cents` | Immutable landed-cost basis consumed by this rip. |
| `allocation_method` | `EQUAL_CARD`, `ACTUAL_LINE_ITEM`, or `MANUAL`, subject to acquisition type. |
| `status` | `OPEN` while receiving cards; `FINALIZED` once allocations are locked. |
| `notes` | Operator notes. |
| `finalized_at` | Allocation lock timestamp. |

Constraints:

- Units opened across active/finalized sessions cannot exceed acquired units after sealed sales/dispositions.
- A finalized rip cannot change unit count or allocated cost without a recorded correction/reversal.
- Its allocated card basis must reconcile exactly to `allocated_cost_cents`.

### Extend `cards`

Add:

| Field | Purpose |
| --- | --- |
| `rip_session_id` | Nullable reference to the producing rip session. |
| `cost_basis_cents` | Immutable allocated acquisition basis for this physical card. |
| `cost_basis_source` | `ACTUAL_LINE_ITEM`, `BATCH_EQUAL`, `RIP_EQUAL`, `MANUAL`, or `UNKNOWN`. |
| `cost_basis_locked_at` | Timestamp after final allocation. |
| `recycle_reason_code` | Required category: `DUPLICATE_ENTRY_ERROR`, `CORRECTION_HOLD`, `DAMAGED`, `MISSING_LOST`, or `OTHER`. |

Do not derive cost basis live from the current card count. The present CSV calculation (`batch total / card count`) changes when cards are added, recycled, or purged and is unsuitable for realized P/L.

### Add `rip_bulk_lots`

Intentionally unscanned or unidentified physical bulk must participate in rip reconciliation without receiving fake card SKUs:

| Field | Purpose |
| --- | --- |
| `id` | Primary key. |
| `rip_session_id` | Required reference to the producing rip. |
| `description` | Operator label such as “unscanned commons.” |
| `quantity` | Count when known; nullable only with an explicit note. |
| `cost_basis_cents` | Reserved immutable share of rip basis. |
| `status` | `HELD`, `LATER_SCANNED`, `SOLD_BULK`, `DISPOSED`, or `CORRECTED`. |
| `created_at` / `resolved_at` | History timestamps. |

When bulk cards are scanned later, an audited transfer moves basis from the bulk lot to the new physical card records without changing total rip basis.

### Record sealed-product sales

Keep `sale_orders` as the common order table. Add `sealed_sale_items` rather than representing a box as a card. In the first release, a sale order is explicitly either `CARD` or `SEALED`; mixed card and sealed lines are rejected.

| Field | Purpose |
| --- | --- |
| `id` | Primary key. |
| `order_id` | Reference to the existing sale order. |
| `batch_id` | Acquisition batch supplying the sealed units. |
| `quantity` | Whole sealed units sold. |
| `gross_sale_cents` | Gross line revenue. |
| `cost_basis_cents` | Immutable basis of the sold sealed units. |
| `net_proceeds_cents` | Deterministically allocated order net proceeds. |

Extend existing `sale_items` with exact integer-cent facts:

- `gross_sale_cents`
- `net_proceeds_cents`
- `cost_basis_cents_at_sale`

Retain `sale_price` temporarily for compatibility. Replace the current equal split of order subtotal with explicit line amounts. Allocate order-level shipping collected, fees, and postage across lines within the applicable card-only or sealed-only order pro rata by gross amount, with deterministic cent rounding. Permit manual line allocation when gross values are unavailable.

### Add the economic correction ledger

Use an append-only `economic_adjustments` table rather than editing finalized history in place. Audited sealed-unit corrections and post-finalization basis corrections are required in the first release; refunds, returns, and chargebacks may be phased later:

- acquisition discount/refund;
- sale refund/chargeback;
- sealed-unit loss or disposal;
- card loss/disposal;
- manual cost-basis correction.

Each adjustment records a unique immutable event ID, duplicate-submission/idempotency key, batch, optional rip/card/order reference, amount or quantity delta, standardized reason code, required notes for material manual corrections, effective date, recorded timestamp, activity-log reference, and optional inverse-event relationship. The ledger may be absent from the read-only preview phase, but it is required before any economics record can be finalized or any corrected/adjusted sealed quantity can affect reconciliation. Records with economic history use durable tombstones rather than ordinary hard deletion.

## Calculations

All calculations operate per batch and can roll up across batches.

### Cost and quantity

- **Landed acquisition cost** = subtotal + tax + inbound shipping + acquisition fees - discounts/refunds.
- **Unit landed cost** = landed acquisition cost / units acquired for a homogeneous sealed batch, with cents distributed deterministically.
- **Opened-product cost** = sum of finalized rip `allocated_cost_cents`.
- **Remaining sealed cost basis** = cost basis of acquired units not opened, sold, returned, or disposed.
- **Remaining card cost basis** = sum of locked card basis for owned, unsold cards.
- **Sold cost basis** = card basis snapshots at sale + sealed-sale basis.

For purchased-singles batches with known line-item costs, use those actual costs. For lump-sum singles lots without individual costs, default to equal allocation. Ripped product also defaults to equal allocation. Manual overrides are permitted before finalization. Any unscanned/unidentified bulk reserve participates in the same exact reconciliation. Market-weighted allocation is deferred unless separately approved later.

### Value

- **Remaining card market value** = sum of `market_average` for active, unsold, non-recycled cards with known values.
- **Remaining sealed market value** = remaining sealed units × reviewed sealed market unit value.
- **Current market value** = remaining card market value + remaining sealed market value.
- **Remaining card listed value** = sum of listing price for active, unsold cards currently marked listed.
- **Remaining sealed listed value** = listed sealed units × sealed listing unit price.
- **Listed value** = remaining card listed value + remaining sealed listed value.

Market and listed totals must include coverage counts, for example `42 of 51 cards valued` and `2 of 3 sealed units valued`. If coverage is incomplete, label the displayed total **known value**, not total value.

### Realized economics

- **Gross realized sales** = sum of card and sealed gross sale line amounts, net of recorded sale refunds.
- **Realized net proceeds** = gross sales + allocated shipping collected - allocated platform fees - allocated postage - sale refunds/chargebacks.
- **Cost recovery percentage** = realized net proceeds / landed acquisition cost × 100.
- **Realized profit/loss** = realized net proceeds - sold cost basis.
- **Unrecovered acquisition cost** = max(landed acquisition cost - realized net proceeds, 0).

Sealed quantity must always reconcile as:

`acquired units = opened units + sold sealed units + remaining sealed units + corrected/adjusted units`

Cost recovery may exceed 100%. It is a cash-recovery measure and is intentionally different from realized profit/loss.

### Current position

- **Economic position** = realized net proceeds + known remaining current market value - landed acquisition cost.
- **Projected listed position** = realized net proceeds + known remaining listed value - landed acquisition cost.
- **Unrealized market P/L** = known remaining market value - remaining inventory cost basis.

Do not call economic position “profit” while unsold value remains estimated. Display freshness and coverage beside every estimated total.

## Proposed UI Workflow

### 1. Create acquisition batch

Extend **New Inbound Batch** with an Economics section:

- acquisition mode: Purchased Singles or Sealed Product / Rip;
- product name/code and units acquired;
- subtotal, tax, inbound shipping, buyer fees, and discount;
- calculated landed cost preview;
- optional invoice/reference and notes.

Keep existing game, set, color, finish, condition, scanner, and location fields. Existing `total_cost` input becomes the simple-mode landed-cost field; an **Enter cost breakdown** expansion reveals components.

### 2. Manage sealed product

The batch header adds a compact product strip:

- acquired, remaining sealed, opened, sold, and disposed quantities;
- landed cost and per-unit cost;
- sealed market/listing values and freshness;
- **Open Product** and **Sell Sealed** actions.

Opening product creates or selects an open rip session. Scanner/browser intake continues unchanged, but newly created cards inherit that `rip_session_id`.

### 3. Finalize a rip

Add **Finish Rip & Allocate Cost** before or alongside the existing **Finish & Print Labels** action:

1. Confirm units opened and resulting card count.
2. Review allocated rip cost.
3. Confirm that every intended card is represented by a scanned card or an unscanned/unidentified bulk reserve.
4. Apply the approved acquisition-type rule: rip equal allocation, known singles line costs, lump-sum equal allocation, or manual override.
5. Resolve rounding, bulk reserves, and any unknown/manual basis.
6. Review a complete reconciliation and explicitly confirm finalization.
7. Finalize allocation, complete the batch if appropriate, and print labels.

Completing a scan batch and finalizing economics should be distinct states. A user may finish one rip while keeping remaining product sealed for a later rip.

### 4. Batch economics view

Add an **Economics** panel to the existing batch detail rather than creating a parallel application area. Show:

- acquisition cost breakdown;
- sealed/opened/resulting-card quantities;
- realized gross sales and net proceeds;
- remaining known market and listed values;
- cost recovery percentage;
- realized P/L;
- economic and projected listed positions;
- valuation coverage/freshness warnings;
- rip-session history and linked sale orders.

### 5. Portfolio rollup

After batch economics is trusted, roll the same calculations into Inventory/Portfolio Analytics with filters for game, set, product, acquisition date, and batch. Batch detail remains the drill-down source of truth.

Receipt/Acquisition Group views may roll up linked batches and show shared transaction provenance. Shared costs remain visibly unreconciled until the operator assigns them to product-specific batches.

### 6. Exports

Extend inventory exports with immutable card basis, rip code/date, and batch economics identifiers. Add a batch-economics CSV containing source facts, coverage, realized amounts, remaining values, and calculation version. Do not replace historical sales exports.

## Edge Cases and Rules

- **Legacy batches:** remain estimate-only by default. Estimated and finalized totals are separated and labeled. Conversion is optional and prioritizable per batch.
- **Unknown basis:** trades, gifts, and existing inventory may use entered fair value or remain `UNKNOWN`; P/L is unavailable until resolved.
- **Zero-cost product:** gifts/promos are valid; cost recovery percentage is `N/A`, not infinity.
- **Partial openings:** multiple rip sessions consume a batch over time; quantities may not exceed remaining sealed units.
- **Mixed acquisitions:** split into homogeneous batches linked by a Receipt/Acquisition Group. Do not guess shared cost splits.
- **Loose packs from boxes:** defer product-component conversion; model the acquired economic unit consistently and document the chosen unit.
- **Cards added after rip finalization:** require reopening/correcting the rip allocation; never silently dilute existing card basis.
- **Recycled cards:** show on an Excluded/Recycled line, exclude from active market/listed value, preserve basis, and require a categorized reason.
- **Purged cards:** purge does not itself create a loss. Duplicate/Entry Error records require audited basis correction/reallocation; physical damage, loss, or disposal may create an audited loss/disposition. Preserve the complete action history before deleting any dependent record.
- **Sold-card restore/Undo:** reverse sale allocations and statuses atomically; do not duplicate proceeds or basis.
- **Returns/refunds/chargebacks:** append reversal adjustments and restore inventory when physically returned.
- **Order-level discounts or shipping:** allocate consistently across card and sealed lines; preserve the original order totals and cent reconciliation.
- **Fees added later:** use adjustments and recompute derived realized net amounts without changing original gross line facts.
- **Missing/stale prices:** report known value, coverage, and timestamp. Do not substitute listing price for market value without labeling the fallback.
- **Market-price changes:** affect only current position, never historical cost basis or realized P/L.
- **Alternate art and identification corrections:** basis stays with the physical SKU even if identity changes.
- **Currency:** calculations use final USD paid only. Original currency and amount are optional references; there is no conversion or FX accounting.
- **Rounding:** every allocation must reconcile exactly in integer cents; assign residual cents deterministically and record the allocation method.
- **Taxes:** acquisition tax belongs in landed basis. Sales-tax collection/remittance is out of scope unless the seller actually receives or pays it.
- **Labor, supplies, grading, and overhead:** excluded initially. They may later become explicit expenses but must not be silently folded into card basis.

## Migration Impact

1. Introduce a versioned migration mechanism before these changes, per `DEX_CURRENT_STATE.md`.
2. Add nullable/defaulted fields and new tables without rewriting existing SKUs, card identities, batches, or sales.
3. Mark existing batches `LEGACY` and preserve `total_cost` exactly.
4. Do not backfill immutable card basis automatically. Offer a guided, per-batch, preview-and-confirm conversion covering acquisition type, total cost, cards present, prior sales, recycled/missing/disposed cards, unscanned bulk, and allocation method.
5. Convert legacy dollar amounts to integer cents with explicit rounding and reconciliation reports.
6. Backfill existing `sale_items.gross_sale_cents` from `sale_price`, but flag multi-card orders as `LEGACY_EQUAL_SPLIT` because current code divided subtotal equally.
7. Derive legacy order net allocation deterministically while retaining original order totals. Report that historical item-level net values are reconstructed estimates.
8. Add indexes for `rip_sessions.batch_id`, `rip_bulk_lots.rip_session_id`, `cards.rip_session_id`, `sealed_sale_items.batch_id`, Receipt/Acquisition Group references, and economic order lookups.
9. Back up and verify the database and images before migration; run upgrade tests against representative v1.x and v2.0-test fixtures.
10. Keep old API response fields during a deprecation window so existing UI and CSV behavior remains stable.

## Proposed API Shape

Exact routes are subject to implementation review:

- `GET/PATCH /api/batches/{id}/economics`
- `POST /api/batches/{id}/rips`
- `GET/PATCH /api/rips/{id}`
- `POST /api/rips/{id}/finalize`
- `POST /api/batches/{id}/sealed-sale`
- `GET /api/economics/batches`
- `GET /api/export/batch-economics.csv`

Calculation responses should include integer-cent facts, display amounts, valuation coverage, price timestamps, calculation version, and explicit `complete/incomplete` flags.

## Implementation Phases

### Phase 1: Foundations and approved-rule fixtures

- **Approval status:** approved and completed; all Phase 1 tests pass.
- Encode the approved terminology, formulas, ownership/status rules, USD-only calculation policy, Receipt/Acquisition Group behavior, and reason categories as specifications and fixtures.
- Collect representative scenarios: full box rip, partial rip, purchased singles, sealed-only sale, card-only sale, rejected mixed order, refund, recycle/disposal, unscanned bulk, and legacy batch.
- Add a versioned migration ledger and deterministic integer-cent allocation helpers before feature schema changes.
- Preserve all current operator workflows and API responses; Phase 1 adds no acquisition-economics fields or screens.
- Keep refactoring minimal. Prefer dedicated economics and migration modules, but do not reorganize unrelated existing code or make `app.py` larger without need.
- Run migrations transactionally where SQLite permits. A failed migration must roll back, remain unrecorded, and never leave the database half-migrated or falsely marked complete.
- Test migrations only against disposable copies and legacy database fixtures, never against a production server database or irreplaceable inventory data.
- Make exact-cent allocation deterministic and fully reconcilable. For example, allocating $10.00 across three ordered cards always produces $3.34, $3.33, and $3.33 according to one documented stable ordering rule.
- Keep all existing eight tests passing and add Phase 1 tests on top of them.

### Phase 2: Read-only legacy batch economics

- **Approval status:** approved and completed; all Phase 2 tests pass.
- Build one calculation service over current `batches`, `cards`, `sale_orders`, and `sale_items`.
- Show clearly labeled legacy estimates and valuation coverage without changing operator workflows.
- Add formula and reconciliation tests.
- Make the estimated state visually unmistakable with wording such as **“Estimate only. Cost basis not finalized.”** A small badge alone is insufficient.
- Show valuation coverage beside every value-dependent total, for example `Market Value: $184.22 • 18/24 cards valued`.
- Preserve unknown prices as `Unknown`; never substitute `$0`. If `total_cost` is not trustworthy, show **Cost Unknown / Incomplete** instead of a zero acquisition cost.
- Show prominent material-understatement warnings when DEX detects unscanned bulk, missing inventory, incomplete sales data, or other reconciliation gaps.
- For orders containing cards from multiple acquisition batches, allocate the existing historical proceeds and fees once across the participating items so no batch preview double-counts an order. Label the historical allocation as estimated.
- Show recycled-card known basis/value separately and exclude it from active inventory value.
- Keep the preview API strictly read-only: loading it must never mutate legacy rows, write allocation choices, finalize basis, or repair data.
- Add a reasonably large-batch performance test so the preview does not make batch pages unacceptably slow.
- Preserve all existing workflows and keep the original eight tests plus every previously approved phase test passing.

### Phase 3: Acquisition cost facts and receipt groups

- **Approval status:** approved with all previously approved decision amendments and the constraints below.
- Add batch economics, optional foreign-currency reference fields, Receipt/Acquisition Group references, and cost-breakdown UI.
- Preserve `total_cost` compatibility.
- Add audit entries and CSV fields for acquisition changes.
- Support the approved acquisition modes: sealed product/rip, purchased singles with known line-item costs, and lump-sum singles lot.
- Keep one homogeneous product type and quantity per batch. Let several product-specific batches share a Receipt/Acquisition Group reference without merging inventory, quantities, or assigned costs.
- Never automatically divide shared transaction shipping, tax, discounts, or fees across linked batches. Shared amounts remain visibly unreconciled until explicitly assigned.
- Treat `final_usd_paid_cents` as the sole authoritative input for cost basis, recovery, and profit/loss. Preserve original currency and foreign amount as optional reference-only fields and perform no FX calculation or conversion.
- Store all new monetary facts in integer cents. If the entered cost components do not equal final USD paid, show the exact difference and require correction or explicit acknowledgement while keeping final USD paid authoritative.
- Keep missing acquisition cost as `Unknown/Incomplete`, never zero.
- Record material acquisition-cost edits in the audit history and prevent silent rewriting of finalized economics.
- Keep existing `total_cost` compatible through a deterministic, tested mirror of the authoritative USD amount during the transition.
- Add no rip session, permanent card basis, sealed-sale workflow, or economics finalization in this phase.
- Preserve all existing workflows and keep the original eight tests plus every previously approved phase test passing.

### Phase 4: Rip sessions, bulk reserves, and immutable card basis

- **Approval status:** approved with all previously approved allocation rules and the constraints below.
- Add rip sessions, intake association, unscanned/unidentified bulk reserves, allocation preview/finalization, and audited correction rules.
- Implement the approved acquisition-type allocation rules and require complete reconciliation plus explicit confirmation.
- Never activate a rip for scanner intake implicitly. The operator must explicitly start/select it. While active, show an unmistakable banner such as **“Scanner intake is currently assigned to RIP-#### / Product Name.”**
- Require confirmation before switching the active rip when unprocessed scanner files exist.
- Enforce that a card belongs to no more than one rip session.
- Lock finalized rips against ordinary intake. Later additions use only the audited correction workflow.
- For unscanned bulk, require either a known physical card quantity or an explicit manually reserved basis amount. DEX must invent neither quantity nor basis.
- When equal allocation is used and bulk quantity is known, include that quantity in the same per-card allocation math as scanned cards. When quantity is unknown, require an explicit manual reserve and label valuation coverage incomplete.
- Allocate remainder cents using a documented stable ordering based on immutable SKU/internal card ID, never UI sorting, scan order, mutable identity fields, or unspecified database order.
- Show a final confirmation reconciliation of **rip cost → scanned-card basis → bulk-reserve basis → total allocated → difference** and require an exact `$0.00` difference.
- Calculate partial-rip consumed cost from authoritative landed unit cost. Cumulative opened units cannot exceed acquired units minus units already sold sealed or corrected/adjusted.
- Preserve original finalized allocations. Every post-finalization correction appends history instead of overwriting the original allocation.
- Keep existing batch completion and label printing fully usable while economics remains unfinished.

### Phase 5: Sealed inventory and separate sealed sales

- **Approval status:** approved with all previously discussed safeguards and the constraints below.
- Track sealed quantity states and values.
- Add sealed-only outbound orders and reject mixed card/sealed orders in the first release.
- Replace equal card sale splitting with explicit gross lines and deterministic net allocation.
- Migrate existing historical sale orders safely to `order_type = CARD` without changing their financial facts.
- Assign sealed-unit basis with the Phase 1 deterministic cent-allocation rule. If the operator does not select specific identical units, consume the lowest available stable unit sequence first.
- Require trustworthy acquisition cost and `units_acquired` before sealed-unit records can be finalized, opened, or sold.
- Define gross sale price as merchandise revenue only. Exclude marketplace-collected sales tax from revenue and profit/loss.
- Define sealed net proceeds as merchandise revenue + shipping collected - marketplace fees - actual postage. Keep packaging and supply costs separate in this release.
- Preserve order-level economics plus the exact sealed-unit IDs and basis consumed for every multi-unit order.
- Keep cancellation/Undo separate from future refund and return workflows.
- Require a reason and complete audit history for every sealed quantity correction.
- Transactionally lock/check unit availability when opening or selling so one unit cannot be consumed twice.
- Keep Receipt/Acquisition Groups informational; they never change or allocate basis automatically.

### Phase 6: Batch economics UI and exports

- **Approval status:** approved with all previously approved reporting safeguards and the constraints below.
- Deliver batch cards, drill-down calculations, rip history, coverage warnings, and batch-economics CSV.
- Verify mobile and desktop layouts and printing/intake regressions.
- Keep **Realized Economics** visually separate from **Unrealized/Remaining Value**. Market and listed value must never appear to be realized profit.
- Define **Cost Recovery %** as realized net proceeds / authoritative acquisition cost. It may exceed 100% and is never capped.
- Define **Current Economic Position** as realized net proceeds + known remaining market value - acquisition cost.
- Define **Projected Listed Position** as realized net proceeds + known remaining listed value - acquisition cost.
- Show valuation coverage for both position figures and label them incomplete whenever unknown-priced inventory exists. Never substitute listed value for missing market value or market value for missing listed value.
- Show valuation freshness date/time when known. If unavailable, display **Freshness Unknown**, never “current.”
- Label Receipt/Acquisition Group rollups as informational aggregation only and state that shared costs were not allocated automatically.
- Allocate/count each sale order exactly once at order/group/portfolio level. Batch views may show attributable portions, but rollups must not duplicate revenue, fees, or other order-level amounts.
- Use backend-generated economics values everywhere; the frontend performs formatting only.
- Store no calculated dashboard totals. Recalculate from source facts to prevent stale results.
- Include a calculation version in every economics API response and export.
- Add CSV columns backwards-compatibly during the compatibility period and never silently change an existing column's meaning.
- Use collapsible batch sections in this order: **Summary**, **Acquisition**, **Recovery & P/L**, **Remaining Inventory**, **Rip Sessions**, **Sales**, and **Reconciliation / Warnings**.
- Make the first screenful answer: **What did this cost? How much have I recovered? What remains? Am I currently ahead or behind?**

### Phase 7: Immutable economic events and Operational Economics

- **Approval status:** approved as the gated **7A → 7B → 7C** sequence below. Each subphase must pass its complete test gate before implementation begins on the next.
- Keep the append-only economic-event architecture. Every event receives a unique immutable event ID, duplicate-submission protection, effective date, recorded timestamp, standardized reason code, and durable audit relationship.
- Require notes for material manual corrections.
- Preserve records/tombstones for anything with economic history; normal workflows must not hard-delete the durable history.
- Represent reversals as linked inverse events. Never modify or delete the original event.
- Reuse the original stable sale allocation for all later cross-batch order attribution; never recalculate the same order using a different allocation rule.
- Call the portfolio dashboard **Operational Economics**. DEX records operational economics, losses, and dispositions only and makes no tax-deduction or tax-accounting conclusions.

#### Phase 7A: Corrections and dispositions

- Add acquisition-cost, card-basis, bulk-reserve, sealed-quantity, duplicate/error, physical damage, loss, disposal, and post-finalization correction workflows.
- Keep Duplicate/Entry Error corrections separate from real physical loss/disposition.
- Preserve original finalized allocations and append every correction or inverse event.
- Block ordinary hard deletion when economic history exists and preserve a durable tombstone/history record.
- Complete migration, reconciliation, duplicate-submission, reversal, disposition, audit, and regression tests before Phase 7B begins.

#### Phase 7B: Refunds, returns, chargebacks, and post-sale corrections

- Model refunds, returns, and chargebacks as distinct event types.
- Support partial refunds.
- Do not restore inventory automatically for a refund or chargeback.
- Return inventory to available status only after physical receipt and condition are explicitly confirmed.
- Route returned damaged items to Damaged/Excluded rather than normal sellable inventory.
- Record marketplace fee credits/reversals as separate events when known.
- Treat postage as spent unless an actual carrier/postage refund is recorded as its own event.
- Add post-sale fee, shipping, and proceeds corrections without overwriting original order facts or stable item/batch attribution.
- Complete financial reconciliation, state-transition, idempotency, cross-batch attribution, audit, and regression tests before Phase 7C begins.

#### Phase 7C: Portfolio Operational Economics

- Roll trusted source facts into the **Operational Economics** dashboard and exports.
- Default portfolio totals to Finalized Economics only. Keep estimated legacy economics clearly separate and opt-in for comparison.
- Preserve the Phase 6 separation of Realized Economics from Unrealized/Remaining Value, including coverage, freshness, calculation version, and incomplete-state warnings.
- Count each order exactly once at portfolio/group level and use its original stable allocation for attributable batch views.
- Add alerts for unreconciled quantities, incomplete allocations, missing basis, stale/unknown values, incomplete sale allocation, and unresolved economic events.
- Store no calculated dashboard totals; recalculate from source facts.
- Complete correctness, de-duplication, calculation-version, coverage, freshness, performance, export, UI, and full regression tests before Phase 7 is complete.

## Acceptance Criteria

- Every resulting card remains linked to its original batch and, when applicable, its rip session.
- Product-specific batches from one transaction can share a Receipt/Acquisition Group without combining their inventory or silently sharing cost.
- Sealed, opened, sold, disposed, and remaining quantities reconcile.
- Allocated card basis plus unscanned/unidentified bulk reserves reconciles exactly to finalized rip cost.
- Known singles use actual line-item basis; rip and lump-sum singles default to equal allocation; manual override is available before finalization.
- Gross sales, order adjustments, and allocated net proceeds reconcile exactly to sale orders.
- Realized P/L uses sold cost basis; cost recovery uses total landed acquisition cost.
- Current and listed positions show price coverage and freshness and never silently value unknown items at zero.
- Finalized cost basis is not changed by later card additions, identification changes, recycling, or market-price updates.
- Finalized basis changes only through an explicit audited correction.
- Final USD paid is the only calculation input; foreign-currency data remains reference-only.
- Sealed orders cannot oversell, may contain multiple units from one batch, and remain separate from card orders.
- Recycled-card reporting and permanent treatment follow the approved reason-aware rules and preserve history.
- Refunds, returns, and chargebacks are distinct immutable event types; refunds and chargebacks do not restore inventory automatically.
- Returned inventory becomes available only after physical receipt and condition confirmation; damaged returns route to Damaged/Excluded.
- Partial refunds, separate marketplace fee credits/reversals, and actual carrier/postage refunds reconcile without rewriting original sale facts.
- Every economic event has immutable identity, duplicate-submission protection, effective date, recorded timestamp, standardized reason, and linked inverse-event reversal support.
- Records with economic history retain durable history/tombstones and are not hard-deleted through ordinary workflows.
- Legacy batches and sales remain readable and are clearly labeled when item-level economics are estimated.
- Existing inbound, SAM, labels, inventory, outbound, Recycle Bin, exports, and Undo workflows continue to pass regression tests.
- No automatic marketplace pricing, tax reporting, or accounting claims are introduced.

## Approval Status

All six design decisions are approved and recorded in **Approved Decisions**. Implementation remains subject to phase-by-phase approval.
