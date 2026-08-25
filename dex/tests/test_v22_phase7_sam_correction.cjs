const assert = require("assert");
const fs = require("fs");
const vm = require("vm");
const { webcrypto } = require("crypto");

class ElementStub {
  constructor() {
    this.innerHTML = "";
    this.textContent = "";
    this.className = "";
    this.value = "";
    this.hidden = true;
    this.disabled = false;
    this.open = false;
    this.isConnected = true;
    this.dataset = {};
    this.style = {};
    this.classList = { add() {}, remove() {}, toggle() {} };
  }
  addEventListener() {}
  querySelector() { return null; }
  querySelectorAll() { return []; }
  setAttribute() {}
  removeAttribute() {}
  focus() {}
  showModal() { this.open = true; }
  close() { this.open = false; }
}

const elements = new Map();
const element = (selector) => {
  if (!elements.has(selector)) elements.set(selector, new ElementStub());
  return elements.get(selector);
};
const document = {
  querySelector: element,
  querySelectorAll: () => [],
  addEventListener() {},
  body: new ElementStub(),
  activeElement: null,
};
const modal = element("#modal");
const requests = [];
let responseBody = {};
let responseOk = true;
let responseStatus = 200;

const context = {
  console,
  document,
  crypto: webcrypto,
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
  requestAnimationFrame: (callback) => setTimeout(callback, 0),
  fetch: async (path, options = {}) => {
    requests.push({ path, options, body: options.body ? JSON.parse(options.body) : null });
    return { ok: responseOk, status: responseStatus, json: async () => responseBody };
  },
  history: { replaceState() {} },
  location: { hash: "", reload() {} },
  navigator: { clipboard: { writeText: async () => {} } },
};
context.window = {
  addEventListener() {},
  lucide: null,
  location: context.location,
  scrollY: 0,
  innerHeight: 900,
  scrollTo() {},
};
context.globalThis = context;
vm.createContext(context);

const source = fs.readFileSync("static/app.js", "utf8").replace(/\nboot\(\);\s*$/, "\n");
vm.runInContext(source, context);
vm.runInContext("loadDashboard = async () => {}; renderSAM = async () => {}; closeModal = () => modal.close();", context);

const initialReview = {
  sku: "OP-SAM-P7-CORRECT",
  current_revision: 1,
  effective_state: "NEEDS_REVIEW",
  authoritative: false,
  scan_image_url: "/media/correct.png",
  job: {
    job_uuid: "SAM-JOB-00000000-0000-0000-0000-000000000001",
    recognition_state: "NEEDS_REVIEW",
    confidence: 1,
    engine_version: "dex-sam-one-piece-v1",
    evidence: {
      candidate_narrowing: "BATCH_SET_OCR_CROSSCHECK",
      candidates_scored: 6,
      card_number: {
        raw: "OP16-034", normalized: "OP16-034", confidence: 1,
        source: "LOCAL_TESSERACT_OCR", agreement: "AGREES_WITH_VISUAL_TOP",
        method_version: "dex-one-piece-card-number-ocr-v1", region_name: "LOWER_RIGHT_PRIMARY",
        preprocessing_ms: 4.5, execution_ms: 75.25, consensus_support: 4,
        valid_candidate_attempts: 4,
      },
      visual_top_candidate: { card_number: "OP16-034", card_name: "Intentional Wrong Suggestion", visual_score: 0.9 },
    },
    exception_codes: ["LOW_RECOGNITION_CONFIDENCE"],
  },
  top_candidate: { id: 34, card_number: "OP16-034", card_name: "Intentional Wrong Suggestion", set_code: "OP16", variant: "Standard", printing: "Original", confidence: 1 },
  candidates: [],
  alternate_candidates: [],
  decisions: [],
};
const correctionReference = { id: 35, card_number: "OP16-035", card_name: "Operator Correct Answer", set_code: "OP16", variant: "Standard", printing: "Original", confidence: 0 };
const correctedResult = {
  ...initialReview,
  current_revision: 2,
  effective_state: "OPERATOR_CORRECTED",
  authoritative: true,
  decisions: [{
    decision_type: "OPERATOR_CORRECTED",
    original_top_reference_id: 34,
    selected_reference_id: 35,
    reason_code: "OPERATOR_IDENTIFICATION_CORRECTION",
    notes: "OP16-035 matches the physical scan.",
  }],
};

