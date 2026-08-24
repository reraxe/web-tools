const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

class ElementStub {
  constructor() {
    this.innerHTML = ""; this.textContent = ""; this.className = ""; this.dataset = {}; this.style = {};
    this.value = ""; this.files = []; this.open = false; this.complete = true; this.type = ""; this.clicked = 0;
    this.listeners = new Map();
    this.classList = { add() {}, remove() {}, toggle() {}, contains() { return false; } };
  }
  addEventListener(type, handler) { if (!this.listeners.has(type)) this.listeners.set(type, []); this.listeners.get(type).push(handler); }
  async dispatch(type, event = {}) { for (const handler of this.listeners.get(type) || []) await handler({ target: this, currentTarget: this, preventDefault() {}, stopPropagation() {}, ...event }); }
  click() { this.clicked += 1; }
  closest(selector) { return selector === "[data-action]" && this.dataset.action ? this : null; }
  focus() {} querySelector() { return null; } querySelectorAll() { return []; }
  getBoundingClientRect() { return { top: 100, bottom: 150 }; } showModal() { this.open = true; } close() { this.open = false; }
}

const elements = new Map();
const globalListeners = new Map();
const document = {
  activeElement: null,
  body: new ElementStub(),
  querySelector(selector) { if (!elements.has(selector)) elements.set(selector, new ElementStub()); return elements.get(selector); },
  querySelectorAll() { return []; },
  addEventListener(type, handler) { globalListeners.set(type, handler); },
};

class FileReaderStub {
  readAsDataURL(file) {
    this.result = `data:${file.type};base64,${Buffer.from(file.name).toString("base64")}`;
    if (this.onload) this.onload();
  }
}

const requests = [];
const createdFiles = new Set();
let revision = 1;
let extractionCount = 0;
let tombstoneCount = 0;
const opened = [];
const notices = [];
const activePayload = () => ({
  acquisition: { id: 71, acquisition_code: "ACQ-UPLOAD-UX", revision, state: "ACQUISITION_INCOMPLETE", wizard_step: "ACQUIRE" },
  lines: [],
  source_documents: { active_count: createdFiles.size, failed_count: 0, documents: [] },
  receipt_intelligence: { jobs: [], warnings: [] },
});

const fetchStub = async (path, options = {}) => {
  const body = options.body ? JSON.parse(options.body) : {};
  requests.push({ path, method: options.method || "GET", body });
  let response;
  if (path === "/api/acquisitions/71/documents") {
    const duplicate = createdFiles.has(body.original_filename);
    if (!duplicate) createdFiles.add(body.original_filename);
    revision += 1;
    response = {
      upload_failed: false,
      duplicate,
      document: duplicate ? null : { id: 91 + createdFiles.size, storage_status: "STORED", document_role: "RECEIPT" },
      acquisition_payload: activePayload(),
    };
  } else if (/\/api\/acquisition-documents\/\d+\/extractions$/.test(path)) {
    extractionCount += 1; revision += 1;
    response = { acquisition_payload: activePayload() };
  } else if (path === "/api/acquisitions/71") {
    revision += 1; response = activePayload();
  } else if (path === "/api/acquisition-documents/91/tombstone") {
    tombstoneCount += 1; revision += 1;
    response = { acquisition_payload: activePayload() };
  } else {
    throw new Error(`Unexpected request ${path}`);
  }
  return { ok: true, status: 200, json: async () => response };
};

const context = {
  console, document, Intl, Date, Set, Map, URL, URLSearchParams, Blob, FileReader: FileReaderStub,
  setTimeout, clearTimeout, requestAnimationFrame: (callback) => callback(), confirm: () => true,
  fetch: fetchStub, history: { replaceState() {} }, location: { hash: "#inbound", reload() {} },
  navigator: { clipboard: { writeText: async () => {} } }, crypto: { randomUUID: (() => { let id = 0; return () => `ux-${++id}`; })() },
};
context.window = {
  addEventListener() {}, lucide: null, location: context.location, innerHeight: 900, scrollY: 0,
  scrollBy() {}, scrollTo() {}, open(...args) { opened.push(args); },
};
context.globalThis = context;
vm.createContext(context);
const source = fs.readFileSync("static/app.js", "utf8").replace(/\nboot\(\);\s*$/, "\n");
const styles = fs.readFileSync("static/styles.css", "utf8");
vm.runInContext(source, context);
vm.runInContext(`state.activeAcquisition = ${JSON.stringify(activePayload())}; renderAcquisitionWizard = async () => {}; toast = (message, type = "success") => globalThis.__notices.push({ message, type });`, context);
context.__notices = notices;

