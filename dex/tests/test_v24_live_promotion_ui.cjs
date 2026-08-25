const assert = require("assert");
const fs = require("fs");

const html = fs.readFileSync("static/index.html", "utf8");
const css = fs.readFileSync("static/styles.css", "utf8");
const app = fs.readFileSync("app.py", "utf8");
const dockerfile = fs.readFileSync("Dockerfile", "utf8");

assert(html.includes('class="environment-badge">LIVE</strong>'));
assert(html.includes('data-runtime-version>Checking version'));
assert(html.includes('/styles.css?v=v2.4-live'));
assert(html.includes('/app.js?v=v2.4-live'));
assert(css.includes('.server-state .environment-badge'));
assert(app.includes('APP_VERSION = "v2.4-live"'));
assert(dockerfile.includes('org.opencontainers.image.version="v2.4-live"'));

console.log("v2.4-live release identity frontend contract: PASS");
