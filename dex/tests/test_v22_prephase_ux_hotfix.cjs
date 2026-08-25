const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

class ElementStub {
  constructor() {
    this.innerHTML = ""; this.textContent = ""; this.dataset = {}; this.style = {};
    this.complete = true; this.value = ""; this.open = false; this.className = "";
    this.listeners = {};
    this.classList = { add() {}, remove() {}, toggle() {} };
  }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  closest() { return null; }
  focus() {}
  querySelector() { return null; }
  querySelectorAll() { return []; }
  getBoundingClientRect() { return { top: 100, bottom: 150 }; }
  showModal() { this.open = true; }
  close() { this.open = false; }
}

let detailsNodes = [];
const elements = new Map();
const document = {
  activeElement: null,
  body: new ElementStub(),
  querySelector(selector) { if (!elements.has(selector)) elements.set(selector, new ElementStub()); return elements.get(selector); },
  querySelectorAll(selector) { return selector === "details" ? detailsNodes : []; },
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
context.window = { addEventListener() {}, lucide: null, location: context.location, innerHeight: 900, scrollY: 0, scrollBy() {}, scrollTo() {}, open() {} };
context.globalThis = context;
vm.createContext(context);
const source = fs.readFileSync("static/app.js", "utf8").replace(/\nboot\(\);\s*$/, "\n");
const styles = fs.readFileSync("static/styles.css", "utf8");
vm.runInContext(source, context);

function disclosure(key, open = false, force = false) {
  const node = new ElementStub();
  node.open = open;
  node.className = "fixture-disclosure";
  node.dataset.disclosureKey = key;
  node.dataset.disclosureForceOpen = String(force);
  node.querySelector = () => ({ textContent: "Fixture section" });
  return node;
}

const first = disclosure("catalog-search", false);
detailsNodes = [first];
vm.runInContext("bindDisclosureState()", context);
first.open = true;
first.listeners.toggle();
assert.strictEqual(vm.runInContext("state.disclosureStates.get('catalog-search')", context), true);

const afterSearch = disclosure("catalog-search", false);
detailsNodes = [afterSearch];
vm.runInContext("bindDisclosureState()", context);
assert.strictEqual(afterSearch.open, true, "Search rerender must preserve expanded state");

afterSearch.open = false;
afterSearch.listeners.toggle();
const afterMutation = disclosure("catalog-search", true);
detailsNodes = [afterMutation];
vm.runInContext("bindDisclosureState()", context);
assert.strictEqual(afterMutation.open, false, "Mutation rerender must preserve explicitly collapsed state");

const critical = disclosure("catalog-search", false, true);
detailsNodes = [critical];
vm.runInContext("bindDisclosureState()", context);
assert.strictEqual(critical.open, true, "Needs Attention must force its section open");
critical.open = false;
critical.listeners.toggle();
assert.strictEqual(critical.open, true, "A forced critical section cannot silently remain collapsed");

const acquisition = {
  acquisition: { id: 71, state: "ACQUISITION_INCOMPLETE", source_scope: "", merchant_name: "", purchased_on: null, payment_method: "", merchant_country: "", original_currency: "", original_foreign_amount_minor: null, order_reference: "", purchase_subtotal_cents: null, acquisition_tax_cents: null, inbound_shipping_cents: null, acquisition_fees_cents: null, import_duties_cents: null, brokerage_cents: null, acquisition_discount_cents: null, final_usd_paid_cents: null },
  lines: [], events: [], source_documents: { documents: [], active_count: 0, failed_count: 0 },
  receipt_intelligence: { status: "NOT_REQUESTED", jobs: [], failed_job_count: 0, candidate_groups: {}, warnings: [] },
  readiness: { warnings: [{ code: "SOURCE_REQUIRED" }, { code: "COST_UNKNOWN" }] },
};
vm.runInContext(`state.activeAcquisition = ${JSON.stringify(acquisition)}`, context);
const purchase = vm.runInContext("purchaseDetailsForm()", context);
assert(purchase.includes('data-disclosure-key="acquisition-71-purchase-details"'));
assert(purchase.includes('data-disclosure-key="acquisition-71-purchase-amounts"'));
assert.strictEqual((purchase.match(/data-disclosure-force-open="true"/g) || []).length, 2);
assert(purchase.includes("Needs Attention") && purchase.includes("Unknown"));

const catalog = vm.runInContext("upcScannerPanel()", context);
// No sealed/pack line means the scanner panel is intentionally absent.
assert.strictEqual(catalog, "");
assert(source.includes('data-disclosure-key="acquisition-${state.activeAcquisition.acquisition.id}-catalog-manual"'));
assert(source.includes("openRemoveAcquisition") && source.includes("restoreAcquisition"));
assert(source.includes("permanent purge unavailable"));
assert(styles.includes(".purchase-disclosure") && styles.includes(".acquisition-recycle-row"));

console.log("Inbound 2.0 pre-phase UX consistency hotfix frontend contract: PASS");
