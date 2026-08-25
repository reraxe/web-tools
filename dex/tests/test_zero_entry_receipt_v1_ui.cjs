const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

class ElementStub {
  constructor() { this.innerHTML = ""; this.textContent = ""; this.dataset = {}; this.style = {}; this.value = ""; this.open = false; this.complete = true; this.type = ""; this.classList = { add() {}, remove() {}, toggle() {} }; }
  addEventListener() {} click() {} closest() { return null; } focus() {} querySelector() { return null; } querySelectorAll() { return []; }
  getBoundingClientRect() { return { top: 100, bottom: 150 }; } showModal() { this.open = true; } close() { this.open = false; }
}
const elements = new Map();
const document = { activeElement: null, body: new ElementStub(),
  querySelector(selector) { if (!elements.has(selector)) elements.set(selector, new ElementStub()); return elements.get(selector); },
  querySelectorAll() { return []; }, addEventListener() {} };
class FormDataStub { constructor(form) { this.values = form?.values || []; } entries() { return this.values[Symbol.iterator](); } }
const context = { console, document, Intl, Date, Set, Map, URL, URLSearchParams, FormData: FormDataStub, Blob,
  FileReader: class {}, setTimeout, clearTimeout, requestAnimationFrame: (callback) => callback(), confirm: () => true,
  fetch: async () => ({ ok: true, status: 200, json: async () => ({}) }), history: { replaceState() {} },
  location: { hash: "#inbound", reload() {} }, navigator: { clipboard: { writeText: async () => {} } } };
context.window = { addEventListener() {}, open() {}, lucide: null, location: context.location, innerHeight: 900, scrollY: 0, scrollBy() {}, scrollTo() {} };
context.globalThis = context;
vm.createContext(context);
const source = fs.readFileSync("static/app.js", "utf8").replace(/\nboot\(\);\s*$/, "\n");
const styles = fs.readFileSync("static/styles.css", "utf8");
vm.runInContext(source, context);

const acquisition = {
  acquisition: { id: 101, acquisition_code: "ACQ-ZERO-ENTRY", revision: 8, state: "ACQUISITION_INCOMPLETE", wizard_step: "REVIEW", source_scope: "DOMESTIC", merchant_name: "Mom and Pop Shop", purchased_on: "2026-08-16", payment_method: "CREDIT_DEBIT_CARD", purchase_subtotal_cents: 12999, acquisition_tax_cents: 418, acquisition_fees_cents: null, acquisition_discount_cents: null, final_usd_paid_cents: 13417, excluded_noninventory_cents: null },
  lines: [
    { id: 1, line_sequence: 1, product_class: "PACK_PRODUCT", game: "One Piece", product_name: "OP13 booster packs", set_code: "OP13", quantity: 4, quantity_certainty: "KNOWN", assigned_landed_cost_cents: null, allocation_status: "UNALLOCATED", canceled_at: null },
    { id: 2, line_sequence: 2, product_class: "PACK_PRODUCT", game: "Riftbound", product_name: "Riftbound Vendetta booster packs", set_code: "Riftbound", quantity: 6, quantity_certainty: "KNOWN", assigned_landed_cost_cents: null, allocation_status: "UNALLOCATED", canceled_at: null },
    { id: 3, line_sequence: 3, product_class: "SEALED_PRODUCT", game: "One Piece", product_name: "Gear Five Luffy", set_code: "Gear", quantity: 1, quantity_certainty: "KNOWN", assigned_landed_cost_cents: null, allocation_status: "UNALLOCATED", canceled_at: null },
    { id: 4, line_sequence: 4, product_class: "PACK_PRODUCT", game: "Magic", product_name: "Hobbit Collector Booster", set_code: "Hobbit", quantity: 1, quantity_certainty: "KNOWN", assigned_landed_cost_cents: null, allocation_status: "UNALLOCATED", canceled_at: null },
  ],
  reconciliation: { component_total_cents: 13417, component_adjustment_cents: 0, component_reconciled: true, final_usd_paid_cents: 13417, difference_cents: 0, difference_percent: 0, severity: "NONE", material: false, extreme: false, assigned_line_cost_cents: 0, inventory_landed_cost_cents: 0, excluded_noninventory_cents: null, partition_difference_cents: 13417, allocation_difference_cents: 13417, partition_reconciled: false, allocation_reconciled: false },
  readiness: { ready_to_confirm: false, warnings: [{ code: "UNRESOLVED_RECEIPT_LINES", message: "Classify unresolved receipt lines" }], authoritative_cost_label: "$134.17" },
  attention: { decision_level: "NEEDS_ATTENTION", attention_level: "REVIEW", headline: "Acquisition setup needs attention", message: "Answer one business question", resolve_mode: "INCOMPLETE_FACTS", reason_codes: [] },
  automatic_single_line_allocation_preview: null,
  source_documents: { active_count: 1, failed_count: 0, documents: [{ id: 7, original_filename: "receipt.png", detected_mime_type: "image/png", byte_size: 4000, document_role: "RECEIPT", storage_status: "STORED", integrity_status: "VERIFIED" }] },
  receipt_intelligence: {
    status: "READY_TO_REVIEW", failed_job_count: 0, manual_fallback_available: false, warnings: [{ code: "UNRESOLVED_RECEIPT_LINES", message: "Classify unresolved receipt lines" }], conflicts: [], candidate_groups: {}, proposed_fields: [], allocation_proposal: null, historical_jobs: [],
    jobs: [{ id: 8, job_uuid: "RCPT-JOB-8", document_id: 7, status: "COMPLETED", provider_name: "LOCAL_RECEIPT_INTELLIGENCE", provider_version: "receipt-local-zero-entry-v1", completed_at: "2026-08-16", receipt_lines: [{ id: 1 }] }],
    receipt_math: { status: "RECONCILED_EXACT", merchandise_total_cents: 12800, printed_subtotal_cents: 12999, final_paid_cents: 13417, difference_cents: 0, components: [
      { kind: "DISCOUNT", label: "Discount", signed_cents: -180, math_role: "INCLUDED_IN_SUBTOTAL" },
      { kind: "FEE", label: "Credit/Debit fee", signed_cents: 379, math_role: "INCLUDED_IN_SUBTOTAL" },
      { kind: "TAX", label: "Tax", signed_cents: 418, math_role: "OUTSIDE_SUBTOTAL" },
    ] },
    receipt_lines: [
      { id: 11, line_sequence: 1, description: "OP13 booster packs", quantity: 4, line_total_cents: 3000, confidence_band: "HIGH", classification: "INVENTORY", best_match: { id: 21, acquisition_line_id: 1, product_name: "OP13 booster packs", match_method: "EXACT_NAME_SET", confidence: .96, status: "ACCEPTED", authoritative_identity: 1 } },
      { id: 12, line_sequence: 2, description: "Gear Five Luffy", quantity: 1, line_total_cents: 1800, confidence_band: "HIGH", classification: "UNRESOLVED", best_match: { id: 22, acquisition_line_id: 3, product_name: "Gear Five Luffy", match_method: "EXACT_NAME_SET", confidence: .96, status: "ACCEPTED", authoritative_identity: 1 } },
    ],
  },
};
vm.runInContext(`state.activeAcquisition = ${JSON.stringify(acquisition)}`, context);

