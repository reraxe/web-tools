const assert = require("assert");
const fs = require("fs");

const dockerfile = fs.readFileSync("Dockerfile", "utf8");
const operator = fs.readFileSync("OPERATOR_DEPLOY_INSTRUCTIONS.md", "utf8");
const standard = fs.readFileSync("DEX_RELEASE_PACKAGING_STANDARD.md", "utf8");
const incident = fs.readFileSync("DEPLOYMENT_INCIDENT_001.md", "utf8");

assert(dockerfile.includes('org.opencontainers.image.version="v2.4-test-jarvis-sam-phase2"'));
for (const file of ["app.py", "static/index.html", "static/app.js", "static/styles.css", "Dockerfile"]) {
  assert(operator.includes(file));
  assert(standard.includes(file));
  assert(incident.includes(file));
}
assert(operator.includes("Record the resulting GitHub commit SHA"));
assert(operator.includes("Do not trigger Jenkins"));
assert(operator.includes("deployment-integrity failure"));
assert(standard.includes("GitHub Build-Context Provenance Gate"));
assert(standard.includes("zero missing or mismatched release files"));
assert(incident.includes("incomplete or stale GitHub upload/commit"));
assert(incident.includes("does not establish a GitHub platform defect"));
assert(incident.includes("may not exist in `/app`"));

console.log("Inventory Intelligence Phase 1 Remediation 2 provenance documentation contract: PASS");
