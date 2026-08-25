const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

class ElementStub {
  constructor() {
    this.innerHTML = ""; this.textContent = ""; this.dataset = {}; this.style = {};
    this.value = ""; this.open = false; this.complete = true; this.type = "";
    this.classList = { add() {}, remove() {}, toggle() {} };
  }
  addEventListener() {} click() {} closest() { return null; } focus() {}
  querySelector() { return null; } querySelectorAll() { return []; }
  getBoundingClientRect() { return { top: 100, bottom: 150 }; }
  showModal() { this.open = true; } close() { this.open = false; }
}

const elements = new Map();
const document = {
  activeElement: null,
  body: new ElementStub(),
  querySelector(selector) {
    if (!elements.has(selector)) elements.set(selector, new ElementStub());
    return elements.get(selector);
  },
  querySelectorAll() { return []; },
  addEventListener() {},
};
class FormDataStub {
  constructor(form) { this.values = form?.values || []; }
  entries() { return this.values[Symbol.iterator](); }
}
const context = {
  console, document, Intl, Date, Set, Map, URL, URLSearchParams,
  FormData: FormDataStub, Blob, FileReader: class {}, setTimeout, clearTimeout,
  requestAnimationFrame: (callback) => callback(), confirm: () => true,
  fetch: async () => ({ ok: true, status: 200, json: async () => ({}) }),
  history: { replaceState() {} }, location: { hash: "#inbound", reload() {} },
  navigator: { clipboard: { writeText: async () => {} } },
};
context.window = {
  addEventListener() {}, open() {}, lucide: null, location: context.location,
  innerHeight: 900, scrollY: 0, scrollBy() {}, scrollTo() {},
};
context.globalThis = context;
vm.createContext(context);
const source = fs.readFileSync("static/app.js", "utf8").replace(/\nboot\(\);\s*$/, "\n");
const styles = fs.readFileSync("static/styles.css", "utf8");
vm.runInContext(source, context);

const review = {
  needs_confirmation_count: 2,
  lines: [
    {
      semantic_uuid: "RCPT-SEM-MERCH", source_line_index: 3, source_page: 1,
      source_location: "line 3", normalized_text: "One Piece booster packs x4 30.00",
      signed_amount_cents: 3000, semantic_class: "MERCHANDISE", numeric_confidence: 0.9,
      confidence_state: "HIGH_CONFIDENCE_SUGGESTION", parser_version: "receipt-structured-math-v1",
      operator_confirmation_required: false, product_match_eligible: true,
    },
    {
      semantic_uuid: "RCPT-SEM-TAX", source_line_index: 10, source_page: 1,
      source_location: "line 10", normalized_text: "State Tax 3.3125% 4.18",
      signed_amount_cents: 418, semantic_class: "TAX", numeric_confidence: 0.98,
      confidence_state: "OPERATOR_CONFIRMED", parser_version: "receipt-structured-math-v1",
      operator_confirmation_required: false, product_match_eligible: false,
    },
    {
      semantic_uuid: "RCPT-SEM-UNKNOWN", source_line_index: 14, source_page: 1,
      source_location: "line 14", normalized_text: "Mystery adjustment -2.00",
      signed_amount_cents: -200, semantic_class: "UNKNOWN", numeric_confidence: 0.45,
      confidence_state: "UNRESOLVED", parser_version: "receipt-structured-math-v1",
      operator_confirmation_required: true, product_match_eligible: false,
    },
  ],
};

const rendered = vm.runInContext(`receiptSemanticReview(${JSON.stringify(review)})`, context);
assert(rendered.includes("Current interpretation · 3 source line(s) · 2 need review"));
assert(rendered.includes("One Piece booster packs x4 30.00"));
assert(rendered.includes("$30.00"));
assert(rendered.includes("State Tax 3.3125% 4.18"));
assert(rendered.includes("Product-match eligible"));
assert(rendered.includes("Excluded from product matching"));
assert(rendered.includes("Operator Confirmed"));
assert(rendered.includes("Current semantic suggestions only"));
assert(rendered.includes('data-action="mark-semantic-unresolved"'));
assert(rendered.includes('aria-label="Semantic class for source line 3"'));

vm.runInContext("globalThis.semanticMutationCapture = null; receiptMutation = async (path, options) => { globalThis.semanticMutationCapture = { path, options }; return {}; };", context);
context.semanticForm = {
  dataset: { semanticUuid: "RCPT-SEM-UNKNOWN", currentClass: "UNKNOWN" },
  elements: {
    semantic_class: { value: "MERCHANDISE" },
    reason_code: { value: "PARSER_MISCLASSIFIED" },
    notes: { value: "Visible product line" },
  },
};
vm.runInContext(`saveReceiptSemanticDecision({ preventDefault() {}, currentTarget: semanticForm })`, context);
setImmediate(() => {
  const mutation = context.semanticMutationCapture;
  assert(mutation);
  assert.strictEqual(mutation.path, "/api/receipt-semantic-lines/RCPT-SEM-UNKNOWN/decision");
  assert.strictEqual(mutation.options.fields.action, "CHANGE");
  assert.strictEqual(mutation.options.fields.semantic_class, "MERCHANDISE");
  assert.strictEqual(mutation.options.fields.reason_code, "PARSER_MISCLASSIFIED");
  assert.strictEqual(mutation.options.fields.notes, "Visible product line");
  assert(styles.includes(".receipt-semantic-review"));
  assert(styles.includes(".receipt-semantic-line.confirmed"));
  console.log("DEX Inventory Intelligence Phase 1 frontend contract: PASS");
});
