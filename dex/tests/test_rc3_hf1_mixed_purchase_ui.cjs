const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

class ElementStub {
  constructor() { this.innerHTML = ""; this.dataset = {}; this.style = {}; this.complete = true; this.open = false; this.value = ""; this.checked = false; this.disabled = false; this.type = "text"; this.name = ""; this.classList = { contains() { return false; }, add() {}, remove() {}, toggle() {} }; }
  addEventListener() {}
  closest() { return null; }
  focus() { this.focused = true; }
  querySelector() { return null; }
  querySelectorAll() { return []; }
  getBoundingClientRect() { return { top: 100, bottom: 160 }; }
  showModal() {}
  close() {}
}

const app = new ElementStub();
const document = { activeElement: null, body: new ElementStub(), querySelector(selector) { return selector === "#app" ? app : new ElementStub(); }, querySelectorAll() { return []; }, addEventListener() {} };
const context = {
  console, document, Intl, Date, Set, Map, URL, URLSearchParams, Blob,
  FormData: class { constructor(form) { this.form = form; } entries() { return (this.form.values || [])[Symbol.iterator](); } },
  FileReader: class {}, setTimeout, clearTimeout, requestAnimationFrame: (callback) => callback(),
  confirm: () => true, fetch: async () => ({ ok: true, status: 200, json: async () => ({}) }),
  history: { replaceState() {} }, location: { hash: "#inbound", reload() {} }, navigator: { clipboard: { writeText: async () => {} } },
};
context.window = { addEventListener() {}, lucide: null, location: context.location, innerHeight: 900, scrollY: 0, scrollBy() {}, scrollTo() {} };
context.globalThis = context;
vm.createContext(context);
const source = fs.readFileSync("static/app.js", "utf8").replace(/\nboot\(\);\s*$/, "\n");
vm.runInContext(source, context);

const acquisition = {
  id: 17, acquisition_code: "ACQ-RC3-HF1", state: "ACQUISITION_INCOMPLETE", revision: 9, wizard_step: "REVIEW",
  merchant_name: "Mom and Pop Shop", source_scope: "DOMESTIC", purchased_on: "2026-08-16", payment_method: "CREDIT_DEBIT_CARD",
  final_usd_paid_cents: 13417, excluded_noninventory_cents: 2417, noninventory_treatment_code: "MIXED_NONINVENTORY",
  noninventory_notes: "Net mixed-purchase exclusion", discrepancy_reason_code: "MERCHANT_TOTAL_CONTROLS", discrepancy_notes: "Merchant credit",
};
const reconciliation = {
  component_total_cents: 13616, final_usd_paid_cents: 13417, difference_cents: -199, component_adjustment_cents: -199,
  difference_percent: 1.46, severity: "NOTICE", material: false, extreme: false, component_reconciled: true,
  assigned_line_cost_cents: 11000, inventory_landed_cost_cents: 11000, excluded_noninventory_cents: 2417,
  partition_difference_cents: 0, partition_reconciled: true, allocation_difference_cents: 0, allocation_reconciled: true,
};
const lines = [3000, 5000, 3000].map((cost, index) => ({ id: index + 1, line_sequence: index + 1, product_class: "SEALED_PRODUCT", game: "One Piece", product_name: `Product ${index + 1}`, quantity: 1, assigned_landed_cost_cents: cost, allocation_method: "ACTUAL_LINE_COST", allocation_status: "CONFIRMED", canceled_at: null, per_unit_cost: { exact_when_uniform: true, base_cents: cost } }));
vm.runInContext(`state.activeAcquisition = ${JSON.stringify({ acquisition, lines, reconciliation, readiness: { warnings: [], authoritative_cost_label: "$134.17" }, attention: { decision_level: "NEEDS_ATTENTION", attention_level: "REVIEW", headline: "Review", message: "Resolve", resolve_mode: "PURCHASE_DISCREPANCY", reason_codes: [] }, source_documents: { active_count: 0, failed_count: 0 }, receipt_intelligence: { status: "NOT_REQUESTED", jobs: [] } })}`, context);

