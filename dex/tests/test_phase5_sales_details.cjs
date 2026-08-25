const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

class ElementStub {
  constructor(key = "") {
    this.innerHTML = "";
    this.textContent = "";
    this.className = "";
    this.dataset = key ? { viewportKey: key } : {};
    this.style = {};
    this.value = "";
    this.open = false;
    this.complete = true;
    this.classList = { add() {}, remove() {}, toggle() {} };
  }
  addEventListener() {}
  closest() { return null; }
  getBoundingClientRect() { return { top: 120, bottom: 180 }; }
  querySelector() { return null; }
  querySelectorAll(selector) {
    if (selector === "[data-viewport-key]" && this === app) return [saleAnchor];
    return [];
  }
  showModal() { this.open = true; }
  close() { this.open = false; }
}

const saleAnchor = new ElementStub("sale-order-42");
const app = new ElementStub();
const modal = new ElementStub();
const topbar = new ElementStub();
topbar.getBoundingClientRect = () => ({ top: 0, bottom: 68 });
const elements = new Map([["#app", app], ["#modal", modal], [".topbar", topbar]]);
const elementFor = (selector) => {
  if (!elements.has(selector)) elements.set(selector, new ElementStub());
  return elements.get(selector);
};
const document = {
  activeElement: null,
  querySelector: elementFor,
  querySelectorAll: () => [],
  addEventListener() {},
  body: new ElementStub(),
};

let canceled = false;
const exactUnits = [
  { id: 101, unit_code: "OP-PHASE5-01-UNIT-0001", unit_sequence: 1, batch_code: "OP-PHASE5-01", product_name: "Disposable Box", merchandise_amount_cents: 751, basis_cents: 334 },
  { id: 102, unit_code: "OP-PHASE5-01-UNIT-0002", unit_sequence: 2, batch_code: "OP-PHASE5-01", product_name: "Disposable Box", merchandise_amount_cents: 749, basis_cents: 333 },
];
const orderDetails = () => ({
  id: 42,
  order_type: "SEALED",
  order_number: "PHASE5-DETAIL-UI",
  platform: "eBay",
  sold_at: "2026-08-14",
  notes: "Disposable operator QA",
  calculation_version: "acquisition-rip-v3",
  merchandise_total_cents: 1500,
  shipping_collected_cents: 200,
  marketplace_fees_cents: 100,
  actual_postage_cents: 300,
  marketplace_tax_cents: 125,
  net_proceeds_cents: 1300,
  sold_basis_cents: 667,
  realized_profit_loss_cents: 633,
  items: exactUnits.map((unit) => ({ item_type: "SEALED_UNIT", sale_item_id: unit.id, identifier: unit.unit_code, batch_code: unit.batch_code, basis_cents: unit.basis_cents, status: "SOLD", returned: false })),
  financials: {
    original: { merchandise_cents: 1500, shipping_cents: 200, marketplace_fees_cents: 100, postage_cents: 300, other_net_cents: 0, net_proceeds_cents: 1300 },
    effective: { merchandise_cents: 1500, shipping_cents: 200, marketplace_fees_cents: 100, postage_cents: 300, other_net_cents: 0, net_proceeds_cents: 1300 },
  },
  events: [],
  post_sale_eligible: !canceled,
  original_sale_immutable_notice: "Original sale and item facts are preserved.",
  canceled_at: canceled ? "2026-08-14T18:00:00+00:00" : null,
  undo_eligible: !canceled,
  undo_eligibility_reason: canceled
    ? "This order is already canceled and its history has been retained."
    : "Eligible. Undo will restore these exact sealed units atomically.",
});
const salesPayload = () => ({
  calculation_version: "acquisition-rip-v3",
  sales: [{
    id: 42,
    sold_at: "2026-08-14",
    order_type: "SEALED",
    platform: "eBay",
    order_number: "PHASE5-DETAIL-UI",
    item_count: 2,
    subtotal: 15,
    merchandise_effective_cents: 1500,
    shipping_collected: 2,
    shipping_effective_cents: 200,
    fees_plus_postage: 4,
    effective_fees_plus_postage_cents: 400,
    net_proceeds: 13,
    net_proceeds_cents: 1300,
    post_sale_event_count: 0,
    sold_basis_cents: 667,
    realized_profit_loss_cents: 633,
    canceled_at: canceled ? "2026-08-14T18:00:00+00:00" : null,
  }, {
    id: 43,
    sold_at: "2026-08-13",
    order_type: "CARD",
    platform: "TCGplayer",
    order_number: "CARD-ORDER-UNCHANGED",
    item_count: 1,
    subtotal: 8,
    merchandise_effective_cents: 800,
    shipping_collected: 0,
    shipping_effective_cents: 0,
    fees_plus_postage: 1,
    effective_fees_plus_postage_cents: 100,
    net_proceeds: 7,
    net_proceeds_cents: 700,
    post_sale_event_count: 0,
    sold_basis_cents: null,
    realized_profit_loss_cents: null,
    canceled_at: null,
  }],
});

