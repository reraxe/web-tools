const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

class ElementStub {
  constructor(key = "", rect = { top: 0, bottom: 0 }) {
    this.dataset = { viewportKey: key };
    this.rect = rect;
    this.innerHTML = "";
    this.textContent = "";
    this.className = "";
    this.style = {};
    this.value = "";
    this.classList = { add() {}, remove() {}, toggle() {} };
  }
  addEventListener() {}
  getBoundingClientRect() { return this.rect; }
  querySelector() { return null; }
  querySelectorAll(selector) { return selector === "[data-viewport-key]" ? anchors : []; }
}

let anchors = [
  new ElementStub("rip-sessions", { top: -180, bottom: 780 }),
  new ElementStub("card-OP16-001", { top: 140, bottom: 360 }),
  new ElementStub("batch-cards", { top: 600, bottom: 1500 }),
];
const app = new ElementStub();
const topbar = new ElementStub("", { top: 0, bottom: 68 });
const generic = new ElementStub();
const document = {
  activeElement: null,
  querySelector(selector) {
    if (selector === "#app") return app;
    if (selector === ".topbar") return topbar;
    return generic;
  },
  querySelectorAll() { return []; },
  addEventListener() {},
  body: new ElementStub(),
};
const scrollCalls = [];
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
  requestAnimationFrame: (callback) => callback(),
  confirm: () => true,
  fetch: async () => ({ ok: true, json: async () => ({}) }),
  history: { replaceState() {} },
  location: { hash: "", reload() {} },
  navigator: { clipboard: { writeText: async () => {} } },
};
context.window = {
  addEventListener() {},
  lucide: null,
  location: context.location,
  innerHeight: 900,
  scrollY: 740,
  scrollBy(options) { scrollCalls.push(["by", options]); },
  scrollTo(options) { scrollCalls.push(["to", options]); },
};
context.globalThis = context;
vm.createContext(context);

const source = fs.readFileSync("static/app.js", "utf8").replace(/\nboot\(\);\s*$/, "\n");
vm.runInContext(source, context);

const snapshot = vm.runInContext("captureLogicalViewport()", context);
assert.strictEqual(snapshot.key, "card-OP16-001");
assert.strictEqual(snapshot.offset, 72);
assert.strictEqual(snapshot.scrollY, 740);

document.activeElement = { closest: () => anchors[2] };
const focusedSnapshot = vm.runInContext("captureLogicalViewport()", context);
assert.strictEqual(focusedSnapshot.key, "batch-cards");
document.activeElement = null;

anchors = [
  new ElementStub("rip-sessions", { top: -180, bottom: 1030 }),
  new ElementStub("card-OP16-001", { top: 1130, bottom: 1350 }),
  new ElementStub("batch-cards", { top: 850, bottom: 1750 }),
];
context.viewportSnapshot = snapshot;
vm.runInContext("restoreLogicalViewport(viewportSnapshot)", context);
assert.strictEqual(scrollCalls.length, 2);
for (const anchoredRestore of scrollCalls) {
  assert.strictEqual(anchoredRestore[0], "by");
  assert.strictEqual(anchoredRestore[1].top, 990);
  assert.strictEqual(anchoredRestore[1].left, 0);
  assert.strictEqual(anchoredRestore[1].behavior, "auto");
}
scrollCalls.length = 0;

anchors = [];
vm.runInContext("restoreLogicalViewport(viewportSnapshot)", context);
assert.strictEqual(scrollCalls.length, 2);
for (const fallbackRestore of scrollCalls) {
  assert.strictEqual(fallbackRestore[0], "to");
  assert.strictEqual(fallbackRestore[1].top, 740);
  assert.strictEqual(fallbackRestore[1].left, 0);
  assert.strictEqual(fallbackRestore[1].behavior, "auto");
}

console.log("Phase 4 logical viewport preservation: PASS");
