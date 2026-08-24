const assert = require("assert");
const fs = require("fs");
const vm = require("vm");
const styles = fs.readFileSync("static/styles.css", "utf8");

class ElementStub {
  constructor(key = "") {
    this.innerHTML = ""; this.textContent = ""; this.dataset = key ? { viewportKey: key } : {};
    this.style = {}; this.complete = true; this.value = ""; this.open = false; this.focused = false;
    this.classList = { add() {}, remove() {}, toggle() {} };
  }
  addEventListener() {}
  closest() { return null; }
  focus() { this.focused = true; }
  querySelector() { return null; }
  querySelectorAll() { return []; }
  getBoundingClientRect() { return { top: 120, bottom: 170 }; }
  showModal() { this.open = true; }
  close() { this.open = false; }
}

const app = new ElementStub();
const heading = new ElementStub();
const topbar = new ElementStub(); topbar.getBoundingClientRect = () => ({ top: 0, bottom: 68 });
const elements = new Map([["#app", app], ["#wizard-screen-title", heading], [".topbar", topbar], ["#modal", new ElementStub()]]);
const document = {
  activeElement: null,
  body: new ElementStub(),
  querySelector(selector) { if (!elements.has(selector)) elements.set(selector, new ElementStub()); return elements.get(selector); },
  querySelectorAll() { return []; },
  addEventListener() {},
};

class FormDataStub {
  constructor(form) { this.values = form?.values || []; }
  entries() { return this.values[Symbol.iterator](); }
}

const draft = {
  acquisition: {
    id: 7, acquisition_uuid: "ACQ-IMMUTABLE", acquisition_code: "ACQ-20260815-0007",
    state: "ACQUISITION_INCOMPLETE", revision: 4, wizard_step: "PRODUCTS", source_scope: "DOMESTIC",
    merchant_name: "Disposable Wizard Shop", merchant_country: "", purchased_on: "2026-08-15",
    payment_method: "CREDIT_DEBIT_CARD", order_reference: "QA-PHASE2", original_currency: "",
    original_foreign_amount_minor: null, purchase_subtotal_cents: 18000, acquisition_tax_cents: 1200,
    inbound_shipping_cents: 800, acquisition_fees_cents: 0, import_duties_cents: null,
    brokerage_cents: null, acquisition_discount_cents: 0, final_usd_paid_cents: 20000,
    discrepancy_reason_code: "", discrepancy_notes: "", created_at: "2026-08-15T12:00:00+00:00",
  },
  lines: [
    { id: 11, line_uuid: "LINE-PACK", line_sequence: 1, product_class: "PACK_PRODUCT", game: "One Piece", product_name: "OP16 Packs", set_code: "OP16", pack_type: "Single Pack", quantity: 12, quantity_certainty: "KNOWN", singles_cost_mode: "", intended_action: "KEEP_SEALED", assigned_landed_cost_cents: 12000, allocation_method: "QUANTITY_WEIGHTED", allocation_status: "CONFIRMED", canceled_at: null, per_unit_cost: { base_cents: 1000, remainder_units: 0, quantity: 12, minimum_cents: 1000, maximum_cents: 1000, exact_when_uniform: true } },
    { id: 12, line_uuid: "LINE-SINGLES", line_sequence: 2, product_class: "SINGLE_CARDS", game: "Pokemon", product_name: "", set_code: "Journey Together", pack_type: "", quantity: 20, quantity_certainty: "KNOWN", singles_cost_mode: "LUMP_SUM", intended_action: "SCAN_IDENTIFY", assigned_landed_cost_cents: 8000, allocation_method: "MANUAL", allocation_status: "CONFIRMED", canceled_at: null, per_unit_cost: { base_cents: 400, remainder_units: 0, quantity: 20, minimum_cents: 400, maximum_cents: 400, exact_when_uniform: true } },
  ],
  events: [],
  reconciliation: { component_total_cents: 20000, final_usd_paid_cents: 20000, difference_cents: 0, difference_percent: 0, severity: "NONE", material: false, extreme: false, assigned_line_cost_cents: 20000, allocation_difference_cents: 0, allocation_reconciled: true },
  readiness: { ready_to_confirm: true, warnings: [], authoritative_cost_label: "$200.00" },
  automatic_single_line_allocation_preview: null,
  attention: { decision_level: "AUTOMATIC_VISIBLE", attention_level: null, headline: "DEX completed the deterministic accounting", message: "Review and confirm.", reason_codes: [], resolve_mode: null, requires_operator_judgment: false },
  projection: { status: "NOT_IMPLEMENTED_PHASE_1", batch_ids: [] },
};

