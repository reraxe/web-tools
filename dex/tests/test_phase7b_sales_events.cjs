const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

class ElementStub {
  constructor() { this.innerHTML = ""; this.textContent = ""; this.dataset = {}; this.style = {}; this.open = false; this.classList = { add() {}, remove() {}, toggle() {} }; }
  addEventListener() {}
  querySelector() { return null; }
  querySelectorAll() { return []; }
  showModal() { this.open = true; }
  close() { this.open = false; }
}
const app = new ElementStub();
const modal = new ElementStub();
const elements = new Map([["#app", app], ["#modal", modal]]);
const document = {
  querySelector(selector) { if (!elements.has(selector)) elements.set(selector, new ElementStub()); return elements.get(selector); },
  querySelectorAll() { return []; }, addEventListener() {}, body: new ElementStub(), activeElement: null,
};

const order = {
  id: 77, order_type: "CARD", order_number: "PHASE7B-UI", platform: "eBay", sold_at: "2026-08-14",
  canceled_at: null, calculation_version: "acquisition-rip-v3", post_sale_eligible: true,
  original_sale_immutable_notice: "Original sale and item facts are preserved.",
  items: [{ item_type: "CARD", sale_item_id: 91, entity_id: 4, identifier: "OP-P7B-001", batch_code: "OP-P7B-01", basis_cents: 500, status: "SOLD", returned: false, return_outcome: null }],
  financials: {
    original: { merchandise_cents: 2000, shipping_cents: 200, marketplace_fees_cents: 300, postage_cents: 400, other_net_cents: 0, net_proceeds_cents: 1500 },
    effective: { merchandise_cents: 1500, shipping_cents: 100, marketplace_fees_cents: 200, postage_cents: 250, other_net_cents: -200, net_proceeds_cents: 950 },
  },
  sold_basis_cents: 500, realized_profit_loss_cents: 450,
  events: [{ event_id: "SALE7B-REFUND", event_type: "PARTIAL_REFUND", reason_code: "CUSTOMER_REQUEST", effective_at: "2026-08-14", recorded_at: "2026-08-14T20:00:00+00:00", notes: "", entries: [{ component_type: "MERCHANDISE", amount_delta_cents: -500 }], reversed: false, reversible: true }],
};
const sales = { calculation_version: "acquisition-rip-v3", sales: [{ ...order, item_count: 1, post_sale_event_count: 1, merchandise_effective_cents: 1500, shipping_effective_cents: 100, effective_fees_plus_postage_cents: 450, net_proceeds_cents: 950 }] };
const calls = [];
const fetch = async (path) => {
  calls.push(path);
  const body = path === "/api/sales" ? sales : path === "/api/sales/77" ? order : null;
  if (!body) throw new Error(`Unexpected request ${path}`);
  return { ok: true, status: 200, json: async () => body };
};
const context = { console, document, Intl, Date, Set, Map, URL, URLSearchParams, FormData, Blob, FileReader: class {}, setTimeout, clearTimeout, requestAnimationFrame: (cb) => cb(), confirm: () => true, fetch, history: { replaceState() {} }, location: { hash: "#sales", reload() {} }, navigator: { clipboard: { writeText: async () => {} } } };
context.window = { addEventListener() {}, lucide: null, location: context.location, innerHeight: 900, scrollY: 0, scrollBy() {}, scrollTo() {} };
context.globalThis = context;
vm.createContext(context);
const source = fs.readFileSync("static/app.js", "utf8").replace(/\nboot\(\);\s*$/, "\n");
vm.runInContext(source, context);

(async () => {
  await vm.runInContext("renderSales()", context);
  assert(app.innerHTML.includes('data-action="open-sale-order"'));
  assert(app.innerHTML.includes("1 post-sale event(s)"));
  assert(app.innerHTML.includes("$9.50"), "Sales row must serialize backend effective net proceeds");
  await vm.runInContext("openSaleOrderDetails(77)", context);
  const body = document.querySelector("#modal-body").innerHTML;
  for (const expected of ["Original recorded facts", "Effective Realized Economics", "OP-P7B-001", "SALE7B-REFUND", "Partial refund", "Customer return", "Chargeback", "Postage refund", "Sale correction", 'data-action="reverse-post-sale-event"']) assert(body.includes(expected), `Missing ${expected}`);
  assert(calls.includes("/api/sales/77"));
  console.log("Phase 7B Sales details and immutable event actions: PASS");
})().catch((error) => { console.error(error.stack); process.exit(1); });