const review = vm.runInContext("wizardReviewScreen()", context);
assert(review.includes("Component discrepancy") && review.includes("Purchase components"));
assert(review.includes("Excluded from inventory basis") && review.includes("Excluded noninventory"));
assert(review.includes("$136.16") && review.includes("-$1.99") && review.includes("$134.17"));
assert(review.includes("$110.00") && review.includes("$24.17") && review.includes("$0.00"));
assert(review.includes('name="confirm_noninventory_exclusion"'));

const confirmedRow = vm.runInContext("allocationForm(state.activeAcquisition.lines[0])", context);
assert(confirmedRow.includes('data-confirmed="true"'));
assert((confirmedRow.match(/Allocation confirmed/g) || []).length >= 2);
assert(confirmedRow.includes("allocation-confirmed-button") && confirmedRow.includes("checked disabled"));
assert(source.includes("invalidateConfirmedAllocationForm") && source.includes("ALLOCATION-INVALIDATE"));

function formStub(kind, lineId = "") {
  return { id: kind === "exception" ? "acquisition-exception-form" : "", dataset: { lineId }, classList: { contains(name) { return kind === "allocation" && name === "acquisition-allocation-form"; } } };
}
function field(form, name, value, type = "text", checked = false) {
  return { form, name, value, type, checked, disabled: false, closest(selector) { return selector === "form" ? this.form : null; }, focus() { this.focused = true; } };
}
const exceptionForm = formStub("exception");
const lineOneForm = formStub("allocation", "1");
const lineTwoForm = formStub("allocation", "2");
const reason = field(exceptionForm, "discrepancy_reason_code", "MERCHANT_TOTAL_CONTROLS");
const explanation = field(exceptionForm, "discrepancy_notes", "Keep this explanation");
const exclusion = field(exceptionForm, "excluded_noninventory", "24.17");
const exclusionCheck = field(exceptionForm, "confirm_noninventory_exclusion", "on", "checkbox", true);
const lineOneAmount = field(lineOneForm, "assigned_landed_cost", "30.00");
const lineTwoAmount = field(lineTwoForm, "assigned_landed_cost", "50.00");
const fields = [reason, explanation, exclusion, exclusionCheck, lineOneAmount, lineTwoAmount];
const root = { querySelectorAll() { return fields; } };
context.document.activeElement = explanation;
context.__root = root;
vm.runInContext("rememberAcquisitionWorkingState(__root)", context);
reason.value = ""; explanation.value = ""; exclusion.value = ""; exclusionCheck.checked = false; lineTwoAmount.value = "0.00";
vm.runInContext("restoreAcquisitionWorkingState(__root)", context);
assert.strictEqual(reason.value, "MERCHANT_TOTAL_CONTROLS");
assert.strictEqual(explanation.value, "Keep this explanation");
assert.strictEqual(exclusion.value, "24.17");
assert.strictEqual(exclusionCheck.checked, true);
assert.strictEqual(lineTwoAmount.value, "50.00");
vm.runInContext("clearAcquisitionWorkingLine(17, 1)", context);
const storedKeys = vm.runInContext("[...state.acquisitionWorkingForms.get(17).fields.keys()]", context);
assert(!storedKeys.some((key) => key.startsWith("allocation:1:")));
assert(storedKeys.includes("exception:discrepancy_reason_code") && storedKeys.includes("allocation:2:assigned_landed_cost"));

const styles = fs.readFileSync("static/styles.css", "utf8");
assert(styles.includes(".allocation-card.confirmed") && styles.includes(".allocation-confirmed-state"));
assert(styles.includes(".reconciliation-block.inventory-partition.pass"));

console.log("RC3 HF1 mixed-purchase reconciliation frontend contract: PASS");
