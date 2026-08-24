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
  acquisition: { id: 81, acquisition_code: "ACQ-MOM-POP", revision: 19, state: "ACQUISITION_INCOMPLETE", wizard_step: "REVIEW", source_scope: "DOMESTIC", merchant_name: "Mom and Pop Shop", purchased_on: "2026-08-16", payment_method: "CREDIT_DEBIT_CARD", purchase_subtotal_cents: 13616, final_usd_paid_cents: 13417, discrepancy_reason_code: "MERCHANT_TOTAL_CONTROLS", discrepancy_notes: "Merchant credit", excluded_noninventory_cents: null, noninventory_treatment_code: null, noninventory_notes: null },
  lines: [
    { id: 811, line_sequence: 1, product_class: "SEALED_PRODUCT", game: "One Piece", product_name: "OP13", set_code: "OP13", quantity: 1, quantity_certainty: "KNOWN", assigned_landed_cost_cents: 3000, allocation_method: "ACTUAL_LINE_COST", allocation_status: "CONFIRMED", canceled_at: null },
    { id: 812, line_sequence: 2, product_class: "SEALED_PRODUCT", game: "Hobbit", product_name: "Hobbit", set_code: "HOBBIT", quantity: 1, quantity_certainty: "KNOWN", assigned_landed_cost_cents: 5000, allocation_method: "ACTUAL_LINE_COST", allocation_status: "CONFIRMED", canceled_at: null },
    { id: 813, line_sequence: 3, product_class: "SEALED_PRODUCT", game: "Riftbound", product_name: "Riftbound", set_code: "RIFTBOUND", quantity: 1, quantity_certainty: "KNOWN", assigned_landed_cost_cents: 3000, allocation_method: "ACTUAL_LINE_COST", allocation_status: "CONFIRMED", canceled_at: null },
  ],
  reconciliation: { component_total_cents: 13616, component_adjustment_cents: -199, component_reconciled: true, final_usd_paid_cents: 13417, difference_cents: -199, difference_percent: 1.48, severity: "NONE", material: false, extreme: false, assigned_line_cost_cents: 11000, inventory_landed_cost_cents: 11000, excluded_noninventory_cents: null, partition_difference_cents: 2417, allocation_difference_cents: 2417, partition_reconciled: false, allocation_reconciled: false },
  readiness: { ready_to_confirm: false, warnings: [
    { code: "ALLOCATION_NOT_RECONCILED", message: "Inventory partition unresolved" },
    { code: "EXCLUDED_NONINVENTORY_REQUIRED", message: "Explicit excluded amount required" },
    { code: "RECEIPT_ALLOCATION_UNRESOLVED", message: "Receipt allocation unresolved" },
  ], authoritative_cost_label: "$134.17" },
  attention: { decision_level: "NEEDS_ATTENTION", attention_level: "REVIEW", headline: "Product-line cost allocation needs attention", message: "Resolve facts", resolve_mode: "MULTI_LINE_ALLOCATION", reason_codes: [] },
  automatic_single_line_allocation_preview: null,
  source_documents: { active_count: 1, failed_count: 0, tombstone_count: 0, documents: [{ id: 91, original_filename: "receipt.jpg", detected_mime_type: "image/jpeg", byte_size: 2048, document_role: "RECEIPT", storage_status: "STORED", integrity_status: "VERIFIED" }] },
  receipt_intelligence: { status: "FAILED_MANUAL_AVAILABLE", failed_job_count: 1, manual_fallback_available: true, manual_fallback_selected: false, retry_plausible: false, warnings: [{ code: "RECEIPT_ALLOCATION_UNRESOLVED", message: "Receipt evidence does not support exact allocation" }], conflicts: [], candidate_groups: {}, proposed_fields: [], receipt_lines: [], allocation_proposal: null, historical_jobs: [], jobs: [{ id: 1, job_uuid: "RCPT-JOB-FAILED", document_id: 91, status: "FAILED", error_code: "FORMAT_PROVIDER_UNAVAILABLE", error_message: "Private local image OCR is not configured", capability_unavailable: true, retry_plausible: false, provider_name: "LOCAL_PDF_TEXT", provider_version: "receipt-local-pattern-v1", failed_at: "2026-08-16T12:00:00Z", receipt_lines: [] }] },
};
vm.runInContext(`state.activeAcquisition = ${JSON.stringify(acquisition)}`, context);

const failedSource = vm.runInContext("sourceDocumentPanel()", context);
assert(failedSource.includes("Automatic image extraction unavailable"));
assert(failedSource.includes("Continue with manual facts"));
assert(!failedSource.includes("Retry extraction"));

const blockedReview = vm.runInContext("wizardReviewScreen()", context);
assert(blockedReview.includes("Component discrepancy") && blockedReview.includes("Excluded from inventory basis"));
assert(blockedReview.includes('name="excluded_noninventory"') && blockedReview.includes('name="noninventory_treatment_code"'));
assert(blockedReview.includes('name="confirm_noninventory_exclusion"'));
assert(blockedReview.includes("Allocation confirmed"));
assert(blockedReview.includes('<button class="button primary" disabled'));

vm.runInContext("state.activeAcquisition.receipt_intelligence.manual_fallback_selected = true; state.activeAcquisition.readiness.warnings = state.activeAcquisition.readiness.warnings.filter((item) => item.code !== 'RECEIPT_ALLOCATION_UNRESOLVED')", context);
const manualReview = vm.runInContext("wizardReviewScreen()", context);
assert(manualReview.includes("Manual line allocation selected"));
assert(manualReview.includes("Informational after your manual-facts decision"));
assert(manualReview.includes("Confirm Acquisition"));
assert(!manualReview.includes('<button class="button primary" disabled'));

const removed = JSON.parse(JSON.stringify(acquisition));
removed.source_documents = { active_count: 0, failed_count: 0, tombstone_count: 1, documents: [{ ...acquisition.source_documents.documents[0], storage_status: "TOMBSTONED" }] };
removed.receipt_intelligence = { status: "NOT_REQUESTED", failed_job_count: 0, manual_fallback_available: false, manual_fallback_selected: false, retry_plausible: false, warnings: [], candidate_groups: {}, proposed_fields: [], receipt_lines: [], allocation_proposal: null, jobs: [], historical_jobs: acquisition.receipt_intelligence.jobs };
vm.runInContext(`state.activeAcquisition = ${JSON.stringify(removed)}`, context);
const removedPanel = vm.runInContext("sourceDocumentPanel()", context);
const removedReview = vm.runInContext("receiptIntelligenceReview()", context);
assert(removedPanel.includes("No receipt currently attached"));
assert(removedPanel.includes("Removed · history retained"));
assert(!removedPanel.includes("Retry extraction"));
assert(removedReview.includes("Removed-document extraction history"));
assert(removedReview.includes("no active retry"));

assert(source.includes("/receipt-manual-fallback"));
assert(source.includes("confirm_manual_fallback: true"));
assert(source.includes("rememberAcquisitionWorkingState(app)"));
assert(source.includes('input.value = ""'));
assert(styles.includes(".receipt-manual-fallback") && styles.includes(".receipt-allocation.manual"));

console.log("RC3 HF2 manual receipt fallback frontend contract: PASS");
