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
const context = { console, document, Intl, Date, Set, Map, URL, URLSearchParams, Blob,
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
  acquisition: { id: 301, final_usd_paid_cents: 1653 },
  lines: [{ id: 1, line_sequence: 1, product_class: "SEALED_PRODUCT", game: "One Piece", product_name: "OP deck", quantity: 1, quantity_certainty: "KNOWN", allocation_status: "UNALLOCATED", canceled_at: null }],
  automatic_single_line_allocation_preview: null,
  single_product_allocation_eligibility: {
    status: "BLOCKED",
    eligible: false,
    reason_codes: ["RECEIPT_MATH_UNRECONCILED", "UNRESOLVED_AMOUNT_BEARING_RECEIPT_LINE"],
    message: "Automatic allocation is not ready. Resolve receipt financial discrepancies first.",
    authority_source: "RECEIPT_INTELLIGENCE",
  },
};
vm.runInContext(`state.activeAcquisition = ${JSON.stringify(acquisition)}`, context);
const blocked = vm.runInContext("singleProductAllocationNotice()", context);
assert(blocked.includes('role="alert"'));
assert(blocked.includes("Automatic allocation is not ready."));
assert(blocked.includes("Resolve receipt financial discrepancies first."));
assert(!blocked.includes("$16.53 will be assigned 100%"));

acquisition.single_product_allocation_eligibility = {
  status: "ELIGIBLE", eligible: true, reason_codes: [],
  message: "Automatic single-product allocation is ready from reconciled receipt evidence.",
  authority_source: "RECONCILED_RECEIPT",
};
acquisition.automatic_single_line_allocation_preview = { assigned_landed_cost_cents: 1653 };
vm.runInContext(`state.activeAcquisition = ${JSON.stringify(acquisition)}`, context);
const eligible = vm.runInContext("singleProductAllocationNotice()", context);
assert(eligible.includes("Automatic single-product allocation"));
assert(eligible.includes("$16.53 will be assigned 100%"));
assert(!eligible.includes('role="alert"'));

assert(source.includes("single_product_allocation_eligibility"));
assert(source.includes("backend confirms allocation eligibility"));
assert(styles.includes(".single-line-allocation-notice.blocked"));
console.log("DEX Inventory Intelligence Phase 1 Remediation 3 frontend safety contract: PASS");