const start = vm.runInContext("wizardAcquireScreen()", context);
assert(start.includes("Start with the receipt"));
assert(start.includes("Take Photo") && start.includes("Upload"));
assert(start.includes("Advanced / Manual entry"));
assert(start.includes("JPG, JPEG, PNG, and text-layer PDF"));

const review = vm.runInContext("wizardReviewScreen()", context);
assert(review.includes("What DEX understood"));
assert(review.includes("Receipt reconciled exactly"));
assert(review.includes("Included In Subtotal") && review.includes("Outside Subtotal"));
assert(review.includes("Gear Five Luffy"));
assert(review.includes("Inventory for resale"));
assert(review.includes("Business noninventory"));
assert(review.includes("Personal / nonbusiness"));
assert(review.includes('data-action="receipt-classify-choice"'));
assert(review.includes('<button class="button primary" disabled'));

acquisition.receipt_intelligence.receipt_lines[1].classification = "PERSONAL_NONBUSINESS";
acquisition.receipt_intelligence.allocation_policy = {
  status: "POLICY_REQUIRED", scope: "MIXED_INVENTORY_NONINVENTORY", preserved_components: acquisition.receipt_intelligence.receipt_math.components,
  required_policy_dimensions: ["SALES_TAX", "TRANSACTION_CARD_FEES", "SHIPPING_FREIGHT", "PURCHASE_DISCOUNTS_CREDITS", "CENT_ROUNDING_REMAINDERS"],
};
acquisition.receipt_intelligence.warnings = [{ code: "MIXED_PURCHASE_ALLOCATION_POLICY_REQUIRED", message: "Approved policy required" }];
vm.runInContext(`state.activeAcquisition = ${JSON.stringify(acquisition)}`, context);
const policyReview = vm.runInContext("wizardReviewScreen()", context);
assert(policyReview.includes("Final landed-cost allocation: Policy required"));
assert(policyReview.includes("sales tax, transaction/card fees, shipping/freight"));
assert(policyReview.includes("Discount") && policyReview.includes("Credit/Debit fee") && policyReview.includes("Tax"));
assert(!policyReview.includes("Try exact allocation"));

assert(source.includes("RECEIPT-ZERO-ENTRY"));
assert(source.includes("RECEIPT-REVIEW-STEP"));
assert(source.includes("chooseReceiptClassification"));
assert(source.includes("Business classification saved. DEX recalculated the acquisition."));
assert(styles.includes(".receipt-understood.exact"));
assert(styles.includes(".receipt-business-question"));

console.log("DEX Zero-Entry Receipt Intelligence v1 frontend contract: PASS");