(async () => {
  vm.runInContext(`state.samReview = ${JSON.stringify(initialReview)}; state.samReviewSelection = state.samReview.top_candidate; state.samReferenceResults = [${JSON.stringify(correctionReference)}];`, context);
  vm.runInContext("renderSamReviewModal()", context);
  assert(element("#modal-body").innerHTML.includes("Card number"));
  assert(element("#modal-body").innerHTML.includes("Read from physical scan · agrees with reference"));
  assert(element("#modal-body").innerHTML.includes("OCR details"));
  vm.runInContext("selectSamReference(35)", context);
  assert.strictEqual(vm.runInContext("state.samReviewSelection.card_number", context), "OP16-035");
  assert(element("#modal-body").innerHTML.includes("Operator-selected reference"));
  assert(element("#modal-body").innerHTML.includes("Correction details required"));
  assert(element("#modal-body").innerHTML.includes("Confirm Correction"));

  element("#sam-correction-reason").value = "OPERATOR_IDENTIFICATION_CORRECTION";
  element("#sam-correction-notes").value = "OP16-035 matches the physical scan.";
  responseBody = correctedResult;
  await vm.runInContext("decideSam('SAM-JOB-00000000-0000-0000-0000-000000000001', 'CORRECT', 1, 35)", context);

  assert.strictEqual(requests.length, 1, "correction request must fire exactly once");
  assert.strictEqual(requests[0].path, "/api/sam/recognitions/SAM-JOB-00000000-0000-0000-0000-000000000001/decision");
  assert.strictEqual(requests[0].body.action, "CORRECT");
  assert.strictEqual(requests[0].body.reference_id, 35);
  assert.strictEqual(requests[0].body.reason_code, "OPERATOR_IDENTIFICATION_CORRECTION");
  assert.strictEqual(requests[0].body.notes, "OP16-035 matches the physical scan.");
  assert.strictEqual(vm.runInContext("state.samReview.effective_state", context), "OPERATOR_CORRECTED");
  assert(element("#toast").textContent.includes("OP16-035 is now the authoritative identity"));
  assert.strictEqual(modal.open, false, "successful correction must exit the review modal");

  requests.length = 0;
  responseOk = false;
  responseStatus = 409;
  responseBody = { error: "Recognition changed; refresh before recording this decision" };
  modal.open = true;
  vm.runInContext(`state.samReview = ${JSON.stringify(initialReview)}; state.samReviewSelection = ${JSON.stringify(correctionReference)}; state.samCorrectionError = '';`, context);
  element("#sam-correction-reason").value = "OPERATOR_IDENTIFICATION_CORRECTION";
  element("#sam-correction-notes").value = "Retry after stale revision.";
  await vm.runInContext("decideSam('SAM-JOB-00000000-0000-0000-0000-000000000001', 'CORRECT', 1, 35)", context);

  assert.strictEqual(requests.length, 1, "rejected correction must still submit only once");
  assert.strictEqual(vm.runInContext("state.samReviewSelection.card_number", context), "OP16-035", "selection must survive failure");
  assert.strictEqual(modal.open, true, "failed correction must preserve the review modal");
  assert.strictEqual(element("#sam-correction-error").hidden, false);
  assert(element("#sam-correction-error").textContent.includes("Recognition changed"));
  assert(element("#toast").textContent.includes("Correction not saved"));
  assert(!source.includes("prompt(\"Why is SAM's original suggestion wrong?"), "native prompt regression must not return");

  console.log("Phase 7 SAM correction success/failure frontend regression: PASS");
})().catch((error) => {
  console.error(error.stack);
  process.exit(1);
});