const context = {
  console, document, Intl, Date, Set, Map, URL, URLSearchParams, FormData: FormDataStub, Blob,
  FileReader: class {}, setTimeout, clearTimeout, requestAnimationFrame: (callback) => callback(),
  confirm: () => true, fetch: async () => ({ ok: true, status: 200, json: async () => draft }),
  history: { replaceState() {} }, location: { hash: "#inbound", reload() {} },
  navigator: { clipboard: { writeText: async () => {} } },
};
context.window = { addEventListener() {}, lucide: null, location: context.location, innerHeight: 900, scrollY: 0, scrollBy() {}, scrollTo() {} };
context.globalThis = context;
vm.createContext(context);
const source = fs.readFileSync("static/app.js", "utf8").replace(/\nboot\(\);\s*$/, "\n");
vm.runInContext(source, context);
vm.runInContext(`state.activeAcquisition = ${JSON.stringify(draft)}`, context);

// The primary flow is exactly three semantic, keyboard-operable screens.
const acquire = vm.runInContext("wizardAcquireScreen()", context);
assert(acquire.includes('id="wizard-screen-title" tabindex="-1"'));
assert(acquire.includes("Single Cards") && acquire.includes("Pack Product") && acquire.includes("Sealed Product"));
assert(acquire.includes('<button class="choice-card"'));
const progress = vm.runInContext("wizardProgress('PRODUCTS')", context);
assert(progress.includes('aria-current="step"'));
assert(progress.includes("What did you acquire?") && progress.includes("Product &amp; Purchase Details") && progress.includes("Review Acquisition"));
assert.strictEqual((progress.match(/<li/g) || []).length, 3);

// Product and purchase details use progressive disclosure and keep extra products explicit.
const products = vm.runInContext("wizardProductsScreen()", context);
assert(products.includes("OP16 Packs") && products.includes("Pokemon • Journey Together"));
assert(products.includes("Pack format") && products.includes("Add another product only if needed"));
assert(products.includes("Payment method") && products.includes("Credit / Debit Card"));
assert(products.includes("Take Photo") && products.includes("Upload") && products.includes("No receipt currently attached"));
assert(products.includes("DEX will reconcile product-line costs on Review"));
assert(!products.includes("Assigned landed cost") && !products.includes("Allocation method") && !products.includes("Confirm line allocation"));
assert(products.includes('class="form-grid international-fields" hidden'));
assert(styles.includes(".international-fields[hidden] { display: none !important; }"));
assert(!products.includes("Quantity confidence") && !products.includes("Singles accounting method") && !products.includes("Identification plan"));
assert(!products.includes("Scanner Order") && !products.includes("Drawer location") && !products.includes("Rarity"));
vm.runInContext("state.activeAcquisition.acquisition.source_scope = 'INTERNATIONAL'", context);
const international = vm.runInContext("wizardProductsScreen()", context);
assert(international.includes("Original currency") && international.includes("Merchant country") && international.includes("Import duties"));
assert(!international.includes('class="form-grid international-fields" hidden'));

// Draft serialization preserves explicit zero and removes irrelevant foreign fields for Domestic.
const serialized = vm.runInContext("acquisitionAutosavePayload({ values: [['source_scope','DOMESTIC'],['payment_method','CASH'],['final_usd_paid','0.00'],['purchase_subtotal',''],['original_currency','JPY'],['original_foreign_amount_minor','1000']] })", context);
assert.strictEqual(serialized.final_usd_paid_cents, 0);
assert.strictEqual(serialized.purchase_subtotal_cents, null);
assert.strictEqual(serialized.original_currency, "");
assert.strictEqual(serialized.original_foreign_amount_minor, null);

// Clean reconciliation is compact; exceptions alone reveal the stronger controls.
vm.runInContext("state.activeAcquisition.acquisition.source_scope = 'DOMESTIC'", context);
const cleanReview = vm.runInContext("wizardReviewScreen()", context);
assert(cleanReview.includes("Reconciled exactly"));
assert(cleanReview.includes("Confirm Acquisition"));
assert.strictEqual((cleanReview.match(/class="button primary"/g) || []).length, 1);
assert(!cleanReview.includes("Resolve") && !cleanReview.includes("reentered_final_usd_paid") && !cleanReview.includes('name="assigned_landed_cost"'));

