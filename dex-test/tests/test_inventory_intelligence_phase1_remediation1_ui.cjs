const assert = require("assert");
const fs = require("fs");

const html = fs.readFileSync("static/index.html", "utf8");
const app = fs.readFileSync("static/app.js", "utf8");
const dockerfile = fs.readFileSync("Dockerfile", "utf8");

assert(html.includes("data-runtime-version"));
assert(html.includes("Checking version…"));
assert(!html.includes("Home Network - v2.2-test"));
assert(app.includes('await api("/api/health")'));
assert(app.includes('runtimeVersion.textContent = health.version'));
assert(/org\.opencontainers\.image\.version="(?:v2\.3-test-inventory-intelligence-phase1-remediation(?:1|2|3)|v2\.4-test-(?:sam-phase1-family-printing|jarvis-sam-phase2))"/.test(dockerfile));

console.log("Inventory Intelligence Phase 1 Remediation 1+ runtime identity compatibility contract: PASS");