;(async () => {
const panel = vm.runInContext("sourceDocumentPanel()", context);
assert.strictEqual((panel.match(/type="file"/g) || []).length, 3);
assert.strictEqual((panel.match(/type="file"[^>]*hidden/g) || []).length, 3);
assert(!panel.includes("visually-hidden"));
assert(panel.includes('<button type="button" class="button secondary" data-action="upload-source-document" aria-controls="source-document-files">'));
assert(panel.includes('<button type="button" class="button secondary" data-action="take-source-photo" aria-controls="source-document-camera">'));
assert(panel.includes('.jpg,.jpeg,.png,.heic,.heif,.pdf'));
assert(panel.includes('image/jpeg,image/png,image/heic,image/heif,application/pdf'));
assert(styles.includes(".source-document-implementation-input[hidden] { display: none !important; }"));

vm.runInContext("bindAcquisitionWizardForms()", context);
const uploadInput = elements.get("#source-document-files");
const cameraInput = elements.get("#source-document-camera");
const clickHandler = globalListeners.get("click");
assert(clickHandler, "Global operator action handler was not registered");

const uploadButton = new ElementStub();
uploadButton.dataset.action = "upload-source-document";
uploadInput.value = "stale-file.pdf";
await clickHandler({ target: uploadButton, stopPropagation() {} });
assert.strictEqual(uploadInput.clicked, 1);
assert.strictEqual(uploadInput.value, "");

const receipt = { name: "receipt.pdf", type: "application/pdf" };
uploadInput.files = [receipt]; uploadInput.value = "receipt.pdf";
await uploadInput.dispatch("change");
assert.strictEqual(uploadInput.value, "");
assert.strictEqual(requests.filter((item) => item.path === "/api/acquisitions/71/documents").length, 1);
assert.strictEqual(createdFiles.size, 1);
assert.strictEqual(extractionCount, 1);
assert.strictEqual(requests.find((item) => item.path === "/api/acquisitions/71/documents").body.capture_method, "PDF_UPLOAD");

const requestsBeforeCancel = requests.length;
uploadInput.files = []; uploadInput.value = "";
await uploadInput.dispatch("change");
assert.strictEqual(requests.length, requestsBeforeCancel);
assert.strictEqual(notices.filter((item) => item.type === "error").length, 0);

await clickHandler({ target: uploadButton, stopPropagation() {} });
assert.strictEqual(uploadInput.clicked, 2);
uploadInput.files = [receipt]; uploadInput.value = "receipt.pdf";
await uploadInput.dispatch("change");
assert.strictEqual(createdFiles.size, 1, "Repeated selection must not create a duplicate attachment");
assert.strictEqual(extractionCount, 1, "Duplicate attachment must not start duplicate extraction");
assert.strictEqual(uploadInput.value, "");

const cameraButton = new ElementStub();
cameraButton.dataset.action = "take-source-photo";
await clickHandler({ target: cameraButton, stopPropagation() {} });
assert.strictEqual(cameraInput.clicked, 1);
const photo = { name: "camera.jpg", type: "image/jpeg" };
cameraInput.files = [photo]; cameraInput.value = "camera.jpg";
await cameraInput.dispatch("change");
const cameraRequest = requests.filter((item) => item.path === "/api/acquisitions/71/documents").at(-1);
assert.strictEqual(cameraRequest.body.capture_method, "CAMERA");
assert.strictEqual(createdFiles.size, 2);
assert.strictEqual(extractionCount, 2);

const viewButton = new ElementStub();
viewButton.dataset.action = "view-source-document"; viewButton.dataset.id = "91";
await clickHandler({ target: viewButton, stopPropagation() {} });
assert.deepStrictEqual(opened[0], ["/api/acquisition-documents/91/content", "_blank", "noopener,noreferrer"]);

const removeButton = new ElementStub();
removeButton.dataset.action = "remove-source-document"; removeButton.dataset.id = "91";
await clickHandler({ target: removeButton, stopPropagation() {} });
assert.strictEqual(tombstoneCount, 1);

assert(source.includes('openSourceDocumentPicker("#source-document-files")'));
assert(source.includes('openSourceDocumentPicker("#source-document-camera")'));
assert(source.includes("handleSourceDocumentSelection(event, \"FILE_UPLOAD\")"));
assert(source.includes("handleSourceDocumentSelection(event, \"CAMERA\")"));
console.log("Remediation 3 Receipt / Source Documents upload UX: PASS");
})().catch((error) => {
  console.error(error.stack || error);
  process.exit(1);
});
