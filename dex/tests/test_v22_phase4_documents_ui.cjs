const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

class ElementStub {
  constructor() { this.innerHTML = ""; this.textContent = ""; this.dataset = {}; this.style = {}; this.value = ""; this.open = false; this.complete = true; this.type = ""; this.classList = { add() {}, remove() {}, toggle() {} }; }
  addEventListener() {} click() { this.clicked = true; } closest() { return null; } focus() {} querySelector() { return null; } querySelectorAll() { return []; }
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
  acquisition: { id: 14, acquisition_code: "ACQ-20260815-0014", revision: 7, state: "ACQUISITION_INCOMPLETE", wizard_step: "PRODUCTS", source_scope: "DOMESTIC", merchant_name: "Receipt QA", merchant_country: "", purchased_on: "2026-08-15", payment_method: "CASH", order_reference: "QA-14", original_currency: "", original_foreign_amount_minor: null, purchase_subtotal_cents: 1000, acquisition_tax_cents: 0, inbound_shipping_cents: 0, acquisition_fees_cents: 0, import_duties_cents: null, brokerage_cents: null, acquisition_discount_cents: 0, final_usd_paid_cents: 1000, discrepancy_reason_code: "", discrepancy_notes: "" },
  lines: [{ id: 1, line_sequence: 1, product_class: "SEALED_PRODUCT", game: "One Piece", product_name: "QA Box", set_code: "OP16", pack_type: "", quantity: 1, quantity_certainty: "KNOWN", singles_cost_mode: "", assigned_landed_cost_cents: null, allocation_method: "", allocation_status: "UNALLOCATED", catalog_product_id: null, canceled_at: null, catalog_product: null }],
  events: [], reconciliation: { component_total_cents: 1000, final_usd_paid_cents: 1000, difference_cents: 0, difference_percent: 0, severity: "NONE", material: false, extreme: false, assigned_line_cost_cents: 0, allocation_difference_cents: 1000, allocation_reconciled: false },
  readiness: { ready_to_confirm: true, warnings: [], authoritative_cost_label: "$10.00" }, attention: { decision_level: "AUTOMATIC_VISIBLE", reason_codes: [] },
  automatic_single_line_allocation_preview: { line_id: 1, assigned_landed_cost_cents: 1000, allocation_method_label: "Single line — 100%", per_unit_cost: { base_cents: 1000, remainder_units: 0, quantity: 1, minimum_cents: 1000, maximum_cents: 1000, exact_when_uniform: true } },
  source_documents: { active_count: 2, failed_count: 1, tombstone_count: 1, has_source_evidence: true, extraction_status: "NOT_REQUESTED", documents: [
    { id: 21, document_uuid: "DOC-21", original_filename: "camera.jpg", safe_filename: "camera-doc.jpg", detected_mime_type: "image/jpeg", byte_size: 2048, sha256: "a".repeat(64), document_role: "RECEIPT", storage_status: "STORED", integrity_status: "VERIFIED", error_message: "" },
    { id: 22, document_uuid: "DOC-22", original_filename: "invoice.pdf", safe_filename: "invoice-doc.pdf", detected_mime_type: "application/pdf", byte_size: 8192, sha256: "b".repeat(64), document_role: "INVOICE", storage_status: "STORED", integrity_status: "VERIFIED", error_message: "" },
    { id: 23, document_uuid: "DOC-23", original_filename: "bad.heic", safe_filename: "bad-doc.heic", detected_mime_type: "", byte_size: 0, sha256: "", document_role: "RECEIPT", storage_status: "FAILED", integrity_status: "NOT_AVAILABLE", error_message: "HEIC decoder unavailable" },
    { id: 24, document_uuid: "DOC-24", original_filename: "removed.png", safe_filename: "removed-doc.png", detected_mime_type: "image/png", byte_size: 100, sha256: "c".repeat(64), document_role: "RECEIPT", storage_status: "TOMBSTONED", integrity_status: "NOT_AVAILABLE", error_message: "" },
  ] }, projection: { batch_ids: [] },
};
vm.runInContext(`state.activeAcquisition = ${JSON.stringify(acquisition)}`, context);

const panel = vm.runInContext("sourceDocumentPanel()", context);
assert(panel.includes("Take Photo") && panel.includes("Upload"));
assert(panel.includes('capture="environment"') && panel.includes('id="source-document-camera"'));
assert(panel.includes('id="source-document-files"') && panel.includes("multiple"));
assert((panel.match(/class="source-document-implementation-input"/g) || []).length === 3);
assert((panel.match(/type="file"[^>]*hidden/g) || []).length === 3);
assert(panel.includes('data-action="upload-source-document" aria-controls="source-document-files"'));
assert(panel.includes('data-action="take-source-photo" aria-controls="source-document-camera"'));
assert(panel.includes(".pdf") && panel.includes(".heic") && panel.includes("image/png"));
assert(panel.includes("camera.jpg") && panel.includes("invoice.pdf") && panel.includes("bad.heic"));
assert(panel.includes('data-action="view-source-document"') && panel.includes('data-action="retry-source-document"'));
assert(panel.includes('data-action="remove-source-document"'));
assert(panel.includes("Upload failed · retryable") && panel.includes("Removed · history retained"));
assert(panel.includes("SHA-256 verified") && panel.includes("Private local extraction"));

const review = vm.runInContext("wizardReviewScreen()", context);
assert(review.includes("Source documents") && review.includes("2 attached") && review.includes("1 failed upload"));
assert(!review.includes("Receipt tools coming in a later phase"));

vm.runInContext("state.activeAcquisition.source_documents = { active_count: 0, failed_count: 0, tombstone_count: 0, documents: [] }", context);
const refreshedEmpty = vm.runInContext("sourceDocumentPanel()", context);
assert(refreshedEmpty.includes("No receipt currently attached") && refreshedEmpty.includes("Missing documents never become a $0.00 cost"));

assert(source.includes("/api/acquisitions/${current.acquisition.id}/documents"));
assert(source.includes("/api/acquisition-documents/${documentId}/retry"));
assert(source.includes("/api/acquisition-documents/${documentId}/tombstone"));
assert(source.includes("captureLogicalViewport()") && source.includes("restoreLogicalViewport(options.viewport)"));
assert(styles.includes(".source-document-panel") && styles.includes(".source-document-row"));
assert(styles.includes(".source-document-implementation-input[hidden]"));
assert(!source.includes("receiptOcr"));

console.log("Inbound 2.0 Phase 4 Source Documents frontend contract: PASS");
