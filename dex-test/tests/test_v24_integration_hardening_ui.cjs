const assert = require("assert");
const fs = require("fs");

const app = fs.readFileSync("static/app.js", "utf8");
const styles = fs.readFileSync("static/styles.css", "utf8");
const backend = fs.readFileSync("dex_jarvis_economics.py", "utf8");
const handler = fs.readFileSync("app.py", "utf8");

// SAM review and JARVIS economics coexist visually while remaining independent.
assert(app.includes("Economics context · display only"));
assert(app.includes("Never used for identity confidence"));
assert(app.includes("WOLFF simplified economics"));
assert(app.includes("Parent acquisition cost"));
assert(app.includes("jarvisCoveredCents(inventory.total_remaining_cost_basis_cents, inventory.authoritative_basis_count, inventory.item_count)"));
assert(app.includes("Identity provenance and append-only history"));
assert(app.includes("job.completed_at || job.submitted_at || job.created_at"));
assert(app.includes("Evidence version unknown"));
assert(app.includes("Economics provenance"));
assert(app.includes("Sale economics provenance"));
assert(app.includes("Realized sale economics"));
assert(app.includes("Legacy text is preserved but is not a confirmed commercial printing"));
assert(app.includes("Legacy identity conflict"));
assert(app.includes("The recorded legacy value is preserved. The printing suggestion does not overwrite it."));
assert(app.includes("market value never influence recognition confidence or authority"));
assert(styles.includes(".sam-economics-context"));
assert(styles.includes(".sam-provenance"));
assert(styles.includes(".jarvis-provenance"));

// Freshness and fail-safe endpoint handling are backend-owned.
for (const state of ["CURRENT", "AGING", "STALE", "UNKNOWN"]) {
  assert(backend.includes(`"${state}"`));
}
assert(handler.includes('self.send_error_json("Card economics not found", 404)'));
assert(handler.includes('self.send_error_json("Sale economics not found", 404)'));
assert(handler.includes('self.send_error_json("JARVIS economics endpoint not found", 404)'));

// Formatting only: the browser still does not duplicate economics formulas.
assert(!app.includes("net = merchandise"));
assert(!app.includes("profit = net"));
assert(!app.includes("marketplace_fees.value_cents -"));
assert(!app.includes("printing.authoritative = true"));

console.log("v2.4 integration hardening frontend contract: PASS");
