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
  acquisition: { id: 51, acquisition_code: "ACQ-RECEIPT-QA", revision: 12, state: "ACQUISITION_INCOMPLETE", wizard_step: "REVIEW", source_scope: "DOMESTIC", merchant_name: "Fixture Shop", merchant_country: "", purchased_on: "2026-08-15", payment_method: "CREDIT_DEBIT_CARD", order_reference: "R-51", original_currency: "", original_foreign_amount_minor: null, purchase_subtotal_cents: 15000, acquisition_tax_cents: 1000, inbound_shipping_cents: 100, acquisition_fees_cents: null, import_duties_cents: null, brokerage_cents: null, acquisition_discount_cents: null, final_usd_paid_cents: 16100, discrepancy_reason_code: "", discrepancy_notes: "" },
  lines: [
    { id: 501, line_sequence: 1, product_class: "SEALED_PRODUCT", game: "One Piece", product_name: "OP16 Booster Box", set_code: "OP16", quantity: 1, quantity_certainty: "KNOWN", assigned_landed_cost_cents: 10734, allocation_method: "RECEIPT_VALUE_PROPORTIONAL", allocation_status: "SUGGESTED", canceled_at: null },
    { id: 502, line_sequence: 2, product_class: "SEALED_PRODUCT", game: "One Piece", product_name: "ST27 Starter Deck", set_code: "ST27", quantity: 1, quantity_certainty: "KNOWN", assigned_landed_cost_cents: 5366, allocation_method: "RECEIPT_VALUE_PROPORTIONAL", allocation_status: "SUGGESTED", canceled_at: null },
  ],
  reconciliation: { component_total_cents: 16100, final_usd_paid_cents: 16100, difference_cents: 0, difference_percent: 0, severity: "NONE", material: false, extreme: false, assigned_line_cost_cents: 16100, allocation_difference_cents: 0, allocation_reconciled: true },
  readiness: { ready_to_confirm: true, warnings: [], authoritative_cost_label: "$161.00" }, attention: { decision_level: "AUTOMATIC_VISIBLE", reason_codes: [] }, automatic_single_line_allocation_preview: null,
  source_documents: { active_count: 1, failed_count: 0, documents: [{ id: 91, original_filename: "fixture.pdf", detected_mime_type: "application/pdf", byte_size: 2048, document_role: "RECEIPT", storage_status: "STORED", integrity_status: "VERIFIED" }] },
  receipt_intelligence: {
    status: "READY_TO_REVIEW", failed_job_count: 0, warnings: [], conflicts: [], external_transmission: false, raw_ocr_available: false, calculation_version: "receipt-landed-allocation-v1",
    jobs: [{ id: 1, job_uuid: "RCPT-JOB-1", document_id: 91, status: "COMPLETED", provider_name: "LOCAL_PDF_TEXT", provider_version: "receipt-local-pattern-v1", completed_at: "2026-08-15T12:00:00Z", receipt_lines: [{ id: 1 }, { id: 2 }] }],
    candidate_groups: { merchant_name: [{ id: 1, field_name: "merchant_name", value_type: "TEXT", value: "Fixture Shop", normalized_value: "Fixture Shop", confidence_band: "HIGH", confidence: .96, source_page: 1, source_location: "merchant", disposition: "PROPOSED", application_status: "PROPOSED", conflicts_with_manual: false }] },
    proposed_fields: [{ field_name: "merchant_name", candidate_id: 1, value: "Fixture Shop", confidence_band: "HIGH", status: "PROPOSED" }],
    receipt_lines: [
      { id: 11, line_sequence: 1, description: "OP16 Booster Box", quantity: 1, line_total_cents: 10000, confidence_band: "HIGH", classification: "INVENTORY", best_match: { id: 21, acquisition_line_id: 501, product_name: "OP16 Booster Box", match_method: "EXACT_NAME_SET", confidence: .92, status: "PROPOSED", authoritative_identity: 0 } },
      { id: 12, line_sequence: 2, description: "ST27 Starter Deck", quantity: 1, line_total_cents: 5000, confidence_band: "HIGH", classification: "INVENTORY", best_match: { id: 22, acquisition_line_id: 502, product_name: "ST27 Starter Deck", match_method: "EXACT_NAME_SET", confidence: .92, status: "PROPOSED", authoritative_identity: 0 } },
    ],
    allocation_proposal: { status: "APPLIED", authoritative: false, calculation_version: "receipt-landed-allocation-v1", total_allocated_cents: 16100, difference_cents: 0, allocations: [{ acquisition_line_id: 501, direct_merchandise_cents: 10000, shared_component_cents: 734, landed_cost_cents: 10734 }, { acquisition_line_id: 502, direct_merchandise_cents: 5000, shared_component_cents: 366, landed_cost_cents: 5366 }] },
  }, projection: { batch_ids: [] },
};
vm.runInContext(`state.activeAcquisition = ${JSON.stringify(acquisition)}`, context);

const products = vm.runInContext("wizardProductsScreen()", context);
assert(products.includes("Ready to review · 2 line(s)"));
assert(products.includes("Receipt suggestion applied to draft"));
assert(products.includes('data-action="extract-source-document"') === false);

const review = vm.runInContext("wizardReviewScreen()", context);
assert(review.includes("Review what DEX understood"));
assert(review.includes("Candidate purchase facts") && review.includes("Receipt product lines and classifications"));
assert(review.includes("Inventory") && review.includes("Personal / Nonbusiness") && review.includes("Duplicate Extraction"));
assert(review.includes("Receipt-value proportional"));
assert(review.includes("$107.34") && review.includes("$53.66") && review.includes("Difference $0.00"));
assert(review.toLowerCase().includes("non-authoritative") && review.includes("sends nothing to an external service"));
assert(review.includes("not raw OCR text"));

vm.runInContext("state.activeAcquisition.receipt_intelligence.jobs[0].status = 'FAILED'; state.activeAcquisition.receipt_intelligence.failed_job_count = 1; state.activeAcquisition.receipt_intelligence.jobs[0].error_message = 'PDF has no text layer'", context);
const failed = vm.runInContext("sourceDocumentPanel()", context);
assert(failed.includes("Extraction failed") && failed.includes("Retry extraction"));
assert(failed.includes("manual purchase facts"));

assert(source.includes("/extractions") && source.includes("/receipt-candidates/apply") && source.includes("/receipt-lines/${form.dataset.lineId}/classification"));
assert(source.includes("/receipt-line-matches/${matchId}/disposition") && source.includes("/receipt-allocation-proposals"));
assert(source.includes("captureLogicalViewport()") && source.includes("expected_revision"));
assert(!source.includes("shared_component_cents /") && !source.includes("final_usd_paid_cents -"));
assert(styles.includes(".receipt-review") && styles.includes(".receipt-field-marker") && styles.includes(".receipt-classification-form"));

console.log("Inbound 2.0 Phase 5 Receipt Intelligence frontend contract: PASS");
