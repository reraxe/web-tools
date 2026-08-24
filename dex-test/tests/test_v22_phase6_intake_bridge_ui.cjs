const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

class ElementStub {
  constructor() { this.innerHTML = ""; this.dataset = {}; this.style = {}; this.value = ""; this.open = false; this.classList = { add() {}, remove() {}, toggle() {} }; }
  addEventListener() {} closest() { return null; } focus() {} querySelector() { return null; } querySelectorAll() { return []; }
  getBoundingClientRect() { return { top: 50, bottom: 100 }; } showModal() { this.open = true; } close() { this.open = false; }
}
const elements = new Map();
const document = { activeElement: null, body: new ElementStub(),
  querySelector(selector) { if (!elements.has(selector)) elements.set(selector, new ElementStub()); return elements.get(selector); },
  querySelectorAll() { return []; }, addEventListener() {} };
const context = { console, document, Intl, Date, Set, Map, URL, URLSearchParams, Blob,
  FormData: class { constructor() {} entries() { return [][Symbol.iterator](); } }, FileReader: class {},
  setTimeout, clearTimeout, requestAnimationFrame: (callback) => callback(), confirm: () => true,
  fetch: async () => ({ ok: true, status: 200, json: async () => ({}) }), history: { replaceState() {} },
  location: { hash: "#inbound", reload() {} }, navigator: { clipboard: { writeText: async () => {} } } };
context.window = { addEventListener() {}, open() {}, lucide: null, location: context.location, innerHeight: 900, scrollY: 0, scrollBy() {}, scrollTo() {} };
context.globalThis = context;
vm.createContext(context);
const source = fs.readFileSync("static/app.js", "utf8").replace(/\nboot\(\);\s*$/, "\n");
const styles = fs.readFileSync("static/styles.css", "utf8");
vm.runInContext(source, context);

const acquisition = {
  acquisition: { id: 61, acquisition_code: "ACQ-P6-QA", revision: 9, state: "INTAKE_IN_PROGRESS", wizard_step: "REVIEW", merchant_name: "Bridge Shop", source_scope: "DOMESTIC", purchased_on: "2026-08-15", payment_method: "CREDIT_DEBIT_CARD", final_usd_paid_cents: 2200 },
  lines: [], reconciliation: { component_total_cents: 2200, final_usd_paid_cents: 2200, allocation_reconciled: true },
  readiness: { warnings: [], authoritative_cost_label: "$22.00" }, attention: { decision_level: "AUTOMATIC_VISIBLE" },
  source_documents: { active_count: 0, failed_count: 0 }, receipt_intelligence: { status: "NOT_REQUESTED", warnings: [], jobs: [], candidate_groups: {}, receipt_lines: [] },
  intake_routing: {
    state: "INTAKE_IN_PROGRESS", revision: 9,
    summary: { quantity_acquired: 7, quantity_routed: 4, quantity_undecided: 3, difference_cents: 0 },
    lines: [
      { line_id: 601, line_sequence: 1, product_class: "SEALED_PRODUCT", product_name: "OP16 Booster Box", quantity_acquired: 3, landed_cost_cents: 1000, undecided_quantity: 1, routed: { keep_sealed_quantity: 1, rip_open_quantity: 1, scan_identify_quantity: 0 }, links: [{ kind: "BATCH", id: 71, label: "ACQ-P6-QA-L01", status: "OPEN" }, { kind: "RIP_SESSION", id: 81, label: "RIP-0081", status: "DRAFT" }] },
      { line_id: 602, line_sequence: 2, product_class: "SINGLE_CARDS", product_name: "OP16 Singles", quantity_acquired: 4, landed_cost_cents: 1200, undecided_quantity: 2, routed: { keep_sealed_quantity: 0, rip_open_quantity: 0, scan_identify_quantity: 2 }, links: [{ kind: "BATCH", id: 72, label: "ACQ-P6-QA-L02", status: "OPEN" }] },
    ],
  }, removal: { protected_history: true },
};
vm.runInContext(`state.activeAcquisition = ${JSON.stringify(acquisition)}`, context);

const panel = vm.runInContext("intakeRoutingPanel()", context);
assert(panel.includes("What happens next?") && panel.includes("Intake in Progress"));
assert(panel.includes("Keep Sealed") && panel.includes("Rip / Open") && panel.includes("Scan & Identify"));
assert(panel.includes("3 acquired") && panel.includes("$10.00 authoritative landed cost"));
assert(panel.includes("1 undecided") && panel.includes("2 undecided"));
assert(panel.includes("Continue Rip · ACQ-P6-QA-L01") && panel.includes("Continue Scanning · ACQ-P6-QA-L02") && panel.includes("RIP-0081"));
assert(panel.includes("Save & continue later") && panel.includes("Review routing"));

const review = vm.runInContext("wizardReviewScreen()", context);
assert(review.includes("Downstream Intake") && !review.includes("Confirm Acquisition"));
assert(source.includes("/intake-routing/preview") && source.includes("/intake-routing/confirm"));
assert(source.includes("preview_token") && source.includes("confirm_routing: true"));
assert(source.includes("captureLogicalViewport()"));
assert(!source.includes("landed_cost_cents /") && !source.includes("requested_basis_cents -"));
assert(styles.includes(".intake-routing") && styles.includes(".intake-route-line") && styles.includes(".intake-preview-total"));

console.log("Inbound 2.0 Phase 6 Downstream Intake Bridge frontend contract: PASS");
