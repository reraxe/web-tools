const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("C:/Users/nusty/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright");

const root = path.resolve(__dirname, "..");
const python = "C:/Users/nusty/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe";
const previewData = path.join(root, "work", "preview-data");
fs.rmSync(previewData, { recursive: true, force: true });
fs.mkdirSync(path.join(root, "outputs"), { recursive: true });

const server = spawn(python, ["app.py"], {
  cwd: root,
  env: { ...process.env, DEX_PORT: "8091", DEX_DATA_DIR: previewData, DEX_SEED_DEMO: "1", DEX_WATCH_INBOUND: "0" },
  stdio: "ignore",
});

async function waitForServer() {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      const response = await fetch("http://127.0.0.1:8091/api/health");
      if (response.ok) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error("Dex preview server did not start");
}

(async () => {
  try {
    await waitForServer();
    const browser = await chromium.launch({
      headless: true,
      executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
    });
    const desktop = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
    const consoleErrors = [];
    desktop.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
    await desktop.goto("http://127.0.0.1:8091", { waitUntil: "networkidle" });
    await desktop.locator("tr[data-expand]").first().click();
    await desktop.locator(".copy-row").first().waitFor({ state: "visible" });
    await desktop.screenshot({ path: path.join(root, "outputs", "dex-desktop.png"), fullPage: true });
    await desktop.locator('[data-view="inbound"]').click();
    await desktop.locator('[data-action="open-batch"]').first().click();
    await desktop.locator("#scan-card-form").waitFor({ state: "visible" });
    await desktop.screenshot({ path: path.join(root, "outputs", "dex-inbound.png"), fullPage: true });
    await desktop.locator('[data-view="labels"]').click();
    await desktop.locator(".thermal-label").first().waitFor({ state: "visible" });
    await desktop.screenshot({ path: path.join(root, "outputs", "dex-labels.png"), fullPage: true });

    const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
    mobile.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
    await mobile.goto("http://127.0.0.1:8091/#outbound", { waitUntil: "networkidle" });
    await mobile.screenshot({ path: path.join(root, "outputs", "dex-mobile.png"), fullPage: true });
    await browser.close();
    if (consoleErrors.length) throw new Error(`Browser console errors: ${consoleErrors.join(" | ")}`);
    console.log("Desktop and mobile screenshots rendered without browser console errors.");
  } finally {
    server.kill();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
