const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const app = fs.readFileSync(path.join(root, "static", "app.js"), "utf8");
const styles = fs.readFileSync(path.join(root, "static", "styles.css"), "utf8");
const server = fs.readFileSync(path.join(root, "app.py"), "utf8");
const challenger = fs.readFileSync(path.join(root, "dex_sam_challenger.py"), "utf8");
const baseline = fs.readFileSync(path.join(root, "dex_sam.py"), "utf8");
const docker = fs.readFileSync(path.join(root, "Dockerfile"), "utf8");

assert(app.includes("Shadow only · no inventory authority"));
assert(app.includes("Correct family in candidate pool"));
assert(app.includes("Original five recovered"));
assert(app.includes("Trusted OCR nominates candidates only"));
assert(app.includes("samChallengerShadowPanel(challenger)"));
assert(styles.includes(".sam-challenger-shadow"));
assert(server.includes('path == "/api/sam/challenger/comparison"'));
assert(server.includes("sam_challenger_shadow_for_job"));
assert(challenger.includes('CHALLENGER_MODE = "SHADOW_ONLY"'));
assert(challenger.includes('"database_writes": 0'));
assert(challenger.includes('"trusted_ocr_is_authority": False'));
assert(challenger.includes("GLOBAL_VISUAL_NEIGHBOR"));
assert(challenger.includes("INDEPENDENT_SET_CONTEXT"));
assert(challenger.includes("UNRESOLVED_VARIANT_AMBIGUITY"));
assert(!baseline.includes("dex_sam_challenger"));
assert(docker.includes("COPY dex_sam_challenger.py ./"));
assert(docker.includes('RUN python -c "import dex_sam_challenger"'));
assert(!app.includes("0.55 * number_score"));

console.log("SAM Challenger v1 shadow-only frontend/runtime contract: PASS");