vm.runInContext("state.activeAcquisition.reconciliation = { component_total_cents: 20000, final_usd_paid_cents: 1000, difference_cents: -19000, difference_percent: 95, severity: 'EXTREME', material: true, extreme: true, assigned_line_cost_cents: 20000, allocation_difference_cents: 19000, allocation_reconciled: false }; state.activeAcquisition.readiness = { ready_to_confirm: false, authoritative_cost_label: '$10.00', warnings: [{ code: 'ALLOCATION_NOT_RECONCILED', message: 'Confirmed line costs do not equal final USD paid exactly.' }] }; state.activeAcquisition.attention = { decision_level: 'NEEDS_ATTENTION', attention_level: 'CRITICAL', headline: 'Product-line cost allocation needs attention', message: 'DEX cannot safely split this cost.', reason_codes: ['ALLOCATION_NOT_RECONCILED'], resolve_mode: 'MULTI_LINE_ALLOCATION', requires_operator_judgment: true }", context);
const extremeReview = vm.runInContext("wizardReviewScreen()", context);
assert(extremeReview.includes("Purchase needs attention") && extremeReview.includes("Material at $5 OR 2%"));
assert(extremeReview.includes("severe 50%+ difference") && extremeReview.includes("Re-enter final USD paid"));
assert(extremeReview.includes("Standardized reason") && extremeReview.includes("Explanation (required)"));
assert(extremeReview.includes('<details class="attention-resolution" data-disclosure-key=') && !extremeReview.includes('attention-resolution" open'));
assert(extremeReview.includes("Manual allocation exception") && extremeReview.includes("Assigned landed cost") && extremeReview.includes("acquisition-allocation-form"));

// Missing cost remains Unknown; explicit zero gets a dedicated operator confirmation.
vm.runInContext("state.activeAcquisition.acquisition.final_usd_paid_cents = null; state.activeAcquisition.readiness = { ready_to_confirm: false, authoritative_cost_label: 'Unknown / Setup incomplete', warnings: [{ code: 'COST_UNKNOWN', message: 'Final USD cost is Unknown / Setup incomplete.' }] }; state.activeAcquisition.reconciliation = { component_total_cents: 0, final_usd_paid_cents: null, difference_cents: null, difference_percent: null, severity: 'UNKNOWN', material: false, extreme: false, assigned_line_cost_cents: 20000, allocation_difference_cents: null, allocation_reconciled: false }; state.activeAcquisition.attention = { decision_level: 'NEEDS_ATTENTION', attention_level: 'CRITICAL', headline: 'Authoritative cost is Unknown', message: 'Enter final USD.', reason_codes: ['COST_UNKNOWN'], resolve_mode: 'INCOMPLETE_FACTS', requires_operator_judgment: true }", context);
const incompleteReview = vm.runInContext("wizardReviewScreen()", context);
assert(incompleteReview.includes("Unknown / Setup incomplete") && incompleteReview.includes("Needs Attention · Critical") && incompleteReview.includes("Complete product & purchase facts"));
vm.runInContext("state.activeAcquisition.lines = [state.activeAcquisition.lines[0]]; state.activeAcquisition.acquisition.final_usd_paid_cents = 0; state.activeAcquisition.acquisition.discrepancy_reason_code = 'EXPLICIT_ZERO_COST'; state.activeAcquisition.readiness = { ready_to_confirm: true, authoritative_cost_label: '$0.00', warnings: [] }; state.activeAcquisition.reconciliation = { component_total_cents: 0, final_usd_paid_cents: 0, difference_cents: 0, difference_percent: 0, severity: 'NONE', material: false, extreme: false, assigned_line_cost_cents: 0, allocation_difference_cents: 0, allocation_reconciled: true }; state.activeAcquisition.automatic_single_line_allocation_preview = { line_id: 11, assigned_landed_cost_cents: 0, allocation_method_label: 'Single line — 100% of authoritative landed cost', per_unit_cost: { base_cents: 0, remainder_units: 0, quantity: 12, minimum_cents: 0, maximum_cents: 0, exact_when_uniform: true } }; state.activeAcquisition.attention = { decision_level: 'NEEDS_ATTENTION', attention_level: 'REVIEW', headline: 'Explicit zero-dollar acquisition needs attention', message: 'Confirm intentional zero.', reason_codes: [], resolve_mode: 'ZERO_COST', requires_operator_judgment: true }", context);
const zeroReview = vm.runInContext("wizardReviewScreen()", context);
assert(zeroReview.includes("$0.00") && zeroReview.includes("intentional $0.00 acquisition") && zeroReview.includes("Resolve"));

// A persisted legacy screen resumes on its matching three-screen destination.
vm.runInContext("state.activeAcquisition.acquisition.wizard_step = 'SOURCE'", context);
vm.runInContext("renderAcquisitionWizard(7, { data: state.activeAcquisition, focusHeading: true })", context);
assert(app.innerHTML.includes("Product &amp; Purchase Details"));
assert(heading.focused, "Wizard heading should receive focus after a deliberate step change");

// Backend remains the only source of allocation/per-unit facts; no financial formula is added here.
assert(source.includes("automatic_single_line_allocation_preview"));
assert(source.includes("authoritative landed cost") && source.includes("Confirmed acquisition"));
assert(source.includes("captureLogicalViewport()") && source.includes("restoreLogicalViewport(options.viewport)"));

console.log("Inbound 2.0 Phase 2 Happy-Path Polish frontend contract: PASS");
