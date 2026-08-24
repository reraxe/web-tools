const assert = require("assert");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const app = fs.readFileSync(path.join(root, "static", "app.js"), "utf8");
const styles = fs.readFileSync(path.join(root, "static", "styles.css"), "utf8");
const index = fs.readFileSync(path.join(root, "static", "index.html"), "utf8");
const backend = fs.readFileSync(path.join(root, "dex_sam.py"), "utf8");
const server = fs.readFileSync(path.join(root, "app.py"), "utf8");
const docker = fs.readFileSync(path.join(root, "Dockerfile"), "utf8");

assert(app.includes("SAM Recognition + Human Review"));
assert(app.includes("Batch Review Queues"));
assert(app.includes("Matched") && app.includes("Needs Review") && app.includes("Unidentified"));
assert(app.includes("Confirm Match") && app.includes("Find Match") && app.includes("Leave Unidentified"));
assert(app.includes("Correction details required") && app.includes("#sam-correction-notes"));
assert(app.includes("Correction not saved") && app.includes("showSamCorrectionError"));
assert(!app.includes("prompt(\"Why is SAM's original suggestion wrong?"));
assert(app.includes("Physical scan") && app.includes("SAM best candidate"));
assert(app.includes("Card number unreadable") && app.includes("agrees with reference"));
assert(app.includes("OCR/visual identity conflict") || app.includes("visual evidence favors"));
assert(app.includes("OCR details") && app.includes("preprocessing_ms") && app.includes("execution_ms"));
assert(app.includes("execution_path") && app.includes("Fast path") && app.includes("Escalated path"));
assert(app.includes("alternate_candidates") && app.includes("original suggestion remains in history"));
assert(app.includes("/sam/recognize") && app.includes("/api/sam/recognitions/"));
assert(app.includes("/api/sam/references/search") && app.includes("/decision"));
assert(app.includes("SAM assigns identity only"));
assert(app.includes("Scanning not blocked"));
assert(app.includes("structured metadata only") && app.includes("No physical scans or local references are transmitted"));

assert(styles.includes(".sam-review-board"));
assert(styles.includes(".sam-side-by-side"));
assert(styles.includes(".sam-review-actions"));
assert(styles.includes(".sam-number-evidence") && styles.includes(".sam-number-debug"));
assert(styles.includes("@media (max-width: 620px)"));
assert(index.includes("v2.2-test-phase7-sam-ocr-pass2-r1"));
assert(index.includes("v2.2-test-phase7-sam-ocr-pass3-r1"));

assert(backend.includes('RULES_VERSION = "sam-conservative-'));
assert(backend.includes("AUTO_MATCH_THRESHOLD"));
assert(backend.includes("sample_watermark_policy"));
assert(backend.includes("LOCAL_TESSERACT_OCR") && backend.includes("CARD_NUMBER_OCR_CONFLICT"));
assert(backend.includes("OCR_METHOD_VERSION") && backend.includes("OCR_CARD_NUMBER_MIN_CONFIDENCE"));
assert(backend.includes("IDENTITY_ONLY_NO_ECONOMICS"));
assert(!app.includes("0.55 * number_score"));
assert(!app.includes("AUTO_MATCH_THRESHOLD ="));

assert(server.includes('path == "/api/sam/provider/health"'));
assert(server.includes('path == "/api/sam/review-queues"'));
assert(server.includes('"/api/sam/references/index"'));
assert(docker.includes("COPY dex_sam.py ./"));
assert(docker.includes('RUN python -c "import dex_sam"'));

console.log("Phase 7 SAM frontend/runtime contract: PASS");
