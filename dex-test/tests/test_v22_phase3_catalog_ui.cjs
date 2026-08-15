const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

class ElementStub {
  constructor() {
    this.innerHTML = ""; this.textContent = ""; this.dataset = {}; this.style = {};
    this.complete = true; this.value = ""; this.open = false;
    this.classList = { add() {}, remove() {}, toggle() {} };
  }
  addEventListener() {}
  closest() { return null; }
  focus() {}
  querySelector() { return null; }
  querySelectorAll() { return []; }
  getBoundingClientRect() { return { top: 100, bottom: 150 }; }
  showModal() { this.open = true; }
  close() { this.open = false; }
}

const elements = new Map();
const document = {
  activeElement: null,
  body: new ElementStub(),
  querySelector(selector) { if (!elements.has(selector)) elements.set(selector, new ElementStub()); return elements.get(selector); },
  querySelectorAll() { return []; },
  addEventListener() {},
};
class FormDataStub { constructor(form) { this.values = form?.values || []; } entries() { return this.values[Symbol.iterator](); } }
const context = {
  console, document, Intl, Date, Set, Map, URL, URLSearchParams, FormData: FormDataStub, Blob,
  FileReader: class {}, setTimeout, clearTimeout, requestAnimationFrame: (callback) => callback(),
  confirm: () => true, fetch: async () => ({ ok: true, status: 200, json: async () => ({}) }),
  history: { replaceState() {} }, location: { hash: "#inbound", reload() {} },
  navigator: { clipboard: { writeText: async () => {} } },
};
context.window = { addEventListener() {}, lucide: null, location: context.location, innerHeight: 900, scrollY: 0, scrollBy() {}, scrollTo() {} };
context.globalThis = context;
vm.createContext(context);
const source = fs.readFileSync("static/app.js", "utf8").replace(/\nboot\(\);\s*$/, "\n");
const styles = fs.readFileSync("static/styles.css", "utf8");
vm.runInContext(source, context);

const acquisition = {
  acquisition: { id: 3, revision: 4, state: "ACQUISITION_INCOMPLETE", wizard_step: "PRODUCTS", source_scope: "DOMESTIC", merchant_name: "Catalog QA", merchant_country: "", purchased_on: "2026-08-15", payment_method: "CASH", order_reference: "", original_currency: "", original_foreign_amount_minor: null, purchase_subtotal_cents: null, acquisition_tax_cents: null, inbound_shipping_cents: null, acquisition_fees_cents: null, import_duties_cents: null, brokerage_cents: null, acquisition_discount_cents: null, final_usd_paid_cents: null },
  lines: [{ id: 9, line_sequence: 1, product_class: "SEALED_PRODUCT", game: "One Piece", product_name: "OP16 Booster Box", set_code: "OP16", pack_type: "", quantity: 3, quantity_certainty: "KNOWN", assigned_landed_cost_cents: null, allocation_method: "", allocation_status: "UNALLOCATED", catalog_product_id: 2, canceled_at: null, catalog_product: { id: 2, game: "One Piece", display_name: "OP16 Booster Box", set_code: "OP16", set_name: "The Time of Battle", product_class: "SEALED_PRODUCT", product_subtype: "Booster Box", provenance: "SEED_FIXTURE", identifiers: [{ identifier_type: "UPC_A", raw_identifier: "012345678905" }] } }],
  events: [], reconciliation: { component_total_cents: 0, final_usd_paid_cents: null, difference_cents: null, difference_percent: null, severity: "NONE", material: false, extreme: false, assigned_line_cost_cents: 0, allocation_difference_cents: null, allocation_reconciled: false },
  readiness: { ready_to_confirm: false, warnings: [], authoritative_cost_label: "Unknown / Setup incomplete" },
  attention: { decision_level: "NEEDS_ATTENTION", reason_codes: [] }, automatic_single_line_allocation_preview: null,
  projection: { batch_ids: [] },
};
vm.runInContext(`state.activeAcquisition = ${JSON.stringify(acquisition)}`, context);

const recognized = vm.runInContext("wizardProductsScreen()", context);
assert(recognized.includes("Scan UPC"));
assert(recognized.includes('id="upc-scan-input"') && recognized.includes('autocomplete="off"'));
assert(recognized.includes("keyboard-emulating barcode scanner"));
assert(recognized.includes("Catalog identified · Automatic + Visible"));
assert(recognized.includes("OP16 Booster Box") && recognized.includes("012345678905"));
assert(recognized.includes("Search catalog or continue with manual entry"));
assert(recognized.includes("Take Photo · Coming Soon") && recognized.includes("Upload Receipt · Coming Soon"));

vm.runInContext("state.pendingUnknownProduct = { identifier: { raw_identifier: '036000291452', identifier_type: 'UPC_A' }, mode: null }", context);
const unknown = vm.runInContext("upcScannerPanel()", context);
assert(unknown.includes("Product not recognized"));
assert(unknown.includes("Search catalog") && unknown.includes("Identify manually") && unknown.includes("Cancel scan"));
assert(unknown.includes("did not create or guess"));

vm.runInContext("state.pendingUnknownProduct.mode = 'identify'", context);
const identify = vm.runInContext("upcScannerPanel()", context);
assert(identify.includes('id="unknown-product-form"'));
assert(identify.includes("Remember this UPC for future purchases"));
assert(identify.includes("operator-confirmed, not manufacturer-authoritative"));

vm.runInContext("state.pendingUnknownProduct.mode = 'search'; state.catalogSearchResults = [{ id: 4, display_name: 'Known Deck', game: 'One Piece', set_code: 'ST27', product_class: 'SEALED_PRODUCT', product_subtype: 'Starter Deck' }]", context);
const search = vm.runInContext("upcScannerPanel()", context);
assert(search.includes("Known Deck") && search.includes("select-unknown-catalog-product"));
assert(search.includes('name="remember_mapping"'));

vm.runInContext("state.activeAcquisition.lines = [{ id: 11, line_sequence: 1, product_class: 'SINGLE_CARDS', game: 'Pokemon', product_name: '', set_code: 'JTG', pack_type: '', quantity: 3, quantity_certainty: 'KNOWN', assigned_landed_cost_cents: null, allocation_method: '', allocation_status: 'UNALLOCATED', catalog_product_id: null, canceled_at: null, catalog_product: null }]; state.pendingUnknownProduct = null", context);
const singles = vm.runInContext("wizardProductsScreen()", context);
assert(!singles.includes("Scan UPC"));
assert(singles.includes("Single Cards"));

assert(source.includes("/product-scan") && source.includes("/identify-product") && source.includes("/catalog-product"));
assert(source.includes("upcScanPending") && source.includes("UPC-SCAN"));
assert(source.includes('event.key !== "Enter"') && source.includes("requestSubmit()"));
assert(styles.includes(".upc-intake") && styles.includes(".unknown-upc") && styles.includes(".catalog-recognition"));

console.log("Inbound 2.0 Phase 3 Product Catalog + UPC frontend contract: PASS");
