const fs = require("fs");
const vm = require("vm");

const baseUrl = process.env.DEX_PHASE4_TEST_URL || "http://127.0.0.1:18084/";

class ElementStub {
  constructor() {
    this.innerHTML = "";
    this.textContent = "";
    this.className = "";
    this.dataset = {};
    this.style = {};
    this.value = "";
    this.classList = { add() {}, remove() {}, toggle() {} };
  }
  addEventListener() {}
  querySelector() { return null; }
  querySelectorAll() { return []; }
}

const elements = new Map();
const getElement = (selector) => {
  if (!elements.has(selector)) elements.set(selector, new ElementStub());
  return elements.get(selector);
};
const document = {
  querySelector: getElement,
  querySelectorAll: () => [],
  addEventListener() {},
  body: new ElementStub(),
};
const realFetch = global.fetch;
const context = {
  console,
  document,
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
  confirm: () => true,
  fetch: (path, options) => realFetch(new URL(path, baseUrl), options),
  history: { replaceState() {} },
  location: { hash: "", reload() {} },
  navigator: { clipboard: { writeText: async () => {} } },
};
context.window = { addEventListener() {}, lucide: null, location: context.location };
context.globalThis = context;
vm.createContext(context);

const source = fs.readFileSync("static/app.js", "utf8").replace(/\nboot\(\);\s*$/, "\n");
if (!source.includes("function ripSessionsPanel")) {
  throw new Error("Phase 4 rip-session renderer is missing");
}
vm.runInContext(source, context);

(async () => {
  await vm.runInContext("renderBatch(1)", context);
  const html = getElement("#app").innerHTML;
  for (const expected of [
    "Batch Economics",
    "Phase 3 Acquisition Facts",
    "Rip Sessions & Cost Allocation",
    "New rip session",
    "Reconciliation / Warnings",
  ]) {
    if (!html.includes(expected)) throw new Error(`Authoritative Phase 4/6 batch detail is missing ${expected}`);
  }
  if (html.includes("Dex hit a snag")) throw new Error("Seeded batch detail entered the error view");
  console.log("Phase 4/6 authoritative batch-detail render contract: PASS");
})().catch((error) => {
  console.error(error.stack);
  process.exit(1);
});
