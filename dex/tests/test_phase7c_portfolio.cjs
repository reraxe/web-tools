const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

class ElementStub {
  constructor() { this.innerHTML = ""; this.textContent = ""; this.dataset = {}; this.style = {}; this.classList = { add() {}, remove() {}, toggle() {} }; }
  addEventListener() {}
  querySelector() { return null; }
  querySelectorAll() { return []; }
}

const app = new ElementStub();
const elements = new Map([["#app", app]]);
const document = {
  querySelector(selector) { if (!elements.has(selector)) elements.set(selector, new ElementStub()); return elements.get(selector); },
  querySelectorAll() { return []; }, addEventListener() {}, body: new ElementStub(), activeElement: null,
};

const report = {
  calculation_version: "acquisition-rip-v3", generated_at: "2026-08-14T22:00:00+00:00",
  state: "FINALIZED_ECONOMICS_ONLY", title: "Operational Economics",
  scope_notice: "Portfolio totals include Finalized Economics only.", tax_notice: "Operational reporting only.",
  scope: { total_batch_count: 3, finalized_batch_count: 2, authoritative_unfinalized_batch_count: 0, legacy_estimate_batch_count: 1 },
  summary: {
    authoritative_acquisition_cost_cents: 200000, effective_realized_net_proceeds_cents: 215000,
    active_sold_basis_cents: 90000, realized_profit_loss_cents: 125000, operational_loss_cents: 10000,
    known_remaining_market_value_cents: 55000, known_remaining_listed_value_cents: 70000,
    current_economic_position_cents: 70000, current_position_complete: false,
    projected_listed_position_cents: 85000, projected_listed_position_complete: false,
    cost_recovery_percent: 107.5, valuation_complete: false,
  },
  realized: {
    gross_merchandise_cents: 250000, shipping_collected_cents: 15000,
    marketplace_fees_cents: 30000, actual_postage_cents: 18000, other_net_cents: -2000,
    net_proceeds_cents: 215000, sold_basis_cents: 90000, sold_basis_known_count: 8,
    sold_basis_total_count: 8, sold_basis_complete: true, realized_profit_loss_cents: 125000,
    cost_recovery_percent: 107.5, unique_order_count: 4,
    cost_recovery_definition: "effective realized net proceeds ÷ authoritative acquisition cost",
    realized_profit_loss_definition: "effective realized net proceeds − active sold basis",
    marketplace_tax_treatment: "Marketplace-collected sales tax is excluded from revenue and P/L.",
  },
  remaining: {
    known_basis_cents: 95000, active_card_count: 12, remaining_sealed_unit_count: 2,
    known_bulk_quantity: 0, bulk_quantity_unknown: false,
    market: { known_value_cents: 55000, valued_count: 10, total_count: 14, complete: false, coverage_label: "10/14 remaining inventory items valued", freshness_label: "2026-08-14T20:00:00+00:00", cards: { valued_count: 10, total_count: 12 }, sealed: { state: "UNKNOWN" } },
    listed: { known_value_cents: 70000, valued_count: 11, total_count: 14, complete: false, coverage_label: "11/14 remaining inventory items valued", freshness_label: "Freshness Unknown", cards: { valued_count: 11, total_count: 12 }, sealed: { state: "UNKNOWN" } },
    current_economic_position_cents: 70000, current_position_complete: false,
    current_position_definition: "effective realized net proceeds + known remaining market value − authoritative acquisition cost",
    projected_listed_position_cents: 85000, projected_listed_position_complete: false,
    projected_listed_position_definition: "effective realized net proceeds + known remaining listed value − authoritative acquisition cost",
  },
  excluded: { known_basis_cents: 10000, operational_loss_cents: 10000 },
  inventory_counts: { remaining_cards: 12, active_sold_cards: 6, active_returned_cards: 1, sealed_acquired: 5, sealed_opened: 1, sealed_sold: 1, sealed_remaining: 2, sealed_corrected_adjusted: 1, active_sold_sealed_units: 1, active_returned_sealed_units: 0, known_bulk_quantity: 0, bulk_quantity_unknown: false },
  receipt_groups: { notice: "Informational aggregation only. Shared costs were not allocated automatically.", group_count: 1, groups: [{ reference: "P7C-GROUP", batch_count: 2, batch_codes: ["P7C-01", "P7C-02"] }] },
  reconciliation: {
    materially_incomplete: true,
    authoritative_cost: { difference_cents: 0 }, realized_net: { difference_cents: 0 },
    stable_order_attribution: { reconciled: true, unique_order_count: 4, attributed_item_count: 9, duplicate_attribution_count: 0 },
  },
  warnings: [{ code: "SEALED_VALUE_UNKNOWN", severity: "material", message: "Remaining sealed inventory remains Unknown." }],
  batches: [{ id: 1, batch_code: "P7C-01", product_name: "Booster Box", receipt_group_reference: "P7C-GROUP", authoritative_cost_cents: 100000, effective_realized_net_proceeds_cents: 120000, known_remaining_market_value_cents: 30000, market_complete: false, operational_loss_cents: 10000 }],
};

const calls = [];
const fetch = async (path) => {
  calls.push(path);
  if (path !== "/api/portfolio/economics") throw new Error(`Unexpected request ${path}`);
  return { ok: true, status: 200, json: async () => report };
};
const context = { console, document, Intl, Date, Set, Map, URL, URLSearchParams, FormData, Blob, FileReader: class {}, setTimeout, clearTimeout, requestAnimationFrame: (cb) => cb(), confirm: () => true, fetch, history: { replaceState() {} }, location: { hash: "#economics", reload() {} }, navigator: { clipboard: { writeText: async () => {} } } };
context.window = { addEventListener() {}, lucide: null, location: context.location, innerHeight: 900, scrollY: 0, scrollBy() {}, scrollTo() {} };
context.globalThis = context;
vm.createContext(context);
const source = fs.readFileSync("static/app.js", "utf8").replace(/\nboot\(\);\s*$/, "\n");
vm.runInContext(source, context);

(async () => {
  await vm.runInContext("renderOperationalEconomics()", context);
  for (const expected of ["Operational Economics", "What did this cost?", "$2,000.00", "$2,150.00", "107.5%", "Incomplete — known values only", "10/14 remaining inventory items valued", "Freshness Unknown", "Marketplace-collected sales tax is excluded", "SEALED VALUE UNKNOWN", "P7C-GROUP", "0 duplicate attributions", "Portfolio CSV"]) {
    assert(app.innerHTML.toUpperCase().includes(expected.toUpperCase()), `Missing ${expected}`);
  }
  assert(calls.includes("/api/portfolio/economics"));
  console.log("Phase 7C backend-only Operational Economics UI: PASS");
})().catch((error) => { console.error(error.stack); process.exit(1); });
