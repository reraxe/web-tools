const assert = require("assert");
const fs = require("fs");

const app = fs.readFileSync("static/app.js", "utf8");
const styles = fs.readFileSync("static/styles.css", "utf8");
const backend = fs.readFileSync("dex_sam.py", "utf8");
const identity = fs.readFileSync("dex_sam_identity.py", "utf8");

assert(app.includes("Family identity"));
assert(app.includes("Exact commercial printing"));
assert(app.includes("Confirm Family"));
assert(app.includes("Confirm Printing"));
assert(app.includes("Leave Printing Unresolved"));
assert(app.includes("Mark Conflict"));
assert(app.includes("Legacy text is preserved but is not a confirmed commercial printing"));
assert(app.includes("commercial_printing_id"));
assert(app.includes("printing.authoritative"));
assert(app.includes("Family may be confirmed without resolving printing"));
assert(styles.includes(".sam-identity-panels"));
assert(styles.includes(".sam-identity-panel.unresolved"));
assert(backend.includes("printing_authority_granted"));
assert(backend.includes("CONFIRM_PRINTING"));
assert(identity.includes("FAMILY_AUTHORITY_NEVER_IMPLIES_PRINTING_AUTHORITY"));
assert(identity.includes("ABSENT_CONFIDENT"));
assert(!app.includes("printing.authoritative = true"));

console.log("SAM Phase 1 family/printing review contract: PASS");