const calls = [];
const fetch = async (path, options = {}) => {
  calls.push([path, options.method || "GET"]);
  let body;
  if (path === "/api/sales") body = salesPayload();
  else if (path === "/api/sales/42" && !options.method) body = orderDetails();
  else if (path === "/api/sealed-sales/42/undo" && options.method === "POST") {
    canceled = true;
    body = { order_id: 42, restored_unit_ids: [101, 102] };
  } else if (path === "/api/dashboard") body = { tcg_slots: 0, tcg_capacity: 500 };
  else throw new Error(`Unexpected request: ${options.method || "GET"} ${path}`);
  return { ok: true, status: 200, json: async () => body };
};

const context = {
  console,
  document,
  Intl,
  Date,
  Set,
  Map,
  URL,
  URLSearchParams,
  FormData,
  Blob,
  FileReader: class {},
  setTimeout,
  clearTimeout,
  requestAnimationFrame: (callback) => callback(),
  confirm: () => true,
  fetch,
  history: { replaceState() {} },
  location: { hash: "#sales", reload() {} },
  navigator: { clipboard: { writeText: async () => {} } },
};
context.window = {
  addEventListener() {},
  lucide: null,
  location: context.location,
  innerHeight: 900,
  scrollY: 420,
  scrollBy() {},
  scrollTo() {},
};
context.globalThis = context;
vm.createContext(context);

const source = fs.readFileSync("static/app.js", "utf8").replace(/\nboot\(\);\s*$/, "\n");
vm.runInContext(source, context);

(async () => {
  await vm.runInContext("renderSales()", context);
  assert(app.innerHTML.includes('data-action="open-sealed-order"'));
  assert(app.innerHTML.includes("PHASE5-DETAIL-UI"));
  assert(app.innerHTML.includes('data-action="search-sale-order"'));
  assert(app.innerHTML.includes("CARD-ORDER-UNCHANGED"));

  await vm.runInContext("openSealedOrderDetails(42)", context);
  const modalBody = elementFor("#modal-body").innerHTML;
  assert(modal.open, "sealed order detail modal did not open");
  assert(modalBody.includes("OP-PHASE5-01-UNIT-0001"));
  assert(modalBody.includes("internal item #101"));
  assert(modalBody.includes("OP-PHASE5-01-UNIT-0002"));
  assert(modalBody.includes('data-action="undo-sealed-order"'));

  await vm.runInContext("undoSealedOrder(42)", context);
  assert(calls.some(([path, method]) => path === "/api/sealed-sales/42/undo" && method === "POST"));
  assert(app.innerHTML.includes("Canceled / undone"), "canceled order disappeared from Sales history");
  assert(app.innerHTML.includes('data-viewport-key="sale-order-42"'), "Sales row lacks a stable viewport anchor");
  assert.strictEqual(canceled, true);

  await vm.runInContext("openSealedOrderDetails(42)", context);
  const retainedBody = elementFor("#modal-body").innerHTML;
  assert(retainedBody.includes("Canceled / undone"));
  assert(retainedBody.includes("OP-PHASE5-01-UNIT-0001"));
  assert(!retainedBody.includes('data-action="undo-sealed-order"'));
  console.log("Phase 5 sealed Sales details and targeted Undo UI: PASS");
})().catch((error) => {
  console.error(error.stack);
  process.exit(1);
});
