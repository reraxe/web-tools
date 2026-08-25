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

const activeBase = {
  id: 201, semantic_uuid: "RCPT-SEM-ACTIVE-1", job_id: 12, active: true,
  source_line_index: 7, source_page: 1, source_location: "line 7", normalized_text: "OP deck $16.00",
  signed_amount_cents: 1600, semantic_class: "MERCHANDISE", numeric_confidence: 0.9,
  confidence_state: "HIGH_CONFIDENCE_SUGGESTION", semantic_status: "PROPOSED",
  parser_version: "receipt-structured-math-v1-remediation2", rules_version: "receipt-semantic-rules-v2-remediation2",
  recorded_at: "2026-08-21T20:00:00Z", operator_confirmation_required: false, product_match_eligible: true,
};
const activeUnknown = {
  ...activeBase, id: 202, semantic_uuid: "RCPT-SEM-ACTIVE-2", source_line_index: 9,
  normalized_text: "UEZ (3.3125%5)} $0.53", signed_amount_cents: 53, semantic_class: "UNKNOWN",
  numeric_confidence: 0.32, confidence_state: "UNRESOLVED", semantic_status: "UNRESOLVED",
  operator_confirmation_required: true, product_match_eligible: false,
};
const historical = {
  ...activeUnknown, id: 101, semantic_uuid: "RCPT-SEM-HISTORICAL", job_id: 11, active: false,
  semantic_class: "MERCHANDISE", numeric_confidence: 0.9, confidence_state: "HIGH_CONFIDENCE_SUGGESTION",
  semantic_status: "PROPOSED", parser_version: "receipt-structured-math-v1", rules_version: "receipt-semantic-rules-v1",
  recorded_at: "2026-08-21T19:00:00Z", operator_confirmation_required: false,
  inactive_reason: "SUPERSEDED_EXTRACTION", superseded_by_semantic_uuid: null,
  superseded_by_job_uuid: "RCPT-JOB-NEW", operator_action: null, product_match_eligible: false,
};
const review = {
  lines: [activeBase, activeUnknown], history: [historical], active_assertion_count: 2,
  historical_assertion_count: 1, total_stored_assertion_count: 3, needs_confirmation_count: 1,
};
const rendered = vm.runInContext(`receiptSemanticReview(${JSON.stringify(review)})`, context);

assert(rendered.includes("Current interpretation · 2 source line(s) · 1 need review"));
assert(rendered.includes("View interpretation history · 1 historical / superseded"));
assert(rendered.includes("Audit history is immutable"));
assert(rendered.includes("Superseded by extraction RCPT-JOB-NEW"));
assert(rendered.includes("receipt-structured-math-v1"));
assert(rendered.includes("receipt-semantic-rules-v1"));
assert(rendered.includes("Current semantic suggestions only"));
assert(rendered.includes('class="receipt-semantic-adjust"'));
assert(rendered.includes("Change classification"));
assert(rendered.indexOf("UEZ (3.3125%5)} $0.53") < rendered.indexOf("View interpretation history"));
assert(styles.includes(".receipt-semantic-history"));
assert(styles.includes(".receipt-semantic-adjust"));
assert(source.includes("Removed-document extraction history / prior attempts"));
assert(source.includes("no active retry or authority"));

console.log("DEX Inventory Intelligence Phase 1 Remediation 4 active semantic UI: PASS");
