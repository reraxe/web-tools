const assert = require("assert");
const fs = require("fs");

const app = fs.readFileSync("static/app.js", "utf8");
const styles = fs.readFileSync("static/styles.css", "utf8");
const backend = fs.readFileSync("dex_jarvis_economics.py", "utf8");
const sam = fs.readFileSync("dex_sam_identity.py", "utf8");
const samBackend = fs.readFileSync("dex_sam.py", "utf8");

// JARVIS inventory, item, and sale surfaces all consume backend facts.
assert(app.includes('/api/jarvis/economics/summary'));
assert(app.includes('/api/jarvis/economics/cards/'));
assert(app.includes('/api/jarvis/economics/sales/'));
assert(app.includes("Known facts, visibly bounded"));
assert(app.includes("WOLFF simplified economics"));
assert(app.includes("Working On Levelling Financial Flows"));
assert(app.includes('jarvisFact("Parent acquisition cost", report.acquisition_cost)'));
assert(app.includes('jarvisFact("Allocated acquisition cost", report.allocated_acquisition_cost)'));
assert(app.includes("function jarvisCoveredCents"));
assert(app.includes("Number(coveredCount || 0) === 0"));
assert(app.includes("jarvisCoveredCents(inventory.total_remaining_cost_basis_cents, inventory.authoritative_basis_count, inventory.item_count)"));
assert(app.includes("Unknown inputs stay Unknown"));
assert(app.includes("Estimated basis is excluded from authoritative totals"));
assert(app.includes("Payment fees, packaging, and other direct costs remain separately unresolved"));
assert(app.includes("Calculation ${escapeHtml(report.calculation_version)}"));
assert(styles.includes(".jarvis-economics-panel"));
assert(styles.includes(".jarvis-fact.unresolved"));
assert(styles.includes(".jarvis-fact.estimated"));

// Backend remains the sole calculation source; JavaScript only selects and formats fields.
assert(backend.includes("net = ("));
assert(backend.includes("profit = net - int(basis)"));
assert(!app.includes("net = merchandise"));
assert(!app.includes("profit = net"));
assert(!app.includes("marketplace_fees.value_cents -"));

// SAM Phase 2 explains evidence per commercial printing and keeps authority separate.
assert(app.includes("Printing evidence intelligence"));
assert(app.includes("Excluded by negative evidence"));
assert(app.includes("Plausible · evidence unresolved"));
assert(app.includes("Phase 2 system evidence remains suggestion-only"));
assert(app.includes("market value never influence recognition confidence or authority"));
assert(samBackend.includes('"economics_value_used_for_identity": False'));
assert(styles.includes(".sam-printing-evidence-card.excluded"));
assert(styles.includes(".sam-marker-state.absent_confident"));
assert(styles.includes(".sam-marker-state.unresolved"));
assert(sam.includes('"authority_granted": False'));
assert(sam.includes("CONTRADICTORY_PRINTING_EVIDENCE"));
assert(sam.includes("REFERENCE_ASSET_QUALITY"));
assert(!app.includes("printing.authoritative = true"));

console.log("JARVIS simplified economics + SAM Phase 2 frontend safety contract: PASS");
