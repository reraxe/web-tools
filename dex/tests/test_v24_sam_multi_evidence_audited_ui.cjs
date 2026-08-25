const assert = require("assert");
const fs = require("fs");

const app = fs.readFileSync("static/app.js", "utf8");
const styles = fs.readFileSync("static/styles.css", "utf8");
const handler = fs.readFileSync("app.py", "utf8");
const backend = fs.readFileSync("dex_sam_audited.py", "utf8");
const worker = fs.readFileSync("dex_sam_audited_worker.py", "utf8");

assert(app.includes("SAM Multi-Evidence Audited Intake"));
assert(app.includes("SAM suggests → operator decides → DEX records"));
assert(app.includes("Immutable pre-operator result"));
assert(app.includes("Verify or correct using the frozen local catalog"));
assert(app.includes("Catalog search begins only after the SAM result is frozen"));
assert(app.includes("CONFIRMED_UNCHANGED"));
assert(app.includes("CORRECTED_FAMILY"));
assert(app.includes("ESCALATED_REVIEW"));
assert(app.includes("MARKED_UNIDENTIFIED"));
assert(app.includes("Exact printing, rarity, treatment, stamps, and marketplace identity remain unresolved"));
assert(app.includes("runSamAudited"));
assert(app.includes("decideSamAudited"));
assert(styles.includes(".sam-audited-panel"));
assert(styles.includes(".sam-audited-freeze"));
assert(styles.includes(".sam-audited-candidate.selected"));

assert(handler.includes('/api/sam/audited/cards/[A-Z0-9-]+/recognize'));
assert(handler.includes('/api/sam/audited/results/SAM-AUDIT-RESULT-[0-9a-f-]+/decision'));
assert(handler.includes("Catalog verification opens only after an audited SAM result is frozen"));
assert(worker.includes('"automatic_family_write": False'));
assert(worker.includes('"exact_printing_authority": False'));
assert(backend.includes('"operator_decision_is_verified_truth": False'));
assert(backend.includes('"used_as_training_label": False'));
assert(!app.includes("printing.authoritative = true"));

console.log("SAM multi-evidence audited operator-trial frontend contract: PASS");
