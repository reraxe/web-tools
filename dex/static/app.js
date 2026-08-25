const ONE_PIECE_SETS = [
  ["Main Booster", "OP01", "Romance Dawn"], ["Main Booster", "OP02", "Paramount War"],
  ["Main Booster", "OP03", "Pillars of Strength"], ["Main Booster", "OP04", "Kingdoms of Intrigue"],
  ["Main Booster", "OP05", "Awakening of the New Era"], ["Main Booster", "OP06", "Wings of the Captain"],
  ["Main Booster", "OP07", "500 Years in the Future"], ["Main Booster", "OP08", "Two Legends"],
  ["Main Booster", "OP09", "Emperors in the New World"], ["Main Booster", "OP10", "Royal Blood"],
  ["Main Booster", "OP11", "A Fist of Divine Speed"], ["Main Booster", "OP12", "Legacy of the Master"],
  ["Main Booster", "OP13", "Carrying on His Will"], ["Main Booster", "OP14", "The Azure Sea's Seven"],
  ["Main Booster", "OP15", "Adventure on Kami's Island"], ["Main Booster", "OP16", "The Time of Battle"],
  ["Extra Booster", "EB01", "Memorial Collection"], ["Extra Booster", "EB02", "Anime 25th Collection"],
  ["Extra Booster", "EB03", "One Piece Heroines Edition"], ["Extra Booster", "EB04", "Extra Booster 04"],
  ["Extra Booster", "EB05", "Extra Booster 05"], ["Premium Booster", "PRB01", "Premium Booster -The Best-"],
  ["Premium Booster", "PRB02", "ONE PIECE CARD THE BEST Vol. 2"],
];

const CARD_COLORS = [
  "RED", "GREEN", "BLUE", "PURPLE", "BLACK", "YELLOW",
  "RED/GREEN", "RED/BLUE", "RED/PURPLE", "RED/BLACK", "RED/YELLOW",
  "GREEN/BLUE", "GREEN/PURPLE", "GREEN/BLACK", "GREEN/YELLOW",
  "BLUE/PURPLE", "BLUE/BLACK", "BLUE/YELLOW",
  "PURPLE/BLACK", "PURPLE/YELLOW", "BLACK/YELLOW",
  "MULTI", "MIXED", "COLORLESS",
];

const state = {
  view: "inventory",
  dashboard: null,
  inventory: [],
  batches: [],
  activeBatch: null,
  labels: [],
  selectedLabels: new Set(),
  outboundCards: [],
  outboundMode: "CARD",
  sealedInventory: null,
  sealedSalePreview: null,
  samSource: null,
  samReview: null,
  samReviewEconomics: null,
  samReviewSelection: null,
  samReferenceResults: [],
  samCorrectionDraft: { reason_code: "OPERATOR_IDENTIFICATION_CORRECTION", notes: "" },
  samCorrectionError: "",
  samDecisionPending: false,
  samAuditedResult: null,
  samAuditedSelection: null,
  samAuditedCatalogResults: [],
  samAuditedPending: false,
  cameraStream: null,
  intakeDefaults: { rarity: "", variant: "Standard" },
  pendingBulkFiles: [],
  selectedBatchCards: new Set(),
  inventoryPreset: null,
  pendingRipFinalization: null,
  acquisitions: [],
  activeAcquisition: null,
  acquisitionContract: null,
  acquisitionMutation: Promise.resolve(),
  upcScanStatus: null,
  pendingUnknownProduct: null,
  catalogSearchResults: [],
  catalogSearchQueries: { manual: "", unknown: "" },
  upcScanPending: false,
  disclosureStates: new Map(),
  acquisitionWorkingForms: new Map(),
  intakeRoutingPreview: null,
  jarvisEconomics: null,
};

const BULK_IMPORT_CHUNK_SIZE = 8;

const app = document.querySelector("#app");
const modal = document.querySelector("#modal");
const moneyFormat = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const dateFormat = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" });

const titles = {
  inventory: ["Inventory", "Every physical card, accounted for."],
  inbound: ["Inbound", "From scanner to labeled inventory."],
  sam: ["SAM", "Source database and assisted matches."],
  labels: ["Labels", "Print queued 2 × 1 sleeve labels."],
  outbound: ["Outbound", "Scan sold cards into an order."],
  sales: ["Sales", "Order history and net proceeds."],
  economics: ["Operational Economics", "Finalized acquisition, recovery, inventory value, and operational position."],
  recycle: ["Recycle Bin", "Restore removed cards or manage eligible permanent deletion."],
};

function icon(name, className = "") {
  return `<i data-lucide="${name}" class="${className}"></i>`;
}

function refreshIcons() {
  bindDisclosureState();
  if (window.lucide) window.lucide.createIcons({ attrs: { "stroke-width": 1.8 } });
}

function disclosureStateKey(details) {
  if (details.dataset.disclosureKey) return details.dataset.disclosureKey;
  const acquisitionId = state.activeAcquisition?.acquisition?.id || "none";
  const batchId = state.activeBatch?.batch?.id || "none";
  const viewport = details.closest?.("[data-viewport-key]")?.dataset?.viewportKey || "page";
  const classKey = String(details.className || "details").trim().replace(/\s+/g, ".");
  const summary = String(details.querySelector?.("summary")?.textContent || "section")
    .trim().replace(/\s+/g, " ").replace(/[$€£¥]?\d[\d,.%]*/g, "#").slice(0, 80);
  return `${state.view}:${acquisitionId}:${batchId}:${viewport}:${classKey}:${summary}`;
}

function bindDisclosureState(root = document) {
  Array.from(root.querySelectorAll?.("details") || []).forEach((details) => {
    const key = disclosureStateKey(details);
    const forceOpen = details.dataset.disclosureForceOpen === "true";
    if (forceOpen) details.open = true;
    else if (state.disclosureStates.has(key)) details.open = state.disclosureStates.get(key);
    if (details.dataset.disclosureStateBound === "true") return;
    details.dataset.disclosureStateBound = "true";
    details.addEventListener("toggle", () => {
      if (details.dataset.disclosureForceOpen === "true" && !details.open) {
        details.open = true;
        return;
      }
      state.disclosureStates.set(key, Boolean(details.open));
    });
  });
}

function acquisitionWorkingFieldKey(field) {
  const form = field.closest?.("form");
  if (!form || !field.name) return "";
  if (form.id === "acquisition-exception-form") return `exception:${field.name}`;
  if (form.classList?.contains?.("acquisition-allocation-form")) return `allocation:${form.dataset.lineId}:${field.name}`;
  return "";
}

function rememberAcquisitionWorkingState(root = document) {
  const acquisitionId = state.activeAcquisition?.acquisition?.id;
  if (!acquisitionId) return null;
  const prior = state.acquisitionWorkingForms.get(acquisitionId) || { fields: new Map(), focusKey: "" };
  Array.from(root.querySelectorAll?.("#acquisition-exception-form [name], .acquisition-allocation-form [name]") || []).forEach((field) => {
    const key = acquisitionWorkingFieldKey(field);
    if (!key) return;
    prior.fields.set(key, {
      value: field.value,
      checked: Boolean(field.checked),
      checkable: field.type === "checkbox" || field.type === "radio",
    });
  });
  const activeKey = acquisitionWorkingFieldKey(document.activeElement);
  if (activeKey) prior.focusKey = activeKey;
  state.acquisitionWorkingForms.set(acquisitionId, prior);
  return prior;
}

function clearAcquisitionWorkingLine(acquisitionId, lineId) {
  const working = state.acquisitionWorkingForms.get(acquisitionId);
  if (!working) return;
  const prefix = `allocation:${lineId}:`;
  [...working.fields.keys()].forEach((key) => { if (key.startsWith(prefix)) working.fields.delete(key); });
  if (working.focusKey?.startsWith(prefix)) working.focusKey = "";
}

function restoreAcquisitionWorkingState(root = document) {
  const acquisitionId = state.activeAcquisition?.acquisition?.id;
  const working = state.acquisitionWorkingForms.get(acquisitionId);
  if (!working) return;
  Array.from(root.querySelectorAll?.("#acquisition-exception-form [name], .acquisition-allocation-form [name]") || []).forEach((field) => {
    const saved = working.fields.get(acquisitionWorkingFieldKey(field));
    if (!saved || field.disabled) return;
    if (saved.checkable) field.checked = saved.checked;
    else field.value = saved.value;
  });
  if (working.focusKey) requestAnimationFrame(() => {
    const target = Array.from(root.querySelectorAll?.("#acquisition-exception-form [name], .acquisition-allocation-form [name]") || [])
      .find((field) => acquisitionWorkingFieldKey(field) === working.focusKey && !field.disabled);
    target?.focus?.({ preventScroll: true });
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatMoney(value, fallback = "—") {
  return value === null || value === undefined || value === "" ? fallback : moneyFormat.format(Number(value));
}

function formatCents(value, fallback = "Unknown") {
  return value === null || value === undefined ? fallback : moneyFormat.format(Number(value) / 100);
}

function jarvisCoveredCents(value, coveredCount, totalCount, fallback = "Unknown") {
  if (Number(totalCount || 0) > 0 && Number(coveredCount || 0) === 0) return fallback;
  return formatCents(value, fallback);
}

function jarvisStatusBadge(status) {
  const value = String(status || "UNRESOLVED").toUpperCase();
  const color = value === "COMPLETE" ? "green" : value === "ESTIMATED" ? "blue" : value === "PARTIAL" ? "amber" : "coral";
  return `<span class="badge ${color}">${escapeHtml(titleCase(value))}</span>`;
}

function jarvisFact(label, fact, options = {}) {
  const stateName = String(fact?.state || "UNRESOLVED").toUpperCase();
  const value = fact?.value_cents == null ? "Unknown" : formatCents(fact.value_cents);
  const explanation = fact?.reason ? titleCase(fact.reason) : stateName === "ESTIMATED" ? "Estimate only" : "";
  return `<div class="jarvis-fact ${stateName.toLowerCase()}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(titleCase(stateName))}${explanation ? ` · ${escapeHtml(explanation)}` : ""}${fact?.freshness?.label ? ` · ${escapeHtml(fact.freshness.label)}` : fact?.observed_at ? ` · ${escapeHtml(formatDate(fact.observed_at))}` : ""}</small></div>`;
}

function jarvisRoi(label, value) {
  const text = value?.percent == null ? "Unknown" : `${Number(value.percent).toFixed(2)}%`;
  return `<div class="jarvis-fact ${String(value?.state || "UNRESOLVED").toLowerCase()}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(text)}</strong><small>${escapeHtml(titleCase(value?.reason || value?.state || "UNRESOLVED"))}</small></div>`;
}

function jarvisProvenance(label, facts) {
  const rows = Object.entries(facts || {}).filter(([, fact]) => fact && fact.source_record).map(([name, fact]) => `<div><dt>${escapeHtml(titleCase(name))}</dt><dd><strong>${escapeHtml(fact.source_record)}</strong><span>${escapeHtml(fact.source_field || "Source field unavailable")}</span><small>${fact.observed_at ? `Observed ${escapeHtml(formatDate(fact.observed_at))}` : "Observation time not recorded"} · ${escapeHtml(titleCase(fact.state || "UNRESOLVED"))}</small></dd></div>`).join("");
  return rows ? `<details class="jarvis-provenance"><summary>${escapeHtml(label)}</summary><dl>${rows}</dl></details>` : "";
}

function jarvisInventorySummary(report) {
  if (!report) return "";
  const inventory = report.remaining_inventory || {};
  const realized = report.realized || {};
  const warnings = (report.warnings || []).map((warning) => `<li>${escapeHtml(warning)}</li>`).join("");
  return `<section class="jarvis-economics-panel compact" aria-labelledby="jarvis-inventory-title"><header><div><span title="Working On Levelling Financial Flows">WOLFF simplified economics</span><h2 id="jarvis-inventory-title">Known facts, visibly bounded</h2></div>${jarvisStatusBadge(report.economics_status)}</header><div class="jarvis-summary-grid"><div><span>Known remaining basis</span><strong>${jarvisCoveredCents(inventory.total_remaining_cost_basis_cents, inventory.authoritative_basis_count, inventory.item_count)}</strong><small>${escapeHtml(inventory.coverage_label || "Coverage unknown")}</small></div><div><span>Known market reference value</span><strong>${formatCents(inventory.total_current_inventory_value_cents)}</strong><small>${inventory.market_valued_count || 0}/${inventory.item_count || 0} items valued · ${escapeHtml(inventory.valuation_freshness?.label || "Freshness Unknown")}</small></div><div><span>Known unrealized difference</span><strong>${formatCents(inventory.total_unrealized_gain_loss_cents)}</strong><small>Only paired authoritative basis and market facts</small></div><div><span>Known realized P/L</span><strong>${formatCents(realized.total_realized_profit_loss_cents)}</strong><small>${escapeHtml(realized.coverage_label || "Coverage unknown")}</small></div></div>${warnings ? `<ul class="jarvis-warnings">${warnings}</ul>` : ""}<footer>Calculation ${escapeHtml(report.calculation_version)} · calculated from source facts; totals are not stored.</footer></section>`;
}

function jarvisCardPanel(report) {
  if (!report) return "";
  const warnings = (report.warnings || []).map((warning) => `<li>${escapeHtml(titleCase(warning))}</li>`).join("");
  const sold = report.sale ? `<div class="jarvis-related-sale"><h4>Realized sale economics</h4><div class="jarvis-fact-grid">${jarvisFact("Gross sale proceeds", report.sale.gross_sale_proceeds)}${jarvisFact("Net proceeds", report.sale.net_proceeds)}${jarvisFact("Realized profit / loss", report.sale.realized_profit_loss)}${jarvisRoi("Realized ROI", report.sale.realized_roi)}</div></div>` : "";
  const provenance = jarvisProvenance("Economics provenance", {
    acquisition_cost: report.acquisition_cost,
    allocated_basis: report.allocated_acquisition_cost,
    market_value: report.current_market_reference_value,
    sale_proceeds: report.sale?.gross_sale_proceeds,
    sold_basis: report.sale?.cost_basis_of_goods_sold,
  });
  return `<section class="jarvis-economics-panel" aria-labelledby="jarvis-card-title"><header><div><span title="Working On Levelling Financial Flows">WOLFF simplified economics</span><h3 id="jarvis-card-title">Item economics</h3></div>${jarvisStatusBadge(report.economics_status)}</header><div class="jarvis-fact-grid">${jarvisFact("Parent acquisition cost", report.acquisition_cost)}${jarvisFact("Allocated acquisition cost", report.allocated_acquisition_cost)}${jarvisFact("Current market reference", report.current_market_reference_value)}${jarvisFact("Current inventory value", report.current_inventory_value)}${jarvisFact("Unrealized gain / loss", report.unrealized_gain_loss)}${jarvisRoi("Unrealized ROI", report.unrealized_roi)}</div>${sold}${warnings ? `<ul class="jarvis-warnings">${warnings}</ul>` : ""}${provenance}<footer>Unknown inputs stay Unknown. Estimated basis is excluded from authoritative totals. Calculation ${escapeHtml(report.calculation_version)}.</footer></section>`;
}

function jarvisSalePanel(report) {
  if (!report) return "";
  const warnings = (report.warnings || []).map((warning) => `<li>${escapeHtml(titleCase(warning))}</li>`).join("");
  const provenance = jarvisProvenance("Sale economics provenance", {
    merchandise: report.gross_merchandise_proceeds,
    shipping_collected: report.shipping_charged_to_buyer,
    marketplace_fees: report.marketplace_fees,
    actual_postage: report.actual_shipping_cost,
    sold_basis: report.cost_basis_of_goods_sold,
  });
  return `<section class="jarvis-economics-panel" aria-labelledby="jarvis-sale-title"><header><div><span title="Working On Levelling Financial Flows">WOLFF simplified economics</span><h3 id="jarvis-sale-title">Sale economics</h3></div>${jarvisStatusBadge(report.economics_status)}</header><div class="jarvis-fact-grid">${jarvisFact("Merchandise proceeds", report.gross_merchandise_proceeds)}${jarvisFact("Shipping charged to buyer", report.shipping_charged_to_buyer)}${jarvisFact("Gross sale proceeds", report.gross_sale_proceeds)}${jarvisFact("Marketplace fees", report.marketplace_fees)}${jarvisFact("Actual shipping cost", report.actual_shipping_cost)}${jarvisFact("Cost basis of goods sold", report.cost_basis_of_goods_sold)}${jarvisFact("Net proceeds", report.net_proceeds)}${jarvisFact("Realized profit / loss", report.realized_profit_loss)}${jarvisRoi("Realized ROI", report.realized_roi)}</div>${warnings ? `<ul class="jarvis-warnings">${warnings}</ul>` : ""}${provenance}<footer>Payment fees, packaging, and other direct costs remain separately unresolved when not recorded. Calculation ${escapeHtml(report.calculation_version)}.</footer></section>`;
}

function formatPercent(value, fallback = "Unknown") {
  return value === null || value === undefined ? fallback : `${Number(value).toLocaleString("en-US", { maximumFractionDigits: 2 })}%`;
}

function centsInputValue(value) {
  return value === null || value === undefined ? "" : (Number(value) / 100).toFixed(2);
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value.length === 10 ? `${value}T12:00:00` : value);
  return Number.isNaN(date.getTime()) ? value : dateFormat.format(date);
}

function localDateValue() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function titleCase(value) {
  return String(value || "").toLowerCase().replace(/(^|\s|_)(\w)/g, (_, a, b) => `${a === "_" ? " " : a}${b.toUpperCase()}`);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(body.error || `Request failed (${response.status})`);
    error.status = response.status;
    error.details = body;
    throw error;
  }
  return body;
}

function toast(message, type = "success") {
  const el = document.querySelector("#toast");
  el.textContent = message;
  el.className = `toast show ${type === "error" ? "error" : ""}`;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { el.className = "toast"; }, 3200);
}

function loading() {
  app.innerHTML = `<div class="skeleton" aria-label="Loading"></div>`;
}

function captureLogicalViewport() {
  const scrollY = Number(window.scrollY || 0);
  const topbarBottom = document.querySelector(".topbar")?.getBoundingClientRect().bottom || 0;
  const viewportBottom = Number(window.innerHeight || 0);
  const anchors = [...app.querySelectorAll("[data-viewport-key]")]
    .map((element) => ({ element, rect: element.getBoundingClientRect() }))
    .filter(({ rect }) => rect.bottom > topbarBottom && (!viewportBottom || rect.top < viewportBottom))
    .sort((left, right) => Math.abs(left.rect.top - topbarBottom) - Math.abs(right.rect.top - topbarBottom));
  const focusedElement = document.activeElement?.closest?.("[data-viewport-key]");
  const anchor = anchors.find(({ element }) => element === focusedElement) || anchors[0];
  return {
    key: anchor?.element.dataset.viewportKey || "",
    offset: anchor ? anchor.rect.top - topbarBottom : 0,
    scrollY,
  };
}

function restoreLogicalViewport(snapshot) {
  if (!snapshot) return;
  const restore = () => {
    const topbarBottom = document.querySelector(".topbar")?.getBoundingClientRect().bottom || 0;
    const anchor = [...app.querySelectorAll("[data-viewport-key]")]
      .find((element) => element.dataset.viewportKey === snapshot.key);
    if (!anchor) {
      window.scrollTo({ top: snapshot.scrollY, left: 0, behavior: "auto" });
      return;
    }
    const currentOffset = anchor.getBoundingClientRect().top - topbarBottom;
    window.scrollBy({ top: currentOffset - snapshot.offset, left: 0, behavior: "auto" });
  };
  [...app.querySelectorAll("img")].forEach((image) => {
    if (image.complete) return;
    const settle = () => requestAnimationFrame(restore);
    image.addEventListener("load", settle, { once: true });
    image.addEventListener("error", settle, { once: true });
  });
  requestAnimationFrame(() => {
    restore();
    requestAnimationFrame(restore);
  });
}

function emptyState(iconName, heading, copy, action = "") {
  return `<div class="empty-state">
    <div class="empty-icon">${icon(iconName)}</div>
    <h3>${escapeHtml(heading)}</h3><p>${escapeHtml(copy)}</p>${action}
  </div>`;
}

function setView(view, options = {}) {
  state.view = view;
  const [title, subtitle] = titles[view];
  document.querySelector("#page-title").textContent = title;
  document.querySelector("#page-subtitle").textContent = subtitle;
  document.querySelectorAll(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  document.body.classList.remove("nav-open");
  history.replaceState(null, "", `#${view}`);
  stopCamera();
  if (view === "inventory") renderInventory();
  if (view === "inbound") renderInbound({ batchId: options.batchId, acquisitionId: options.acquisitionId, newAcquisition: options.newAcquisition });
  if (view === "sam") renderSAM();
  if (view === "labels") renderLabels();
  if (view === "outbound") renderOutbound();
  if (view === "sales") renderSales();
  if (view === "economics") renderOperationalEconomics();
  if (view === "recycle") renderRecycle();
}

async function loadDashboard() {
  state.dashboard = await api("/api/dashboard");
  const used = Number(state.dashboard.tcg_slots || 0);
  const capacity = Number(state.dashboard.tcg_capacity || 500);
  document.querySelector("#capacity-label").textContent = `${used} / ${capacity}`;
  document.querySelector("#capacity-bar").style.width = `${Math.min(100, (used / capacity) * 100)}%`;
  document.querySelector("#capacity-note").textContent = `${Math.max(0, capacity - used)} slots available`;
  document.querySelector("#nav-review-count").textContent = state.dashboard.needs_review || 0;
  document.querySelector("#nav-label-count").textContent = state.dashboard.labels_waiting || 0;
  document.querySelector("#nav-recycle-count").textContent = state.dashboard.recycle_total_count ?? state.dashboard.recycled_count ?? 0;
}

function summaryStrip() {
  const d = state.dashboard || {};
  return `<section class="summary-strip" aria-label="Inventory summary">
    <div class="metric"><span>In stock</span><strong>${d.in_stock || 0}</strong><small>${d.total_cards || 0} lifetime cards</small></div>
    <div class="metric"><span>Market value</span><strong>${formatMoney(d.market_value, "$0.00")}</strong><small>Based on average prices</small></div>
    <div class="metric"><span>Needs Review</span><strong>${d.needs_review || 0}</strong><small>Identification or details</small></div>
    <div class="metric"><span>eBay candidates</span><strong>${d.ebay_candidates || 0}</strong><small>Average price $20+</small></div>
  </section>`;
}

function inventoryToolbar() {
  return `<section class="toolbar" aria-label="Inventory filters">
    <div class="search-box">${icon("search")}<input id="inventory-search" type="search" placeholder="Search card, number, SKU, drawer, or order" autocomplete="off"></div>
    <select id="inventory-game" aria-label="Filter game"><option value="">All games</option><option>Pokemon</option><option>One Piece</option><option>Riftbound</option></select>
    <select id="inventory-status" aria-label="Filter Status"><option value="">All Statuses</option><option value="IN_STOCK">In Stock</option><option value="REVIEW">Needs Review</option><option value="SOLD">Sold</option><option value="HOLD">Hold</option></select>
    <select id="inventory-sort" aria-label="Sort inventory">
      <option value="average_desc">Average: high to low</option><option value="average_asc">Average: low to high</option>
      <option value="low_desc">Low: high to low</option><option value="high_desc">High: high to low</option>
      <option value="name_asc">Name: A to Z</option>
    </select>
    <button class="button secondary" data-action="undo-last">${icon("undo-2")}Undo</button>
    <button class="button secondary" data-action="open-settings">${icon("settings")}Settings</button>
    <button class="button secondary" data-action="export-csv">${icon("download")}Inventory CSV</button>
    <span class="filter-count" id="inventory-count"></span>
  </section>`;
}

function thumbFor(group) {
  const image = group.copies.find((card) => card.front_image)?.front_image;
  return image
    ? `<img class="card-thumb" src="/media/${encodeURI(image)}" alt="">`
    : `<span class="card-thumb placeholder">${icon("image")}</span>`;
}

function statusBadge(status) {
  const map = {
    IN_STOCK: ["In Stock", "green"], REVIEW: ["Needs Review", "amber"],
    SOLD: ["Sold", "neutral"], HOLD: ["Hold", "coral"],
  };
  const [label, color] = map[status] || [titleCase(status), "neutral"];
  return `<span class="badge ${color}">${label}</span>`;
}

function confidenceLabel(value) {
  const number = Number(value || 0);
  return number ? `${Math.round(number * 100)}%` : "";
}

function samBadge(card) {
  if (!card.match_confidence) return `<span class="sam-chip manual">Manual</span>`;
  const label = confidenceLabel(card.match_confidence);
  const strong = Number(card.match_confidence) >= 0.9;
  return `<span class="sam-chip ${strong ? "strong" : "soft"}">${escapeHtml(card.match_source || "SAM")} ${label}</span>`;
}

function batchIdentityKey(card) {
  const number = String(card.card_number || "").trim().toUpperCase();
  if (!number) return "";
  return [number, String(card.variant || "Standard").trim().toUpperCase()].join("|");
}

function batchIdentityCounts(cards) {
  return cards.reduce((counts, card) => {
    const key = batchIdentityKey(card);
    if (key) counts.set(key, (counts.get(key) || 0) + 1);
    return counts;
  }, new Map());
}

function batchCountBadge(card, counts) {
  const count = counts.get(batchIdentityKey(card)) || 0;
  return count > 1 ? `<span class="batch-count-badge" title="${count} copies of this identified card in this batch">x${count}</span>` : "";
}

function platformBadge(group) {
  const platforms = [...new Set(group.copies.map((card) => card.listing_platform).filter(Boolean))];
  if (!platforms.length) {
    if (group.market_average !== null && group.market_average !== undefined) {
      const suggested = Number(group.market_average) >= 20 ? "eBay suggested" : "TCG suggested";
      return `<span class="badge ${Number(group.market_average) >= 20 ? "blue" : "amber"}">${suggested}</span>`;
    }
    return `<span class="badge neutral">Unlisted</span>`;
  }
  return platforms.map((platform) => `<span class="badge ${platform === "eBay" ? "blue" : "green"}">${escapeHtml(platform)}</span>`).join(" ");
}

function inventoryTable(groups) {
  if (!groups.length) return emptyState("search-x", "No cards found", "Try a different search or create an inbound batch.", `<button class="button primary" data-action="new-batch">${icon("plus")}New batch</button>`);
  const rows = groups.map((group, index) => {
    const statuses = [...new Set(group.copies.map((copy) => copy.status))];
    const status = statuses.length === 1 ? statusBadge(statuses[0]) : `<span class="badge neutral">Mixed</span>`;
    const copies = group.copies.map((card) => `<div class="copy-row">
      <code>${escapeHtml(card.sku)}</code><span>${escapeHtml(card.location || "Unassigned")}</span>
      <span>${statusBadge(card.status)}</span><span>${escapeHtml(card.listing_platform || "Unlisted")}</span>
      <button class="icon-button" title="Edit card" data-action="edit-card" data-sku="${escapeHtml(card.sku)}">${icon("square-pen")}</button>
    </div>`).join("");
    return `<tr data-expand="${index}">
      <td><div class="card-primary">${thumbFor(group)}<div><strong>${escapeHtml(group.name)}</strong><small>${escapeHtml(group.card_number || "Identification pending")} · ${escapeHtml(group.variant)}</small></div></div></td>
      <td>${escapeHtml(group.set_code)}<br><small>${escapeHtml(group.rarity || "—")}</small></td>
      <td><span class="quantity">${group.quantity}</span></td>
      <td>${status}</td><td>${platformBadge(group)}</td>
      <td class="price-cell"><strong>${formatMoney(group.market_low)}</strong></td>
      <td class="price-cell"><strong>${formatMoney(group.market_average)}</strong><small>${group.market_updated_at ? formatDate(group.market_updated_at) : "No pricing"}</small></td>
      <td class="price-cell"><strong>${formatMoney(group.market_high)}</strong></td>
      <td>${icon("chevron-down")}</td>
    </tr><tr class="expanded-row" data-expanded-row="${index}" hidden><td colspan="9"><div class="copy-list">${copies}</div></td></tr>`;
  }).join("");
  return `<div class="table-wrap"><table>
    <thead><tr><th>Card</th><th>Set / rarity</th><th>Qty</th><th>Status</th><th>Listing</th><th>Low</th><th>Average</th><th>High</th><th></th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

async function renderInventory() {
  loading();
  try {
    const [, jarvis] = await Promise.all([
      loadDashboard(),
      api("/api/jarvis/economics/summary").catch(() => null),
    ]);
    state.jarvisEconomics = jarvis;
    app.innerHTML = `<div class="view-stack">${summaryStrip()}${jarvisInventorySummary(jarvis)}${inventoryToolbar()}<div id="inventory-results"><div class="skeleton"></div></div></div>`;
    refreshIcons();
    if (state.inventoryPreset) {
      const preset = state.inventoryPreset;
      document.querySelector("#inventory-search").value = preset.q || "";
      document.querySelector("#inventory-status").value = preset.status || "";
      document.querySelector("#inventory-game").value = preset.game || "";
      document.querySelector("#inventory-sort").value = preset.sort || "average_desc";
      state.inventoryPreset = null;
    }
    const update = debounce(loadInventory, 220);
    document.querySelector("#inventory-search").addEventListener("input", update);
    document.querySelectorAll("#inventory-game,#inventory-status,#inventory-sort").forEach((el) => el.addEventListener("change", loadInventory));
    await loadInventory();
  } catch (error) { showError(error); }
}

async function loadInventory() {
  const search = document.querySelector("#inventory-search")?.value || "";
  const game = document.querySelector("#inventory-game")?.value || "";
  const status = document.querySelector("#inventory-status")?.value || "";
  const sort = document.querySelector("#inventory-sort")?.value || "average_desc";
  const params = new URLSearchParams({ q: search, game, status, sort });
  const data = await api(`/api/inventory?${params}`);
  state.inventory = data.groups;
  document.querySelector("#inventory-results").innerHTML = inventoryTable(data.groups);
  document.querySelector("#inventory-count").textContent = `${data.groups.length} grouped cards`;
  refreshIcons();
}

function openModal(title, subtitle, body) {
  document.querySelector("#modal-title").textContent = title;
  document.querySelector("#modal-subtitle").textContent = subtitle || "";
  document.querySelector("#modal-body").innerHTML = body;
  modal.showModal();
  refreshIcons();
}

function closeModal() { if (modal.open) modal.close(); }

function setOptionsMarkup() {
  return ONE_PIECE_SETS.map(([group, code, name]) => `<option value="${code} - ${escapeHtml(name)}">${escapeHtml(group)}</option>`).join("");
}

function colorOptionsMarkup() {
  return CARD_COLORS.map((color) => `<option value="${escapeHtml(color)}"></option>`).join("");
}

function colorField(name, value = "", placeholder = "Search RED, BLUE, PURPLE, or MIXED") {
  return `<input name="${name}" list="tcg-color-options" value="${escapeHtml(value)}" placeholder="${escapeHtml(placeholder)}" autocomplete="off"><datalist id="tcg-color-options">${colorOptionsMarkup()}</datalist>`;
}

function parseSetChoice(value) {
  const text = String(value || "").trim();
  const match = text.match(/^([A-Z0-9]+)\s*[-:]\s*(.+)$/i);
  if (match) return { set_code: match[1].toUpperCase(), set_name: match[2].trim() };
  const codeOnly = text.match(/^([A-Z]{1,4}\d{1,3})$/i);
  if (codeOnly) return { set_code: codeOnly[1].toUpperCase(), set_name: codeOnly[1].toUpperCase() };
  return text ? { set_code: text.slice(0, 20).toUpperCase(), set_name: text } : null;
}

function normalizeColorChoice(value) {
  const text = String(value || "").trim();
  const known = CARD_COLORS.find((color) => color.toLowerCase() === text.toLowerCase());
  return known || text;
}

function newBatchForm() {
  return `<form id="new-batch-form">
    <div class="form-grid batch-form-grid">
      <label>Game<select name="game" required><option value="">Select game</option><option>Pokemon</option><option>One Piece</option><option>Riftbound</option></select></label>
      <label>Set<input name="set_choice" list="tcg-set-options" required placeholder="Search OP16, EB03, or Time of Battle" autocomplete="off"><datalist id="tcg-set-options">${setOptionsMarkup()}</datalist><span class="help-text">Use CODE - Set Name. You can type future sets directly.</span></label>
      <label>Color${colorField("color")}<span class="help-text">Pick a known color or type a custom drawer label.</span></label>
      <label>Scan group<select name="finish_group"><option>Common / Non-Foil</option><option>Rare / Foil</option><option>Rare / Non-Foil</option><option>Promo</option><option>Mixed</option></select></label>
      <label>Condition<select name="default_condition"><option>Near Mint</option><option>Lightly Played</option><option>Moderately Played</option><option>Heavily Played</option><option>Damaged</option></select></label>
      <label>Acquired as<select name="acquisition_type" required><option>Booster Box</option><option>Single Pack(s)</option><option>Purchased Singles</option><option>Trade</option><option>Existing Inventory</option></select></label>
      <label>Economics mode<select name="economics_mode"><option value="SEALED_RIP">Sealed product / rip</option><option value="SINGLES_KNOWN_COST">Purchased singles — known line costs</option><option value="SINGLES_LUMP_SUM">Purchased singles — lump-sum lot</option></select></label>
      <label>Product / lot name<input name="product_name" required placeholder="OP-16 Booster Box"></label>
      <label>Units acquired<input name="units_acquired" type="number" min="0" step="1" value="1"><span class="help-text">Use whole sealed units; singles modes use 0.</span></label>
      <label>Receipt / Acquisition Group<input name="receipt_group_reference" placeholder="RECEIPT-2026-001"></label>
      <label>Invoice / order reference<input name="invoice_reference" placeholder="Optional receipt or order number"></label>
      <label>Purchase subtotal<div class="money-input"><span>$</span><input name="purchase_subtotal" inputmode="decimal" type="number" min="0" step=".01"></div></label>
      <label>Tax<div class="money-input"><span>$</span><input name="acquisition_tax" inputmode="decimal" type="number" min="0" step=".01"></div></label>
      <label>Inbound shipping<div class="money-input"><span>$</span><input name="inbound_shipping" inputmode="decimal" type="number" min="0" step=".01"></div></label>
      <label>Acquisition fees<div class="money-input"><span>$</span><input name="acquisition_fees" inputmode="decimal" type="number" min="0" step=".01"></div></label>
      <label>Discounts / credits<div class="money-input"><span>$</span><input name="acquisition_discount" inputmode="decimal" type="number" min="0" step=".01"></div></label>
      <label>Final USD actually paid<div class="money-input"><span>$</span><input name="final_usd_paid" inputmode="decimal" type="number" min="0" step=".01"></div><span class="help-text">Authoritative for all future basis and P/L.</span></label>
      <label>Original currency<input name="original_currency" maxlength="3" placeholder="JPY"></label>
      <label>Original foreign amount<input name="original_foreign_amount" inputmode="decimal" type="number" min="0" step=".01" placeholder="Reference only"></label>
      <label class="full checkbox-label"><input name="cost_reconciliation_acknowledged" type="checkbox" value="1"><span>Acknowledge an intentional difference between components and final USD paid.</span></label>
      <label>Drawer location<input name="location" placeholder="Auto: OP16-Yellow"><span class="help-text">Leave blank to use set and color.</span></label>
      <label>Scanner Order<select name="scan_order"><option value="FRONT_FIRST">Front First (Face Down)</option><option value="BACK_FIRST">Back First (Face Up)</option></select></label>
      <label class="full">Notes<textarea name="notes" placeholder="Optional batch notes"></textarea></label>
    </div>
    <div class="form-actions"><button type="button" class="button secondary" data-action="close-modal">Cancel</button><button class="button primary">${icon("arrow-right")}Create batch</button></div>
  </form>`;
}

function openNewBatch() {
  openModal("New Inbound Batch", "One purchase batch can contain several organized scan groups.", newBatchForm());
  const form = document.querySelector("#new-batch-form");
  form.addEventListener("submit", createBatch);
}

async function createBatch(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = Object.fromEntries(form.entries());
  const parsedSet = parseSetChoice(payload.set_choice);
  if (!parsedSet) return toast("Enter a set, like OP16 - The Time of Battle.", "error");
  payload.set_code = parsedSet.set_code;
  payload.set_name = parsedSet.set_name;
  payload.color = normalizeColorChoice(payload.color);
  try {
    const batch = await api("/api/batches", { method: "POST", body: JSON.stringify(payload) });
    closeModal(); toast(`${batch.batch_code} is ready for scans.`);
    await loadDashboard(); setView("inbound", { batchId: batch.id });
  } catch (error) { toast(error.message, "error"); }
}

function batchRows(batches) {
  if (!batches.length) return emptyState("package-open", "No inbound batches yet", "Start with an existing-inventory batch or your next booster box.", `<button class="button primary" data-action="new-batch">${icon("plus")}New batch</button>`);
  return `<div class="batch-list">${batches.map((batch) => `<div class="batch-row">
    <div><strong>${escapeHtml(batch.batch_code)}</strong><small>${escapeHtml(batch.game)} · ${escapeHtml(batch.set_code)} · ${escapeHtml(batch.color || "Mixed color")}</small></div>
    <div><strong>${batch.card_count || 0} cards</strong><small>${batch.review_count || 0} need review</small></div>
    <div><strong>${escapeHtml(batch.acquisition_type)}</strong><small>${formatMoney(batch.total_cost)}</small></div>
    <div><span class="badge ${batch.status === "OPEN" ? "blue" : "green"}">${batch.status === "OPEN" ? "Open" : "Complete"}</span><small>${formatDate(batch.created_at)}</small></div>
    <div class="batch-actions"><button class="button secondary" data-action="open-batch" data-id="${batch.id}">${icon("arrow-right")}Open</button><button class="icon-button danger-icon" title="Move batch to Recycle Bin" data-action="open-recycle-batch" data-id="${batch.id}" data-code="${escapeHtml(batch.batch_code)}" data-count="${batch.card_count || 0}">${icon("trash-2")}</button></div>
  </div>`).join("")}</div>`;
}

function acquisitionStateLabel(value) {
  if (value === "READY_FOR_INTAKE") return "Ready for Intake";
  if (value === "INTAKE_IN_PROGRESS") return "Intake in Progress";
  if (value === "INTAKE_COMPLETE") return "Intake Complete";
  if (value === "RECONCILIATION_REQUIRED") return "Setup incomplete — reconcile purchase";
  if (value === "ACQUISITION_INCOMPLETE") return "Setup incomplete";
  return titleCase(value);
}

function acquisitionRows(acquisitions) {
  if (!acquisitions.length) return emptyState(
    "clipboard-plus",
    "No acquisitions yet",
    "Start with what entered the business. You can save setup incomplete and resume later.",
    `<button class="button primary" data-action="new-acquisition">${icon("plus")}New Acquisition</button>`,
  );
  return `<div class="acquisition-list">${acquisitions.map((acquisition) => {
    const canceled = acquisition.state === "CANCELED";
    const confirmed = ["READY_FOR_INTAKE", "INTAKE_IN_PROGRESS", "INTAKE_COMPLETE"].includes(acquisition.state);
    const incomplete = !canceled && !confirmed;
    const cost = acquisition.final_usd_paid_cents === null || acquisition.final_usd_paid_cents === undefined
      ? "Unknown / Setup incomplete"
      : formatCents(acquisition.final_usd_paid_cents);
    const removal = acquisition.removal || {};
    const removalAction = removal.can_recycle_draft
      ? `<button class="icon-button danger-icon" title="Move acquisition to Recycle Bin" data-action="open-remove-acquisition" data-mode="recycle" data-id="${acquisition.id}">${icon("trash-2")}</button>`
      : removal.can_cancel_confirmed
        ? `<button class="button tertiary" data-action="open-remove-acquisition" data-mode="cancel" data-id="${acquisition.id}">${icon("ban")}Cancel</button>`
        : (removal.protected_history || removal.internal_economic_history) && !canceled
          ? `<button class="icon-button danger-icon" title="${escapeHtml(removal.blocked_message || "Protected history — use correction or reversal")}" disabled>${icon("lock-keyhole")}</button>`
          : "";
    return `<article class="acquisition-row ${canceled ? "canceled" : incomplete ? "incomplete" : "ready"}" data-viewport-key="acquisition-${acquisition.id}">
      <div><span class="eyebrow">${escapeHtml(acquisition.acquisition_code)}</span><strong>${escapeHtml(acquisition.merchant_name || "Merchant not entered")}</strong><small>${acquisition.active_line_count || 0} product line(s) · ${formatDate(acquisition.purchased_on || acquisition.created_at)}</small></div>
      <div><span>Authoritative landed cost</span><strong>${escapeHtml(cost)}</strong><small>${canceled ? "Preserved historical fact" : incomplete ? "Not finalized" : "Confirmed USD facts"}</small></div>
      <div><span class="badge ${canceled ? "gray" : incomplete ? "amber" : "green"}">${escapeHtml(acquisitionStateLabel(acquisition.state))}</span><small>${canceled ? "Canceled · history retained" : incomplete ? `Resume at ${titleCase(acquisition.wizard_step || "ACQUIRE")}` : acquisition.state === "READY_FOR_INTAKE" ? "Choose what happens next" : acquisition.state === "INTAKE_IN_PROGRESS" ? "Some quantity still undecided" : "All quantity routed"}</small></div>
      <div class="batch-actions"><button class="button ${incomplete || acquisition.state === "READY_FOR_INTAKE" || acquisition.state === "INTAKE_IN_PROGRESS" ? "primary" : "secondary"}" data-action="open-acquisition" data-id="${acquisition.id}">${icon(incomplete ? "play" : acquisition.state === "INTAKE_COMPLETE" ? "eye" : "route")}${incomplete ? "Resume" : acquisition.state === "INTAKE_COMPLETE" ? "View Inventory" : "Continue Intake"}</button>${removalAction}</div>
    </article>`;
  }).join("")}</div>`;
}

async function startNewAcquisition() {
  try {
    state.upcScanStatus = null;
    state.pendingUnknownProduct = null;
    state.catalogSearchResults = [];
    const result = await api("/api/acquisitions", {
      method: "POST",
      body: JSON.stringify({ request_id: requestId("ACQUISITION-CREATE") }),
    });
    state.activeAcquisition = result;
    await renderAcquisitionWizard(result.acquisition.id, { focusHeading: true });
  } catch (error) { showError(error); }
}

async function renderInbound(target = {}) {
  loading();
  try {
    if (typeof target === "number" || typeof target === "string") return renderBatch(Number(target));
    if (target.batchId) return renderBatch(Number(target.batchId));
    if (target.newAcquisition) return startNewAcquisition();
    if (target.acquisitionId) return renderAcquisitionWizard(Number(target.acquisitionId), { focusHeading: true });
    const [batchData, acquisitionData, contract] = await Promise.all([
      api("/api/batches"), api("/api/acquisitions"), api("/api/inbound/foundation"),
    ]);
    state.batches = batchData.batches;
    state.acquisitions = acquisitionData.acquisitions;
    state.acquisitionContract = contract;
    app.innerHTML = `<div class="view-stack inbound-home">
      <section class="section-header"><div><span class="eyebrow">Inbound 2.0</span><h2>Acquisitions</h2><p>Record what entered the business first. Inventory processing happens afterward.</p></div><button class="button primary" data-action="new-acquisition">${icon("plus")}New Acquisition</button></section>
      ${acquisitionRows(acquisitionData.acquisitions)}
      <details class="legacy-inbound"><summary>Advanced / Legacy batch workflow</summary><div class="legacy-inbound-body"><div class="section-header"><div><h3>Processing Batches</h3><p>Compatibility path for existing Phase 3–7C workflows.</p></div><button class="button secondary" data-action="new-batch">${icon("package-plus")}Legacy New Batch</button></div>${batchRows(batchData.batches)}</div></details>
    </div>`;
    refreshIcons();
  } catch (error) { showError(error); }
}

const ACQUISITION_WIZARD_STEPS = ["ACQUIRE", "PRODUCTS", "REVIEW"];
const ACQUISITION_STEP_LABELS = {
  ACQUIRE: "What did you acquire?", PRODUCTS: "Product & Purchase Details", REVIEW: "Review Acquisition",
};

function activeAcquisitionLines() {
  return (state.activeAcquisition?.lines || []).filter((line) => !line.canceled_at);
}

function wizardProgress(current) {
  const currentIndex = ACQUISITION_WIZARD_STEPS.indexOf(current);
  return `<ol class="wizard-progress" aria-label="Acquisition setup progress">${ACQUISITION_WIZARD_STEPS.map((step, index) => `<li class="${index < currentIndex ? "complete" : index === currentIndex ? "current" : ""}" ${index === currentIndex ? 'aria-current="step"' : ""}><span>${index + 1}</span>${escapeHtml(ACQUISITION_STEP_LABELS[step])}</li>`).join("")}</ol>`;
}

function productClassLabel(value) {
  return { SINGLE_CARDS: "Single Cards", PACK_PRODUCT: "Pack Product", SEALED_PRODUCT: "Sealed Product" }[value] || titleCase(value);
}

function productClassIcon(value) {
  return { SINGLE_CARDS: "layers-3", PACK_PRODUCT: "package-open", SEALED_PRODUCT: "package" }[value] || "package";
}

function catalogIdentity(line) {
  const product = line.catalog_product;
  if (!product) return "";
  const identifier = (product.identifiers || [])[0];
  return `<div class="catalog-recognition" role="status">${icon("badge-check")}<div><span>Catalog identified · Automatic + Visible</span><strong>${escapeHtml(product.display_name)}</strong><small>${escapeHtml(product.game)}${product.set_code ? ` · ${escapeHtml(product.set_code)}` : ""} · ${escapeHtml(productClassLabel(product.product_class))} · ${escapeHtml(product.product_subtype || "Commercial product")}${identifier ? ` · ${escapeHtml(identifier.identifier_type.replaceAll("_", "-"))} ${escapeHtml(identifier.raw_identifier)}` : ""}</small></div>${identifier ? `<button type="button" class="button secondary mapping-details" data-action="open-identifier-history" data-id="${identifier.id}">Mapping details</button>` : ""}</div>`;
}

function wizardAcquireScreen() {
  return `<section class="wizard-screen" data-viewport-key="wizard-acquire"><div class="wizard-heading"><span>Step 1</span><h2 id="wizard-screen-title" tabindex="-1">Start with the receipt</h2><p>Scan or upload the receipt. DEX will extract purchase facts, identify known products, reconcile the printed math, and ask only genuine business questions.</p></div>
    <section class="receipt-first-start"><div><span class="eyebrow">Recommended</span><h3>Scan receipt → Review → Confirm</h3><p>JPG, JPEG, PNG, and text-layer PDF processing stays private and local. Original files are never modified.</p></div>${sourceDocumentPanel()}</section>
    <details class="manual-acquisition-start" data-disclosure-key="acquisition-${state.activeAcquisition.acquisition.id}-manual-start"><summary>Advanced / Manual entry</summary><p>Use this for damaged, handwritten, or unreadable receipts, or when no receipt is available.</p>
    <div class="wizard-heading"><h3>What did you acquire?</h3><p>Choose the commercial product type. You can add different product lines to the same acquisition on the next screen.</p></div>
    <div class="choice-grid" role="group" aria-label="Product type">
      ${[
        ["SINGLE_CARDS", "Single Cards", "A known or provisional lot of individual cards. Identify now or later."],
        ["PACK_PRODUCT", "Pack Product", "Scan a UPC for fast identification or enter the product manually."],
        ["SEALED_PRODUCT", "Sealed Product", "Scan a UPC for boxes, decks, collections, and other sealed products."],
      ].map(([value, label, copy]) => `<button class="choice-card" data-action="choose-acquisition-type" data-product-class="${value}">${icon(productClassIcon(value))}<strong>${label}</strong><span>${copy}</span></button>`).join("")}
    </div></details>
    <div class="wizard-actions"><button class="button secondary" data-action="back-acquisitions">${icon("arrow-left")}Save incomplete & exit</button></div>
  </section>`;
}

function lineDetailsForm(line) {
  const singles = line.product_class === "SINGLE_CARDS";
  const pack = line.product_class === "PACK_PRODUCT";
  const heading = singles
    ? (line.game && line.set_code ? `${line.game} • ${line.set_code}` : "Single Cards")
    : (line.product_name || line.set_code || productClassLabel(line.product_class));
  return `<form class="product-line-card acquisition-line-form ${line.catalog_product ? "catalog-linked" : ""}" data-line-id="${line.id}" data-viewport-key="acquisition-line-${line.id}">
    <div class="product-line-head"><div>${icon(productClassIcon(line.product_class))}<span><strong>${escapeHtml(heading)}</strong><small>${escapeHtml(productClassLabel(line.product_class))} · Independent product line</small></span></div><button type="button" class="button danger" data-action="remove-acquisition-line" data-id="${line.id}">${icon("trash-2")}Remove</button></div>
    ${catalogIdentity(line)}
    <div class="form-grid">
      <label>TCG<input name="game" list="tcg-game-options" value="${escapeHtml(line.game)}" required placeholder="Pokemon, One Piece, Riftbound, …"></label>
      <label>${singles ? "Set" : pack ? "Set" : "Product / set"}<input name="set_code" value="${escapeHtml(line.set_code)}" required placeholder="OP16"></label>
      ${singles ? "" : `<label>${pack ? "Pack / product type" : "Product type"}<input name="product_name" value="${escapeHtml(line.product_name)}" required placeholder="${pack ? "Single pack, blister, bundle" : "Booster box, starter deck, collection"}"></label>`}
      ${pack ? `<label>Pack format <span class="optional">(optional detail)</span><input name="pack_type" value="${escapeHtml(line.pack_type)}" placeholder="Sleeved, blister, loose"></label>` : ""}
      <label>Quantity<input name="quantity" type="number" min="1" step="1" value="${line.quantity || ""}" required><span class="help-text">Enter the intended physical quantity received.</span></label>
    </div>
    <div class="inline-save"><span class="autosave-status" aria-live="polite">${line.catalog_product ? "Catalog facts persist with this draft; editing identity switches this line to manual" : "Draft facts autosave"}</span><button class="button secondary">Save line</button></div>
  </form>`;
}

function paymentMethodOptions(selected) {
  return [["", "Select payment method"], ["CREDIT_DEBIT_CARD", "Credit / Debit Card"], ["CASH", "Cash"], ["PAYPAL", "PayPal"], ["STORE_CREDIT", "Store Credit"], ["OTHER", "Other"]]
    .map(([value, label]) => `<option value="${value}" ${selected === value ? "selected" : ""}>${label}</option>`).join("");
}

function receiptIntelligence() {
  return state.activeAcquisition?.receipt_intelligence || { status: "NOT_REQUESTED", jobs: [], candidate_groups: {}, proposed_fields: [], conflicts: [], receipt_lines: [], warnings: [] };
}

function latestReceiptJob(documentId) {
  return [...(receiptIntelligence().jobs || [])].filter((job) => Number(job.document_id) === Number(documentId)).sort((a, b) => Number(b.id) - Number(a.id))[0] || null;
}

function receiptFieldSuggestion(fieldName) {
  const candidates = receiptIntelligence().candidate_groups?.[fieldName] || [];
  if (!candidates.length) return "";
  const active = candidates.filter((item) => item.disposition !== "REJECTED");
  if (!active.length) return "";
  const applied = active.find((item) => ["PROPOSED", "ACCEPTED"].includes(item.application_status));
  const conflicts = active.some((item) => item.conflicts_with_manual) || new Set(active.map((item) => String(item.normalized_value))).size > 1;
  const candidate = applied || active[0];
  const stateLabel = conflicts ? "Receipt conflict" : applied ? "Receipt suggestion applied to draft" : "Receipt suggestion available";
  return `<span class="receipt-field-marker ${conflicts ? "conflict" : "proposed"}" title="Candidate ${escapeHtml(candidate.confidence_band)} confidence · not authoritative">${icon(conflicts ? "triangle-alert" : "sparkles")}${escapeHtml(stateLabel)} · ${escapeHtml(titleCase(candidate.confidence_band))}</span>`;
}

function receiptJobControls(document, job) {
  if (!job) return `<button type="button" class="button secondary" data-action="extract-source-document" data-id="${document.id}">${icon("sparkles")}Extract purchase details</button>`;
  if (job.status === "FAILED" || job.status === "NO_FACTS") {
    const unavailable = job.capability_unavailable || job.error_code === "FORMAT_PROVIDER_UNAVAILABLE";
    const label = unavailable ? "Automatic image extraction unavailable" : job.status === "NO_FACTS" ? "No purchase facts found" : "Extraction failed";
    const retry = job.retry_plausible === false || unavailable ? "" : `<button type="button" class="button secondary" data-action="retry-receipt-extraction" data-job-uuid="${escapeHtml(job.job_uuid)}">${icon("rotate-ccw")}Retry extraction</button>`;
    return `<span class="receipt-job-state failed">${escapeHtml(label)}</span>${retry}`;
  }
  if (job.status === "PROCESSING") return `<span class="receipt-job-state processing">Extracting privately…</span>`;
  return `<span class="receipt-job-state ready">${icon("circle-check")}Ready to review · ${job.receipt_lines?.length || 0} line(s)</span>`;
}

function receiptManualFallbackPanel() {
  const intel = receiptIntelligence();
  if (!intel.manual_fallback_available) return "";
  if (intel.manual_fallback_selected) return `<section class="receipt-manual-fallback selected" role="status">${icon("circle-check")}<div><strong>Continuing with manual purchase facts</strong><p>Automatic extraction remains unavailable. The receipt stays attached as supporting evidence, while your confirmed manual facts control reconciliation.</p></div></section>`;
  return `<section class="receipt-manual-fallback" role="status">${icon("file-warning")}<div><strong>Receipt image attached</strong><p>Automatic image extraction is unavailable. You can continue using manual purchase facts; the receipt will remain attached as supporting evidence.</p><button type="button" class="button primary" data-action="select-receipt-manual-fallback">Continue with manual facts</button></div></section>`;
}

function sourceDocumentPanel() {
  const summary = state.activeAcquisition.source_documents || { documents: [], active_count: 0, failed_count: 0 };
  const acquisition = state.activeAcquisition.acquisition;
  const documents = Array.isArray(summary.documents) ? summary.documents : [];
  const rows = documents.map((document) => {
    const stored = document.storage_status === "STORED";
    const failed = document.storage_status === "FAILED";
    const tombstoned = document.storage_status === "TOMBSTONED";
    const statusLabel = tombstoned ? "Removed · history retained" : failed ? "Upload failed · retryable" : `${titleCase(document.document_role)} · ${Math.max(1, Math.round(document.byte_size / 1024))} KB`;
    const job = latestReceiptJob(document.id);
    return `<article class="source-document-row ${document.storage_status.toLowerCase()}"><div>${icon(document.detected_mime_type === "application/pdf" ? "file-text" : "image")}<span><strong>${escapeHtml(document.original_filename)}</strong><small>${escapeHtml(statusLabel)}${document.integrity_status === "VERIFIED" ? " · SHA-256 verified" : ""}</small>${failed ? `<em>${escapeHtml(document.error_message || "Document could not be stored")}</em>` : ""}</span></div><div class="source-document-actions">${stored && !tombstoned ? receiptJobControls(document, job) : ""}${stored ? `<button type="button" class="button tertiary" data-action="view-source-document" data-id="${document.id}">${icon("eye")}View</button>` : ""}${failed ? `<button type="button" class="button secondary" data-action="retry-source-document" data-id="${document.id}">${icon("rotate-ccw")}Retry upload</button>` : ""}${!tombstoned ? `<button type="button" class="button tertiary" data-action="remove-source-document" data-id="${document.id}">${icon("x")}Remove</button>` : ""}</div></article>`;
  }).join("");
  const confirmed = acquisition.state === "READY_FOR_INTAKE";
  return `<section class="source-document-panel" data-viewport-key="source-documents"><div class="source-document-head"><div><span class="eyebrow">Receipt / Source Documents</span><strong>${summary.active_count ? `${summary.active_count} document(s) attached` : "No receipt currently attached"}</strong><small>Private local extraction supports JPG, JPEG, PNG, and text-layer PDF. Suggestions stay non-authoritative until you confirm the acquisition.</small></div><div><button type="button" class="button secondary" data-action="take-source-photo" aria-controls="source-document-camera">${icon("camera")}Take Photo</button><button type="button" class="button secondary" data-action="upload-source-document" aria-controls="source-document-files">${icon("upload")}Upload</button></div></div>
    <input id="source-document-camera" class="source-document-implementation-input" type="file" accept="image/jpeg,image/png,image/heic,image/heif" capture="environment" hidden>
    <input id="source-document-files" class="source-document-implementation-input" type="file" accept=".jpg,.jpeg,.png,.heic,.heif,.pdf,image/jpeg,image/png,image/heic,image/heif,application/pdf" multiple hidden>
    <input id="source-document-retry" class="source-document-implementation-input" type="file" accept=".jpg,.jpeg,.png,.heic,.heif,.pdf,image/jpeg,image/png,image/heic,image/heif,application/pdf" hidden>
    ${rows ? `<div class="source-document-list">${rows}</div>` : ""}
    ${summary.failed_count ? `<p class="source-document-warning">${icon("triangle-alert")}A document upload needs attention. Manual acquisition entry remains available.</p>` : ""}
    ${receiptManualFallbackPanel()}
    ${receiptIntelligence().failed_job_count && !receiptIntelligence().manual_fallback_available ? `<p class="source-document-warning">${icon("triangle-alert")}Receipt extraction needs attention. Retry it or continue with manual purchase facts.</p>` : ""}
    <p class="source-document-policy">${confirmed ? "Confirmed evidence can be tombstoned but is retained for durable history." : "Draft attachments can be removed; their audit metadata remains."} Missing documents never become a $0.00 cost.</p>
  </section>`;
}

function purchaseDetailsForm() {
  const acquisition = state.activeAcquisition.acquisition;
  const international = acquisition.source_scope === "INTERNATIONAL";
  const warningCodes = new Set((state.activeAcquisition.readiness?.warnings || []).map((warning) => warning.code));
  const documentSummary = state.activeAcquisition.source_documents || { failed_count: 0 };
  const receiptStatus = state.activeAcquisition.receipt_intelligence?.status || "NOT_REQUESTED";
  const purchaseDetailsAttention = ["SOURCE_REQUIRED", "MERCHANT_REQUIRED", "PURCHASE_DATE_REQUIRED", "PAYMENT_METHOD_REQUIRED"].some((code) => warningCodes.has(code))
    || Boolean(documentSummary.failed_count) || ["FAILED_RETRYABLE", "FAILED_MANUAL_AVAILABLE"].includes(receiptStatus);
  const purchaseAmountsAttention = ["COST_UNKNOWN", "DISCREPANCY_REASON_REQUIRED", "ZERO_COST_REASON_REQUIRED", "MATERIAL_NOTE_REQUIRED", "ALLOCATION_NOT_RECONCILED"].some((code) => warningCodes.has(code))
    || [...warningCodes].some((code) => code.startsWith("RECEIPT_") || code.startsWith("EXTRACTION_"));
  return `<form id="acquisition-purchase-form" class="wizard-form purchase-details" data-viewport-key="purchase-details">
    <details class="purchase-disclosure" data-disclosure-key="acquisition-${acquisition.id}-purchase-details" data-disclosure-force-open="${purchaseDetailsAttention}" ${purchaseDetailsAttention ? "open" : ""}><summary><span><strong>Purchase details</strong><small>Where and how did you buy it?</small></span><span class="badge ${purchaseDetailsAttention ? "amber" : "green"}">${purchaseDetailsAttention ? "Needs Attention" : "Complete"}</span></summary><div class="purchase-disclosure-body">
      <fieldset class="segmented-choice"><legend>Purchase source</legend><label><input type="radio" name="source_scope" value="DOMESTIC" ${acquisition.source_scope === "DOMESTIC" ? "checked" : ""} required><span>Domestic</span></label><label><input type="radio" name="source_scope" value="INTERNATIONAL" ${international ? "checked" : ""} required><span>International</span></label></fieldset>
      <div class="form-grid">
        <label>Merchant / seller<input name="merchant_name" value="${escapeHtml(acquisition.merchant_name)}" required placeholder="Store or seller name">${receiptFieldSuggestion("merchant_name")}</label>
        <label>Purchase date<input name="purchased_on" type="date" value="${escapeHtml(acquisition.purchased_on || "")}" required>${receiptFieldSuggestion("purchased_on")}</label>
        <label>Payment method<select name="payment_method" required>${paymentMethodOptions(acquisition.payment_method || "")}</select></label>
      </div>
      <div class="form-grid international-fields" ${international ? "" : "hidden"}><label>Merchant country<input name="merchant_country" value="${escapeHtml(acquisition.merchant_country)}" placeholder="Japan"></label><label>Original currency<input name="original_currency" maxlength="3" value="${escapeHtml(acquisition.original_currency)}" placeholder="JPY"></label><label>Original foreign amount (minor units)<input name="original_foreign_amount_minor" type="number" min="0" step="1" value="${acquisition.original_foreign_amount_minor ?? ""}" placeholder="Reference only"><span class="help-text">Reference only. DEX performs no FX conversion.</span></label></div>
      ${sourceDocumentPanel()}
      <details class="additional-purchase" data-disclosure-key="acquisition-${acquisition.id}-additional-purchase"><summary>Additional purchase details</summary><label>Manual order / receipt reference<input name="order_reference" value="${escapeHtml(acquisition.order_reference)}" placeholder="Optional order number">${receiptFieldSuggestion("order_reference")}</label></details>
    </div></details>
    <details class="purchase-disclosure purchase-economics" data-disclosure-key="acquisition-${acquisition.id}-purchase-amounts" data-disclosure-force-open="${purchaseAmountsAttention}" ${purchaseAmountsAttention ? "open" : ""}><summary><span><strong>Advanced / Manual purchase amounts</strong><small>Receipt-derived values populate automatically. Blank remains Unknown.</small></span><span class="badge ${purchaseAmountsAttention ? "amber" : "green"}">${purchaseAmountsAttention ? "Needs Attention" : "Complete / clean"}</span></summary><div class="purchase-disclosure-body"><div class="form-grid">
      ${moneyField("purchase_subtotal", "Subtotal")}${moneyField("acquisition_tax", "Tax")}${moneyField("inbound_shipping", "Shipping")}${moneyField("acquisition_fees", "Fees")}
      ${international ? `${moneyField("import_duties", "Import duties")}${moneyField("brokerage", "Brokerage")}` : ""}
      ${moneyField("acquisition_discount", "Discounts / credits")}${moneyField("final_usd_paid", "Final USD actually paid", "Missing cost stays Unknown; DEX performs no FX conversion.")}
    </div></div></details>
    <div class="inline-save"><span class="autosave-status" aria-live="polite">Purchase details autosave as a draft</span><button class="button secondary">Save purchase details</button></div>
  </form>`;
}

function scannableAcquisitionLines() {
  return activeAcquisitionLines().filter((line) => ["PACK_PRODUCT", "SEALED_PRODUCT"].includes(line.product_class));
}

function catalogResultRows(mode = "manual") {
  const lines = scannableAcquisitionLines();
  const target = lines.find((line) => !line.catalog_product_id && !line.product_name) || lines[0];
  if (!state.catalogSearchResults.length) return `<p class="catalog-search-empty">No catalog results loaded yet.</p>`;
  return `<div class="catalog-search-results">${state.catalogSearchResults.map((product) => `<article><div><strong>${escapeHtml(product.display_name)}</strong><small>${escapeHtml(product.game)}${product.set_code ? ` · ${escapeHtml(product.set_code)}` : ""} · ${escapeHtml(productClassLabel(product.product_class))} · ${escapeHtml(product.product_subtype)}</small></div><button type="button" class="button secondary" data-action="${mode === "unknown" ? "select-unknown-catalog-product" : "apply-catalog-product"}" data-product-id="${product.id}" ${target ? `data-line-id="${target.id}"` : "disabled"}>Use product</button></article>`).join("")}</div>`;
}

function catalogSearchForm(mode = "manual") {
  const unknown = mode === "unknown";
  return `<form class="catalog-search-form" data-catalog-search-mode="${mode}"><div class="catalog-search-controls"><label>Search commercial-product catalog<input name="catalog_query" type="search" autocomplete="off" value="${escapeHtml(state.catalogSearchQueries[mode] || "")}" placeholder="Product, set, TCG, or manufacturer code"></label><button class="button secondary">${icon("search")}Search</button></div>${unknown ? `<label class="checkbox-label catalog-remember"><input name="remember_mapping" type="checkbox" checked><span>Remember this UPC for future purchases after I choose the correct product.</span></label>` : ""}</form>${catalogResultRows(mode)}`;
}

function unknownProductPanel() {
  const pending = state.pendingUnknownProduct;
  if (!pending) return "";
  const raw = pending.identifier.raw_identifier;
  const defaultClass = scannableAcquisitionLines()[0]?.product_class || "SEALED_PRODUCT";
  if (pending.mode === "search") {
    return `<section class="unknown-upc" role="alert" data-viewport-key="unknown-upc"><div class="unknown-upc-head">${icon("circle-help")}<div><span>Needs Attention</span><strong>Product not recognized</strong><small>${escapeHtml(pending.identifier.identifier_type.replaceAll("_", "-"))} · ${escapeHtml(raw)}</small></div></div>${catalogSearchForm("unknown")}<div class="unknown-upc-actions"><button type="button" class="button secondary" data-action="unknown-identify">Identify manually</button><button type="button" class="button tertiary" data-action="cancel-unknown-scan">Cancel scan</button></div></section>`;
  }
  if (pending.mode === "identify") {
    return `<section class="unknown-upc" role="alert" data-viewport-key="unknown-upc"><div class="unknown-upc-head">${icon("circle-help")}<div><span>Needs Attention</span><strong>Identify ${escapeHtml(raw)}</strong><small>DEX will use only the facts you confirm. It will not guess.</small></div></div><form id="unknown-product-form" class="unknown-identify-form"><div class="form-grid"><label>TCG / game<input name="game" list="tcg-game-options" required placeholder="Enter the TCG"></label><label>Product name<input name="display_name" required placeholder="OP16 Booster Box"></label><label>Set code<input name="set_code" placeholder="OP16"></label><label>Set name<input name="set_name" placeholder="The Time of Battle"></label><label>Product class<select name="product_class" required><option value="PACK_PRODUCT" ${defaultClass === "PACK_PRODUCT" ? "selected" : ""}>Pack Product</option><option value="SEALED_PRODUCT" ${defaultClass === "SEALED_PRODUCT" ? "selected" : ""}>Sealed Product</option></select></label><label>Product subtype<input name="product_subtype" list="catalog-subtype-options" required placeholder="Booster Box, ETB, Starter Deck"></label><label>Manufacturer / product code <span class="optional">(optional)</span><input name="manufacturer_product_code"></label></div><label class="checkbox-label catalog-remember"><input name="remember_mapping" type="checkbox"><span>Remember this UPC for future purchases. The mapping will be stored as operator-confirmed, not manufacturer-authoritative.</span></label><div class="unknown-upc-actions"><button class="button primary">Use identification</button><button type="button" class="button secondary" data-action="unknown-search">Search catalog</button><button type="button" class="button tertiary" data-action="cancel-unknown-scan">Cancel scan</button></div></form></section>`;
  }
  return `<section class="unknown-upc" role="alert" data-viewport-key="unknown-upc"><div class="unknown-upc-head">${icon("circle-help")}<div><span>Needs Attention</span><strong>Product not recognized</strong><small>${escapeHtml(pending.identifier.identifier_type.replaceAll("_", "-"))} · ${escapeHtml(raw)}</small></div></div><p>DEX did not create or guess a catalog product.</p><div class="unknown-upc-actions"><button type="button" class="button primary" data-action="unknown-search">Search catalog</button><button type="button" class="button secondary" data-action="unknown-identify">Identify manually</button><button type="button" class="button tertiary" data-action="cancel-unknown-scan">Cancel scan</button></div></section>`;
}

function upcRecognitionStatus() {
  const status = state.upcScanStatus;
  if (!status || status.status !== "RECOGNIZED") return "";
  const product = status.product;
  return `<div class="upc-recognized" role="status">${icon("circle-check-big")}<div><span>Recognized · Automatic + Visible</span><strong>${escapeHtml(product.display_name)} ×${status.quantity}</strong><small>${escapeHtml(product.game)}${product.set_code ? ` · ${escapeHtml(product.set_code)}` : ""} · ${escapeHtml(productClassLabel(product.product_class))} · ${escapeHtml(product.product_subtype)}</small></div></div>`;
}

function upcScannerPanel() {
  if (!scannableAcquisitionLines().length) return "";
  return `<section class="upc-intake" data-viewport-key="upc-intake"><div class="upc-intake-copy"><span class="eyebrow">Product Catalog</span><h3>Scan UPC</h3><p>Use a normal keyboard-emulating barcode scanner, or type a UPC-A, EAN-13, or GTIN-14 and press Enter. Each recognized scan adds one physical quantity; UPC identifies the commercial product, never an individual sealed unit.</p></div><form id="upc-scan-form" class="upc-scan-form"><label for="upc-scan-input">UPC / EAN / GTIN</label><div><input id="upc-scan-input" name="raw_identifier" autocomplete="off" inputmode="numeric" placeholder="Scan barcode" required><button class="button primary" ${state.upcScanPending ? "disabled" : ""}>${icon("scan-barcode")}${state.upcScanPending ? "Checking…" : "Apply scan"}</button></div></form>${upcRecognitionStatus()}${unknownProductPanel()}<details class="catalog-manual-fallback" data-disclosure-key="acquisition-${state.activeAcquisition.acquisition.id}-catalog-manual"><summary>Search catalog or continue with manual entry</summary><p>UPC is optional. Search DEX's local catalog to populate a line, or use the editable product cards below.</p>${catalogSearchForm("manual")}</details></section>`;
}

function singleProductAllocationNotice() {
  const data = state.activeAcquisition;
  const finalCost = data.acquisition.final_usd_paid_cents;
  const eligibility = data.single_product_allocation_eligibility || {};
  const eligible = eligibility.eligible === true
    || (!eligibility.status && Boolean(data.automatic_single_line_allocation_preview));
  if (!eligible) {
    return `<div class="single-line-allocation-notice blocked" role="alert">${icon("triangle-alert")}<div><strong>Automatic allocation is not ready.</strong><p>${escapeHtml(eligibility.message || "Resolve receipt financial discrepancies first.")}</p><small>DEX will not assign the final-paid amount to this product until the backend confirms allocation eligibility.</small></div></div>`;
  }
  return `<div class="single-line-allocation-notice">${icon("equal")}<div><strong>Automatic single-product allocation</strong><p>${finalCost == null ? "When Final USD is entered and confirmed, 100% will be assigned to this product line." : `${formatCents(finalCost)} will be assigned 100% to this product line at confirmation.`}</p><small>Method: Single line — 100% of authoritative landed cost. The audited allocation event is recorded with confirmation.</small></div></div>`;
}

function wizardProductsScreen() {
  const lines = activeAcquisitionLines();
  const multiple = lines.length > 1;
  return `<section class="wizard-screen" data-viewport-key="wizard-products"><div class="wizard-heading"><span>Step 2</span><h2 id="wizard-screen-title" tabindex="-1">Product & Purchase Details</h2><p>Tell DEX what arrived and where/how you bought it. Accounting safeguards remain in the background.</p></div>
    <datalist id="tcg-game-options"><option value="Pokemon"><option value="One Piece"><option value="Riftbound"></datalist><datalist id="catalog-subtype-options"><option value="Booster Pack"><option value="Sleeved Booster"><option value="Blister"><option value="Promo Pack"><option value="Booster Box"><option value="Starter Deck"><option value="Double Pack"><option value="Collection Box"><option value="Illustration Box"><option value="ETB"></datalist>
    ${upcScannerPanel()}
    <div class="product-line-stack">${lines.map(lineDetailsForm).join("")}</div>
    <div class="add-line-panel"><strong>Add another product only if needed</strong><div>${["SINGLE_CARDS", "PACK_PRODUCT", "SEALED_PRODUCT"].map((value) => `<button class="button secondary" data-action="add-acquisition-line" data-product-class="${value}">${icon("plus")}${escapeHtml(productClassLabel(value))}</button>`).join("")}</div></div>
    ${purchaseDetailsForm()}
    ${multiple ? `<div class="multi-line-accounting-notice">${icon("sparkles")}<div><strong>DEX will reconcile product-line costs on Review</strong><p>Routine accounting stays out of this screen. If authoritative facts are not sufficient to split landed cost safely, Review will request attention and offer manual resolution.</p><small>DEX never guesses an allocation method or invents missing source facts.</small></div></div>` : singleProductAllocationNotice()}
    <div class="wizard-actions"><button class="button secondary" data-action="wizard-step" data-step="ACQUIRE">${icon("arrow-left")}Back</button><button class="button primary" data-action="wizard-next" data-step="REVIEW">Review Acquisition${icon("arrow-right")}</button></div>
  </section>`;
}

function acquisitionFieldValue(name) {
  const value = state.activeAcquisition?.acquisition?.[name];
  return value === null || value === undefined ? "" : value;
}

function moneyField(name, label, help = "") {
  const cents = state.activeAcquisition?.acquisition?.[`${name}_cents`];
  return `<label>${label}<div class="money-input"><span>$</span><input name="${name}" inputmode="decimal" type="number" min="0" step=".01" value="${centsInputValue(cents)}"></div>${receiptFieldSuggestion(`${name}_cents`)}${help ? `<span class="help-text">${escapeHtml(help)}</span>` : ""}</label>`;
}

function linePerUnitLabel(line) {
  const unit = line.per_unit_cost;
  if (!unit) return "Per-unit cost Unknown";
  if (unit.exact_when_uniform) return `${formatCents(unit.base_cents)} per unit`;
  return `${unit.remainder_units} unit(s) at ${formatCents(unit.maximum_cents)}; ${unit.quantity - unit.remainder_units} at ${formatCents(unit.minimum_cents)}`;
}

function allocationForm(line) {
  const confirmed = line.allocation_status === "CONFIRMED";
  return `<form class="allocation-card acquisition-allocation-form ${confirmed ? "confirmed" : ""}" data-line-id="${line.id}" data-confirmed="${confirmed}" data-viewport-key="allocation-${line.id}">
    <div><strong>Line ${line.line_sequence}: ${escapeHtml(line.product_name || productClassLabel(line.product_class))}</strong><small>${line.quantity || "Unknown"} unit(s) · ${escapeHtml(linePerUnitLabel(line))}</small>${confirmed ? `<span class="allocation-confirmed-state">${icon("circle-check")}Allocation confirmed</span>` : `<span class="allocation-pending-state">Reconfirmation required</span>`}</div>
    <label>Assigned landed cost<div class="money-input"><span>$</span><input name="assigned_landed_cost" type="number" min="0" step=".01" value="${centsInputValue(line.assigned_landed_cost_cents)}" required></div></label>
    <label>Allocation method<select name="allocation_method" required><option value="">Choose and disclose method</option>${[
      ["ACTUAL_LINE_COST", "Actual line-item cost"], ["EQUAL", "Equal allocation"], ["SUBTOTAL_WEIGHTED", "Subtotal weighted"], ["QUANTITY_WEIGHTED", "Quantity weighted"], ["MANUAL", "Manual allocation"],
    ].map(([value, label]) => `<option value="${value}" ${line.allocation_method === value ? "selected" : ""}>${label}</option>`).join("")}</select></label>
    <label class="checkbox-label"><input name="confirm_allocation" type="checkbox" ${confirmed ? "checked disabled" : "required"}><span>I confirm this line cost and disclosed method. It remains draft-only until the full acquisition is confirmed.</span></label>
    ${confirmed ? `<button type="button" class="button allocation-confirmed-button" disabled>${icon("check")}Allocation confirmed</button>` : `<button class="button primary">Reconfirm allocation</button>`}
  </form>`;
}

function componentReconciliationPanel(reconciliation) {
  const severity = String(reconciliation.severity || "NONE").toLowerCase();
  const adjustment = reconciliation.component_adjustment_cents === undefined ? reconciliation.difference_cents : reconciliation.component_adjustment_cents;
  const componentReconciled = reconciliation.component_reconciled ?? (adjustment === 0);
  const status = componentReconciled ? "Reconciled" : "Needs explanation";
  return `<section class="reconciliation-block component-reconciliation ${severity}" role="status"><h3>Component discrepancy</h3><div><span>Purchase components</span><strong>${formatCents(reconciliation.component_total_cents)}</strong></div><div><span>Adjustment</span><strong>${formatCents(adjustment)}</strong><small>${reconciliation.difference_percent === null ? "Unknown" : `${reconciliation.difference_percent}%`}</small></div><div><span>Final paid</span><strong>${formatCents(reconciliation.final_usd_paid_cents)}</strong></div><div><span>Status</span><strong>${status}</strong><small>Material at $5 OR 2%; severe at 50%+</small></div></section>`;
}

function inventoryPartitionPanel(reconciliation) {
  const partitionReconciled = reconciliation.partition_reconciled ?? reconciliation.allocation_reconciled;
  const status = partitionReconciled ? "Reconciled" : "Needs Attention";
  return `<section class="reconciliation-block inventory-partition ${partitionReconciled ? "pass" : "fail"}" role="status"><h3>Excluded from inventory basis</h3><div><span>Inventory landed cost</span><strong>${formatCents(reconciliation.inventory_landed_cost_cents ?? reconciliation.assigned_line_cost_cents)}</strong></div><div><span>Excluded noninventory</span><strong>${formatCents(reconciliation.excluded_noninventory_cents, "Unknown / unconfirmed")}</strong></div><div><span>Final paid</span><strong>${formatCents(reconciliation.final_usd_paid_cents)}</strong></div><div><span>Difference</span><strong>${formatCents(reconciliation.partition_difference_cents ?? reconciliation.allocation_difference_cents)}</strong><small>Status: ${status}</small></div></section>`;
}

function reviewLine(line) {
  const automatic = state.activeAcquisition.automatic_single_line_allocation_preview;
  const automaticForLine = automatic?.line_id === line.id && line.allocation_status !== "CONFIRMED";
  const assigned = automaticForLine ? automatic.assigned_landed_cost_cents : line.assigned_landed_cost_cents;
  const method = automaticForLine
    ? automatic.allocation_method_label
    : line.allocation_method === "SINGLE_LINE_100_PERCENT"
      ? "Single line — 100% of authoritative landed cost"
      : (line.allocation_method ? titleCase(line.allocation_method) : "Method unconfirmed");
  const unit = automaticForLine ? automatic.per_unit_cost : line.per_unit_cost;
  const unitLabel = unit ? (unit.exact_when_uniform ? `${formatCents(unit.base_cents)} per unit` : `${unit.remainder_units} at ${formatCents(unit.maximum_cents)}; ${unit.quantity - unit.remainder_units} at ${formatCents(unit.minimum_cents)}`) : "Per-unit cost Unknown";
  const heading = line.product_class === "SINGLE_CARDS"
    ? (line.game && line.set_code ? `${line.game} • ${line.set_code}` : "Single Cards")
    : (line.product_name || line.set_code || "Product setup incomplete");
  return `<article><div><span>${escapeHtml(productClassLabel(line.product_class))}</span><strong>${escapeHtml(heading)}</strong><small>${escapeHtml(line.game || "TCG not selected")} · ${line.quantity || "Unknown"} unit(s)</small></div><div><span>Assigned landed cost</span><strong>${formatCents(assigned)}</strong><small>${escapeHtml(method)} · ${escapeHtml(unitLabel)}</small></div></article>`;
}

function paymentMethodLabel(value) {
  return { CREDIT_DEBIT_CARD: "Credit / Debit Card", CASH: "Cash", PAYPAL: "PayPal", STORE_CREDIT: "Store Credit", OTHER: "Other" }[value] || "Not selected";
}

function reconciliationExceptionControls(acquisition, reconciliation) {
  const zero = acquisition.final_usd_paid_cents === 0;
  const discrepancy = reconciliation.difference_cents !== null && reconciliation.difference_cents !== 0;
  const exclusionNeeded = acquisition.excluded_noninventory_cents !== null && acquisition.excluded_noninventory_cents !== undefined
    || (reconciliation.partition_difference_cents ?? reconciliation.allocation_difference_cents) > 0;
  if (!zero && !discrepancy && !exclusionNeeded) return "";
  return `<form id="acquisition-exception-form" class="exception-body">
      ${discrepancy || zero ? `<fieldset class="component-resolution"><legend>Resolve component discrepancy</legend>
      <label>Standardized reason<select name="discrepancy_reason_code" required><option value="">Select reason</option>${[
        ["ROUNDING", "Rounding"], ["COMPONENTS_INCOMPLETE", "Components incomplete"], ["MERCHANT_TOTAL_CONTROLS", "Merchant final total controls"], ["NONINVENTORY_INCLUDED", "Noninventory included (legacy reason; amount still required)"], ["EXPLICIT_ZERO_COST", "Intentional $0.00 acquisition"], ["OTHER", "Other"],
      ].map(([value, label]) => `<option value="${value}" ${acquisition.discrepancy_reason_code === value ? "selected" : ""}>${label}</option>`).join("")}</select></label>
      <label>Explanation${discrepancy ? " (required)" : ""}<textarea name="discrepancy_notes" ${discrepancy ? "required" : ""} placeholder="Explain why final USD differs from the purchase components">${escapeHtml(acquisition.discrepancy_notes)}</textarea></label>
      ${zero ? `<label class="checkbox-label zero-confirm"><input name="confirm_zero_cost" type="checkbox" required><span>I confirm this is an intentional $0.00 acquisition, not a missing cost.</span></label>` : ""}
      ${reconciliation.material ? `<label>Re-enter final USD paid<div class="money-input"><span>$</span><input name="reentered_final_usd_paid" type="number" min="0" step=".01" required></div></label><label class="checkbox-label"><input name="confirm_material_discrepancy" type="checkbox" required><span>I explicitly accept the material $5 OR 2% difference and its recorded explanation.</span></label>` : ""}
      ${reconciliation.extreme ? `<label class="checkbox-label severe-confirm"><input name="confirm_extreme_discrepancy" type="checkbox" required><span>I rechecked and explicitly accept this severe 50%+ difference.</span></label>` : ""}
      </fieldset>` : ""}
      ${exclusionNeeded ? `<fieldset class="noninventory-resolution"><legend>Excluded from inventory basis</legend><p>Record the net part of final payment that must not become inventory cost basis. This is not a tax or general-ledger classification.</p>
        <label>Excluded noninventory amount<div class="money-input"><span>$</span><input name="excluded_noninventory" type="number" min="0" step=".01" value="${centsInputValue(acquisition.excluded_noninventory_cents)}" required></div></label>
        <label>Treatment<select name="noninventory_treatment_code" required><option value="">Choose treatment</option>${[["BUSINESS_NONINVENTORY", "Business noninventory"], ["PERSONAL_NONBUSINESS", "Personal / nonbusiness"], ["MIXED_NONINVENTORY", "Mixed noninventory"], ["OTHER", "Other"]].map(([value, label]) => `<option value="${value}" ${acquisition.noninventory_treatment_code === value ? "selected" : ""}>${label}</option>`).join("")}</select></label>
        <label>Noninventory explanation<textarea name="noninventory_notes" placeholder="Optional unless Other is selected">${escapeHtml(acquisition.noninventory_notes)}</textarea></label>
        <label class="checkbox-label"><input name="confirm_noninventory_exclusion" type="checkbox" required><span>I confirm this net amount is intentionally excluded from inventory basis.</span></label>
      </fieldset>` : ""}
    </form>`;
}

function attentionPanel(data, blockingWarnings) {
  const attention = data.attention;
  if (!attention || attention.decision_level !== "NEEDS_ATTENTION") return "";
  const reconciliation = data.reconciliation;
  const acquisition = data.acquisition;
  const allocationUnresolved = attention.resolve_mode === "MULTI_LINE_ALLOCATION";
  const financialException = acquisition.final_usd_paid_cents === 0 || Boolean(reconciliation.difference_cents)
    || acquisition.excluded_noninventory_cents != null
    || (reconciliation.partition_difference_cents ?? reconciliation.allocation_difference_cents) > 0;
  const reasons = (data.readiness?.warnings || []).map((warning) => `<li><code>${escapeHtml(warning.code)}</code><span>${escapeHtml(warning.message)}</span></li>`).join("");
  const recordedReason = acquisition.discrepancy_reason_code ? titleCase(acquisition.discrepancy_reason_code) : "Unresolved";
  const allocationStatus = allocationUnresolved ? `<div class="allocation-attention-summary"><span>Assigned line cost</span><strong>${formatCents(reconciliation.assigned_line_cost_cents)}</strong><span>Difference from final USD</span><strong>${formatCents(reconciliation.allocation_difference_cents)}</strong></div>` : "";
  const resolution = `<details class="attention-resolution" data-disclosure-key="acquisition-${acquisition.id}-attention-resolution"><summary>${icon("wrench")}Resolve</summary><div class="attention-resolution-body">
    ${allocationUnresolved ? `<div class="allocation-section"><div><h4>Manual allocation exception</h4><p>Use this only because DEX lacks authoritative evidence for an automatic split. Every line must reconcile exactly.</p></div>${activeAcquisitionLines().map(allocationForm).join("")}</div>` : ""}
    ${financialException ? reconciliationExceptionControls(acquisition, reconciliation) : ""}
    ${attention.resolve_mode === "INCOMPLETE_FACTS" ? `<button type="button" class="button secondary" data-action="wizard-step" data-step="PRODUCTS">Complete product & purchase facts</button>` : ""}
  </div></details>`;
  return `<section class="purchase-needs-review ${String(attention.attention_level || "review").toLowerCase()}" aria-labelledby="acquisition-attention-title">
    <div class="attention-head"><div><span class="attention-state">Needs Attention · ${escapeHtml(titleCase(attention.attention_level || "Review"))}</span><strong id="acquisition-attention-title">Purchase needs attention</strong><p><b>${escapeHtml(attention.headline)}</b> · ${escapeHtml(attention.message)}</p><small>Status: ${escapeHtml(attention.decision_level)} · Recorded reason: ${escapeHtml(recordedReason)}</small></div>${icon(attention.attention_level === "CRITICAL" ? "octagon-alert" : "triangle-alert")}</div>
    ${allocationStatus}
    ${reasons ? `<ul class="attention-reasons">${reasons}</ul>` : ""}
    ${resolution}
  </section>`;
}

function receiptCandidateDisplay(candidate) {
  if (candidate.value_type === "CENTS") return formatCents(Number(candidate.value));
  if (candidate.field_name === "original_foreign_amount_minor") return String(candidate.value);
  return String(candidate.value ?? "Unknown");
}

function receiptCandidateLabel(field) {
  return ({
    merchant_name: "Merchant", purchased_on: "Purchase date", order_reference: "Order / receipt reference",
    source_scope: "Purchase source", original_currency: "Original currency",
    original_foreign_amount_minor: "Original foreign amount", purchase_subtotal_cents: "Subtotal",
    acquisition_tax_cents: "Tax", inbound_shipping_cents: "Shipping", acquisition_fees_cents: "Fees",
    import_duties_cents: "Duties", brokerage_cents: "Brokerage", acquisition_discount_cents: "Discounts",
    final_usd_paid_cents: "Final paid", payment_method: "Payment method",
  })[field] || titleCase(field);
}

function receiptMathPanel(math) {
  if (!math) return "";
  const exact = math.status === "RECONCILED_EXACT";
  const components = (math.components || []).map((item) => `<li><span>${escapeHtml(item.label || titleCase(item.kind))}</span><strong>${formatCents(item.signed_cents)}</strong><small>${escapeHtml(titleCase(item.math_role || "Unresolved"))}</small></li>`).join("");
  return `<section class="receipt-understood ${exact ? "exact" : "attention"}" role="status"><div class="receipt-understood-head"><div><span>What DEX understood</span><h3>${exact ? "Receipt reconciled exactly" : "Receipt math needs attention"}</h3><p>${exact ? "Printed subtotal components were distinguished from amounts outside the subtotal. Included fees or discounts will not be counted twice." : "DEX will not guess between competing receipt interpretations."}</p></div><span class="badge ${exact ? "green" : "amber"}">${escapeHtml(titleCase(math.status))}</span></div><div class="receipt-math-summary"><div><span>Merchandise</span><strong>${formatCents(math.merchandise_total_cents)}</strong></div><div><span>Printed subtotal</span><strong>${formatCents(math.printed_subtotal_cents)}</strong></div><div><span>Final paid</span><strong>${formatCents(math.final_paid_cents)}</strong></div><div><span>Difference</span><strong>${formatCents(math.difference_cents)}</strong></div></div>${components ? `<details><summary>How printed components were interpreted</summary><ul>${components}</ul></details>` : ""}</section>`;
}

function receiptSemanticReview(review) {
  const lines = review?.lines || [];
  const history = review?.history || [];
  if (!lines.length && !history.length) return "";
  const classes = [
    "MERCHANDISE", "DISCOUNT_CREDIT", "FEE_SURCHARGE", "TAX", "SHIPPING",
    "SUBTOTAL", "TOTAL", "TENDER_PAYMENT_METHOD", "PAYMENT_SUMMARY",
    "INFORMATIONAL_FOOTER", "STRUCTURAL", "UNKNOWN",
  ];
  const rows = lines.map((line) => {
    const confidence = line.numeric_confidence === null || line.numeric_confidence === undefined
      ? "Confidence unavailable"
      : `${Math.round(Number(line.numeric_confidence) * 100)}% parser confidence`;
    const amount = line.signed_amount_cents === null || line.signed_amount_cents === undefined
      ? "No amount"
      : formatCents(line.signed_amount_cents);
    const confirmed = line.confidence_state === "OPERATOR_CONFIRMED";
    const statusClass = confirmed ? "green" : ["UNRESOLVED", "CONFLICTING"].includes(line.confidence_state) ? "amber" : "";
    const options = classes.map((value) => `<option value="${value}" ${line.semantic_class === value ? "selected" : ""}>${escapeHtml(titleCase(value))}</option>`).join("");
    const form = `<form class="receipt-semantic-form" data-semantic-uuid="${escapeHtml(line.semantic_uuid)}" data-current-class="${escapeHtml(line.semantic_class)}">
      <label>Semantic class<select name="semantic_class" aria-label="Semantic class for source line ${line.source_line_index}">${options}</select></label>
      <label>Correction reason<select name="reason_code"><option value="OPERATOR_REVIEW">Operator review</option><option value="PARSER_MISCLASSIFIED">Parser misclassified</option><option value="AMBIGUOUS_SOURCE">Ambiguous source line</option><option value="OTHER">Other</option></select></label>
      <label>Notes<input name="notes" maxlength="1000" placeholder="Optional review note"></label>
      <div><button class="button secondary">${line.semantic_class === "UNKNOWN" ? "Save review" : confirmed ? "Update classification" : "Confirm / change"}</button>${line.semantic_class !== "UNKNOWN" ? `<button type="button" class="button tertiary" data-action="mark-semantic-unresolved" data-semantic-uuid="${escapeHtml(line.semantic_uuid)}">Mark unresolved</button>` : ""}</div>
    </form>`;
    const needsReview = Boolean(line.operator_confirmation_required) || ["UNRESOLVED", "CONFLICTING"].includes(line.confidence_state);
    const controls = needsReview
      ? form
      : `<details class="receipt-semantic-adjust"><summary>Change classification</summary>${form}</details>`;
    return `<article class="receipt-semantic-line ${confirmed ? "confirmed" : ""}" data-viewport-key="receipt-semantic-${escapeHtml(line.semantic_uuid)}">
      <div class="receipt-semantic-source"><span>Source line ${line.source_line_index} · page ${line.source_page || "Unknown"}</span><strong>${escapeHtml(line.normalized_text)}</strong><small>${escapeHtml(line.source_location || "Location unavailable")} · ${amount} · ${escapeHtml(line.parser_version)}</small></div>
      <div class="receipt-semantic-result"><span class="badge ${statusClass}">${escapeHtml(titleCase(line.semantic_class))}</span><strong>${escapeHtml(titleCase(line.confidence_state))}</strong><small>${confidence} · ${line.operator_confirmation_required ? "Operator confirmation requested" : "No confirmation required"} · ${line.product_match_eligible ? "Product-match eligible" : "Excluded from product matching"}</small></div>
      ${controls}
    </article>`;
  }).join("");
  const historyRows = history.map((line) => {
    const confidence = line.numeric_confidence === null || line.numeric_confidence === undefined
      ? "Confidence unavailable"
      : `${Math.round(Number(line.numeric_confidence) * 100)}% parser confidence`;
    const supersededBy = line.superseded_by_semantic_uuid
      ? `semantic decision ${line.superseded_by_semantic_uuid}`
      : line.superseded_by_job_uuid
        ? `extraction ${line.superseded_by_job_uuid}`
        : titleCase(line.inactive_reason || "Historical");
    const action = line.operator_action ? ` · ${titleCase(line.operator_action)}` : "";
    return `<li><div><span>Source line ${line.source_line_index} · ${escapeHtml(titleCase(line.inactive_reason || "Historical"))}</span><strong>${escapeHtml(line.normalized_text)}</strong><small>${escapeHtml(titleCase(line.semantic_class))} · ${confidence} · ${escapeHtml(line.parser_version)} · ${escapeHtml(line.rules_version || "Rules version unavailable")}</small></div><div><span>${escapeHtml(formatDate(line.recorded_at))}</span><strong>Superseded by ${escapeHtml(supersededBy)}</strong><small>${escapeHtml(action.replace(/^ · /, "")) || "No operator action"}${line.operator_reason_code ? ` · ${escapeHtml(titleCase(line.operator_reason_code))}` : ""}</small></div></li>`;
  }).join("");
  const activeCount = review.active_assertion_count ?? lines.length;
  const historyPanel = historyRows ? `<details class="receipt-semantic-history" data-disclosure-key="receipt-semantic-history"><summary>View interpretation history · ${review.historical_assertion_count ?? history.length} historical / superseded</summary><p>Audit history is immutable and does not participate in matching, receipt math, allocation, or confirmation.</p><ul>${historyRows}</ul></details>` : "";
  return `<details class="receipt-semantic-review" open data-disclosure-key="receipt-semantic-review"><summary>Current interpretation · ${activeCount} source line(s) · ${review.needs_confirmation_count || 0} need review</summary><div class="receipt-semantic-intro"><strong>Current semantic suggestions only</strong><p>Only the active interpretation participates in review and downstream safeguards. Earlier parser results remain available in audit history.</p></div><div class="receipt-semantic-lines">${rows}</div>${historyPanel}</details>`;
}

function receiptIntelligenceReview() {
  const intel = receiptIntelligence();
  const historicalJobs = intel.historical_jobs || [];
  const historical = historicalJobs.length ? `<details class="receipt-history"><summary>Removed-document extraction history / prior attempts · ${historicalJobs.length}</summary><ul class="receipt-job-list">${historicalJobs.map((job) => `<li><div><strong>${escapeHtml(titleCase(job.history_reason || "Historical extraction"))} · ${escapeHtml(titleCase(job.status))}</strong><small>${escapeHtml(job.provider_name)} · ${escapeHtml(formatDate(job.completed_at || job.failed_at || job.queued_at))}</small></div><span>History retained; no active retry or authority</span></li>`).join("")}</ul></details>` : "";
  if (!(intel.jobs || []).length) return `<section class="receipt-review empty"><div class="section-header"><div><span>Receipt Intelligence</span><h3>No active receipt extraction</h3><p>${historicalJobs.length ? "No receipt currently attached. Removed-document history remains below." : "Manual entry remains fully available. Attach a text-based PDF and choose Extract purchase details if you want suggestions."}</p></div></div>${historical}</section>`;
  const jobs = (intel.jobs || []).map((job) => `<li><div><strong>${escapeHtml(job.status === "COMPLETED" ? "Ready to review" : titleCase(job.status))}</strong><small>${escapeHtml(job.provider_name)} · ${escapeHtml(job.provider_version)} · ${escapeHtml(formatDate(job.completed_at || job.failed_at || job.queued_at))}</small></div><span>${job.status === "FAILED" ? escapeHtml(job.error_message || "Retryable local extraction failure") : `${job.receipt_lines?.length || 0} receipt line(s)`}</span></li>`).join("");
  const candidates = Object.entries(intel.candidate_groups || {}).flatMap(([field, items]) => (items || []).map((candidate) => {
    const conflict = Boolean(candidate.conflicts_with_manual) || (intel.conflicts || []).some((item) => item.field_name === field);
    const applied = ["PROPOSED", "ACCEPTED"].includes(candidate.application_status);
    return `<article class="receipt-candidate ${conflict ? "conflict" : ""} ${candidate.disposition === "REJECTED" ? "rejected" : ""}"><div><span>${escapeHtml(receiptCandidateLabel(field))}</span><strong>${escapeHtml(receiptCandidateDisplay(candidate))}</strong><small>${escapeHtml(titleCase(candidate.confidence_band))} confidence · page ${candidate.source_page || "Unknown"} · ${escapeHtml(candidate.source_location || "location unavailable")}</small></div><div><span class="badge ${conflict ? "amber" : applied ? "green" : ""}">${conflict ? "Conflict" : applied ? "Proposed in draft" : titleCase(candidate.disposition)}</span>${candidate.disposition !== "REJECTED" && !applied ? `<button type="button" class="button secondary" data-action="use-receipt-candidate" data-id="${candidate.id}">Use suggestion</button>` : ""}${candidate.disposition !== "REJECTED" ? `<button type="button" class="button tertiary" data-action="reject-receipt-candidate" data-id="${candidate.id}">Reject</button>` : ""}</div></article>`;
  })).join("");
  const receiptLines = (intel.receipt_lines || []).map((line) => {
    const match = line.best_match;
    const matchName = match ? (match.product_name || `Acquisition line ${match.acquisition_line_id}`) : "No product match";
    const needsMatch = match?.match_method === "FUZZY_TEXT" && match.status !== "ACCEPTED";
    const question = line.classification === "UNRESOLVED" ? `<section class="receipt-business-question" aria-labelledby="receipt-question-${line.id}"><span>Needs Attention</span><strong id="receipt-question-${line.id}">How should ${escapeHtml(line.description)} be treated?</strong><div><button type="button" class="button secondary" data-action="receipt-classify-choice" data-id="${line.id}" data-classification="INVENTORY">Inventory for resale</button><button type="button" class="button secondary" data-action="receipt-classify-choice" data-id="${line.id}" data-classification="BUSINESS_NONINVENTORY">Business noninventory</button><button type="button" class="button secondary" data-action="receipt-classify-choice" data-id="${line.id}" data-classification="PERSONAL_NONBUSINESS">Personal / nonbusiness</button></div></section>` : `<span class="badge green">${escapeHtml(titleCase(line.classification))}</span>`;
    return `<article class="receipt-review-line" data-viewport-key="receipt-line-${line.id}"><div><span>Receipt line ${line.line_sequence}</span><strong>${escapeHtml(line.description)}</strong><small>${line.quantity || "Unknown"} unit(s) · ${formatCents(line.line_total_cents)} · ${escapeHtml(titleCase(line.confidence_band))} confidence</small></div><div><span>Product match</span><strong>${escapeHtml(matchName)}</strong><small>${match ? `${escapeHtml(titleCase(match.match_method))} · ${Math.round(Number(match.confidence) * 100)}%${match.authoritative_identity ? " · deterministic catalog identity" : " · suggestion only"}` : "Resolve manually before automatic allocation"}</small>${needsMatch ? `<button type="button" class="button secondary" data-action="accept-receipt-match" data-id="${match.id}">Accept suggested match</button>` : ""}</div>${question}<details class="receipt-line-advanced"><summary>Advanced classification</summary><form class="receipt-classification-form" data-line-id="${line.id}"><label>Classification<select name="classification" aria-label="Classification for ${escapeHtml(line.description)}">${[
      ["UNRESOLVED", "Unresolved"], ["INVENTORY", "Inventory"], ["SHIPPING_FEE", "Shipping / Fee"], ["BUSINESS_NONINVENTORY", "Business Noninventory"], ["PERSONAL_NONBUSINESS", "Personal / Nonbusiness"], ["DUPLICATE_EXTRACTION", "Duplicate Extraction"],
    ].map(([value, label]) => `<option value="${value}" ${line.classification === value ? "selected" : ""}>${label}</option>`).join("")}</select></label><button class="button tertiary">Save</button></form></details></article>`;
  }).join("");
  const proposal = intel.allocation_proposal;
  const lineNames = new Map(activeAcquisitionLines().map((line) => [Number(line.id), line.product_name || productClassLabel(line.product_class)]));
  const allocations = proposal ? proposal.allocations.map((item) => `<li><span>${escapeHtml(lineNames.get(Number(item.acquisition_line_id)) || `Line ${item.acquisition_line_id}`)}</span><span>Merchandise ${formatCents(item.direct_merchandise_cents)} + shared ${formatCents(item.shared_component_cents)}</span><strong>${formatCents(item.landed_cost_cents)}</strong></li>`).join("") : "";
  const warnings = (intel.warnings || []).map((warning) => `<li><code>${escapeHtml(warning.code)}</code><span>${escapeHtml(warning.message)}${warning.code === "RECEIPT_ALLOCATION_UNRESOLVED" && intel.manual_fallback_selected ? " · Informational after your manual-facts decision; HF1 accounting still controls confirmation." : ""}</span></li>`).join("");
  const policyRequired = intel.allocation_policy?.status === "POLICY_REQUIRED";
  const policyComponents = policyRequired ? (intel.allocation_policy.preserved_components || []).map((item) => `<li><span>${escapeHtml(item.label || titleCase(item.kind))}</span><strong>${formatCents(item.signed_cents)}</strong><small>${escapeHtml(titleCase(item.math_role || "Unresolved"))}</small></li>`).join("") : "";
  const unavailableAllocation = !proposal && activeAcquisitionLines().length > 1;
  const singleProductBlocked = !proposal
    && activeAcquisitionLines().length === 1
    && state.activeAcquisition.single_product_allocation_eligibility?.eligible === false
    && state.activeAcquisition.single_product_allocation_eligibility?.authority_source === "RECEIPT_INTELLIGENCE";
  const allocationFallback = policyRequired
    ? `<div class="receipt-allocation unresolved receipt-policy-required" role="alert"><strong>Final landed-cost allocation: Policy required</strong><p>Receipt extraction, product matching, arithmetic, and business-purpose classification are complete. DEX will not assume how shared purchase components should be divided between inventory and noninventory.</p>${policyComponents ? `<ul>${policyComponents}</ul>` : ""}<small>Pending policy: sales tax, transaction/card fees, shipping/freight, purchase-level discounts or credits, and cent-rounding/remainder handling.</small></div>`
    : singleProductBlocked
      ? `<div class="receipt-allocation unresolved" role="alert"><strong>Automatic allocation is not ready.</strong><p>${escapeHtml(state.activeAcquisition.single_product_allocation_eligibility.message || "Resolve receipt financial discrepancies first.")}</p><small>No final-paid amount will be assigned automatically while receipt financial evidence remains unresolved.</small></div>`
    : unavailableAllocation && intel.manual_fallback_selected
    ? `<div class="receipt-allocation manual"><strong>Manual line allocation selected.</strong><p>Confirm each product-line landed cost and complete both reconciliation equations. Receipt extraction remains failed/unavailable and does not supply authority.</p></div>`
    : unavailableAllocation && intel.manual_fallback_available
      ? receiptManualFallbackPanel()
      : unavailableAllocation
        ? `<div class="receipt-allocation unresolved"><strong>Automatic line allocation is not ready.</strong><p>Resolve receipt classifications, product matches, quantities, conflicts, and final USD first.</p><button type="button" class="button secondary" data-action="generate-receipt-allocation">Try exact allocation</button></div>`
        : "";
  return `<section class="receipt-review" data-viewport-key="receipt-intelligence-review"><div class="section-header"><div><span>Receipt Intelligence</span><h3>Review what DEX understood</h3><p>DEX performs deterministic receipt math and asks only unresolved business questions. Final acquisition confirmation remains the authority boundary.</p></div><span class="badge ${intel.status === "READY_TO_REVIEW" ? "green" : "amber"}">${escapeHtml(titleCase(intel.status))}</span></div>
    ${receiptMathPanel(intel.receipt_math)}
    <details><summary>Source and extraction status · ${(intel.jobs || []).filter((job) => job.status === "COMPLETED").length} ready</summary><ul class="receipt-job-list">${jobs}</ul></details>
    ${historical}
    ${receiptSemanticReview(intel.semantic_review)}
    ${candidates ? `<details><summary>Candidate purchase facts · ${Object.values(intel.candidate_groups || {}).flat().length} suggestion(s)</summary><div class="receipt-candidates">${candidates}</div></details>` : ""}
    ${receiptLines ? `<details><summary>Receipt product lines and classifications · ${(intel.receipt_lines || []).length} line(s)</summary><div class="receipt-review-lines">${receiptLines}</div></details>` : ""}
    ${proposal ? `<details open><summary>Suggested landed-cost allocation · ${formatCents(proposal.total_allocated_cents)} · exact</summary><div class="receipt-allocation"><div><span>Method</span><strong>Receipt-value proportional</strong><small>${escapeHtml(proposal.explanation || "Net transaction components are allocated proportionally by merchandise value.")} ${escapeHtml(proposal.calculation_version)} · deterministic remainder cents</small></div><ul>${allocations}</ul>${proposal.input_facts?.excluded_noninventory_cents ? `<p>Explicitly classified noninventory: ${formatCents(proposal.input_facts.excluded_noninventory_cents)} · ${escapeHtml(titleCase(proposal.input_facts.noninventory_treatment_code))}</p>` : ""}<p>Total inventory basis ${formatCents(proposal.total_allocated_cents)} · Difference ${formatCents(proposal.difference_cents)} · Non-authoritative until acquisition confirmation.</p></div></details>` : allocationFallback}
    ${warnings ? `<ul class="attention-reasons receipt-warnings">${warnings}</ul>` : ""}
    <p class="receipt-privacy-note">${icon("shield-check")}Extraction is local and provider-neutral. DEX stores normalized candidates and provenance—not raw OCR text—and sends nothing to an external service.</p>
  </section>`;
}

function wizardReviewScreen() {
  const data = state.activeAcquisition;
  const acquisition = data.acquisition;
  const reconciliation = data.reconciliation;
  const confirmed = ["READY_FOR_INTAKE", "INTAKE_IN_PROGRESS", "INTAKE_COMPLETE"].includes(acquisition.state);
  const ready = confirmed;
  const canceled = acquisition.state === "CANCELED";
  const warnings = data.readiness?.warnings || [];
  const allocationClean = reconciliation.allocation_reconciled || Boolean(data.automatic_single_line_allocation_preview);
  const resolvableCodes = new Set([
    "DISCREPANCY_REASON_REQUIRED", "DISCREPANCY_NOTE_REQUIRED", "ZERO_COST_REASON_REQUIRED",
    "MATERIAL_NOTE_REQUIRED", "EXCLUDED_NONINVENTORY_REQUIRED", "NONINVENTORY_AMOUNT_REQUIRED",
    "NONINVENTORY_TREATMENT_REQUIRED", "NONINVENTORY_NOTE_REQUIRED", "ALLOCATION_NOT_RECONCILED",
  ]);
  const blockingWarnings = warnings.filter((warning) => !resolvableCodes.has(warning.code));
  const needsAttention = data.attention?.decision_level === "NEEDS_ATTENTION";
  const documentSummary = data.source_documents || { active_count: 0, failed_count: 0 };
  const extractionStatus = data.receipt_intelligence?.status || "NOT_REQUESTED";
  const documentStatusCopy = documentSummary.failed_count
    ? `${documentSummary.failed_count} failed upload(s) · manual facts unaffected`
    : extractionStatus === "READY_TO_REVIEW"
      ? "Receipt suggestions ready to review"
      : extractionStatus === "FAILED_MANUAL_AVAILABLE"
        ? (data.receipt_intelligence?.manual_fallback_selected ? "Manual facts selected · receipt retained as evidence" : "Automatic image extraction unavailable · manual facts available")
      : extractionStatus === "FAILED_RETRYABLE"
        ? "Extraction failed · retry or use manual facts"
        : documentSummary.active_count ? "Source evidence attached · extraction not requested" : "No receipt currently attached";
  return `<section class="wizard-screen" data-viewport-key="wizard-review"><div class="wizard-heading"><span>Step 3</span><h2 id="wizard-screen-title" tabindex="-1">Review Acquisition</h2><p>What did I buy? Where and how did I buy it? Is this summary correct?</p></div>
    <div class="review-hero ${ready ? "ready" : "incomplete"}"><div><span>${escapeHtml(acquisition.acquisition_code)}</span><h3>${escapeHtml(acquisition.merchant_name || "Merchant not entered")}</h3><p>${escapeHtml(acquisition.source_scope ? titleCase(acquisition.source_scope) : "Source incomplete")} · ${formatDate(acquisition.purchased_on)} · ${escapeHtml(paymentMethodLabel(acquisition.payment_method))}</p></div><div><span>Final USD paid</span><strong>${escapeHtml(data.readiness?.authoritative_cost_label || "Unknown / Setup incomplete")}</strong><small>${ready ? "Authoritative" : "Not authoritative until confirmed"}</small></div></div>
    <div class="review-lines">${activeAcquisitionLines().map(reviewLine).join("") || `<p>No product lines added.</p>`}</div>
    <div class="review-purchase-grid"><div><span>Purchase components</span><strong>${formatCents(reconciliation.component_total_cents)}</strong><small>Subtotal + tax + shipping + fees + duties/brokerage − discounts</small></div><div><span>Final USD paid</span><strong>${formatCents(reconciliation.final_usd_paid_cents)}</strong><small>Authoritative reporting currency</small></div><div><span>Source documents</span><strong>${documentSummary.active_count ? `${documentSummary.active_count} attached` : "Not attached"}</strong><small>${escapeHtml(documentStatusCopy)}</small></div></div>
    <div class="independent-reconciliations">${componentReconciliationPanel(reconciliation)}${inventoryPartitionPanel(reconciliation)}</div>
    ${receiptIntelligenceReview()}
    ${ready || canceled ? "" : attentionPanel(data, blockingWarnings)}
    ${!needsAttention && allocationClean && acquisition.final_usd_paid_cents !== null ? `<div class="review-ready">${icon("circle-check")}Reconciled exactly</div>` : ""}
    ${ready ? `<div class="review-ready">${icon("circle-check")}Authoritative acquisition facts are confirmed.</div>` : ""}
    ${canceled ? `<div class="acquisition-canceled-panel"><span class="badge gray">Canceled</span><h3>Acquisition history retained</h3><p>${escapeHtml(acquisition.cancel_notes || titleCase(acquisition.cancel_reason_code || "Canceled by operator"))}</p></div>` : confirmed ? intakeRoutingPanel() : `<form id="acquisition-confirm-form" class="confirmation-group">
      <div class="wizard-actions"><button type="button" class="button secondary" data-action="back-acquisitions">Save incomplete & exit</button><button class="button primary" ${blockingWarnings.length ? "disabled" : ""}>${icon("circle-check")}Confirm Acquisition</button></div>
    </form>`}
    ${ready || canceled ? "" : `<div class="wizard-actions review-back"><button class="button secondary" data-action="wizard-step" data-step="PRODUCTS">${icon("arrow-left")}Back to product & purchase details</button></div>`}
  </section>`;
}

function intakeRoutingPanel() {
  const routing = state.activeAcquisition.intake_routing;
  if (!routing) return `<div class="ready-for-intake-panel"><h3>Intake routing unavailable</h3><p>Reload this acquisition before continuing.</p></div>`;
  const complete = routing.state === "INTAKE_COMPLETE";
  const lines = (routing.lines || []).map((line) => {
    const product = line.product_name || line.pack_type || line.set_code || productClassLabel(line.product_class);
    const routed = line.routed;
    const hasRip = (line.links || []).some((link) => link.kind === "RIP_SESSION");
    const batchActionLabel = line.product_class === "SINGLE_CARDS" ? "Continue Scanning" : hasRip ? "Continue Rip" : "View Inventory";
    const links = (line.links || []).map((link) => link.kind === "BATCH"
      ? `<button type="button" class="button secondary" data-action="open-projected-batch" data-id="${link.id}">${icon(line.product_class === "SINGLE_CARDS" ? "scan-line" : hasRip ? "package-open" : "package-search")}${batchActionLabel} · ${escapeHtml(link.label)}</button>`
      : `<span class="badge ${link.status === "FINALIZED" ? "green" : "blue"}">${escapeHtml(link.label)} · ${escapeHtml(titleCase(link.status))}</span>`).join("");
    const inputs = line.product_class === "SINGLE_CARDS"
      ? `<label>Scan & Identify<input type="number" min="0" max="${line.undecided_quantity}" step="1" name="scan_${line.line_id}" value="0"></label>`
      : `<label>Keep Sealed<input type="number" min="0" max="${line.undecided_quantity}" step="1" name="keep_${line.line_id}" value="0"></label><label>Rip / Open<input type="number" min="0" max="${line.undecided_quantity}" step="1" name="rip_${line.line_id}" value="0"></label>`;
    return `<article class="intake-route-line" data-line-id="${line.line_id}" data-viewport-key="intake-line-${line.line_id}"><div class="intake-route-heading"><div><span>Product line ${line.line_sequence} · ${escapeHtml(productClassLabel(line.product_class))}</span><strong>${escapeHtml(product)}</strong><small>${line.quantity_acquired} acquired · ${formatCents(line.landed_cost_cents)} authoritative landed cost</small></div><span class="badge ${line.undecided_quantity ? "amber" : "green"}">${line.undecided_quantity ? `${line.undecided_quantity} undecided` : "Fully routed"}</span></div><div class="intake-route-accounting"><span>Keep sealed <strong>${routed.keep_sealed_quantity}</strong></span><span>Rip/open <strong>${routed.rip_open_quantity}</strong></span><span>Scan/identify <strong>${routed.scan_identify_quantity}</strong></span><span>Undecided <strong>${line.undecided_quantity}</strong></span></div>${line.undecided_quantity ? `<div class="intake-route-inputs">${inputs}<p>Leave the rest undecided to continue later.</p></div>` : ""}${links ? `<div class="intake-route-links">${links}</div>` : ""}</article>`;
  }).join("");
  return `<section class="intake-routing" data-viewport-key="intake-routing"><div class="section-header"><div><span>Downstream Intake</span><h3>${complete ? "Intake routing complete" : "What happens next?"}</h3><p>Route each confirmed product line into the existing DEX inventory workflows. No cost entry is needed.</p></div><span class="badge ${complete ? "green" : "blue"}">${escapeHtml(acquisitionStateLabel(routing.state))}</span></div><div class="intake-routing-summary"><div><span>Acquired</span><strong>${routing.summary.quantity_acquired}</strong></div><div><span>Routed</span><strong>${routing.summary.quantity_routed}</strong></div><div><span>Undecided</span><strong>${routing.summary.quantity_undecided}</strong></div><div><span>Basis difference</span><strong>${formatCents(routing.summary.difference_cents)}</strong></div></div><form id="intake-routing-form" data-revision="${routing.revision}">${lines}${complete ? "" : `<div class="wizard-actions"><button type="button" class="button secondary" data-action="back-acquisitions">Save & continue later</button><button class="button primary">${icon("scan-search")}Review routing</button></div>`}</form><p class="help-text">Singles cost remains pending until the established allocation workflow is finalized. Receipt and catalog provenance stay attached through each acquisition line.</p></section>`;
}

function wizardScreen(step) {
  if (step === "ACQUIRE") return wizardAcquireScreen();
  if (step === "PRODUCTS") return wizardProductsScreen();
  return wizardReviewScreen();
}

async function renderAcquisitionWizard(acquisitionId, options = {}) {
  try {
    const data = options.data || await api(`/api/acquisitions/${acquisitionId}`);
    state.activeAcquisition = data;
    const acquisition = data.acquisition;
    const legacyStepMap = { SOURCE: "PRODUCTS", ECONOMICS: "PRODUCTS", RECONCILIATION: "REVIEW" };
    const confirmedStates = ["READY_FOR_INTAKE", "INTAKE_IN_PROGRESS", "INTAKE_COMPLETE"];
    const step = [...confirmedStates, "CANCELED"].includes(acquisition.state) ? "REVIEW" : (legacyStepMap[acquisition.wizard_step] || acquisition.wizard_step || "ACQUIRE");
    const costStatus = acquisition.final_usd_paid_cents === null
      ? "Cost Unknown / Setup incomplete"
      : confirmedStates.includes(acquisition.state)
        ? `${formatCents(acquisition.final_usd_paid_cents)} authoritative landed cost`
        : `${formatCents(acquisition.final_usd_paid_cents)} draft final USD`;
    const canceled = acquisition.state === "CANCELED";
    const removal = data.removal || {};
    const removalAction = removal.can_recycle_draft
      ? `<button class="button danger" data-action="open-remove-acquisition" data-mode="recycle" data-id="${acquisition.id}">${icon("trash-2")}Move to Recycle Bin</button>`
      : removal.can_cancel_confirmed
        ? `<button class="button danger" data-action="open-remove-acquisition" data-mode="cancel" data-id="${acquisition.id}">${icon("ban")}Cancel acquisition</button>`
        : (removal.protected_history || removal.internal_economic_history) && !canceled ? `<span class="protected-removal-note" title="${escapeHtml(removal.blocked_message || "Use correction or reversal")}">${icon("lock-keyhole")}Protected history</span>` : "";
    app.innerHTML = `<div class="acquisition-wizard"><header class="wizard-shell-head"><button class="button secondary" data-action="back-acquisitions">${icon("arrow-left")}${[...confirmedStates, "CANCELED"].includes(acquisition.state) ? "Back to Inbound" : "Save incomplete & exit"}</button><div><span class="eyebrow">${escapeHtml(acquisition.acquisition_code)}</span><strong>${canceled ? "Canceled · history retained" : confirmedStates.includes(acquisition.state) ? acquisitionStateLabel(acquisition.state) : "ACQUISITION_INCOMPLETE · Setup incomplete"}</strong><small>${costStatus}</small></div><div class="wizard-shell-actions"><span class="autosave-indicator">${icon(canceled ? "archive" : "cloud-check")}${canceled ? "Read-only history" : confirmedStates.includes(acquisition.state) ? "Confirmed acquisition" : "Resumable draft"}</span>${removalAction}</div></header>${wizardProgress(step)}${wizardScreen(step)}</div>`;
    bindAcquisitionWizardForms();
    restoreAcquisitionWorkingState(app);
    refreshIcons();
    if (options.focusHeading) requestAnimationFrame(() => document.querySelector("#wizard-screen-title")?.focus());
    if (options.viewport) restoreLogicalViewport(options.viewport);
  } catch (error) { showError(error); }
}

function enqueueAcquisitionMutation(mutator) {
  const run = async () => {
    const result = await mutator(state.activeAcquisition);
    state.activeAcquisition = result;
    return result;
  };
  state.acquisitionMutation = state.acquisitionMutation.catch(() => {}).then(run);
  return state.acquisitionMutation;
}

function acquisitionAutosavePayload(form) {
  const raw = Object.fromEntries(new FormData(form).entries());
  const centsFields = ["purchase_subtotal", "acquisition_tax", "inbound_shipping", "acquisition_fees", "import_duties", "brokerage", "acquisition_discount", "final_usd_paid"];
  centsFields.forEach((name) => {
    if (!(name in raw)) return;
    const value = raw[name];
    raw[`${name}_cents`] = value === "" ? null : Math.round(Number(value) * 100);
    delete raw[name];
  });
  if ("original_foreign_amount_minor" in raw) raw.original_foreign_amount_minor = raw.original_foreign_amount_minor === "" ? null : Number(raw.original_foreign_amount_minor);
  if (raw.source_scope === "DOMESTIC") {
    raw.merchant_country = "";
    raw.original_currency = "";
    raw.original_foreign_amount_minor = null;
  }
  return raw;
}

function lineAutosavePayload(form) {
  const raw = Object.fromEntries(new FormData(form).entries());
  if ("quantity" in raw) raw.quantity = raw.quantity === "" ? null : Number(raw.quantity);
  return raw;
}

async function saveAcquisitionForm(form, quiet = false) {
  const fields = acquisitionAutosavePayload(form);
  const result = await enqueueAcquisitionMutation((current) => api(`/api/acquisitions/${current.acquisition.id}`, { method: "PATCH", body: JSON.stringify({ request_id: requestId("ACQ-AUTOSAVE"), expected_revision: current.acquisition.revision, ...fields }) }));
  const status = form.querySelector?.(".autosave-status");
  if (status) status.textContent = "Saved just now";
  if (!quiet) toast("Acquisition draft saved.");
  return result;
}

async function saveLineForm(form, quiet = false) {
  const fields = lineAutosavePayload(form);
  const result = await enqueueAcquisitionMutation((current) => api(`/api/acquisition-lines/${form.dataset.lineId}`, { method: "PATCH", body: JSON.stringify({ request_id: requestId("LINE-AUTOSAVE"), expected_revision: current.acquisition.revision, ...fields }) }));
  const status = form.querySelector?.(".autosave-status");
  if (status) status.textContent = "Saved just now";
  if (!quiet) toast("Product line saved.");
  return result;
}

async function saveCurrentWizardScreen() {
  const legacyStepMap = { SOURCE: "PRODUCTS", ECONOMICS: "PRODUCTS", RECONCILIATION: "REVIEW" };
  const persistedStep = state.activeAcquisition.acquisition.wizard_step || "ACQUIRE";
  const step = legacyStepMap[persistedStep] || persistedStep;
  if (step === "PRODUCTS") {
    for (const form of document.querySelectorAll(".acquisition-line-form")) await saveLineForm(form, true);
    const purchaseForm = document.querySelector("#acquisition-purchase-form");
    if (purchaseForm) await saveAcquisitionForm(purchaseForm, true);
  }
}

async function moveWizardTo(step, options = {}) {
  if (!ACQUISITION_WIZARD_STEPS.includes(step)) return;
  try {
    rememberAcquisitionWorkingState(app);
    if (options.saveCurrent) await saveCurrentWizardScreen();
    await enqueueAcquisitionMutation((current) => api(`/api/acquisitions/${current.acquisition.id}`, { method: "PATCH", body: JSON.stringify({ request_id: requestId("WIZARD-STEP"), expected_revision: current.acquisition.revision, wizard_step: step }) }));
    await renderAcquisitionWizard(state.activeAcquisition.acquisition.id, { data: state.activeAcquisition, focusHeading: true });
  } catch (error) { toast(error.message, "error"); }
}

function bindAcquisitionWizardForms() {
  document.querySelectorAll(".acquisition-line-form").forEach((form) => {
    form.addEventListener("submit", async (event) => { event.preventDefault(); try { await saveLineForm(form); } catch (error) { toast(error.message, "error"); } });
    form.addEventListener("change", async () => { try { await saveLineForm(form, true); } catch (error) { toast(error.message, "error"); } });
  });
  const purchaseForm = document.querySelector("#acquisition-purchase-form");
  if (purchaseForm) {
    const form = purchaseForm;
    form.addEventListener("submit", async (event) => { event.preventDefault(); try { await saveAcquisitionForm(form); } catch (error) { toast(error.message, "error"); } });
    form.addEventListener("change", async (event) => {
      if (event.target.type === "file") return;
      if (event.target.name === "source_scope") {
        form.querySelector(".international-fields").hidden = event.target.value !== "INTERNATIONAL";
      }
      try { await saveAcquisitionForm(form, true); } catch (error) { toast(error.message, "error"); }
    });
  }
  document.querySelector("#source-document-camera")?.addEventListener("change", (event) => handleSourceDocumentSelection(event, "CAMERA"));
  document.querySelector("#source-document-files")?.addEventListener("change", (event) => handleSourceDocumentSelection(event, "FILE_UPLOAD"));
  document.querySelector("#source-document-retry")?.addEventListener("change", (event) => handleSourceDocumentRetrySelection(event));
  document.querySelectorAll(".acquisition-allocation-form").forEach((form) => {
    form.addEventListener("submit", confirmAllocationForm);
    form.querySelectorAll("[name]").forEach((field) => {
      field.addEventListener("input", () => rememberAcquisitionWorkingState(app));
      field.addEventListener("change", () => rememberAcquisitionWorkingState(app));
    });
    if (form.dataset.confirmed === "true") {
      form.elements.assigned_landed_cost?.addEventListener("change", invalidateConfirmedAllocationForm);
      form.elements.allocation_method?.addEventListener("change", invalidateConfirmedAllocationForm);
    }
  });
  const exceptionForm = document.querySelector("#acquisition-exception-form");
  exceptionForm?.addEventListener("submit", (event) => event.preventDefault());
  exceptionForm?.querySelectorAll("[name]").forEach((field) => {
    field.addEventListener("input", () => rememberAcquisitionWorkingState(app));
    field.addEventListener("change", () => rememberAcquisitionWorkingState(app));
  });
  document.querySelector("#acquisition-confirm-form")?.addEventListener("submit", confirmAcquisitionForm);
  document.querySelector("#intake-routing-form")?.addEventListener("submit", previewIntakeRouting);
  document.querySelector("#upc-scan-form")?.addEventListener("submit", scanUpcForm);
  document.querySelector("#upc-scan-input")?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    event.currentTarget.form?.requestSubmit();
  });
  document.querySelectorAll(".catalog-search-form").forEach((form) => form.addEventListener("submit", searchCatalogForm));
  document.querySelector("#unknown-product-form")?.addEventListener("submit", identifyUnknownProductForm);
  document.querySelectorAll(".receipt-classification-form").forEach((form) => form.addEventListener("submit", saveReceiptClassification));
  document.querySelectorAll(".receipt-semantic-form").forEach((form) => form.addEventListener("submit", saveReceiptSemanticDecision));
}

async function receiptMutation(path, options = {}) {
  rememberAcquisitionWorkingState(app);
  const viewport = captureLogicalViewport();
  try {
    let response;
    const run = async () => {
      const current = state.activeAcquisition;
      response = await api(path, {
        method: "POST",
        body: JSON.stringify({ request_id: requestId(options.prefix || "RECEIPT"), expected_revision: current.acquisition.revision, ...(options.fields || {}) }),
      });
      state.activeAcquisition = response.acquisition_payload || current;
      return state.activeAcquisition;
    };
    state.acquisitionMutation = state.acquisitionMutation.catch(() => {}).then(run);
    await state.acquisitionMutation;
    toast(options.success || "Receipt review updated.");
    await renderAcquisitionWizard(state.activeAcquisition.acquisition.id, { data: state.activeAcquisition, viewport });
    return response;
  } catch (error) {
    toast(error.message, "error");
    return null;
  }
}

async function extractSourceDocument(documentId) {
  return receiptMutation(`/api/acquisition-documents/${documentId}/extractions`, { prefix: "RECEIPT-EXTRACT", success: "Purchase-detail suggestions are ready to review." });
}

async function retryReceiptExtraction(jobUuid) {
  return receiptMutation(`/api/receipt-extractions/${encodeURIComponent(jobUuid)}/retry`, { prefix: "RECEIPT-RETRY", success: "Receipt extraction retry completed." });
}

async function selectReceiptManualFallback() {
  return receiptMutation(`/api/acquisitions/${state.activeAcquisition.acquisition.id}/receipt-manual-fallback`, {
    prefix: "RECEIPT-MANUAL-FALLBACK",
    fields: { confirm_manual_fallback: true },
    success: "Manual purchase facts selected. The receipt remains attached as supporting evidence.",
  });
}

async function useReceiptCandidate(candidateId) {
  return receiptMutation(`/api/acquisitions/${state.activeAcquisition.acquisition.id}/receipt-candidates/apply`, { prefix: "RECEIPT-CANDIDATE-USE", fields: { candidate_ids: [Number(candidateId)] }, success: "Suggestion added to the draft for your review." });
}

async function rejectReceiptCandidate(candidateId) {
  if (!confirm("Reject this extracted suggestion? The candidate and decision remain in audit history.")) return;
  return receiptMutation(`/api/receipt-candidates/${candidateId}/disposition`, { prefix: "RECEIPT-CANDIDATE-REJECT", fields: { disposition: "REJECTED", reason: "Operator rejected during receipt review" }, success: "Suggestion rejected; audit history retained." });
}

async function acceptReceiptMatch(matchId) {
  return receiptMutation(`/api/receipt-line-matches/${matchId}/disposition`, { prefix: "RECEIPT-MATCH-ACCEPT", fields: { disposition: "ACCEPTED", notes: "Operator confirmed suggested product match" }, success: "Product match accepted as an operator decision." });
}

async function saveReceiptClassification(event) {
  event.preventDefault();
  const form = event.currentTarget;
  return receiptMutation(`/api/receipt-lines/${form.dataset.lineId}/classification`, { prefix: "RECEIPT-CLASSIFY", fields: { classification: form.elements.classification.value }, success: "Receipt-line classification saved." });
}

async function chooseReceiptClassification(lineId, classification) {
  return receiptMutation(`/api/receipt-lines/${lineId}/classification`, {
    prefix: "RECEIPT-BUSINESS-CLASSIFICATION",
    fields: { classification },
    success: "Business classification saved. DEX recalculated the acquisition.",
  });
}

async function saveReceiptSemanticDecision(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const selected = form.elements.semantic_class.value;
  const current = form.dataset.currentClass;
  const action = selected === "UNKNOWN" ? "MARK_UNRESOLVED" : selected === current ? "CONFIRM" : "CHANGE";
  return receiptMutation(`/api/receipt-semantic-lines/${encodeURIComponent(form.dataset.semanticUuid)}/decision`, {
    prefix: "RECEIPT-SEMANTIC",
    fields: {
      action,
      semantic_class: selected,
      reason_code: form.elements.reason_code.value,
      notes: form.elements.notes.value,
    },
    success: action === "CONFIRM" ? "Receipt meaning confirmed; original evidence retained." : "Receipt meaning updated; correction history retained.",
  });
}

async function markReceiptSemanticUnresolved(semanticUuid) {
  return receiptMutation(`/api/receipt-semantic-lines/${encodeURIComponent(semanticUuid)}/decision`, {
    prefix: "RECEIPT-SEMANTIC-UNRESOLVED",
    fields: { action: "MARK_UNRESOLVED", reason_code: "OPERATOR_UNRESOLVED", notes: "Left unresolved during semantic review" },
    success: "Receipt meaning remains unresolved; no product match authority was created.",
  });
}

async function generateReceiptAllocation() {
  return receiptMutation(`/api/acquisitions/${state.activeAcquisition.acquisition.id}/receipt-allocation-proposals`, { prefix: "RECEIPT-ALLOCATE", fields: { auto_apply: true }, success: "Exact-cent allocation suggestion generated." });
}

async function enqueueCatalogAcquisitionMutation(requester) {
  let response;
  const run = async () => {
    response = await requester(state.activeAcquisition);
    const next = response?.acquisition?.acquisition ? response.acquisition : response;
    if (next?.acquisition && next?.lines) state.activeAcquisition = next;
    return state.activeAcquisition;
  };
  state.acquisitionMutation = state.acquisitionMutation.catch(() => {}).then(run);
  await state.acquisitionMutation;
  return response;
}

async function scanUpcForm(event) {
  event.preventDefault();
  if (state.upcScanPending) return;
  const form = event.currentTarget;
  const rawIdentifier = String(form.elements.raw_identifier.value || "").trim();
  if (!rawIdentifier) return;
  state.upcScanPending = true;
  const viewport = captureLogicalViewport();
  const scanRequestId = requestId("UPC-SCAN");
  try {
    const response = await enqueueCatalogAcquisitionMutation((current) => api(`/api/acquisitions/${current.acquisition.id}/product-scan`, {
      method: "POST",
      body: JSON.stringify({ request_id: scanRequestId, expected_revision: current.acquisition.revision, raw_identifier: rawIdentifier }),
    }));
    if (response.status === "UNKNOWN") {
      state.upcScanStatus = null;
      state.pendingUnknownProduct = { identifier: response.identifier, mode: null };
      state.catalogSearchResults = [];
      toast("Product not recognized. Identify it without guessing.", "error");
    } else {
      state.pendingUnknownProduct = null;
      state.catalogSearchResults = [];
      state.upcScanStatus = { status: "RECOGNIZED", product: response.product, quantity: response.scan.quantity };
      toast(`${response.product.display_name} ×${response.scan.quantity}`);
    }
  } catch (error) { toast(error.message, "error"); }
  finally { state.upcScanPending = false; }
  await renderAcquisitionWizard(state.activeAcquisition.acquisition.id, { data: state.activeAcquisition, viewport });
  requestAnimationFrame(() => document.querySelector("#upc-scan-input")?.focus());
}

async function searchCatalogForm(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const query = String(form.elements.catalog_query.value || "").trim();
  const mode = form.dataset.catalogSearchMode || "manual";
  state.catalogSearchQueries[mode] = query;
  try {
    const response = await api(`/api/catalog/products?q=${encodeURIComponent(query)}`);
    state.catalogSearchResults = response.products || [];
    const viewport = captureLogicalViewport();
    await renderAcquisitionWizard(state.activeAcquisition.acquisition.id, { data: state.activeAcquisition, viewport });
    requestAnimationFrame(() => document.querySelector(`.catalog-search-form[data-catalog-search-mode="${mode}"] input[name="catalog_query"]`)?.focus());
  } catch (error) { toast(error.message, "error"); }
}

async function identifyUnknownWithCatalog(productId, rememberMapping) {
  const pending = state.pendingUnknownProduct;
  if (!pending) return;
  const viewport = captureLogicalViewport();
  try {
    const response = await enqueueCatalogAcquisitionMutation((current) => api(`/api/acquisitions/${current.acquisition.id}/identify-product`, {
      method: "POST",
      body: JSON.stringify({
        request_id: requestId("UPC-IDENTIFY-CATALOG"), expected_revision: current.acquisition.revision,
        raw_identifier: pending.identifier.raw_identifier, identifier_type: pending.identifier.identifier_type,
        catalog_product_id: Number(productId), remember_mapping: Boolean(rememberMapping),
      }),
    }));
    state.upcScanStatus = { status: "RECOGNIZED", product: response.product, quantity: response.scan.quantity };
    state.pendingUnknownProduct = null;
    state.catalogSearchResults = [];
    toast(rememberMapping ? "Product identified and UPC remembered." : "Product identified for this acquisition only.");
    await renderAcquisitionWizard(state.activeAcquisition.acquisition.id, { data: state.activeAcquisition, viewport });
  } catch (error) { toast(error.message, "error"); }
}

async function identifyUnknownProductForm(event) {
  event.preventDefault();
  const pending = state.pendingUnknownProduct;
  if (!pending) return;
  const form = event.currentTarget;
  const fields = Object.fromEntries(new FormData(form).entries());
  fields.remember_mapping = form.elements.remember_mapping.checked;
  const viewport = captureLogicalViewport();
  try {
    const response = await enqueueCatalogAcquisitionMutation((current) => api(`/api/acquisitions/${current.acquisition.id}/identify-product`, {
      method: "POST",
      body: JSON.stringify({
        request_id: requestId("UPC-IDENTIFY-MANUAL"), expected_revision: current.acquisition.revision,
        raw_identifier: pending.identifier.raw_identifier, identifier_type: pending.identifier.identifier_type, ...fields,
      }),
    }));
    state.upcScanStatus = { status: "RECOGNIZED", product: response.product, quantity: response.scan.quantity };
    state.pendingUnknownProduct = null;
    state.catalogSearchResults = [];
    toast(fields.remember_mapping ? "Product identified and UPC remembered." : "Product identified for this acquisition only.");
    await renderAcquisitionWizard(state.activeAcquisition.acquisition.id, { data: state.activeAcquisition, viewport });
  } catch (error) { toast(error.message, "error"); }
}

async function applyCatalogProduct(lineId, productId) {
  const viewport = captureLogicalViewport();
  try {
    await enqueueCatalogAcquisitionMutation((current) => api(`/api/acquisition-lines/${lineId}/catalog-product`, {
      method: "POST",
      body: JSON.stringify({ request_id: requestId("CATALOG-APPLY"), expected_revision: current.acquisition.revision, catalog_product_id: Number(productId) }),
    }));
    state.catalogSearchResults = [];
    toast("Catalog product applied. Enter or scan the physical quantity.");
    await renderAcquisitionWizard(state.activeAcquisition.acquisition.id, { data: state.activeAcquisition, viewport });
  } catch (error) { toast(error.message, "error"); }
}

async function openIdentifierHistory(identifierId) {
  try {
    const [history, catalog] = await Promise.all([
      api(`/api/catalog/identifiers/${identifierId}/history`),
      api("/api/catalog/products?include_inactive=1"),
    ]);
    const products = catalog.products || [];
    const names = new Map(products.map((product) => [Number(product.id), product.display_name]));
    const events = (history.events || []).map((item) => `<li><div><strong>${escapeHtml(titleCase(item.event_type))}</strong><small>${escapeHtml(formatDate(item.recorded_at))} · ${escapeHtml(item.reason_code || "Recorded")}</small></div><p>${item.from_catalog_product_id ? `${escapeHtml(names.get(Number(item.from_catalog_product_id)) || `Product ${item.from_catalog_product_id}`)} → ` : ""}${escapeHtml(names.get(Number(item.to_catalog_product_id)) || history.product.display_name)}${item.notes ? `<br>${escapeHtml(item.notes)}` : ""}</p></li>`).join("");
    const options = products.filter((product) => Number(product.id) !== Number(history.catalog_product_id)).map((product) => `<option value="${product.id}">${escapeHtml(product.display_name)} · ${escapeHtml(product.game)}${product.set_code ? ` · ${escapeHtml(product.set_code)}` : ""}</option>`).join("");
    openModal("UPC mapping details", `${history.identifier_type.replaceAll("_", "-")} ${history.raw_identifier}`, `<div class="mapping-history"><div class="mapping-current"><span>Current product</span><strong>${escapeHtml(history.product.display_name)}</strong><small>${escapeHtml(history.provenance)} · ${history.verified_at ? `Verified ${escapeHtml(formatDate(history.verified_at))}` : "Verification date Unknown"}</small></div><ol>${events}</ol><details class="mapping-correction"><summary>Correct this mapping</summary><p>This changes future recognition only. Prior mapping and scan events remain visible.</p><form id="mapping-correction-form" data-identifier-id="${history.id}"><label>Correct product<select name="catalog_product_id" required><option value="">Choose the correct catalog product</option>${options}</select></label><label>Reason<select name="reason_code" required><option value="">Choose reason</option><option value="WRONG_PRODUCT">Wrong product</option><option value="MANUFACTURER_CORRECTION">Manufacturer correction</option><option value="DUPLICATE_ENTRY">Duplicate entry</option><option value="OTHER">Other</option></select></label><label>Explanation<input name="notes" required placeholder="Explain why this mapping is changing"></label><button class="button danger">Record mapping correction</button></form></details></div>`);
    document.querySelector("#mapping-correction-form")?.addEventListener("submit", submitMappingCorrection);
  } catch (error) { toast(error.message, "error"); }
}

async function submitMappingCorrection(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const fields = Object.fromEntries(new FormData(form).entries());
  if (!confirm("Correct this UPC mapping for future scans? The original mapping history will remain.")) return;
  try {
    const result = await api(`/api/catalog/identifiers/${form.dataset.identifierId}/correct`, {
      method: "POST",
      body: JSON.stringify({ request_id: requestId("UPC-MAPPING-CORRECTION"), catalog_product_id: Number(fields.catalog_product_id), reason_code: fields.reason_code, notes: fields.notes }),
    });
    toast("UPC mapping corrected with append-only history.");
    closeModal();
    await renderAcquisitionWizard(state.activeAcquisition.acquisition.id);
    return result;
  } catch (error) { toast(error.message, "error"); }
}

async function confirmAllocationForm(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const amount = form.elements.assigned_landed_cost.value;
  const acquisitionId = state.activeAcquisition.acquisition.id;
  const viewport = captureLogicalViewport();
  rememberAcquisitionWorkingState(app);
  try {
    await enqueueAcquisitionMutation((current) => api(`/api/acquisition-lines/${form.dataset.lineId}/confirm-allocation`, { method: "POST", body: JSON.stringify({ request_id: requestId("ALLOCATION-CONFIRM"), expected_revision: current.acquisition.revision, assigned_landed_cost_cents: Math.round(Number(amount) * 100), allocation_method: form.elements.allocation_method.value, confirm_allocation: form.elements.confirm_allocation.checked }) }));
    clearAcquisitionWorkingLine(acquisitionId, form.dataset.lineId);
    toast("Product-line cost allocation confirmed.");
    await renderAcquisitionWizard(acquisitionId, { data: state.activeAcquisition, viewport });
  } catch (error) { toast(error.message, "error"); }
}

async function invalidateConfirmedAllocationForm(event) {
  const form = event.currentTarget.closest(".acquisition-allocation-form");
  if (!form || form.dataset.confirmed !== "true") return;
  const acquisitionId = state.activeAcquisition.acquisition.id;
  const viewport = captureLogicalViewport();
  rememberAcquisitionWorkingState(app);
  try {
    const amount = form.elements.assigned_landed_cost.value;
    await enqueueAcquisitionMutation((current) => api(`/api/acquisition-lines/${form.dataset.lineId}`, { method: "PATCH", body: JSON.stringify({
      request_id: requestId("ALLOCATION-INVALIDATE"), expected_revision: current.acquisition.revision,
      assigned_landed_cost_cents: Math.round(Number(amount) * 100), allocation_method: form.elements.allocation_method.value,
    }) }));
    clearAcquisitionWorkingLine(acquisitionId, form.dataset.lineId);
    toast("Allocation changed. Reconfirmation is required.");
    await renderAcquisitionWizard(acquisitionId, { data: state.activeAcquisition, viewport });
  } catch (error) { toast(error.message, "error"); }
}

async function confirmAcquisitionForm(event) {
  event.preventDefault();
  const exceptionForm = document.querySelector("#acquisition-exception-form");
  if (exceptionForm?.checkValidity && !exceptionForm.checkValidity()) {
    const resolution = exceptionForm.closest("details");
    if (resolution) resolution.open = true;
    exceptionForm.reportValidity();
    return;
  }
  const fields = exceptionForm?.elements || {};
  const reentered = fields.reentered_final_usd_paid;
  try {
    const discrepancyFields = {};
    if (fields.discrepancy_reason_code) discrepancyFields.discrepancy_reason_code = fields.discrepancy_reason_code.value;
    if (fields.discrepancy_notes) discrepancyFields.discrepancy_notes = fields.discrepancy_notes.value;
    if (fields.excluded_noninventory) discrepancyFields.excluded_noninventory_cents = fields.excluded_noninventory.value === "" ? null : Math.round(Number(fields.excluded_noninventory.value) * 100);
    if (fields.noninventory_treatment_code) discrepancyFields.noninventory_treatment_code = fields.noninventory_treatment_code.value;
    if (fields.noninventory_notes) discrepancyFields.noninventory_notes = fields.noninventory_notes.value;
    if (Object.keys(discrepancyFields).length) {
      await enqueueAcquisitionMutation((current) => api(`/api/acquisitions/${current.acquisition.id}`, { method: "PATCH", body: JSON.stringify({
        request_id: requestId("ACQ-EXCEPTION-AUTOSAVE"), expected_revision: current.acquisition.revision, ...discrepancyFields,
      }) }));
    }
    await enqueueAcquisitionMutation((current) => api(`/api/acquisitions/${current.acquisition.id}/confirm`, { method: "POST", body: JSON.stringify({
      request_id: requestId("ACQUISITION-CONFIRM"), expected_revision: current.acquisition.revision,
      confirm_authoritative_financial_facts: true,
      confirm_reconciliation: true,
      confirm_zero_cost: fields.confirm_zero_cost?.checked || false,
      confirm_material_discrepancy: fields.confirm_material_discrepancy?.checked || false,
      confirm_extreme_discrepancy: fields.confirm_extreme_discrepancy?.checked || false,
      confirm_noninventory_exclusion: fields.confirm_noninventory_exclusion?.checked || false,
      reentered_final_usd_paid_cents: reentered ? Math.round(Number(reentered.value) * 100) : undefined,
    }) }));
    state.acquisitionWorkingForms.delete(state.activeAcquisition.acquisition.id);
    toast(`${state.activeAcquisition.acquisition.acquisition_code} is Ready for Intake.`);
    await renderAcquisitionWizard(state.activeAcquisition.acquisition.id, { data: state.activeAcquisition, focusHeading: true });
  } catch (error) { toast(error.message, "error"); }
}

function intakeRoutingPayload(form) {
  const lines = [];
  form.querySelectorAll(".intake-route-line").forEach((row) => {
    const lineId = Number(row.dataset.lineId);
    const keep = Number(form.elements[`keep_${lineId}`]?.value || 0);
    const rip = Number(form.elements[`rip_${lineId}`]?.value || 0);
    const scan = Number(form.elements[`scan_${lineId}`]?.value || 0);
    if (keep || rip || scan) lines.push({ line_id: lineId, keep_sealed_quantity: keep, rip_open_quantity: rip, scan_identify_quantity: scan });
  });
  return { expected_revision: Number(form.dataset.revision), lines };
}

async function previewIntakeRouting(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = intakeRoutingPayload(form);
  if (!payload.lines.length) return toast("Choose at least one unit to keep sealed, rip/open, or scan & identify.", "error");
  try {
    const acquisitionId = state.activeAcquisition.acquisition.id;
    const preview = await api(`/api/acquisitions/${acquisitionId}/intake-routing/preview`, { method: "POST", body: JSON.stringify(payload) });
    state.intakeRoutingPreview = { acquisitionId, payload, preview };
    const rows = preview.lines.map((line) => {
      const actions = Object.entries(line.actions).filter(([, action]) => action.quantity).map(([name, action]) => `<li><span>${escapeHtml(titleCase(name))} · ${action.quantity}</span><strong>${formatCents(action.basis_cents)}</strong><small>Stable ordinal ${action.ordinal_start}${action.ordinal_end !== action.ordinal_start ? `–${action.ordinal_end}` : ""}</small></li>`).join("");
      return `<article class="intake-preview-line"><h4>Product line ${line.line_sequence} · ${escapeHtml(line.product_name || productClassLabel(line.product_class))}</h4><ul>${actions}</ul><p><span>Still undecided after confirmation</span><strong>${line.undecided_after_quantity}</strong><span>Basis held for later</span><strong>${formatCents(line.undecided_after_basis_cents)}</strong></p></article>`;
    }).join("");
    openModal("Confirm intake routing", "Review exact quantity, basis, and destination before DEX creates inventory records.", `<form id="confirm-intake-routing-form"><div class="intake-preview">${rows}</div><div class="intake-preview-total"><span>Quantity routed now</span><strong>${preview.summary.requested_quantity}</strong><span>Exact basis routed now</span><strong>${formatCents(preview.summary.requested_basis_cents)}</strong><span>Difference</span><strong>${formatCents(preview.summary.difference_cents)}</strong></div><label class="checkbox-label"><input name="confirm" type="checkbox" required><span>I confirm these quantities and destinations. Projected inventory will require correction or reversal rather than draft editing.</span></label><div class="form-actions"><button type="button" class="button secondary" data-action="close-modal">Go back</button><button class="button primary">${icon("route")}Confirm routing</button></div></form>`);
    document.querySelector("#confirm-intake-routing-form")?.addEventListener("submit", confirmIntakeRouting);
  } catch (error) { toast(error.message, "error"); }
}

async function confirmIntakeRouting(event) {
  event.preventDefault();
  const pending = state.intakeRoutingPreview;
  if (!pending) return toast("Routing preview expired. Review the routing again.", "error");
  try {
    await api(`/api/acquisitions/${pending.acquisitionId}/intake-routing/confirm`, {
      method: "POST",
      body: JSON.stringify({ ...pending.payload, request_id: requestId("INTAKE-ROUTE"), preview_token: pending.preview.preview_token, confirm_routing: true }),
    });
    closeModal();
    state.intakeRoutingPreview = null;
    const data = await api(`/api/acquisitions/${pending.acquisitionId}`);
    toast(data.acquisition.state === "INTAKE_COMPLETE" ? "Intake routing complete." : "Intake routing saved. Undecided quantity remains resumable.");
    await renderAcquisitionWizard(pending.acquisitionId, { data, viewport: captureLogicalViewport() });
  } catch (error) { toast(error.message, "error"); }
}

function imageDrop(side) {
  return `<label class="image-drop" id="${side}-drop">
    <input type="file" name="${side}" accept="image/jpeg,image/png,image/webp" required>
    <span>${icon(side === "front" ? "scan" : "image")}<b>${titleCase(side)}</b><br>Choose scanned image</span>
  </label>`;
}

function cardIngestForm(batch) {
  return `<div class="scan-form" data-viewport-key="scan-controls">
    <label class="bulk-drop">${icon("images")}<span><strong>Add a whole scan batch</strong><small>Select front/back files together; Dex pairs names first, then scan order.</small></span><input id="bulk-images" type="file" accept="image/jpeg,image/png,image/webp" multiple></label>
    <details class="single-card-panel">
      <summary>${icon("badge-plus")}Add One Card</summary>
      <form id="scan-card-form">
        <div class="image-pair">${imageDrop("front")}${imageDrop("back")}</div>
        <div class="form-grid">
          <label>Card Number<input name="card_number" placeholder="${batch.game === "One Piece" ? "OP16-112" : "121/191"}"></label>
          <label>Card Name<input name="name" placeholder="Boa Hancock"></label>
          <label>Rarity<select name="rarity"><option value="">Select rarity</option>${["Common","Uncommon","Rare","Super Rare","Secret Rare","Promo"].map((v) => `<option ${state.intakeDefaults.rarity === v ? "selected" : ""}>${v}</option>`).join("")}</select></label>
          <label>Variant<select name="variant">${["Standard","Alternate Art","Full Art","Parallel","Foil","Promo"].map((v) => `<option ${state.intakeDefaults.variant === v ? "selected" : ""}>${v}</option>`).join("")}</select></label>
        </div>
        <div class="form-actions"><button class="button primary">${icon("badge-plus")}Save and Next</button></div>
      </form>
    </details>
  </div>`;
}

function batchCardList(cards, batch) {
  if (!cards.length) return `<div class="scan-list">${emptyState("scan-line", "Waiting for the first card", "Add one pair or select a whole scan batch. Dex assigns every physical card its own SKU.")}</div>`;
  const review = cards.filter((card) => card.status === "REVIEW").length;
  const selected = state.selectedBatchCards.size;
  const identityCounts = batchIdentityCounts(cards);
  return `<section class="batch-cards" data-viewport-key="batch-cards"><div class="batch-grid-head"><div><h3>Batch Cards</h3><p>${cards.length} Scanned - ${cards.length - review} Ready - ${review} Need Review</p></div><div class="batch-select-actions"><button class="button secondary" data-action="sam-match-batch">${icon("sparkles")}SAM Match All</button><button class="button secondary" data-action="select-visible-batch">${icon("check-square")}Select All</button><button class="button secondary" data-action="clear-batch-selection" ${selected ? "" : "disabled"}>${icon("x")}Clear</button></div></div>
  <div class="bulk-action-bar ${selected ? "show" : ""}"><strong>${selected} Selected</strong><button class="button secondary" data-action="sam-match-selected">${icon("sparkles")}SAM Match Selected</button><button class="button secondary" data-action="bulk-edit">${icon("square-pen")}Bulk Edit</button><button class="button secondary" data-action="bulk-reprint-labels">${icon("printer")}Print/Reprint Labels</button><button class="button danger" data-action="bulk-recycle">${icon("trash-2")}Move to Recycle Bin</button></div>
  <div class="batch-card-grid">${cards.slice().reverse().map((card) => `<article class="batch-card ${state.selectedBatchCards.has(card.sku) ? "selected" : ""}" data-viewport-key="card-${escapeHtml(card.sku)}">
    <label class="batch-card-check" title="Select ${escapeHtml(card.sku)}"><input type="checkbox" data-batch-select="${escapeHtml(card.sku)}" ${state.selectedBatchCards.has(card.sku) ? "checked" : ""}></label>
    ${batchCountBadge(card, identityCounts)}
    ${card.front_image ? `<img src="/media/${encodeURI(card.front_image)}" alt="">` : `<div class="batch-card-placeholder">${icon("image")}</div>`}
    <div class="batch-card-body"><strong>${escapeHtml(card.name)}</strong><small>${escapeHtml(card.card_number || "Identification pending")}</small><code>${escapeHtml(card.sku)}</code><div class="batch-card-badges">${statusBadge(card.status)}${samBadge(card)}</div></div>
    <div class="batch-card-actions"><button class="icon-button" title="Reprint label" data-action="reprint-label" data-sku="${escapeHtml(card.sku)}">${icon("printer")}</button><button class="icon-button" title="Edit card" data-action="edit-card" data-sku="${escapeHtml(card.sku)}">${icon("square-pen")}</button></div>
  </article>`).join("")}</div>${batch.status === "OPEN" ? `<div class="bottom-finish-bar"><div><strong>${cards.length} Cards In Batch</strong><small>${review} Need Review - ${cards.length} Labels Will Queue</small></div><button class="button primary" data-action="complete-batch" data-id="${batch.id}">${icon("printer")}Finish & Print Labels</button></div>` : ""}</section>`;
}

function valuationLine(label, valuation) {
  const coverage = `${valuation.valued_count}/${valuation.total_count} cards valued`;
  return `<div class="estimate-value-row"><span>${escapeHtml(label)}</span><strong>${formatCents(valuation.known_value_cents)}</strong><small>${escapeHtml(coverage)} &bull; ${escapeHtml(valuation.freshness_label)}</small></div>`;
}

function estimatedEconomicsPanel(estimate) {
  const a = estimate.acquisition;
  const r = estimate.realized;
  const remaining = estimate.remaining;
  const excluded = estimate.excluded_recycled;
  const material = estimate.warnings.filter((warning) => warning.severity === "material");
  const info = estimate.warnings.filter((warning) => warning.severity !== "material");
  const warningBlock = estimate.warnings.length ? `<div class="estimate-warnings ${material.length ? "material" : ""}">
    <strong>${material.length ? "Economics may be materially understated" : "Estimate notes"}</strong>
    <ul>${[...material, ...info].map((warning) => `<li>${escapeHtml(warning.message)}</li>`).join("")}</ul>
  </div>` : "";
  const currentCoverage = `${remaining.market.valued_count}/${remaining.market.total_count} cards valued`;
  const listedCoverage = `${remaining.listed.valued_count}/${remaining.listed.total_count} cards valued`;
  return `<section class="estimated-economics" data-viewport-key="estimated-economics" aria-labelledby="estimated-economics-title">
    <div class="estimate-banner">${icon("triangle-alert")}<div><span>Estimated Economics</span><strong id="estimated-economics-title">${escapeHtml(estimate.notice)}</strong><small>Legacy preview only. Loading this panel does not write or repair inventory data.</small></div></div>
    ${warningBlock}
    <div class="estimate-sections">
      <details open><summary>Summary</summary><div class="estimate-summary-grid">
        <div><span>What did this cost?</span><strong>${a.cost_known ? formatCents(a.estimated_cost_cents) : "Cost Unknown / Incomplete"}</strong><small>${escapeHtml(a.label)}</small></div>
        <div><span>How much recovered?</span><strong>${formatCents(r.net_proceeds_cents, "$0.00")}</strong><small>${r.cost_recovery_percent === null ? "Recovery Unknown" : `${r.cost_recovery_percent}% estimated recovery`}</small></div>
        <div><span>What remains?</span><strong>${formatCents(remaining.market.known_value_cents, "$0.00")}</strong><small>${escapeHtml(currentCoverage)} &bull; known market value</small></div>
        <div><span>Ahead or behind?</span><strong>${formatCents(remaining.current_position_cents)}</strong><small>${remaining.current_position_complete ? "Estimated current position" : `Incomplete &bull; ${escapeHtml(currentCoverage)}`}</small></div>
      </div></details>
      <details open><summary>Realized Economics</summary><div class="estimate-grid">
        <div><span>Gross Merchandise Sales</span><strong>${formatCents(r.gross_merchandise_cents, "$0.00")}</strong></div>
        <div><span>Realized Net Proceeds</span><strong>${formatCents(r.net_proceeds_cents, "$0.00")}</strong></div>
        <div><span>Estimated Sold Basis</span><strong>${formatCents(r.estimated_sold_basis_cents)}</strong></div>
        <div><span>Estimated Realized P/L</span><strong>${formatCents(r.estimated_profit_loss_cents)}</strong></div>
      </div><p class="estimate-footnote">${escapeHtml(r.allocation_notice)}</p></details>
      <details open><summary>Unrealized / Remaining Value</summary><div class="estimate-value-list">
        ${valuationLine("Known Market Value", remaining.market)}
        ${valuationLine("Known Listed Value", remaining.listed)}
        <div class="estimate-value-row"><span>Current Economic Position</span><strong>${formatCents(remaining.current_position_cents)}</strong><small>${remaining.current_position_complete ? escapeHtml(currentCoverage) : `Incomplete &bull; ${escapeHtml(currentCoverage)}`}</small></div>
        <div class="estimate-value-row"><span>Projected Listed Position</span><strong>${formatCents(remaining.projected_listed_position_cents)}</strong><small>${remaining.projected_listed_position_complete ? escapeHtml(listedCoverage) : `Incomplete &bull; ${escapeHtml(listedCoverage)}`}</small></div>
      </div></details>
      <details ${excluded.card_count ? "open" : ""}><summary>Excluded / Recycled (${excluded.card_count})</summary><div class="estimate-grid">
        <div><span>Estimated Basis</span><strong>${formatCents(excluded.estimated_basis_cents)}</strong></div>
        <div><span>Known Market Value</span><strong>${formatCents(excluded.market.known_value_cents, "$0.00")}</strong><small>${excluded.market.valued_count}/${excluded.market.total_count} cards valued</small></div>
      </div><p class="estimate-footnote">Excluded values do not inflate active remaining inventory.</p></details>
    </div><div class="estimate-version">Calculation version: ${escapeHtml(estimate.calculation_version)}</div>
  </section>`;
}

function acquisitionFactsPanel(facts) {
  const cost = facts.authoritative_cost;
  const breakdown = facts.cost_breakdown;
  const group = facts.receipt_group;
  const groupBatches = Array.isArray(group?.batches) ? group.batches : [];
  const difference = breakdown.difference_cents;
  const reconciliation = difference === null
    ? "Incomplete — final USD amount is unknown"
    : difference === 0
      ? "Reconciled exactly"
      : `${formatCents(Math.abs(difference))} ${difference > 0 ? "unitemized" : "over-itemized"}${breakdown.acknowledged ? " — acknowledged" : ""}`;
  const groupRows = groupBatches.map((batch) => `<li><strong>${escapeHtml(batch.batch_code)}</strong><span>${escapeHtml(batch.product_name || "Unnamed product")}</span><em>${formatCents(batch.final_usd_paid_cents)}</em></li>`).join("");
  const acquisitionAction = facts.economics_status === "FINALIZED"
    ? `<span class="badge green">Basis finalized · audited corrections only</span>`
    : `<button class="button secondary" data-action="edit-acquisition">${icon("receipt-text")}Edit acquisition</button>`;
  return `<section class="acquisition-facts" aria-labelledby="acquisition-facts-title">
    <div class="acquisition-facts-head"><div><span>Phase 3 Acquisition Facts</span><h3 id="acquisition-facts-title">${escapeHtml(facts.product_name || "Acquisition details incomplete")}</h3><p>USD is authoritative. Original-currency values are reference only; no FX calculation is performed.</p></div>${acquisitionAction}</div>
    <div class="acquisition-facts-grid">
      <div><span>Final USD paid</span><strong>${cost.known ? formatCents(cost.final_usd_paid_cents) : "Cost Unknown / Incomplete"}</strong><small>Authoritative landed cost</small></div>
      <div><span>Acquisition mode</span><strong>${escapeHtml(titleCase(facts.economics_mode))}</strong><small>${facts.units_acquired === null ? "Quantity incomplete" : `${facts.units_acquired} sealed unit(s)`}</small></div>
      <div><span>Receipt / Group</span><strong>${escapeHtml(group.reference || "Not grouped")}</strong><small>Informational link only</small></div>
      <div><span>USD reconciliation</span><strong>${escapeHtml(reconciliation)}</strong><small>Components: ${formatCents(breakdown.component_total_cents, "$0.00")}</small></div>
    </div>
    <details><summary>Cost breakdown and references</summary><div class="acquisition-breakdown">
      <div><span>Subtotal</span><strong>${formatCents(breakdown.purchase_subtotal_cents)}</strong></div>
      <div><span>Tax</span><strong>${formatCents(breakdown.acquisition_tax_cents)}</strong></div>
      <div><span>Inbound shipping</span><strong>${formatCents(breakdown.inbound_shipping_cents)}</strong></div>
      <div><span>Fees</span><strong>${formatCents(breakdown.acquisition_fees_cents)}</strong></div>
      <div><span>Discounts</span><strong>${formatCents(breakdown.acquisition_discount_cents)}</strong></div>
      <div><span>Original reference</span><strong>${facts.original_foreign_amount_minor === null ? "Not provided" : `${escapeHtml(facts.original_currency)} ${centsInputValue(facts.original_foreign_amount_minor)}`}</strong></div>
    </div></details>
    ${group.reference ? `<details><summary>Receipt / Acquisition Group (${groupBatches.length} batch${groupBatches.length === 1 ? "" : "es"})</summary><ul class="receipt-group-list">${groupRows}</ul><p class="acquisition-notice">${escapeHtml(group.notice)}</p></details>` : ""}
    <div class="acquisition-version">Status: ${escapeHtml(facts.economics_status)} · Calculation version: ${escapeHtml(facts.calculation_version)}</div>
  </section>`;
}

function ripSessionsPanel(rips) {
  const active = rips?.active_intake || null;
  const ripSessions = Array.isArray(rips?.sessions) ? rips.sessions : [];
  const banner = active ? `<div class="rip-active-banner" data-viewport-key="active-rip-banner">${icon("scan-line")}<div><strong>Scanner intake is currently assigned to ${escapeHtml(active.rip_code)} / ${escapeHtml(active.product_name || "Unnamed product")}.</strong><span>New browser and scanner cards for that batch will join this rip until intake is stopped or the rip is finalized.</span></div></div>` : "";
  const sessions = ripSessions.map((rip) => {
    const rec = rip?.reconciliation || {};
    const cards = Array.isArray(rip?.cards) ? rip.cards : [];
    const events = Array.isArray(rip?.events) ? rip.events : [];
    const finalized = rip.status === "FINALIZED";
    return `<article class="rip-session-card" data-viewport-key="rip-${rip.id}"><div><span>${escapeHtml(rip.rip_code)}</span><strong>${escapeHtml(rip.status)}</strong><small>${rip.units_opened ? `${rip.units_opened} sealed unit(s) opened` : "Singles allocation"} · ${cards.length} allocated/intake card(s)</small></div>
      <div class="rip-session-values"><span>Rip cost <b>${formatCents(rec.rip_cost_cents)}</b></span><span>Scanned basis <b>${formatCents(rec.scanned_card_basis_cents, "$0.00")}</b></span><span>Bulk reserve <b>${formatCents(rec.bulk_reserve_basis_cents, "$0.00")}</b></span></div>
      <div class="rip-session-actions">${!finalized && !rip.active_for_intake ? `<button class="button secondary" data-action="activate-rip" data-id="${rip.id}">${icon("play")}Start intake</button>` : ""}${rip.active_for_intake ? `<button class="button danger" data-action="deactivate-rip" data-id="${rip.id}">${icon("square")}Stop intake</button>` : ""}${!finalized ? `<button class="button primary" data-action="finalize-rip" data-id="${rip.id}">${icon("badge-check")}Review & finalize</button>` : `<button class="button secondary" data-action="correct-rip" data-id="${rip.id}">${icon("history")}Audited correction</button>`}</div>
      ${finalized ? `<small class="rip-history-note">Finalized ${formatDate(rip.finalized_at)} · ${events.length} immutable economic event(s) · valuation ${rip.valuation_complete ? "complete" : "incomplete"}</small>` : ""}</article>`;
  }).join("");
  return `${banner}<section class="rip-sessions" data-viewport-key="rip-sessions" aria-labelledby="rip-sessions-title"><div class="section-header"><div><span>Phase 4</span><h3 id="rip-sessions-title">Rip Sessions & Cost Allocation</h3><p>Intake begins only when you explicitly start a session. Batch completion and labels remain independent.</p></div><button class="button secondary" data-action="create-rip">${icon("package-open")}New rip session</button></div>${sessions || `<p class="acquisition-notice">No rip session exists. Scanner intake is not assigned to economics until you create and start one.</p>`}</section>`;
}

function sealedUnitsPanel(sealed, corrections = null) {
  if (!sealed) return "";
  const c = sealed.counts;
  const unitRows = (Array.isArray(sealed.units) ? sealed.units : []).map((unit) => `<tr><td>${escapeHtml(unit.unit_code)}</td><td>${unit.unit_sequence}</td><td><span class="badge ${unit.status === "REMAINING" ? "green" : unit.status === "SOLD" ? "blue" : ""}">${escapeHtml(titleCase(unit.status))}</span></td><td>${formatCents(unit.basis_cents)}</td><td>${unit.status === "REMAINING" ? `<button class="button secondary" data-action="adjust-sealed" data-id="${unit.id}" data-code="${escapeHtml(unit.unit_code)}" ${corrections ? "" : "title=\"Finalize or economically lock the acquisition first\""}>Correct / dispose</button>` : "—"}</td></tr>`).join("");
  return `<section class="sealed-units-panel" data-viewport-key="sealed-units" aria-labelledby="sealed-units-title"><div class="section-header"><div><span>Phase 5</span><h3 id="sealed-units-title">Sealed Unit Inventory</h3><p>Each unit has a stable internal identity and exact landed basis. Receipt groups do not change these batch-level facts.</p></div><button class="button secondary" data-action="sell-sealed">${icon("package-check")}Sell sealed units</button></div><div class="acquisition-facts-grid"><div><span>Acquired</span><strong>${sealed.units_acquired}</strong></div><div><span>Opened</span><strong>${c.opened}</strong></div><div><span>Sold sealed</span><strong>${c.sold}</strong></div><div><span>Remaining</span><strong>${c.remaining}</strong></div><div><span>Corrected / adjusted</span><strong>${c.corrected_adjusted}</strong></div><div><span>Difference</span><strong>${sealed.reconciliation.difference}</strong></div></div><details><summary>Exact sealed units and basis</summary><div class="table-wrap"><table><thead><tr><th>Unit</th><th>Sequence</th><th>State</th><th>Basis</th><th>Correction</th></tr></thead><tbody>${unitRows}</tbody></table></div></details><p class="acquisition-notice">${sealed.units_acquired} acquired = ${c.opened} opened + ${c.sold} sold + ${c.remaining} remaining + ${c.corrected_adjusted} corrected/adjusted. ${escapeHtml(sealed.group_notice)}</p></section>`;
}

function economicsValueRow(label, value, valuation) {
  return `<div class="economics-value-row"><span>${escapeHtml(label)}</span><strong>${formatCents(value, "$0.00")}</strong><small>${escapeHtml(valuation.coverage_label)} &bull; ${escapeHtml(valuation.freshness_label)}</small></div>`;
}

function economicsRipHistory(rips) {
  const sessions = Array.isArray(rips?.sessions) ? rips.sessions : [];
  const rows = sessions.flatMap((rip) => (Array.isArray(rip.events) ? rip.events : []).map((event) => `<tr><td><strong>${escapeHtml(rip.rip_code)}</strong><small>${escapeHtml(rip.status)}</small></td><td>${escapeHtml(titleCase(event.event_type))}</td><td><code>${escapeHtml(event.event_id)}</code></td><td>${formatDate(event.effective_at)}</td><td>${formatDate(event.recorded_at)}</td><td>${escapeHtml(event.reason_code || "—")}${event.notes ? `<small>${escapeHtml(event.notes)}</small>` : ""}</td></tr>`));
  if (!rows.length) return `<p class="economics-empty">No finalized allocation or correction events yet.</p>`;
  return `<div class="table-wrap economics-history"><table><thead><tr><th>Rip</th><th>Event</th><th>Immutable ID</th><th>Effective</th><th>Recorded</th><th>Reason / notes</th></tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
}

function economicsSales(report) {
  const orders = Array.isArray(report.sales?.orders) ? report.sales.orders : [];
  if (!orders.length) return `<p class="economics-empty">No card or sealed sales are attributed to this batch.</p>`;
  return `<div class="economics-order-list">${orders.map((order) => {
    const items = Array.isArray(order.items) ? order.items : [];
    const action = order.order_type === "SEALED"
      ? `<button class="button secondary" data-action="open-sealed-order" data-id="${order.order_id}">${icon("eye")}Details</button>`
      : order.order_number ? `<button class="button secondary" data-action="search-sale-order" data-order="${escapeHtml(order.order_number)}">${icon("search")}Find cards</button>` : "";
    return `<details class="economics-order ${order.canceled ? "canceled" : ""}"><summary><span><strong>${escapeHtml(order.order_number || `Order #${order.order_id}`)}</strong><small>${escapeHtml(titleCase(order.order_type))} &bull; ${escapeHtml(order.platform)} &bull; ${formatDate(order.sold_at)}${order.canceled ? " &bull; Canceled / excluded from realized totals" : ""}</small></span><span><b>${formatCents(order.net_proceeds_cents, "$0.00")}</b><small>Attributable net proceeds</small></span></summary><div class="economics-order-body"><div class="economics-mini-grid"><div><span>Merchandise</span><strong>${formatCents(order.gross_merchandise_cents, "$0.00")}</strong></div><div><span>Shipping collected</span><strong>${formatCents(order.shipping_collected_cents, "$0.00")}</strong></div><div><span>Fees</span><strong>${formatCents(order.marketplace_fees_cents, "$0.00")}</strong></div><div><span>Postage</span><strong>${formatCents(order.actual_postage_cents, "$0.00")}</strong></div><div><span>Sold basis</span><strong>${formatCents(order.sold_basis_cents)}</strong></div><div><span>Realized P/L</span><strong>${formatCents(order.realized_profit_loss_cents)}</strong></div></div><ul class="economics-item-list">${items.map((item) => `<li><code>${escapeHtml(item.identifier)}</code><span>${escapeHtml(titleCase(item.item_type))} &bull; basis ${formatCents(item.basis_cents)}</span><em>Net ${formatCents(item.net_proceeds_cents, "$0.00")}</em></li>`).join("")}</ul><div class="economics-order-footer"><small>${escapeHtml(order.attribution)}</small>${action}</div></div></details>`;
  }).join("")}</div>`;
}

function correctionsPanel(corrections) {
  if (!corrections) return `<div class="corrections-unavailable"><strong>Audited corrections are not active yet.</strong><span>Finalize the allocation, or economically lock a sealed acquisition by opening or selling a unit, before recording Phase 7A events.</span></div>`;
  const events = Array.isArray(corrections.events) ? corrections.events : [];
  const rows = events.map((event) => `<tr><td><strong>${escapeHtml(titleCase(event.event_type))}</strong><small>${escapeHtml(event.reason_code)}</small></td><td><code>${escapeHtml(event.event_id)}</code></td><td>${formatDate(event.effective_at)}<small>Recorded ${formatDate(event.recorded_at)}</small></td><td>${escapeHtml(event.notes)}</td><td>${event.reversible ? `<button class="button secondary" data-action="reverse-economic-event" data-id="${escapeHtml(event.event_id)}">Reverse</button>` : event.reversed ? `<span class="badge">Reversed</span>` : "—"}</td></tr>`).join("");
  return `<section class="phase7a-panel" data-viewport-key="phase7a-corrections"><div class="section-header"><div><span>Phase 7A &bull; Append-only</span><h3>Corrections &amp; Dispositions</h3><p>Original source facts stay preserved. Every correction has an immutable event ID, effective date, recorded timestamp, reason, notes, and linked reversal history.</p></div><div class="phase7a-actions"><button class="button secondary" data-action="correct-acquisition-cost">Correct acquisition cost</button><button class="button secondary" data-action="transfer-basis">Transfer card / bulk basis</button></div></div><div class="economics-mini-grid"><div><span>Preserved source cost</span><strong>${formatCents(corrections.acquisition_cost.preserved_source_cents)}</strong></div><div><span>Correction delta</span><strong>${formatCents(corrections.acquisition_cost.correction_delta_cents, "$0.00")}</strong></div><div><span>Current authoritative cost</span><strong>${formatCents(corrections.acquisition_cost.current_authoritative_cents)}</strong></div><div><span>Operational loss / disposition</span><strong>${formatCents(corrections.operational_loss_cents, "$0.00")}</strong><small>Operational economics only; no tax conclusion</small></div></div>${rows ? `<div class="table-wrap economics-history"><table><thead><tr><th>Event</th><th>Immutable ID</th><th>When</th><th>Notes</th><th>Action</th></tr></thead><tbody>${rows}</tbody></table></div>` : `<p class="economics-empty">No Phase 7A correction or disposition events recorded.</p>`}</section>`;
}

function batchEconomicsInterface(report, acquisition, rips, sealed, corrections) {
  const realized = report.realized;
  const remaining = report.remaining;
  const excluded = report.excluded;
  const rec = report.reconciliation;
  const group = report.receipt_group_rollup;
  const material = report.warnings.filter((warning) => warning.severity === "material");
  const warnings = report.warnings.map((warning) => `<li class="${warning.severity === "material" ? "material" : ""}"><strong>${escapeHtml(warning.code.replaceAll("_", " "))}</strong><span>${escapeHtml(warning.message)}</span></li>`).join("");
  const groupPanel = group ? `<div class="economics-group-rollup"><div class="economics-group-head"><div><span>Receipt / Acquisition Group</span><strong>${escapeHtml(group.reference)}</strong></div><small>${escapeHtml(group.notice)}</small></div><div class="economics-mini-grid"><div><span>Assigned cost</span><strong>${formatCents(group.authoritative_assigned_cost_cents)}</strong><small>${group.cost_coverage.known}/${group.cost_coverage.total} batches authoritative</small></div><div><span>Recovered</span><strong>${formatCents(group.realized.net_proceeds_cents, "$0.00")}</strong><small>${formatPercent(group.realized.cost_recovery_percent)} cost recovery</small></div><div><span>Known market value</span><strong>${formatCents(group.remaining.market.known_value_cents, "$0.00")}</strong><small>${escapeHtml(group.remaining.market.coverage_label)}</small></div><div><span>Unique orders</span><strong>${group.realized.unique_order_count}</strong><small>Counted once across the group</small></div></div><p>${escapeHtml(group.realized.allocation_notice)}</p></div>` : "";
  const quantity = rec.sealed_quantity;
  return `<section class="batch-economics" data-viewport-key="batch-economics" aria-labelledby="batch-economics-title"><div class="batch-economics-head"><div><span>Phase 6 &bull; Backend-calculated</span><h2 id="batch-economics-title">Batch Economics</h2><p>Realized results and unrealized values remain separate. No calculated dashboard total is stored.</p></div><div><span class="badge ${report.batch.economics_status === "FINALIZED" ? "green" : "amber"}">${escapeHtml(titleCase(report.batch.economics_status))}</span><button class="button secondary" data-action="export-batch-economics" data-id="${report.batch.id}">${icon("download")}Batch CSV</button></div></div>${material.length ? `<div class="economics-material-warning">${icon("triangle-alert")}<div><strong>Economics are incomplete</strong><span>${material.length} material coverage or reconciliation warning(s) require attention.</span></div></div>` : ""}<div class="batch-economics-sections">
    <details open data-economics-section="summary"><summary>Summary</summary><div class="economics-summary-grid"><div><span>What did this cost?</span><strong>${formatCents(report.summary.authoritative_cost_cents)}</strong><small>Authoritative final USD paid</small></div><div><span>How much have I recovered?</span><strong>${formatCents(report.summary.realized_net_proceeds_cents, "$0.00")}</strong><small>${formatPercent(realized.cost_recovery_percent)} cost recovery &bull; may exceed 100%</small></div><div><span>What remains?</span><strong>${formatCents(report.summary.known_remaining_market_value_cents, "$0.00")}</strong><small>${escapeHtml(remaining.market.coverage_label)}</small></div><div class="${report.summary.current_position_complete ? "" : "incomplete"}"><span>Am I currently ahead or behind?</span><strong>${formatCents(report.summary.current_economic_position_cents)}</strong><small>${report.summary.current_position_complete ? "Complete current position" : `Incomplete &bull; ${escapeHtml(remaining.market.coverage_label)}`}</small></div></div><div class="economics-version">Calculation version: ${escapeHtml(report.calculation_version)} &bull; Generated ${escapeHtml(report.generated_at)}</div></details>
    <details data-economics-section="acquisition"><summary>Acquisition</summary><div class="economics-section-body">${acquisitionFactsPanel(acquisition)}${groupPanel}</div></details>
    <details data-economics-section="recovery"><summary>Recovery &amp; P/L <small>Realized Economics</small></summary><div class="economics-section-body"><div class="economics-metric-grid"><div><span>Gross merchandise</span><strong>${formatCents(realized.gross_merchandise_cents, "$0.00")}</strong></div><div><span>Shipping collected</span><strong>${formatCents(realized.shipping_collected_cents, "$0.00")}</strong></div><div><span>Marketplace fees</span><strong>${formatCents(realized.marketplace_fees_cents, "$0.00")}</strong></div><div><span>Actual postage</span><strong>${formatCents(realized.actual_postage_cents, "$0.00")}</strong></div><div><span>Realized net proceeds</span><strong>${formatCents(realized.net_proceeds_cents, "$0.00")}</strong></div><div><span>Sold basis</span><strong>${formatCents(realized.sold_basis_cents)}</strong><small>${realized.sold_basis_known_count}/${realized.sold_basis_total_count} sold items with basis</small></div><div><span>Realized P/L</span><strong>${formatCents(realized.realized_profit_loss_cents)}</strong><small>${realized.sold_basis_complete ? "Complete" : "Incomplete sold basis"}</small></div><div><span>Cost Recovery %</span><strong>${formatPercent(realized.cost_recovery_percent)}</strong><small>${escapeHtml(realized.cost_recovery_definition)}</small></div></div><p class="economics-notice">Market value and listed value are not realized profit. ${escapeHtml(realized.allocation_notice)}</p></div></details>
    <details data-economics-section="remaining"><summary>Remaining Inventory <small>Unrealized / Remaining Value</small></summary><div class="economics-section-body"><div class="economics-value-list">${economicsValueRow("Known remaining market value", remaining.market.known_value_cents, remaining.market)}${economicsValueRow("Known remaining listed value", remaining.listed.known_value_cents, remaining.listed)}<div class="economics-value-row ${remaining.current_position_complete ? "" : "incomplete"}"><span>Current Economic Position</span><strong>${formatCents(remaining.current_economic_position_cents)}</strong><small>${remaining.current_position_complete ? "Complete" : "Incomplete"} &bull; ${escapeHtml(remaining.market.coverage_label)}</small></div><div class="economics-value-row ${remaining.projected_listed_position_complete ? "" : "incomplete"}"><span>Projected Listed Position</span><strong>${formatCents(remaining.projected_listed_position_cents)}</strong><small>${remaining.projected_listed_position_complete ? "Complete" : "Incomplete"} &bull; ${escapeHtml(remaining.listed.coverage_label)}</small></div></div><p class="economics-notice">${escapeHtml(remaining.current_position_definition)}. ${escapeHtml(remaining.projected_listed_position_definition)}. Missing market and listed values are never substituted for one another.</p><div class="economics-mini-grid"><div><span>Active cards</span><strong>${remaining.active_card_count}</strong></div><div><span>Remaining sealed</span><strong>${remaining.remaining_sealed_unit_count}</strong></div><div><span>Known bulk quantity</span><strong>${remaining.known_bulk_quantity}</strong></div><div><span>Known remaining basis</span><strong>${formatCents(remaining.known_basis_cents)}</strong><small>${remaining.basis_complete ? "Complete" : "Incomplete"}</small></div></div><details class="economics-excluded" ${excluded.recycled_card_count || excluded.adjusted_sealed_unit_count || excluded.operational_loss_cents ? "open" : ""}><summary>Excluded / Recycled</summary><div class="economics-mini-grid"><div><span>Recycled cards</span><strong>${excluded.recycled_card_count}</strong></div><div><span>Adjusted sealed units</span><strong>${excluded.adjusted_sealed_unit_count}</strong></div><div><span>Known excluded basis</span><strong>${formatCents(excluded.known_basis_cents, "$0.00")}</strong></div><div><span>Operational loss / disposition</span><strong>${formatCents(excluded.operational_loss_cents, "$0.00")}</strong><small>Not a tax-deduction conclusion</small></div><div><span>Known excluded market value</span><strong>${formatCents(excluded.market.known_value_cents, "$0.00")}</strong><small>${escapeHtml(excluded.market.coverage_label)}</small></div></div><p class="economics-notice">Excluded basis and values do not inflate active remaining inventory.</p></details>${sealedUnitsPanel(sealed, corrections)}</div></details>
    <details data-economics-section="rips"><summary>Rip Sessions</summary><div class="economics-section-body">${ripSessionsPanel(rips)}<h3 class="economics-subheading">Immutable rip history</h3>${economicsRipHistory(rips)}</div></details>
    <details data-economics-section="sales"><summary>Sales</summary><div class="economics-section-body">${economicsSales(report)}<p class="economics-notice">${escapeHtml(report.sales.allocation_notice)}</p></div></details>
    <details ${rec.materially_incomplete ? "open" : ""} data-economics-section="reconciliation"><summary>Reconciliation / Warnings</summary><div class="economics-section-body"><div class="economics-reconciliation"><div><span>Authoritative cost</span><strong>${formatCents(rec.basis.authoritative_cost_cents)}</strong></div><div><span>Unit/finalized allocation ledger</span><strong>${formatCents(rec.basis.ledger_or_finalized_allocation_cents, "$0.00")}</strong></div><div><span>Difference</span><strong>${formatCents(rec.basis.difference_cents, "$0.00")}</strong></div><div><span>Basis reconciliation</span><strong>${rec.basis.reconciled ? "Reconciled" : "Incomplete"}</strong></div>${quantity.applicable ? `<div><span>Sealed quantity</span><strong>${quantity.acquired} = ${quantity.opened} opened + ${quantity.sold} sold + ${quantity.remaining} remaining + ${quantity.corrected_adjusted} adjusted</strong></div><div><span>Quantity difference</span><strong>${quantity.difference}</strong></div>` : ""}</div>${warnings ? `<ul class="economics-warning-list">${warnings}</ul>` : `<p class="economics-empty">No economics warnings detected.</p>`}${correctionsPanel(corrections)}</div></details>
  </div></section>`;
}

async function renderBatch(id) {
  const viewport = state.activeBatch?.batch?.id === Number(id) ? captureLogicalViewport() : null;
  loading();
  try {
    const [data, economics, acquisition, rips, report] = await Promise.all([
      api(`/api/batches/${id}`),
      api(`/api/batches/${id}/economics/estimate`),
      api(`/api/batches/${id}/economics`),
      api(`/api/batches/${id}/rips`),
      api(`/api/batches/${id}/economics/report`),
    ]);
    const sealed = acquisition.economics_mode === "SEALED_RIP"
      ? await api(`/api/batches/${id}/sealed-units`)
      : null;
    let corrections = null;
    if (report.authoritative && (acquisition.economics_status === "FINALIZED" || sealed?.acquisition_facts_locked)) {
      corrections = await api(`/api/batches/${id}/corrections`);
    }
    data.economics = economics;
    data.acquisition = acquisition;
    data.rips = rips;
    data.sealed = sealed;
    data.economicsReport = report;
    data.corrections = corrections;
    state.activeBatch = data;
    const b = data.batch;
    const validSkus = new Set(data.cards.map((card) => card.sku));
    state.selectedBatchCards = new Set([...state.selectedBatchCards].filter((sku) => validSkus.has(sku)));
    app.innerHTML = `<div class="view-stack">
      <div class="section-header"><div><button class="button secondary" data-action="back-batches">${icon("arrow-left")}All Batches</button></div>${b.status === "OPEN" ? `<button class="button primary" data-action="complete-batch" data-id="${b.id}">${icon("printer")}Finish & Print Labels</button>` : `<div class="batch-actions"><span class="badge green">Complete</span><button class="button primary" data-action="reopen-batch" data-id="${b.id}">${icon("plus")}Add More Cards</button></div>`}</div>
      ${report.authoritative ? batchEconomicsInterface(report, acquisition, rips, sealed, corrections) : `${acquisitionFactsPanel(acquisition)}${sealedUnitsPanel(sealed, corrections)}${ripSessionsPanel(rips)}${estimatedEconomicsPanel(economics)}`}
      <div class="batch-workspace" data-viewport-key="batch-workspace">
        <aside class="batch-summary"><h3>${escapeHtml(b.batch_code)}</h3><div class="detail-list">
          <div><span>Game</span><strong>${escapeHtml(b.game)}</strong></div><div><span>Set</span><strong>${escapeHtml(b.set_code)}</strong></div>
          <div><span>Color</span><strong>${escapeHtml(b.color || "Mixed")}</strong></div><div><span>Group</span><strong>${escapeHtml(b.finish_group)}</strong></div>
          <div><span>Source</span><strong>${escapeHtml(b.acquisition_type)}</strong></div><div><span>Cost</span><strong>${formatMoney(b.total_cost)}</strong></div>
          <div><span>Location</span><strong>${escapeHtml(b.location)}</strong></div><div><span>Cards</span><strong>${data.cards.length}</strong></div>
          <div><span>Scanner folder</span><strong>${escapeHtml(b.batch_code)}</strong></div>
        </div><button class="button secondary" style="width:100%;margin-top:16px" data-action="change-group">${icon("sliders-horizontal")}Change scan group</button><button class="button danger" style="width:100%;margin-top:8px" data-action="open-recycle-batch" data-id="${b.id}" data-code="${escapeHtml(b.batch_code)}" data-count="${data.cards.length}">${icon("trash-2")}Move Batch to Recycle Bin</button></aside>
        <section class="ingest-panel"><div class="ingest-head"><h3>Add Scanned Cards</h3><span class="badge blue">SKU Assigned On Save</span></div>
          ${b.status === "OPEN" ? cardIngestForm(b) : ""}${batchCardList(data.cards, b)}
        </section>
      </div></div>`;
    refreshIcons();
    const form = document.querySelector("#scan-card-form");
    if (form) {
      form.querySelectorAll('.image-drop input[type="file"]').forEach((input) => input.addEventListener("change", previewImage));
      form.addEventListener("submit", addScannedCard);
    }
    document.querySelector("#bulk-images")?.addEventListener("change", addBulkScans);
    restoreLogicalViewport(viewport);
  } catch (error) { showError(error); }
}

function correctionTargetOptions(corrections, exclude = "") {
  const cards = (Array.isArray(corrections?.cards) ? corrections.cards : []).filter((item) => item.rip_status === "FINALIZED" && !item.active_tombstone);
  const bulk = Array.isArray(corrections?.bulk_targets) ? corrections.bulk_targets : [];
  return [...cards.map((item) => ({ value: `CARD:${item.id}`, label: `${item.sku} / ${item.name} — ${formatCents(item.basis_cents)}` })), ...bulk.map((item) => ({ value: `RIP_BULK:${item.id}`, label: `${item.rip_code} bulk — ${formatCents(item.basis_cents)}` }))].filter((item) => item.value !== exclude).map((item) => `<option value="${item.value}">${escapeHtml(item.label)}</option>`).join("");
}

function correctionFields(reasonOptions) {
  return `<label>Reason<select name="reason_code">${reasonOptions}</select></label><label>Effective date<input type="date" name="effective_at"></label><label class="full">Operator notes<textarea name="notes" required placeholder="Required: explain what changed and the evidence used"></textarea></label>`;
}

function openAcquisitionCorrection() {
  const corrections = state.activeBatch?.corrections;
  if (!corrections) return toast("Finalize or economically lock this acquisition before using audited corrections.", "error");
  const targets = correctionTargetOptions(corrections);
  const target = corrections.economics_mode === "SEALED_RIP" ? `<p class="help-text full">The cost change will be allocated across stable sealed-unit IDs using deterministic exact-cent allocation.</p>` : `<label class="full">Basis target for the cost change<select name="allocation_target">${targets}</select></label>`;
  openModal("Correct acquisition cost", "The stored source amount remains unchanged. This records an append-only delta and reconciled basis adjustment.", `<form id="acquisition-correction-form"><div class="form-grid"><label>New authoritative USD total<div class="money-input"><span>$</span><input name="new_total_usd" type="number" min="0" step=".01" required value="${centsInputValue(corrections.acquisition_cost.current_authoritative_cents)}"></div></label>${correctionFields(`<option value="ACQUISITION_COST_ERROR">Acquisition cost error</option><option value="SHIPPING_TAX_FEE_CORRECTION">Shipping / tax / fee correction</option><option value="DISCOUNT_CORRECTION">Discount correction</option><option value="OTHER">Other</option>`)}${target}</div><div class="form-actions"><button type="button" class="button secondary" data-action="close-modal">Cancel</button><button class="button primary">Record correction</button></div></form>`);
  document.querySelector("#acquisition-correction-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
    if (payload.allocation_target) [payload.allocation_target_type, payload.allocation_target_id] = payload.allocation_target.split(":");
    delete payload.allocation_target;
    payload.request_id = requestId("ACQUISITION-CORRECTION");
    try { await api(`/api/batches/${state.activeBatch.batch.id}/corrections/acquisition`, { method: "POST", body: JSON.stringify(payload) }); closeModal(); toast("Acquisition correction recorded."); await renderBatch(state.activeBatch.batch.id); }
    catch (error) { toast(error.message, "error"); }
  });
}

function openBasisTransfer() {
  const corrections = state.activeBatch?.corrections;
  const options = correctionTargetOptions(corrections);
  if (!options) return toast("No finalized card or bulk basis targets are available.", "error");
  openModal("Transfer card / bulk basis", "Move an exact amount between existing finalized targets without changing total acquisition cost.", `<form id="basis-transfer-form"><div class="form-grid"><label>From<select name="source">${options}</select></label><label>To<select name="destination">${options}</select></label><label>Amount<div class="money-input"><span>$</span><input name="amount" type="number" min=".01" step=".01" required></div></label>${correctionFields(`<option value="BASIS_REALLOCATION">Basis reallocation</option><option value="LATE_CARD_IDENTIFICATION">Late card identification</option><option value="BULK_CORRECTION">Bulk correction</option><option value="DUPLICATE_ENTRY_ERROR">Duplicate / entry error</option><option value="OTHER">Other</option>`)}</div><div class="form-actions"><button type="button" class="button secondary" data-action="close-modal">Cancel</button><button class="button primary">Record transfer</button></div></form>`);
  document.querySelector("#basis-transfer-form").addEventListener("submit", async (event) => {
    event.preventDefault(); const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
    [payload.source_type, payload.source_id] = payload.source.split(":"); [payload.destination_type, payload.destination_id] = payload.destination.split(":"); delete payload.source; delete payload.destination; payload.request_id = requestId("BASIS-TRANSFER");
    try { await api(`/api/batches/${state.activeBatch.batch.id}/corrections/basis-transfer`, { method: "POST", body: JSON.stringify(payload) }); closeModal(); toast("Basis transfer recorded."); await renderBatch(state.activeBatch.batch.id); }
    catch (error) { toast(error.message, "error"); }
  });
}

function openCardDisposition(sku) {
  const corrections = state.activeBatch?.corrections;
  const card = corrections?.cards?.find((item) => item.sku === sku);
  if (!card) return toast("This card is not eligible for the Phase 7A correction workflow.", "error");
  const destinations = correctionTargetOptions(corrections, `CARD:${card.id}`);
  openModal(`Disposition ${sku}`, "Choose whether this is a duplicate/entry correction, a temporary hold, or a real physical loss. The history cannot be hard-deleted.", `<form id="card-disposition-form" data-sku="${escapeHtml(sku)}"><div class="form-grid">${correctionFields(`<option value="DUPLICATE_ENTRY_ERROR">Duplicate / entry error</option><option value="CORRECTION_HOLD">Correction hold</option><option value="DAMAGED">Damaged</option><option value="MISSING_LOST">Missing / lost</option><option value="DISPOSED">Disposed</option><option value="OTHER">Other physical disposition</option>`)}<label class="full">Duplicate-basis destination<select name="destination">${destinations}</select><small>Used only for Duplicate / entry error; physical loss routes basis to Operational Loss.</small></label></div><div class="form-actions"><button type="button" class="button secondary" data-action="close-modal">Cancel</button><button class="button danger">Record disposition</button></div></form>`);
  document.querySelector("#card-disposition-form").addEventListener("submit", async (event) => {
    event.preventDefault(); const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
    if (payload.destination) [payload.destination_type, payload.destination_id] = payload.destination.split(":"); delete payload.destination; payload.request_id = requestId("CARD-DISPOSITION");
    try { await api(`/api/cards/${encodeURIComponent(sku)}/disposition`, { method: "POST", body: JSON.stringify(payload) }); closeModal(); toast("Card disposition recorded with durable history."); await loadDashboard(); await renderBatch(state.activeBatch.batch.id); }
    catch (error) { toast(error.message, "error"); }
  });
}

function openSealedAdjustment(id, code) {
  if (!state.activeBatch?.corrections) return toast("Finalize or economically lock this acquisition before recording an audited sealed correction.", "error");
  openModal(`Correct / dispose ${code}`, "Only a remaining unit is eligible. Duplicate basis is deterministically reallocated; physical damage, loss, or disposal becomes an operational-loss event.", `<form id="sealed-adjustment-form" data-id="${id}"><div class="form-grid">${correctionFields(`<option value="DUPLICATE_ENTRY_ERROR">Duplicate / entry error</option><option value="CORRECTION_HOLD">Correction hold</option><option value="DAMAGED">Damaged</option><option value="MISSING_LOST">Missing / lost</option><option value="DISPOSED">Disposed</option><option value="OTHER">Other physical disposition</option>`)}</div><div class="form-actions"><button type="button" class="button secondary" data-action="close-modal">Cancel</button><button class="button danger">Record correction</button></div></form>`);
  document.querySelector("#sealed-adjustment-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
    payload.request_id = requestId("SEALED-DISPOSITION");
    try {
      await api(`/api/sealed-units/${event.currentTarget.dataset.id}/disposition`, { method: "POST", body: JSON.stringify(payload) });
      closeModal(); toast("Sealed correction recorded with durable history."); await renderBatch(state.activeBatch.batch.id);
    } catch (error) { toast(error.message, "error"); }
  });
}

function openEconomicEventReversal(eventId) {
  openModal("Reverse economic event", `This creates a linked inverse event. The original ${eventId} remains immutable and visible.`, `<form id="economic-reversal-form" data-id="${escapeHtml(eventId)}"><label>Reversal notes<textarea name="notes" required placeholder="Explain why this event is being reversed"></textarea></label><label>Effective date<input type="date" name="effective_at"></label><div class="form-actions"><button type="button" class="button secondary" data-action="close-modal">Cancel</button><button class="button danger">Create linked reversal</button></div></form>`);
  document.querySelector("#economic-reversal-form").addEventListener("submit", async (event) => {
    event.preventDefault(); const payload = Object.fromEntries(new FormData(event.currentTarget).entries()); payload.request_id = requestId("ECONOMIC-REVERSAL");
    try { await api(`/api/economic-events/${encodeURIComponent(eventId)}/reverse`, { method: "POST", body: JSON.stringify(payload) }); closeModal(); toast("Linked inverse event recorded."); state.view === "recycle" ? await renderRecycle() : await renderBatch(state.activeBatch.batch.id); }
    catch (error) { toast(error.message, "error"); }
  });
}

function acquisitionEditForm(facts) {
  const b = facts.cost_breakdown;
  const modeOptions = [
    ["SEALED_RIP", "Sealed product / rip"],
    ["SINGLES_KNOWN_COST", "Purchased singles — known line costs"],
    ["SINGLES_LUMP_SUM", "Purchased singles — lump-sum lot"],
  ];
  return `<form id="acquisition-edit-form" data-id="${facts.batch_id}"><div class="form-grid">
    <label>Economics mode<select name="economics_mode">${modeOptions.map(([value, label]) => `<option value="${value}" ${facts.economics_mode === value ? "selected" : ""}>${label}</option>`).join("")}</select></label>
    <label>Product / lot name<input name="product_name" required value="${escapeHtml(facts.product_name)}"></label>
    <label>Product code<input name="product_code" value="${escapeHtml(facts.product_code)}"></label>
    <label>Units acquired<input name="units_acquired" type="number" min="0" step="1" value="${facts.units_acquired ?? ""}"></label>
    <label>Receipt / Acquisition Group<input name="receipt_group_reference" value="${escapeHtml(facts.receipt_group.reference)}"></label>
    <label>Invoice / order reference<input name="invoice_reference" value="${escapeHtml(facts.invoice_reference)}"></label>
    <label>Purchase subtotal<div class="money-input"><span>$</span><input name="purchase_subtotal" type="number" min="0" step=".01" value="${centsInputValue(b.purchase_subtotal_cents)}"></div></label>
    <label>Tax<div class="money-input"><span>$</span><input name="acquisition_tax" type="number" min="0" step=".01" value="${centsInputValue(b.acquisition_tax_cents)}"></div></label>
    <label>Inbound shipping<div class="money-input"><span>$</span><input name="inbound_shipping" type="number" min="0" step=".01" value="${centsInputValue(b.inbound_shipping_cents)}"></div></label>
    <label>Acquisition fees<div class="money-input"><span>$</span><input name="acquisition_fees" type="number" min="0" step=".01" value="${centsInputValue(b.acquisition_fees_cents)}"></div></label>
    <label>Discounts / credits<div class="money-input"><span>$</span><input name="acquisition_discount" type="number" min="0" step=".01" value="${centsInputValue(b.acquisition_discount_cents)}"></div></label>
    <label>Final USD actually paid<div class="money-input"><span>$</span><input name="final_usd_paid" type="number" min="0" step=".01" value="${centsInputValue(facts.authoritative_cost.final_usd_paid_cents)}"></div></label>
    <label>Original currency<input name="original_currency" maxlength="3" value="${escapeHtml(facts.original_currency)}"></label>
    <label>Original foreign amount<input name="original_foreign_amount" type="number" min="0" step=".01" value="${centsInputValue(facts.original_foreign_amount_minor)}"></label>
    <label class="full checkbox-label"><input name="cost_reconciliation_acknowledged" type="checkbox" value="1" ${b.acknowledged ? "checked" : ""}><span>Acknowledge an intentional difference. DEX still uses final USD paid as authoritative.</span></label>
  </div><div class="form-actions"><button type="button" class="button secondary" data-action="close-modal">Cancel</button><button class="button primary">${icon("save")}Save acquisition facts</button></div></form>`;
}

function openAcquisitionEdit() {
  const facts = state.activeBatch?.acquisition;
  if (!facts) return;
  openModal("Acquisition Facts", "Receipt groups link batches but never allocate shared costs automatically.", acquisitionEditForm(facts));
  document.querySelector("#acquisition-edit-form").addEventListener("submit", saveAcquisition);
}

async function saveAcquisition(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const batchId = form.dataset.id;
  const payload = Object.fromEntries(new FormData(form).entries());
  payload.cost_reconciliation_acknowledged = form.elements.cost_reconciliation_acknowledged.checked;
  try {
    await api(`/api/batches/${batchId}/economics`, { method: "PATCH", body: JSON.stringify(payload) });
    closeModal(); toast("Acquisition facts updated and audited.");
    await renderBatch(batchId);
  } catch (error) { toast(error.message, "error"); }
}

function requestId(prefix) {
  return `${prefix}-${globalThis.crypto?.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`}`;
}

function openCreateRip() {
  const data = state.activeBatch;
  if (!data) return;
  const sealed = data.acquisition.economics_mode === "SEALED_RIP";
  openModal("New Rip Session", "Creating a session does not activate scanner intake. Start it explicitly after review.", `<form id="create-rip-form" data-id="${data.batch.id}">${sealed ? `<label>Sealed units opened<input name="units_opened" type="number" min="1" step="1" required value="1"></label>` : `<p class="acquisition-notice">This purchased-singles batch will use one allocation session for the full authoritative acquisition cost.</p>`}<div class="form-actions"><button type="button" class="button secondary" data-action="close-modal">Cancel</button><button class="button primary">${icon("package-open")}Create session</button></div></form>`);
  document.querySelector("#create-rip-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = Object.fromEntries(new FormData(form).entries());
    try {
      await api(`/api/batches/${form.dataset.id}/rips`, { method: "POST", body: JSON.stringify(payload) });
      closeModal(); toast("Rip session created. Scanner intake is still unassigned."); await renderBatch(form.dataset.id);
    } catch (error) { toast(error.message, "error"); }
  });
}

async function activateRip(id, confirmed = false) {
  try {
    await api(`/api/rip-sessions/${id}/activate`, { method: "POST", body: JSON.stringify({ confirm_switch: confirmed }) });
    toast("Scanner intake explicitly assigned to this rip.");
    await renderBatch(state.activeBatch.batch.id);
  } catch (error) {
    if (error.status === 409 && error.details?.requires_confirmation && confirm(`${error.message}. Switch active rip anyway?`)) return activateRip(id, true);
    toast(error.message, "error");
  }
}

async function deactivateRipSession(id) {
  try {
    await api(`/api/rip-sessions/${id}/deactivate`, { method: "POST", body: "{}" });
    toast("Scanner intake stopped. No rip is active for this session.");
    await renderBatch(state.activeBatch.batch.id);
  } catch (error) { toast(error.message, "error"); }
}

function ripAllocationForm(rip) {
  const manualDefault = state.activeBatch.acquisition.economics_mode === "SINGLES_KNOWN_COST";
  const cards = Array.isArray(rip?.cards) ? rip.cards : [];
  const cardInputs = cards.map((card) => `<label>${escapeHtml(card.sku)} · ${escapeHtml(card.name)}${card.recycled_at ? " · Excluded/Recycled" : ""}<div class="money-input"><span>$</span><input name="basis_${card.sku}" type="number" min="0" step=".01" value="${centsInputValue(card.basis_cents ?? null)}"></div></label>`).join("");
  return `<form id="rip-allocation-form" data-id="${rip.id}"><div class="form-grid">
    <label>Allocation method<select name="allocation_method"><option value="EQUAL" ${manualDefault ? "" : "selected"}>Equal allocation</option><option value="MANUAL" ${manualDefault ? "selected" : ""}>Manual per-card costs</option></select></label>
    <label>Unscanned bulk<select name="bulk_mode"><option value="NONE">None — all intended cards are scanned</option><option value="KNOWN_QUANTITY">Known physical card quantity</option><option value="MANUAL_RESERVE">Unknown quantity — manual reserve</option></select></label>
    <label class="rip-bulk-field" data-bulk-field="quantity" hidden>Known physical bulk quantity<input name="bulk_quantity" type="number" min="1" step="1" placeholder="Enter the physical card count" disabled></label>
    <label class="rip-bulk-field" data-bulk-field="reserve" hidden>Manual bulk-reserve amount<div class="money-input"><span>$</span><input name="bulk_reserve" type="number" min="0" step=".01" placeholder="Enter the exact USD basis to reserve" disabled></div></label>
    <details class="full"><summary>Manual per-card basis overrides</summary><div class="form-grid">${cardInputs || `<p>No cards are currently assigned to this rip.</p>`}</div></details>
  </div><p class="acquisition-notice" data-bulk-help>No bulk reserve will be included. Every intended card must be represented by a scanned card.</p><div class="form-actions"><button type="button" class="button secondary" data-action="close-modal">Cancel</button><button class="button primary">Preview final reconciliation</button></div></form>`;
}

function syncRipBulkFields(form) {
  const mode = form.elements.bulk_mode.value;
  const quantityField = form.querySelector('[data-bulk-field="quantity"]');
  const reserveField = form.querySelector('[data-bulk-field="reserve"]');
  const quantityInput = form.elements.bulk_quantity;
  const reserveInput = form.elements.bulk_reserve;
  const help = form.querySelector("[data-bulk-help]");
  const knownQuantity = mode === "KNOWN_QUANTITY";
  const manualReserve = mode === "MANUAL_RESERVE";
  quantityField.hidden = !knownQuantity;
  reserveField.hidden = !manualReserve;
  quantityInput.disabled = !knownQuantity;
  reserveInput.disabled = !manualReserve;
  help.textContent = knownQuantity
    ? "Enter the known physical card quantity. Bulk participates in the same deterministic per-card allocation."
    : manualReserve
      ? "Enter the exact USD basis reserved for unknown-quantity bulk. Valuation coverage will remain incomplete."
      : "No bulk reserve will be included. Every intended card must be represented by a scanned card.";
}

function allocationPayload(form) {
  const raw = Object.fromEntries(new FormData(form).entries());
  const payload = { allocation_method: raw.allocation_method, bulk_mode: raw.bulk_mode, bulk_quantity: raw.bulk_quantity, bulk_reserve: raw.bulk_reserve };
  payload.card_overrides = [...form.elements].filter((element) => element.name?.startsWith("basis_")).map((element) => ({ sku: element.name.slice(6), basis: element.value }));
  return payload;
}

function openFinalizeRip(id) {
  const sessions = Array.isArray(state.activeBatch?.rips?.sessions) ? state.activeBatch.rips.sessions : [];
  const rip = sessions.find((item) => String(item.id) === String(id));
  if (!rip) return;
  openModal(`Finalize ${rip.rip_code}`, "Review who participates in allocation. Finalization locks ordinary intake.", ripAllocationForm(rip));
  const form = document.querySelector("#rip-allocation-form");
  form.elements.bulk_mode.addEventListener("change", () => syncRipBulkFields(form));
  syncRipBulkFields(form);
  form.addEventListener("submit", previewRipFinalization);
}

async function previewRipFinalization(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = allocationPayload(form);
  try {
    const preview = await api(`/api/rip-sessions/${form.dataset.id}/preview`, { method: "POST", body: JSON.stringify(payload) });
    state.pendingRipFinalization = { id: form.dataset.id, payload, preview };
    const r = preview.reconciliation;
    openModal(`Final confirmation · ${preview.rip_code}`, "Finalization is immutable except through an audited correction event.", `<form id="confirm-rip-finalization"><div class="rip-final-reconciliation"><div><span>Rip cost</span><strong>${formatCents(r.rip_cost_cents)}</strong></div><div><span>Scanned-card basis</span><strong>${formatCents(r.scanned_card_basis_cents, "$0.00")}</strong></div><div><span>Bulk-reserve basis</span><strong>${formatCents(r.bulk_reserve_basis_cents, "$0.00")}</strong></div><div><span>Total allocated</span><strong>${formatCents(r.total_allocated_cents)}</strong></div><div class="${r.difference_cents === 0 ? "reconciled" : "warning-text"}"><span>Difference</span><strong>${formatCents(r.difference_cents)}</strong></div></div><label class="checkbox-label"><input name="accounted" type="checkbox" required><span>I confirm every intended scanned card and any unscanned bulk are accounted for.</span></label><label class="checkbox-label"><input name="final" type="checkbox" required><span>I understand ordinary intake into this rip will be locked.</span></label><div class="form-actions"><button type="button" class="button secondary" data-action="close-modal">Cancel</button><button class="button primary" ${r.difference_cents === 0 ? "" : "disabled"}>Finalize allocation</button></div></form>`);
    document.querySelector("#confirm-rip-finalization").addEventListener("submit", finalizeRipAllocation);
  } catch (error) { toast(error.message, "error"); }
}

async function finalizeRipAllocation(event) {
  event.preventDefault();
  const pending = state.pendingRipFinalization;
  if (!pending) return;
  const payload = { ...pending.payload, confirm_all_cards_accounted: true, confirm_finalization: true, request_id: requestId("RIP-FINALIZE") };
  try {
    await api(`/api/rip-sessions/${pending.id}/finalize`, { method: "POST", body: JSON.stringify(payload) });
    state.pendingRipFinalization = null; closeModal(); toast("Rip finalized with a $0.00 difference."); await renderBatch(state.activeBatch.batch.id);
  } catch (error) { toast(error.message, "error"); }
}

function openRipCorrection(id) {
  const sessions = Array.isArray(state.activeBatch?.rips?.sessions) ? state.activeBatch.rips.sessions : [];
  const rip = sessions.find((item) => String(item.id) === String(id));
  if (!rip) return;
  openModal(`Audited correction · ${rip.rip_code}`, "This appends a new event; the original allocation is never overwritten.", `<form id="rip-correction-form" data-id="${rip.id}"><div class="form-grid"><label>Card SKU<input name="sku" required placeholder="Existing or late same-batch SKU"></label><label>Card basis change<div class="money-input"><span>$</span><input name="delta" type="number" step=".01" required placeholder="Use negative to reduce"></div></label><label>Optional offset card SKU<input name="offset_sku" placeholder="Use when reallocating between cards"></label><label>Optional offset card change<div class="money-input"><span>$</span><input name="offset_delta" type="number" step=".01" placeholder="Usually the inverse amount"></div></label><label>Offsetting bulk change<div class="money-input"><span>$</span><input name="bulk_delta" type="number" step=".01" required value="0.00"></div></label><label>Reason<select name="reason_code"><option value="LATE_CARD_ADDITION">Late card addition</option><option value="BASIS_REALLOCATION">Basis reallocation</option><option value="BULK_CORRECTION">Bulk correction</option><option value="ENTRY_ERROR">Entry error</option><option value="OTHER">Other</option></select></label><label class="full">Required notes<textarea name="notes" required></textarea></label></div><p class="acquisition-notice">All card changes plus the bulk change must net to exactly $0.00. The original event remains unchanged.</p><div class="form-actions"><button type="button" class="button secondary" data-action="close-modal">Cancel</button><button class="button primary">Append correction event</button></div></form>`);
  document.querySelector("#rip-correction-form").addEventListener("submit", submitRipCorrection);
}

async function submitRipCorrection(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const raw = Object.fromEntries(new FormData(form).entries());
  const cardAdjustments = [{ sku: raw.sku, delta: raw.delta }];
  if (raw.offset_sku || raw.offset_delta) cardAdjustments.push({ sku: raw.offset_sku, delta: raw.offset_delta });
  const payload = { request_id: requestId("RIP-CORRECTION"), reason_code: raw.reason_code, notes: raw.notes, bulk_delta: raw.bulk_delta, card_adjustments: cardAdjustments };
  try {
    await api(`/api/rip-sessions/${form.dataset.id}/corrections`, { method: "POST", body: JSON.stringify(payload) });
    closeModal(); toast("Audited correction appended; original history preserved."); await renderBatch(state.activeBatch.batch.id);
  } catch (error) { toast(error.message, "error"); }
}

function changeGroupForm(batch) {
  return `<form id="change-group-form" data-id="${batch.id}"><div class="form-grid">
    <label>Color${colorField("color", batch.color)}<span class="help-text">Pick a known color or type a custom drawer label.</span></label>
    <label>Finish / rarity group<select name="finish_group">${["Common / Non-Foil","Rare / Foil","Rare / Non-Foil","Promo","Mixed"].map((value) => `<option ${batch.finish_group === value ? "selected" : ""}>${value}</option>`).join("")}</select></label>
    <label class="full">Drawer location<input name="location" value="${escapeHtml(batch.location)}" placeholder="OP16-Yellow"></label>
    <label class="full">Scanner Order<select name="scan_order"><option value="FRONT_FIRST" ${batch.scan_order !== "BACK_FIRST" ? "selected" : ""}>Front First (Face Down)</option><option value="BACK_FIRST" ${batch.scan_order === "BACK_FIRST" ? "selected" : ""}>Back First (Face Up)</option></select></label>
  </div><div class="form-actions"><button type="button" class="button secondary" data-action="close-modal">Cancel</button><button class="button primary">${icon("check")}Use this group</button></div></form>`;
}

function openChangeGroup() {
  const batch = state.activeBatch?.batch;
  if (!batch) return;
  openModal("Change scan group", "Cards already scanned keep their details and purchase-batch cost.", changeGroupForm(batch));
  document.querySelector("#change-group-form").addEventListener("submit", saveScanGroup);
}

async function saveScanGroup(event) {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
  payload.color = normalizeColorChoice(payload.color);
  const batchId = event.currentTarget.dataset.id;
  try {
    await api(`/api/batches/${batchId}`, { method: "PATCH", body: JSON.stringify(payload) });
    closeModal(); toast("Scan group updated."); await renderBatch(batchId);
  } catch (error) { toast(error.message, "error"); }
}

function previewImage(event) {
  const file = event.target.files[0];
  if (!file) return;
  const drop = event.target.closest(".image-drop");
  const reader = new FileReader();
  reader.onload = () => { drop.querySelector("span").innerHTML = `<img src="${reader.result}" alt="Scan preview">`; };
  reader.readAsDataURL(file);
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function openSourceDocumentPicker(selector, documentId = null) {
  const input = document.querySelector(selector);
  if (!input) return false;
  input.value = "";
  if (documentId === null) delete input.dataset.documentId;
  else input.dataset.documentId = String(documentId);
  input.click();
  return true;
}

async function handleSourceDocumentSelection(event, captureMethod) {
  const input = event.currentTarget || event.target;
  const files = [...(input?.files || [])];
  if (input) input.value = "";
  if (!files.length) return;
  await uploadSourceDocuments(files, captureMethod);
}

async function handleSourceDocumentRetrySelection(event) {
  const input = event.currentTarget || event.target;
  const documentId = input?.dataset?.documentId;
  const file = input?.files?.[0];
  if (input) input.value = "";
  if (!file) return;
  await retrySourceDocumentUpload(documentId, file);
}

async function uploadSourceDocuments(fileList, captureMethod) {
  const files = [...(fileList || [])];
  if (!files.length || !state.activeAcquisition) return;
  const viewport = captureLogicalViewport();
  let attached = 0;
  let failed = 0;
  let extractionAttempts = 0;
  try {
    for (const file of files) {
      const data = await fileToDataUrl(file);
      let response;
      await enqueueAcquisitionMutation(async (current) => {
        response = await api(`/api/acquisitions/${current.acquisition.id}/documents`, {
          method: "POST",
          body: JSON.stringify({
            request_id: requestId("SOURCE-DOCUMENT"), expected_revision: current.acquisition.revision,
            original_filename: file.name, declared_mime_type: file.type, data_base64: data,
            document_role: "RECEIPT", capture_method: file.type === "application/pdf" ? "PDF_UPLOAD" : captureMethod,
          }),
        });
        return response.acquisition_payload;
      });
      if (response.upload_failed) failed += 1;
      else if (!response.duplicate) {
        attached += 1;
        if (response.document?.storage_status === "STORED" && response.document?.document_role === "RECEIPT") {
          await enqueueAcquisitionMutation(async (current) => {
            const extraction = await api(`/api/acquisition-documents/${response.document.id}/extractions`, {
              method: "POST",
              body: JSON.stringify({
                request_id: requestId("RECEIPT-ZERO-ENTRY"),
                expected_revision: current.acquisition.revision,
                auto_apply: true,
              }),
            });
            extractionAttempts += 1;
            return extraction.acquisition_payload;
          });
        }
      }
      else toast(`${file.name} already exists on this acquisition.`);
    }
    if (attached) toast(`${attached} source document(s) attached privately${extractionAttempts ? " and analyzed locally" : ""}.`);
    if (failed) toast(`${failed} upload(s) need attention. Manual entry remains available.`, "error");
    if (extractionAttempts) {
      await enqueueAcquisitionMutation((current) => api(`/api/acquisitions/${current.acquisition.id}`, {
        method: "PATCH",
        body: JSON.stringify({ request_id: requestId("RECEIPT-REVIEW-STEP"), expected_revision: current.acquisition.revision, wizard_step: "REVIEW" }),
      }));
    }
    await renderAcquisitionWizard(state.activeAcquisition.acquisition.id, { data: state.activeAcquisition, viewport });
  } catch (error) { toast(error.message, "error"); }
}

async function retrySourceDocumentUpload(documentId, file) {
  if (!documentId || !file || !state.activeAcquisition) return;
  const viewport = captureLogicalViewport();
  try {
    const data = await fileToDataUrl(file);
    let response;
    await enqueueAcquisitionMutation(async (current) => {
      response = await api(`/api/acquisition-documents/${documentId}/retry`, {
        method: "POST",
        body: JSON.stringify({ request_id: requestId("SOURCE-DOCUMENT-RETRY"), expected_revision: current.acquisition.revision,
          original_filename: file.name, declared_mime_type: file.type, data_base64: data }),
      });
      return response.acquisition_payload;
    });
    toast(response.upload_failed ? "Retry failed; manual entry remains available." : "Source document retry succeeded.", response.upload_failed ? "error" : undefined);
    await renderAcquisitionWizard(state.activeAcquisition.acquisition.id, { data: state.activeAcquisition, viewport });
  } catch (error) { toast(error.message, "error"); }
}

async function removeSourceDocument(documentId) {
  if (!state.activeAcquisition) return;
  const confirmed = state.activeAcquisition.acquisition.state === "READY_FOR_INTAKE";
  if (!confirm(confirmed ? "Remove this document from normal view? Confirmed evidence and audit history will be retained." : "Remove this draft document? Audit metadata will remain.")) return;
  const viewport = captureLogicalViewport();
  for (const selector of ["#source-document-camera", "#source-document-files", "#source-document-retry"]) {
    const input = document.querySelector(selector);
    if (input) input.value = "";
  }
  try {
    let response;
    await enqueueAcquisitionMutation(async (current) => {
      response = await api(`/api/acquisition-documents/${documentId}/tombstone`, {
        method: "POST",
        body: JSON.stringify({ request_id: requestId("SOURCE-DOCUMENT-REMOVE"), expected_revision: current.acquisition.revision,
          reason_code: "OPERATOR_REMOVED", notes: confirmed ? "Confirmed source evidence removed from normal view" : "Removed during draft setup" }),
      });
      return response.acquisition_payload;
    });
    toast(confirmed ? "Document tombstoned; durable evidence history retained." : "Draft document removed; audit metadata retained.");
    await renderAcquisitionWizard(state.activeAcquisition.acquisition.id, { data: state.activeAcquisition, viewport });
  } catch (error) { toast(error.message, "error"); }
}

function pairBulkFiles(fileList, scanOrder = "FRONT_FIRST") {
  const files = [...fileList].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
  const explicit = new Map();
  const remaining = [];
  for (const file of files) {
    const stem = file.name.replace(/\.[^.]+$/, "");
    const match = stem.match(/^(.*?)[_ -](front|back)$/i);
    if (!match) { remaining.push(file); continue; }
    const key = match[1].toLowerCase();
    if (!explicit.has(key)) explicit.set(key, {});
    explicit.get(key)[match[2].toLowerCase()] = file;
  }
  const pairs = [...explicit.values()].filter((item) => item.front && item.back).map((item) => ({ front: item.front, back: item.back, explicit: true }));
  for (let index = 0; index + 1 < remaining.length; index += 2) {
    const first = remaining[index]; const second = remaining[index + 1];
    pairs.push(scanOrder === "BACK_FIRST" ? { front: second, back: first, explicit: false } : { front: first, back: second, explicit: false });
  }
  const used = new Set(pairs.flatMap((pair) => [pair.front, pair.back]));
  return { pairs, unmatched: files.filter((file) => !used.has(file)) };
}

function pairReviewRows(scanOrder) {
  const { pairs, unmatched } = pairBulkFiles(state.pendingBulkFiles, scanOrder);
  return `<div class="pair-review-summary"><strong>${pairs.length} Card Pairs</strong><span>${unmatched.length ? `${unmatched.length} unmatched file(s)` : "All files paired"}</span></div><div class="pair-review-list">${pairs.map((pair, index) => `<div><b>${index + 1}</b><span><small>Front</small>${escapeHtml(pair.front.name)}</span><span><small>Back</small>${escapeHtml(pair.back.name)}</span><em>${pair.explicit ? "Named" : scanOrder === "BACK_FIRST" ? "Back First" : "Front First"}</em></div>`).join("")}</div>${unmatched.length ? `<p class="warning-text">Skipped: ${unmatched.map((file) => escapeHtml(file.name)).join(", ")}</p>` : ""}`;
}

function addBulkScans(event) {
  state.pendingBulkFiles = [...event.currentTarget.files];
  if (!state.pendingBulkFiles.length) return;
  const order = state.activeBatch.batch.scan_order || "FRONT_FIRST";
  openModal("Review Scan Pairs", "Confirm front/back orientation before Dex creates physical-card records.", `<form id="bulk-review-form"><label>Scanner Order<select name="scan_order"><option value="FRONT_FIRST" ${order !== "BACK_FIRST" ? "selected" : ""}>Front First (Face Down)</option><option value="BACK_FIRST" ${order === "BACK_FIRST" ? "selected" : ""}>Back First (Face Up)</option></select></label><div id="pair-review-list">${pairReviewRows(order)}</div><div class="form-actions"><button type="button" class="button secondary" data-action="close-modal">Cancel</button><button class="button primary">${icon("images")}Import Pairs</button></div></form>`);
  const form = document.querySelector("#bulk-review-form");
  form.elements.scan_order.addEventListener("change", () => { document.querySelector("#pair-review-list").innerHTML = pairReviewRows(form.elements.scan_order.value); });
  form.addEventListener("submit", importBulkScans);
}

async function importBulkScans(event) {
  event.preventDefault();
  const submit = event.currentTarget.querySelector('button[type="submit"], button:not([type])');
  const scanOrder = event.currentTarget.elements.scan_order.value;
  const { pairs, unmatched } = pairBulkFiles(state.pendingBulkFiles, scanOrder);
  if (!pairs.length) return toast("Select at least one complete front/back pair.", "error");
  if (unmatched.length && !confirm(`${unmatched.length} unmatched file(s) will be skipped. Continue?`)) return;
  submit.disabled = true;
  let created = 0;
  toast(`Preparing ${pairs.length} card pair(s)...`);
  try {
    const batchId = state.activeBatch.batch.id;
    await api(`/api/batches/${batchId}`, { method: "PATCH", body: JSON.stringify({ scan_order: scanOrder }) });
    for (let start = 0; start < pairs.length; start += BULK_IMPORT_CHUNK_SIZE) {
      const chunk = pairs.slice(start, start + BULK_IMPORT_CHUNK_SIZE);
      const end = start + chunk.length;
      toast(`Importing card pairs ${start + 1}-${end} of ${pairs.length}...`);
      const cards = [];
      for (const pair of chunk) {
        cards.push({
          rarity: state.intakeDefaults.rarity,
          variant: state.intakeDefaults.variant,
          front_image: await fileToDataUrl(pair.front),
          back_image: await fileToDataUrl(pair.back),
        });
      }
      const result = await api(`/api/batches/${batchId}/cards/bulk`, { method: "POST", body: JSON.stringify({ cards }) });
      created += result.created || 0;
    }
    state.pendingBulkFiles = [];
    closeModal();
    toast(`${created} physical card(s) added and assigned SKUs.`);
    await loadDashboard(); await renderBatch(batchId);
  } catch (error) {
    toast(created ? `Import stopped after ${created} card(s): ${error.message}` : error.message, "error");
    submit.disabled = false;
  }
}

async function addScannedCard(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = form.querySelector('button[type="submit"], button:not([type])');
  submit.disabled = true;
  try {
    const data = new FormData(form);
    const payload = {
      card_number: data.get("card_number"), name: data.get("name"), rarity: data.get("rarity"), variant: data.get("variant"),
      front_image: await fileToDataUrl(data.get("front")), back_image: await fileToDataUrl(data.get("back")),
    };
    state.intakeDefaults = { rarity: payload.rarity || "", variant: payload.variant || "Standard" };
    const card = await api(`/api/batches/${state.activeBatch.batch.id}/cards`, { method: "POST", body: JSON.stringify(payload) });
    toast(`${card.sku} added to Dex.`);
    await loadDashboard(); await renderBatch(state.activeBatch.batch.id);
  } catch (error) { toast(error.message, "error"); submit.disabled = false; }
}

async function reopenBatch(id) {
  try {
    await api(`/api/batches/${id}/reopen`, { method: "POST", body: "{}" });
    toast("Batch reopened. Existing SKUs and labels are unchanged.");
    await loadDashboard(); await renderBatch(id);
  } catch (error) { toast(error.message, "error"); }
}

async function reprintLabel(sku) {
  try {
    await api("/api/labels/requeue", { method: "POST", body: JSON.stringify({ sku }) });
    closeModal(); toast(`${sku} added to the label queue.`); await loadDashboard(); setView("labels");
  } catch (error) { toast(error.message, "error"); }
}

async function completeBatch(id) {
  try {
    await api(`/api/batches/${id}/complete`, { method: "POST", body: "{}" });
    toast("Batch complete. Labels are ready."); await loadDashboard(); setView("labels");
  } catch (error) { toast(error.message, "error"); }
}

function selectedBatchSkus() {
  return [...state.selectedBatchCards];
}

async function selectVisibleBatchCards() {
  const cards = state.activeBatch?.cards || [];
  state.selectedBatchCards = new Set(cards.map((card) => card.sku));
  await renderBatch(state.activeBatch.batch.id);
}

async function clearBatchSelection() {
  state.selectedBatchCards.clear();
  await renderBatch(state.activeBatch.batch.id);
}

async function bulkRecycleCards() {
  const skus = selectedBatchSkus();
  if (!skus.length) return toast("Select at least one card.", "error");
  if (!confirm(`Move ${skus.length} selected card(s) to the Recycle Bin?`)) return;
  try {
    for (const sku of skus) {
      await api(`/api/cards/${encodeURIComponent(sku)}/recycle`, { method: "POST", body: JSON.stringify({ reason: "Bulk selection" }) });
    }
    state.selectedBatchCards.clear();
    toast(`${skus.length} card(s) moved to Recycle Bin.`);
    await loadDashboard(); await renderBatch(state.activeBatch.batch.id);
  } catch (error) { toast(error.message, "error"); }
}

async function bulkReprintLabels() {
  const skus = selectedBatchSkus();
  if (!skus.length) return toast("Select at least one card.", "error");
  try {
    for (const sku of skus) {
      await api("/api/labels/requeue", { method: "POST", body: JSON.stringify({ sku }) });
    }
    toast(`${skus.length} label(s) added to the queue.`);
    await loadDashboard(); setView("labels");
  } catch (error) { toast(error.message, "error"); }
}

function openBulkEdit() {
  const skus = selectedBatchSkus();
  if (!skus.length) return toast("Select at least one card.", "error");
  openModal("Bulk Edit Selected Cards", `${skus.length} physical card(s) selected. Blank fields are left unchanged.`, `<form id="bulk-edit-form"><div class="form-grid">
    <label>Status<select name="status"><option value="">No change</option><option value="IN_STOCK">In Stock</option><option value="REVIEW">Needs Review</option><option value="HOLD">Hold</option></select></label>
    <label>Rarity<input name="rarity" placeholder="No change"></label>
    <label>Variant<select name="variant"><option value="">No change</option>${["Standard","Alternate Art","Full Art","Parallel","Foil","Promo"].map((v) => `<option>${v}</option>`).join("")}</select></label>
    <label>Listing Platform<select name="listing_platform"><option value="">No change</option><option value="__blank__">Unlisted</option><option>TCGplayer</option><option>eBay</option></select></label>
    <label class="full">Drawer Location<input name="location" placeholder="No change"></label>
  </div><div class="form-actions"><button type="button" class="button secondary" data-action="close-modal">Cancel</button><button class="button primary">${icon("save")}Apply to Selected</button></div></form>`);
  document.querySelector("#bulk-edit-form").addEventListener("submit", bulkEditCards);
}

async function bulkEditCards(event) {
  event.preventDefault();
  const skus = selectedBatchSkus();
  const raw = Object.fromEntries(new FormData(event.currentTarget).entries());
  const payload = {};
  for (const [key, value] of Object.entries(raw)) {
    if (value === "") continue;
    payload[key] = value === "__blank__" ? "" : value;
  }
  if (!Object.keys(payload).length) return toast("Choose at least one field to update.", "error");
  try {
    for (const sku of skus) {
      await api(`/api/cards/${sku}`, { method: "PATCH", body: JSON.stringify(payload) });
    }
    closeModal();
    state.selectedBatchCards.clear();
    toast(`${skus.length} card(s) updated.`);
    await loadDashboard(); await renderBatch(state.activeBatch.batch.id);
  } catch (error) { toast(error.message, "error"); }
}

function editCardForm(card, economics = null) {
  const sourceImage = card.source_full_image_url || card.source_small_image_url;
  const sourceBlock = card.source_card_id ? `<div class="source-reference"><div>${sourceImage ? `<img src="${sourceImage}" alt="">` : icon("image")}</div><section><span>Matched Source</span><strong>${escapeHtml(card.source_card_number || card.card_number)}</strong><small>${escapeHtml(card.source_name || card.name)}${card.match_confidence ? ` · ${confidenceLabel(card.match_confidence)} confidence` : ""}</small></section></div>` : `<div class="source-reference empty">${icon("sparkles")}<section><span>SAM</span><strong>No source match yet</strong><small>Use SAM Match to compare this scan with the local source database.</small></section></div>`;
  const evidence = (side) => card[`${side}_image`] ? `<a href="/media/${encodeURI(card[`${side}_image`])}" target="_blank" rel="noopener"><img src="/media/${encodeURI(card[`${side}_image`])}" alt="${titleCase(side)} scan for ${escapeHtml(card.sku)}"><span>${titleCase(side)} · Open Full Resolution</span></a>` : `<div class="missing-evidence">${icon("image-off")}<span>No ${titleCase(side)} Image</span></div>`;
  const correctionCard = state.activeBatch?.corrections?.cards?.find((item) => item.sku === card.sku);
  const dispositionAction = correctionCard && correctionCard.rip_status === "FINALIZED" && card.status !== "SOLD" && !correctionCard.active_tombstone ? `<button type="button" class="button danger" data-action="dispose-card" data-sku="${escapeHtml(card.sku)}">${icon("history")}Audited disposition</button>` : "";
  return `<form id="edit-card-form" data-sku="${escapeHtml(card.sku)}"><div class="card-evidence">${evidence("front")}${evidence("back")}</div><div class="evidence-actions"><button type="button" class="button secondary" data-action="swap-images" data-sku="${escapeHtml(card.sku)}">${icon("arrow-left-right")}Swap Front/Back</button><button type="button" class="button secondary" data-action="sam-match-card" data-sku="${escapeHtml(card.sku)}">${icon("sparkles")}SAM Match</button></div>${sourceBlock}${jarvisCardPanel(economics)}<div class="form-grid">
    <label>SKU<div class="input-action"><input value="${escapeHtml(card.sku)}" disabled><button type="button" class="icon-button" title="Copy SKU" data-action="copy-sku" data-sku="${escapeHtml(card.sku)}">${icon("copy")}</button></div></label>
    <label>Status<select name="status">${["IN_STOCK","REVIEW","HOLD","SOLD"].map((v) => `<option value="${v}" ${card.status === v ? "selected" : ""}>${v === "IN_STOCK" ? "In Stock" : v === "REVIEW" ? "Needs Review" : titleCase(v)}</option>`).join("")}</select></label>
    <label>Card Number<input name="card_number" value="${escapeHtml(card.card_number)}"></label>
    <label>Card Name<input name="name" value="${escapeHtml(card.name)}"></label>
    <label>Rarity<input name="rarity" value="${escapeHtml(card.rarity)}"></label>
    <label>Variant<input name="variant" value="${escapeHtml(card.variant)}"></label>
    <label>Drawer Location<input name="location" value="${escapeHtml(card.location)}"></label>
    <label>Listing Platform<select name="listing_platform"><option value="">Unlisted</option><option ${card.listing_platform === "TCGplayer" ? "selected" : ""}>TCGplayer</option><option ${card.listing_platform === "eBay" ? "selected" : ""}>eBay</option></select></label>
    <label>Market Low<div class="money-input"><span>$</span><input name="market_low" type="number" step=".01" min="0" value="${card.market_low ?? ""}"></div></label>
    <label>Market Average<div class="money-input"><span>$</span><input name="market_average" type="number" step=".01" min="0" value="${card.market_average ?? ""}"></div></label>
    <label>Market High<div class="money-input"><span>$</span><input name="market_high" type="number" step=".01" min="0" value="${card.market_high ?? ""}"></div></label>
    <label>Listing Price<div class="money-input"><span>$</span><input name="listing_price" type="number" step=".01" min="0" value="${card.listing_price ?? ""}"></div></label>
  </div><div class="form-actions card-form-actions"><div>${dispositionAction}<button type="button" class="button danger" data-action="open-recycle-card" data-sku="${escapeHtml(card.sku)}">${icon("trash-2")}Move to Recycle Bin</button><button type="button" class="button secondary" data-action="reprint-label" data-sku="${escapeHtml(card.sku)}">${icon("printer")}Reprint Label</button></div><div><button type="button" class="button secondary" data-action="close-modal">Cancel</button><button class="button primary">${icon("save")}Save Card</button></div></div></form>`;
}

async function openEditCard(sku) {
  try {
    const [card, economics] = await Promise.all([
      api(`/api/cards/${encodeURIComponent(sku)}`),
      api(`/api/jarvis/economics/cards/${encodeURIComponent(sku)}`).catch(() => null),
    ]);
    openModal(card.name, `${card.sku} · ${card.game} · ${card.set_code}`, editCardForm(card, economics));
    document.querySelector("#edit-card-form").addEventListener("submit", saveCard);
  } catch (error) { toast(error.message, "error"); }
}

async function saveCard(event) {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
  try {
    await api(`/api/cards/${event.currentTarget.dataset.sku}`, { method: "PATCH", body: JSON.stringify(payload) });
    closeModal(); toast("Card updated."); await loadDashboard(); setView(state.view, state.activeBatch ? { batchId: state.activeBatch.batch.id } : {});
  } catch (error) { toast(error.message, "error"); }
}

async function copySku(sku) {
  try {
    if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(sku);
    else {
      const input = document.createElement("textarea"); input.value = sku; document.body.appendChild(input); input.select(); document.execCommand("copy"); input.remove();
    }
    toast(`${sku} copied.`);
  } catch { toast("Could not copy the SKU on this device.", "error"); }
}

async function swapCardImages(sku) {
  try {
    await api(`/api/cards/${encodeURIComponent(sku)}/swap-images`, { method: "POST", body: "{}" });
    toast("Front and back images swapped."); await openEditCard(sku);
  } catch (error) { toast(error.message, "error"); }
}

function openRecycleCard(sku) {
  openModal("Move to Recycle Bin", `The SKU ${sku} can be restored during the retention period.`, `<form id="recycle-card-form" data-sku="${escapeHtml(sku)}"><label>Removal Reason<textarea name="reason" placeholder="Duplicate scan, incorrect entry, returned card, or another reason"></textarea></label><div class="form-actions"><button type="button" class="button secondary" data-action="close-modal">Cancel</button><button class="button danger">${icon("trash-2")}Move to Recycle Bin</button></div></form>`);
  document.querySelector("#recycle-card-form").addEventListener("submit", recycleCard);
}

async function recycleCard(event) {
  event.preventDefault();
  const sku = event.currentTarget.dataset.sku;
  const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
  try {
    await api(`/api/cards/${encodeURIComponent(sku)}/recycle`, { method: "POST", body: JSON.stringify(payload) });
    closeModal(); toast(`${sku} moved to Recycle Bin. Use Undo to restore it.`); await loadDashboard();
    state.activeBatch ? await renderBatch(state.activeBatch.batch.id) : setView("inventory");
  } catch (error) { toast(error.message, "error"); }
}

function openRecycleBatch(id, code, count) {
  const cards = Number(count || 0);
  const cardText = cards === 1 ? "1 card" : `${cards} cards`;
  openModal("Move Batch to Recycle Bin", `${code} contains ${cardText}. This is recoverable during the retention period.`, `<form id="recycle-batch-form" data-id="${escapeHtml(id)}"><label>Removal Reason<textarea name="reason" placeholder="Duplicate batch, test import, wrong set, or another reason"></textarea></label><p class="help-text">Every active card in this batch will move to the Recycle Bin. Sold/audit protections and retention rules still apply.</p><div class="form-actions"><button type="button" class="button secondary" data-action="close-modal">Cancel</button><button class="button danger">${icon("trash-2")}Move Batch to Recycle Bin</button></div></form>`);
  document.querySelector("#recycle-batch-form").addEventListener("submit", recycleBatch);
}

async function recycleBatch(event) {
  event.preventDefault();
  const id = event.currentTarget.dataset.id;
  const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
  try {
    const result = await api(`/api/batches/${encodeURIComponent(id)}/recycle`, { method: "POST", body: JSON.stringify(payload) });
    closeModal(); state.activeBatch = null;
    toast(`${result.batch.batch_code} moved to Recycle Bin with ${result.recycled} card(s). Use Undo to restore it.`);
    await loadDashboard(); setView("inbound");
  } catch (error) { toast(error.message, "error"); }
}

async function openSettings() {
  try {
    const [settings, activity] = await Promise.all([api("/api/settings"), api("/api/activity")]);
    const history = activity.actions.length ? activity.actions.map((item) => `<li><strong>${escapeHtml(item.description)}</strong><small>${formatDate(item.created_at)}${item.undone_at ? " · Undone" : ""}</small></li>`).join("") : `<li><small>No actions recorded yet.</small></li>`;
    openModal("Dex Settings", "Change seller limits and Recycle Bin retention without rebuilding Dex.", `<form id="settings-form"><div class="form-grid">
      <label>Business Timezone<input name="timezone" value="${escapeHtml(settings.timezone || "America/New_York")}"></label>
      <label>TCGplayer Capacity<input name="tcg_capacity" type="number" min="1" step="1" value="${settings.tcg_capacity || 500}"></label>
      <label>Recycle Retention (Days)<input name="recycle_retention_days" type="number" min="1" step="1" value="${settings.recycle_retention_days || 180}"></label>
      <label class="toggle-label"><input name="recycle_auto_purge" type="checkbox" value="1" ${settings.recycle_auto_purge ? "checked" : ""}>Automatically Purge Eligible Cards</label>
    </div><h3 class="subheading">Recent Actions</h3><ul class="activity-list">${history}</ul><div class="form-actions"><button type="button" class="button secondary" data-action="close-modal">Cancel</button><button class="button primary">${icon("save")}Save Settings</button></div></form>`);
    document.querySelector("#settings-form").addEventListener("submit", saveSettings);
  } catch (error) { toast(error.message, "error"); }
}

async function saveSettings(event) {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
  try {
    await api("/api/settings", { method: "POST", body: JSON.stringify(payload) });
    closeModal(); toast("Settings saved."); await loadDashboard();
  } catch (error) { toast(error.message, "error"); }
}

function sourceCardRows(cards) {
  if (!cards.length) return emptyState("database", "No source cards indexed", "Place One Piece card images or a card-list CSV in the source database folder, then rescan.");
  return `<div class="source-card-grid">${cards.map((card) => `<article class="source-card">
    ${card.small_image_url || card.full_image_url ? `<img src="${card.small_image_url || card.full_image_url}" alt="">` : `<span>${icon("image")}</span>`}
    <div><strong>${escapeHtml(card.card_number)}</strong><small>${escapeHtml(card.name || "Image only")} · ${escapeHtml(card.set_name || card.set_code)}</small></div>
    <em>${escapeHtml(card.rarity || "No rarity")}</em>
  </article>`).join("")}</div>`;
}

function samStateLabel(value) {
  return ({ AUTO_MATCHED: "Auto Matched", NEEDS_REVIEW: "Needs Review", UNIDENTIFIED: "Unidentified", OPERATOR_CONFIRMED: "Operator Confirmed", OPERATOR_CORRECTED: "Operator Corrected" })[value] || titleCase(value || "Unknown");
}

function samQueueLane(title, items, tone) {
  return `<section class="sam-review-lane ${tone}"><header><h3>${escapeHtml(title)}</h3><span>${items.length}</span></header><div>${items.length ? items.map((item) => `<article data-viewport-key="sam-job-${escapeHtml(item.job_uuid)}">${item.scan_image_url ? `<img src="${item.scan_image_url}" alt="Scanned ${escapeHtml(item.sku)}">` : `<span class="sam-image-placeholder">${icon("image-off")}</span>`}<div><strong>${escapeHtml(item.sku)}</strong><small>${escapeHtml(item.batch_code)} · ${samStateLabel(item.state)}</small><span>${Math.round(Number(item.confidence || 0) * 100)}% family confidence${(item.exception_codes || []).length ? ` · ${escapeHtml(item.exception_codes.join(", "))}` : ""}</span>${item.review_priority_reasons?.length ? `<small class="sam-priority">Review priority: ${escapeHtml(item.review_priority_reasons.map(titleCase).join(" · "))}</small>` : ""}</div><button class="button secondary" data-action="open-sam-review" data-id="${escapeHtml(item.job_uuid)}">${icon("scan-search")}Review</button></article>`).join("") : `<p>No cards in this lane.</p>`}</div></section>`;
}

function samChallengerShadowPanel(report) {
  if (!report?.available) return "";
  const baseline = report.baseline || {};
  const challenger = report.challenger || {};
  const baseStates = baseline.states || {};
  const challengerStates = challenger.states || {};
  const originalFive = report.original_five || {};
  const gates = report.gates || {};
  const metric = (label, before, after) => `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(before ?? "Unknown"))} <em>→</em> ${escapeHtml(String(after ?? "Unknown"))}</strong></article>`;
  return `<section class="sam-challenger-shadow" data-viewport-key="sam-challenger-shadow">
    <header><div><span class="eyebrow">Shadow only · no inventory authority</span><h2>SAM Challenger v1 comparison</h2><p>Candidate generation is broadened; SAM v1 scoring, thresholds, OCR policy, and authority rules remain unchanged.</p></div><span class="badge ${gates.false_auto_matches_zero ? "green" : "red"}">${gates.false_auto_matches_zero ? "Safety gate passed" : "Safety gate failed"}</span></header>
    <div class="sam-challenger-metrics">
      ${metric("Correct family in candidate pool", `${baseline.correct_family_entered_candidate_pool || 0}/50`, `${challenger.correct_family_entered_candidate_pool || 0}/50`)}
      ${metric("Correct top family", `${baseline.correct_top_family || 0}/50`, `${challenger.correct_top_family || 0}/50`)}
      ${metric("Original five recovered", `${originalFive.baseline_correct_top_family || 0}/5`, `${originalFive.challenger_correct_top_family || 0}/5`)}
      ${metric("False auto-matches", baseline.false_auto_matches ?? "Unknown", challenger.false_auto_matches ?? "Unknown")}
      ${metric("Auto Match", baseStates.AUTO_MATCHED || 0, challengerStates.AUTO_MATCHED || 0)}
      ${metric("Needs Review", baseStates.NEEDS_REVIEW || 0, challengerStates.NEEDS_REVIEW || 0)}
      ${metric("Unidentified", baseStates.UNIDENTIFIED || 0, challengerStates.UNIDENTIFIED || 0)}
      ${metric("Average end-to-end latency", `${baseline.latency_ms?.average ?? "Unknown"} ms`, `${challenger.latency_ms?.average ?? "Unknown"} ms`)}
    </div>
    <footer><strong>${escapeHtml(report.challenger_version || "SAM Challenger v1")}</strong><span>Trusted OCR nominates candidates only. Family recognition and printing resolution remain separate.</span></footer>
  </section>`;
}

function samAuditedIntakePanel(audited, intake) {
  const cards = intake?.cards || [];
  const status = audited?.available ? "Frozen build verified" : "Audited build unavailable";
  return `<section class="sam-audited-panel" data-viewport-key="sam-audited-intake">
    <header><div><span class="eyebrow">Assisted use · operator authority only</span><h2>SAM Multi-Evidence Audited Intake</h2><p>SAM suggests a One Piece family. Nothing enters inventory identity until you confirm or correct it.</p></div><span class="badge ${audited?.available ? "green" : "red"}">${escapeHtml(status)}</span></header>
    <div class="sam-audited-safety"><strong>SAM suggests → operator decides → DEX records</strong><span>${audited?.pending || 0} frozen result(s) awaiting a decision · exact printing remains manual</span></div>
    <details open data-disclosure-key="sam-audited-existing-scans"><summary>Select an existing One Piece front scan</summary>
      <div class="sam-audited-intake-list">${cards.length ? cards.map((card) => `<article>
        ${card.front_image ? `<img src="/media/${escapeHtml(card.front_image)}" alt="Front scan ${escapeHtml(card.sku)}">` : `<span>${icon("image-off")}</span>`}
        <div><strong>${escapeHtml(card.sku)}</strong><small>${escapeHtml(card.batch_code)} · ${escapeHtml(card.name || "Needs identification")}</small><span>${card.latest_result_uuid ? "Audited result already recorded" : "Ready for audited suggestion"}</span></div>
        ${card.latest_result_uuid ? `<button class="button secondary" data-action="open-sam-audited-result" data-id="${escapeHtml(card.latest_result_uuid)}">${icon("clipboard-check")}Review result</button>` : `<button class="button primary" data-action="run-sam-audited" data-sku="${escapeHtml(card.sku)}" ${audited?.available ? "" : "disabled"}>${icon("scan-search")}Process scan</button>`}
      </article>`).join("") : `<p>No One Piece cards with a front scan are available. Add a scan through normal inbound intake first.</p>`}</div>
    </details>
  </section>`;
}

function samAuditedCandidate(candidate, selected = false) {
  if (!candidate) return `<p>No family suggestion was produced.</p>`;
  const assertions = (candidate.assertions || []).filter((item) => ["STRONG_SUPPORT", "SUPPORT", "CONFLICT"].includes(item.state));
  return `<button type="button" class="sam-audited-candidate ${selected ? "selected" : ""}" data-action="select-sam-audited-family" data-family="${escapeHtml(candidate.card_number)}" data-name="${escapeHtml(candidate.canonical_name || "")}">
    <span><strong>${escapeHtml(candidate.card_number)}</strong><em>${escapeHtml(candidate.canonical_name || "Unknown name")}</em></span>
    <small>${candidate.strong_support_count || 0} strong · ${candidate.support_count || 0} supporting · ${candidate.conflict_count || 0} conflict</small>
    ${assertions.length ? `<ul>${assertions.slice(0, 3).map((item) => `<li class="${String(item.state).toLowerCase()}">${escapeHtml(item.reason || item.state)}</li>`).join("")}</ul>` : ""}
  </button>`;
}

function renderSamAuditedModal() {
  const payload = state.samAuditedResult;
  if (!payload) return;
  const result = payload.original_result || {};
  const suggested = result.suggested_family || "";
  const selected = state.samAuditedSelection || (suggested ? { card_number: suggested, canonical_name: result.suggested_name } : null);
  const candidates = (result.candidates || []).slice(0, 10);
  const decided = Boolean(payload.decision_recorded);
  const catalogRows = (state.samAuditedCatalogResults || []).map((item) => `<button type="button" class="sam-audited-catalog-row" data-action="select-sam-audited-family" data-family="${escapeHtml(item.card_number)}" data-name="${escapeHtml(item.canonical_name || "")}"><strong>${escapeHtml(item.card_number)}</strong><span>${escapeHtml(item.canonical_name || "Unknown name")}</span></button>`).join("");
  const evidence = (result.human_explanation || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  const decision = payload.operator_decisions?.[payload.operator_decisions.length - 1];
  const selectionDiffers = selected?.card_number && selected.card_number !== suggested;
  openModal("Audited SAM Assisted Intake", `${payload.sku} · immutable suggestion + operator decision`, `<div class="sam-audited-review">
    <section class="sam-audited-freeze"><span>Immutable pre-operator result</span><strong>${escapeHtml(result.evidence_state || "UNRESOLVED")} · ${escapeHtml(result.review_state || "NEEDS REVIEW")}</strong><small>Build ${escapeHtml(result.accepted_build_identifier || "Frozen v1a")} · result SHA-256 ${escapeHtml(payload.original_result_sha256)}</small></section>
    <div class="sam-side-by-side"><article class="sam-scan-card"><span>Physical scan</span>${payload.scan_image_url ? `<img src="${escapeHtml(payload.scan_image_url)}" alt="Physical scan ${escapeHtml(payload.sku)}">` : `<div>${icon("image-off")}No scan</div>`}<strong>${escapeHtml(payload.sku)}</strong></article><section><span>SAM suggestion · not inventory truth</span><h2>${escapeHtml(suggested || "Unidentified")}</h2><strong>${escapeHtml(result.suggested_name || "No canonical name suggested")}</strong><p>Exact printing, rarity, treatment, stamps, and marketplace identity remain unresolved and operator-only.</p></section></div>
    ${evidence ? `<details open><summary>Evidence summary and conflicts</summary><ul class="sam-audited-evidence">${evidence}</ul></details>` : ""}
    <details open data-disclosure-key="sam-audited-candidates"><summary>Bounded candidate list · ${(result.candidates || []).length}</summary><div class="sam-audited-candidates">${candidates.map((candidate) => samAuditedCandidate(candidate, selected?.card_number === candidate.card_number)).join("") || "<p>No candidates.</p>"}</div></details>
    <details data-disclosure-key="sam-audited-catalog"><summary>Verify or correct using the frozen local catalog</summary><form id="sam-audited-catalog-search"><label>Card number or name<input name="q" autocomplete="off" placeholder="OP16-034 or Monkey.D.Luffy"></label><button class="button secondary">${icon("search")}Search after inference</button></form><div class="sam-audited-catalog-results">${catalogRows}</div></details>
    <section class="sam-audited-selection"><span>Operator-selected family</span><strong>${escapeHtml(selected?.card_number || "None")}</strong><small>${escapeHtml(selected?.canonical_name || "Choose a candidate or search the catalog")}</small></section>
    ${decided ? `<div class="success"><strong>Decision recorded: ${escapeHtml(decision?.action || "Complete")}</strong><p>${decision?.identity_applied ? "The operator-approved family is now inventory truth." : "No inventory identity was written."} Original SAM evidence remains immutable.</p></div>` : `<div class="sam-correction-grid"><label>Reason for correction/review<select id="sam-audited-reason"><option value="">Not required for unchanged confirmation</option><option value="OPERATOR_VISUAL_IDENTIFICATION">Operator visual identification</option><option value="OCR_FAILURE">OCR failure</option><option value="CANDIDATE_GENERATION_FAILURE">Candidate generation failure</option><option value="FUSION_RANKING_FAILURE">Evidence fusion/ranking failure</option><option value="INSUFFICIENT_EVIDENCE">Insufficient evidence</option><option value="OTHER">Other</option></select></label><label>Operator note<textarea id="sam-audited-note" placeholder="Required for corrections, review, unidentified, or rescan."></textarea></label></div>
      <div class="sam-review-actions"><button class="button primary" data-action="decide-sam-audited" data-id="${escapeHtml(payload.result_uuid)}" data-decision="${selectionDiffers ? "CORRECTED_FAMILY" : "CONFIRMED_UNCHANGED"}" ${selected?.card_number ? "" : "disabled"}>${icon(selectionDiffers ? "square-pen" : "circle-check")}${selectionDiffers ? "Correct Family" : "Confirm Family"}</button><button class="button secondary" data-action="decide-sam-audited" data-id="${escapeHtml(payload.result_uuid)}" data-decision="ESCALATED_REVIEW">Needs Review</button><button class="button tertiary" data-action="decide-sam-audited" data-id="${escapeHtml(payload.result_uuid)}" data-decision="MARKED_UNIDENTIFIED">Unidentified</button></div>`}
    <p class="help-text">Catalog search begins only after the SAM result is frozen. Operator decisions are never fed back into this active recognizer or used automatically as training labels.</p>
  </div>`);
  document.querySelector("#sam-audited-catalog-search")?.addEventListener("submit", searchSamAuditedCatalog);
}

async function runSamAudited(sku) {
  if (state.samAuditedPending) return;
  state.samAuditedPending = true;
  try {
    toast(`Processing ${sku} with the frozen audited recognizer...`);
    state.samAuditedResult = await api(`/api/sam/audited/cards/${encodeURIComponent(sku)}/recognize`, { method: "POST", body: JSON.stringify({ request_id: requestId("SAM-AUDIT-RESULT") }) });
    const result = state.samAuditedResult.original_result || {};
    state.samAuditedSelection = result.suggested_family ? { card_number: result.suggested_family, canonical_name: result.suggested_name } : null;
    state.samAuditedCatalogResults = [];
    renderSamAuditedModal();
  } catch (error) { toast(`Audited SAM did not write identity: ${error.message}`, "error"); }
  finally { state.samAuditedPending = false; }
}

async function openSamAuditedResult(resultUuid) {
  try {
    state.samAuditedResult = await api(`/api/sam/audited/results/${encodeURIComponent(resultUuid)}`);
    const result = state.samAuditedResult.original_result || {};
    state.samAuditedSelection = result.suggested_family ? { card_number: result.suggested_family, canonical_name: result.suggested_name } : null;
    state.samAuditedCatalogResults = [];
    renderSamAuditedModal();
  } catch (error) { toast(error.message, "error"); }
}

function selectSamAuditedFamily(family, name) {
  state.samAuditedSelection = { card_number: family, canonical_name: name || "" };
  renderSamAuditedModal();
}

async function searchSamAuditedCatalog(event) {
  event.preventDefault();
  const query = new URLSearchParams(new FormData(event.currentTarget));
  query.set("result_uuid", state.samAuditedResult?.result_uuid || "");
  try {
    const result = await api(`/api/sam/audited/catalog-search?${query.toString()}`);
    state.samAuditedCatalogResults = result.families || [];
    renderSamAuditedModal();
  } catch (error) { toast(error.message, "error"); }
}

async function decideSamAudited(resultUuid, action) {
  if (state.samAuditedPending) return;
  const selection = state.samAuditedSelection || {};
  const payload = { request_id: requestId(`SAM-AUDIT-${action}`), action };
  if (selection.card_number) payload.selected_family = selection.card_number;
  if (selection.canonical_name) payload.selected_name = selection.canonical_name;
  if (action !== "CONFIRMED_UNCHANGED") {
    payload.reason_code = document.querySelector("#sam-audited-reason")?.value?.trim() || "";
    payload.notes = document.querySelector("#sam-audited-note")?.value?.trim() || "";
    if (!payload.reason_code || !payload.notes) return toast("Choose a reason and enter a note before recording this decision.", "error");
  }
  state.samAuditedPending = true;
  try {
    state.samAuditedResult = await api(`/api/sam/audited/results/${encodeURIComponent(resultUuid)}/decision`, { method: "POST", body: JSON.stringify(payload) });
    const wrote = state.samAuditedResult.operator_decisions?.at(-1)?.identity_applied;
    toast(wrote ? "Operator-approved family entered inventory. Exact printing remains manual." : "Decision recorded. No inventory identity was written.");
    renderSamAuditedModal();
  } catch (error) { toast(`Decision not recorded: ${error.message}`, "error"); }
  finally { state.samAuditedPending = false; }
}

async function renderSAM() {
  loading();
  try {
    const data = await api("/api/sam/source");
    state.samSource = data;
    const s = data.summary;
    const phase7 = data.phase7 || {};
    const provider = phase7.provider || {};
    const references = phase7.references || {};
    const review = phase7.review || { counts: {}, lanes: {} };
    const challenger = phase7.challenger || {};
    const audited = phase7.audited || {};
    const auditedIntake = phase7.audited_intake || { cards: [] };
    app.innerHTML = `<div class="view-stack">
      <section class="summary-strip">
        <div class="metric"><span>Matched</span><strong>${review.counts?.MATCHED || 0}</strong><small>Trusted identities</small></div>
        <div class="metric"><span>Needs Review</span><strong>${review.counts?.NEEDS_REVIEW || 0}</strong><small>Operator decision needed</small></div>
        <div class="metric"><span>Unidentified</span><strong>${review.counts?.UNIDENTIFIED || 0}</strong><small>No trustworthy match</small></div>
        <div class="metric"><span>Auto-match rule</span><strong>${Math.round(Number(phase7.auto_match_threshold || 0.90) * 100)}%</strong><small>${escapeHtml(phase7.rules_version || "Conservative backend rules")}</small></div>
      </section>
      <section class="sam-panel">
        <div><span class="eyebrow">One Piece only</span><h2>SAM Recognition + Human Review</h2><p>${escapeHtml(references.configured_path || s.source_path || "No source path configured")}</p><small>${references.last_indexed ? `Reference index updated ${formatDate(references.last_indexed)}` : "Reference library not indexed yet"} · original images remain unchanged</small></div>
        <div class="sam-panel-actions"><button class="button secondary" data-action="probe-sam-provider">${icon("activity")}Check OPTCG</button><button class="button primary" data-action="rescan-source">${icon("refresh-cw")}Incremental Index</button></div>
      </section>
      <section class="sam-health-grid"><article><span>Local references</span><strong>${references.active || 0}</strong><small>${references.sets || 0} set(s) · ${references.duplicate_hashes || 0} exact duplicate(s)</small></article><article><span>OPTCG metadata cache</span><strong>${provider.cache?.active || 0}</strong><small>${provider.cache?.stale || 0} stale · ${provider.cache?.missing || 0} missing · structured metadata only</small></article><article><span>Provider safety</span><strong>${provider.configured ? "Configured" : "Not configured"}</strong><small>No physical scans or local references are transmitted.</small></article></section>
      ${samAuditedIntakePanel(audited, auditedIntake)}
      ${samChallengerShadowPanel(challenger)}
      <section class="sam-queue-head"><div><h2>Batch Review Queues</h2><p>Scanning continues while uncertain cards wait here. Confidence is not authority.</p></div><span class="badge green">Scanning not blocked</span></section>
      <div class="sam-review-board">${samQueueLane("Matched", review.lanes?.MATCHED || [], "matched")}${samQueueLane("Needs Review", review.lanes?.NEEDS_REVIEW || [], "review")}${samQueueLane("Unidentified", review.lanes?.UNIDENTIFIED || [], "unidentified")}</div>
      <details class="sam-reference-browser" data-disclosure-key="sam-reference-browser"><summary>Indexed reference catalog</summary>${sourceCardRows(data.cards || [])}</details>
    </div>`;
    refreshIcons();
  } catch (error) { showError(error); }
}

async function rescanSource() {
  try {
    toast("SAM is scanning the source database...");
    const result = await api("/api/sam/source/rescan", { method: "POST", body: JSON.stringify({ request_id: requestId("SAM-INDEX") }) });
    const indexed = result.phase7_index || {};
    toast(`SAM indexed ${indexed.indexed || 0}, refreshed ${indexed.changed || 0}, and skipped ${indexed.unchanged || 0} unchanged reference(s).`);
    await renderSAM();
  } catch (error) { toast(error.message, "error"); }
}

async function probeSamProvider() {
  try {
    const result = await api("/api/sam/provider/health?probe=1");
    toast(result.available ? `OPTCG metadata provider is reachable (${result.latency_ms} ms).` : "OPTCG is unavailable. SAM will use cached metadata, local references, and manual review.", result.available ? "success" : "error");
  } catch (error) { toast(`Provider check failed. Local SAM remains available: ${error.message}`, "error"); }
}

function samReferenceCard(reference, selected = false) {
  if (!reference) return `<div class="sam-comparison-card empty">${icon("image-off")}<strong>No trustworthy candidate</strong><small>Use Find Match or leave this scan unidentified.</small></div>`;
  return `<article class="sam-comparison-card ${selected ? "selected" : ""}">${reference.image_url ? `<img src="${reference.image_url}" alt="Reference ${escapeHtml(reference.card_number)}">` : `<span>${icon("image")}</span>`}<div><strong>${escapeHtml(reference.card_number || "Unknown number")}</strong><h3>${escapeHtml(reference.card_name || "Unknown name")}</h3><small>${escapeHtml(reference.set_code || "Unknown set")} · ${escapeHtml(reference.variant || "Unknown variant")} · ${escapeHtml(reference.printing || "Unknown printing")}</small><span>${Math.round(Number(reference.confidence || 0) * 100)}% confidence</span></div></article>`;
}

function renderSamReviewModal() {
  const result = state.samReview;
  if (!result) return;
  const job = result.job;
  const selected = state.samReviewSelection || result.top_candidate;
  const alternates = (result.alternate_candidates || []).map((item) => `<button type="button" class="sam-alternate" data-action="select-sam-reference" data-id="${item.id}">${samReferenceCard(item, selected?.id === item.id)}</button>`).join("");
  const searchRows = (state.samReferenceResults || []).map((item) => `<button type="button" class="sam-search-result" data-action="select-sam-reference" data-id="${item.id}">${samReferenceCard(item, selected?.id === item.id)}</button>`).join("");
  const exceptions = (job.exception_codes || []).map((code) => `<span class="badge amber">${escapeHtml(titleCase(code))}</span>`).join("");
  const numberEvidence = job.evidence?.card_number || {};
  const visualTop = job.evidence?.visual_top_candidate || {};
  const numberSource = numberEvidence.source === "LOCAL_TESSERACT_OCR" ? "Read from physical scan" : numberEvidence.source === "SCAN_FILENAME" ? "Read from scan filename" : numberEvidence.source === "EXISTING_OPERATOR_OR_INTAKE_FIELD" ? "Provided during intake" : "";
  const numberAgreement = numberEvidence.agreement;
  const numberEvidenceClass = numberAgreement === "CONFLICT" || numberAgreement === "REFERENCE_MISSING" ? "warning" : numberEvidence.normalized ? "confirmed" : "unknown";
  const numberEvidenceMessage = numberAgreement === "CONFLICT"
    ? `OCR read ${escapeHtml(numberEvidence.normalized)} but visual evidence favors ${escapeHtml(visualTop.card_number || "another reference")}. Automatic authority is blocked.`
    : numberAgreement === "REFERENCE_MISSING"
      ? `OCR read ${escapeHtml(numberEvidence.normalized)}, but no matching local reference is available. Automatic authority is blocked.`
      : numberEvidence.normalized
        ? `${escapeHtml(numberSource || "Card-number evidence available")}${numberAgreement === "AGREES_WITH_VISUAL_TOP" ? " · agrees with reference" : ""}`
        : "Card number unreadable. Visual recognition remains available.";
  const numberDebug = `<details class="sam-number-debug"><summary>OCR details</summary><dl><div><dt>Raw OCR</dt><dd>${escapeHtml(numberEvidence.raw || "No valid text")}</dd></div><div><dt>Method</dt><dd>${escapeHtml(numberEvidence.method_version || "Not available")}</dd></div><div><dt>Region</dt><dd>${escapeHtml(numberEvidence.region_name || "Not available")}</dd></div><div><dt>Path</dt><dd>${escapeHtml(numberEvidence.execution_path === "FAST_PATH" ? "Fast path" : numberEvidence.execution_path === "ESCALATED_PATH" ? "Escalated path" : "Not available")}${numberEvidence.attempts ? ` · ${Number(numberEvidence.attempts)} OCR attempt${Number(numberEvidence.attempts) === 1 ? "" : "s"}` : ""}</dd></div><div><dt>Confidence</dt><dd>${Math.round(Number(numberEvidence.confidence || 0) * 100)}%${numberEvidence.consensus_support ? ` · ${numberEvidence.consensus_support}/${numberEvidence.valid_candidate_attempts || numberEvidence.consensus_support} valid reads agreed` : ""}</dd></div><div><dt>Timing</dt><dd>${Number(numberEvidence.preprocessing_ms || 0).toFixed(2)} ms preprocessing · ${Number(numberEvidence.execution_ms || 0).toFixed(2)} ms OCR</dd></div></dl></details>`;
  const cardNumberEvidence = `<section class="sam-number-evidence ${numberEvidenceClass}" aria-label="Card number evidence"><span>Card number</span><strong>${escapeHtml(numberEvidence.normalized || "Unreadable")}${numberAgreement === "AGREES_WITH_VISUAL_TOP" ? " ✓" : ""}</strong><p>${numberEvidenceMessage}</p>${numberDebug}</section>`;
  const family = result.family || {};
  const printing = result.printing || {};
  const languageIdentity = result.language || {};
  const finishIdentity = result.finish || {};
  const inventoryIdentity = result.inventory || {};
  const economics = state.samReviewEconomics;
  const selectedFamilyId = Number(selected?.family_id || 0);
  const selectedPrintingId = Number(selected?.commercial_printing_id || 0);
  const familyCorrecting = Boolean(
    selected && result.top_candidate && Number(selected.id) !== Number(result.top_candidate.id)
    && (!selectedFamilyId || !Number(result.top_candidate.family_id || 0) || Number(result.top_candidate.family_id || 0) !== selectedFamilyId)
  );
  const printingCorrecting = Boolean(printing.authoritative && selectedPrintingId && Number(printing.printing_id || 0) !== selectedPrintingId);
  const correcting = familyCorrecting || printingCorrecting;
  const correctionDraft = state.samCorrectionDraft || {};
  const correctionFields = correcting ? `<section class="sam-correction-fields" aria-labelledby="sam-correction-heading"><div><h3 id="sam-correction-heading">Correction details required</h3><p>Record why the selected identity replaces SAM's original suggestion. Both values are preserved in recognition history.</p></div><div class="sam-correction-grid"><label>Correction reason<select id="sam-correction-reason" required><option value="OPERATOR_IDENTIFICATION_CORRECTION" ${correctionDraft.reason_code === "OPERATOR_IDENTIFICATION_CORRECTION" ? "selected" : ""}>Wrong card identity</option><option value="VARIANT_OR_PRINTING_CORRECTION" ${correctionDraft.reason_code === "VARIANT_OR_PRINTING_CORRECTION" ? "selected" : ""}>Wrong variant or printing</option><option value="REFERENCE_METADATA_CORRECTION" ${correctionDraft.reason_code === "REFERENCE_METADATA_CORRECTION" ? "selected" : ""}>Reference metadata issue</option><option value="OTHER" ${correctionDraft.reason_code === "OTHER" ? "selected" : ""}>Other</option></select></label><label>Operator note<textarea id="sam-correction-notes" required placeholder="Explain why OP16-035 is the correct identity.">${escapeHtml(correctionDraft.notes || "")}</textarea></label></div><p id="sam-correction-error" class="sam-correction-error" role="alert" ${state.samCorrectionError ? "" : "hidden"}>${escapeHtml(state.samCorrectionError)}</p></section>` : "";
  const familyAction = familyCorrecting
    ? `<button type="button" class="button primary" title="Confirm Correction" data-action="correct-sam-family" data-id="${escapeHtml(job.job_uuid)}" data-revision="${result.current_revision}" data-reference-id="${selected?.id || ""}">${icon("square-pen")}Correct Family</button>`
    : family.authoritative
      ? `<button type="button" class="button success" disabled>${icon("circle-check")}Family confirmed</button>`
      : `<button type="button" class="button primary" aria-label="Confirm Match by confirming card family" data-action="confirm-sam-family" data-id="${escapeHtml(job.job_uuid)}" data-revision="${result.current_revision}" data-reference-id="${selected?.id || ""}" ${selected ? "" : "disabled"}>${icon("circle-check")}Confirm Family</button>`;
  const printingAction = selectedPrintingId
    ? printingCorrecting
      ? `<button type="button" class="button secondary" data-action="correct-sam-printing" data-id="${escapeHtml(job.job_uuid)}" data-revision="${result.current_revision}" data-reference-id="${selected?.id || ""}" data-printing-id="${selectedPrintingId}">${icon("square-pen")}Correct Printing</button>`
      : printing.authoritative && Number(printing.printing_id) === selectedPrintingId
        ? `<button type="button" class="button success" disabled>${icon("circle-check")}Printing confirmed</button>`
        : `<button type="button" class="button secondary" data-action="confirm-sam-printing" data-id="${escapeHtml(job.job_uuid)}" data-revision="${result.current_revision}" data-reference-id="${selected?.id || ""}" data-printing-id="${selectedPrintingId}">${icon("circle-check")}Confirm Printing</button>`
    : `<button type="button" class="button secondary" disabled>Printing not documented</button>`;
  const markerEvidence = (printing.positive_evidence?.marker_evidence || []).map((item) => `<li><strong>${escapeHtml(titleCase(item.marker))}</strong><span class="sam-marker-state ${String(item.state || "UNRESOLVED").toLowerCase()}">${escapeHtml(titleCase(item.state))}</span><small>${escapeHtml(item.explanation || item.source_kind || "Evidence explanation unavailable")}</small></li>`).join("");
  const printingEvidenceRows = (printing.competing_same_family_printings || []).map((item) => {
    const observations = (item.marker_evidence || item.evidence_observations || []).map((evidence) => `<li><strong>${escapeHtml(titleCase(evidence.marker || evidence.evidence_type))}</strong><span class="sam-marker-state ${String(evidence.state || "UNRESOLVED").toLowerCase()}">${escapeHtml(titleCase(evidence.state || "UNRESOLVED"))}</span><small>${escapeHtml(evidence.explanation || evidence.source_kind || "No additional explanation")}</small></li>`).join("");
    const disposition = item.excluded_by_negative_evidence ? "Excluded by negative evidence" : item.positive_evidence_complete ? "Positive evidence complete" : "Plausible · evidence unresolved";
    return `<article class="sam-printing-evidence-card ${item.excluded_by_negative_evidence ? "excluded" : ""}"><header><div><strong>#${item.rank || "—"} · ${escapeHtml(item.variant_label || item.artwork_identity || `Printing ${item.printing_id}`)}</strong><small>${Math.round(Number(item.confidence || 0) * 100)}% quality-adjusted visual evidence</small></div><span class="badge ${item.excluded_by_negative_evidence ? "coral" : item.positive_evidence_complete ? "green" : "amber"}">${escapeHtml(disposition)}</span></header><p>${escapeHtml(item.explanation || "Evidence unresolved")}</p>${item.quality_warnings?.length ? `<small>Reference quality: ${escapeHtml(item.quality_warnings.map(titleCase).join(" · "))}</small>` : ""}${observations ? `<ul class="sam-marker-evidence">${observations}</ul>` : ""}</article>`;
  }).join("");
  const assertions = (result.history?.assertions || []).map((item) => `<li><strong>${escapeHtml(titleCase(item.field_scope))} · ${escapeHtml(titleCase(item.certainty))}</strong><span>${escapeHtml(item.actor)} · ${escapeHtml(item.assertion_uuid)}</span><small>${escapeHtml(item.reason_code || "No reason code")} · ${escapeHtml(formatDate(item.created_at))}${item.supersedes_assertion_id ? ` · supersedes assertion #${Number(item.supersedes_assertion_id)}` : ""}</small></li>`).join("");
  const observations = (result.printing_evidence_observations || []).map((item) => `<li><strong>${escapeHtml(titleCase(item.evidence_type))} · ${escapeHtml(titleCase(item.observed_state))}</strong><span>${escapeHtml(item.source_kind)}${item.reference_id ? ` · reference #${Number(item.reference_id)}` : " · no authoritative reference link"}</span><small>${escapeHtml(item.explanation || "No explanation recorded")} · ${escapeHtml(item.evidence?.evidence_version || "Evidence version unknown")} · ${escapeHtml(formatDate(item.observed_at))}</small></li>`).join("");
  const provenance = `<details class="sam-provenance"><summary>Identity provenance and append-only history</summary><p>Engine ${escapeHtml(job.engine_version || "Unknown")} · job ${escapeHtml(job.job_uuid)} · ${escapeHtml(formatDate(job.completed_at || job.submitted_at || job.created_at))}</p><h4>Assertions</h4><ul>${assertions || "<li>No identity assertions recorded.</li>"}</ul><h4>Printing observations</h4><ul>${observations || "<li>No printing observations recorded.</li>"}</ul></details>`;
  const identityPanels = `<div class="sam-identity-panels"><section class="sam-identity-panel"><span>Family identity</span><h3>${escapeHtml(family.card_number || selected?.card_number || "Unresolved")} · ${escapeHtml(family.canonical_name || selected?.card_name || "Unknown")}</h3><p>${Math.round(Number(family.confidence || 0) * 100)}% family confidence</p><strong class="sam-certainty">${escapeHtml(titleCase(family.certainty || "UNRESOLVED"))}${family.authoritative ? " · Inventory truth" : " · Suggestion"}</strong></section><section class="sam-identity-panel ${printing.authoritative ? "confirmed" : "unresolved"}"><span>Exact commercial printing</span><h3>${escapeHtml(printing.variant_label || printing.artwork_identity || "Unresolved")}</h3><p>${Math.round(Number(printing.confidence || 0) * 100)}% printing confidence</p><strong class="sam-certainty">${escapeHtml(titleCase(printing.certainty || "UNRESOLVED"))}${printing.authoritative ? " · Operator confirmed" : " · Not inventory truth"}</strong><p>Language: ${escapeHtml(languageIdentity.value || "Unknown")} · ${escapeHtml(titleCase(languageIdentity.certainty || "UNRESOLVED"))}<br>Finish: ${escapeHtml(finishIdentity.value || "Unknown")} · ${escapeHtml(titleCase(finishIdentity.certainty || "UNRESOLVED"))}</p><p>${escapeHtml(printing.unresolved_reason ? titleCase(printing.unresolved_reason) : "Positive printing evidence recorded")}</p>${markerEvidence ? `<ul class="sam-marker-evidence">${markerEvidence}</ul>` : ""}</section></div>${printingEvidenceRows ? `<details class="sam-printing-evidence" ${printing.certainty === "CONFLICTING" ? "open" : ""}><summary>Printing evidence intelligence · ${(printing.competing_same_family_printings || []).length} same-family candidate(s)</summary><p>Each commercial printing is evaluated independently. Missing evidence remains unresolved; confident negative evidence can exclude but never select a printing.</p><div>${printingEvidenceRows}</div></details>` : ""}<section class="sam-inventory-identity"><strong>Existing inventory value</strong><span>Legacy variant: ${escapeHtml(inventoryIdentity.legacy_variant || "None")} · provenance ${escapeHtml(titleCase(inventoryIdentity.legacy_variant_provenance || "LEGACY_RECORDED"))}</span><small>Legacy text is preserved but is not a confirmed commercial printing.</small></section>`;
  const economicsContext = economics ? `<section class="sam-economics-context"><header><strong>Economics context · display only</strong><span>Never used for identity confidence</span></header>${jarvisCardPanel(economics)}</section>` : `<p class="sam-economics-unavailable">Economics context unavailable. Identity review remains usable and independent.</p>`;
  openModal("SAM Human Review", `${result.sku} · family and printing review`, `<div class="sam-review-modal"><div class="sam-side-by-side"><article class="sam-scan-card"><span>Physical scan</span>${result.scan_image_url ? `<img src="${result.scan_image_url}" alt="Physical scan ${escapeHtml(result.sku)}">` : `<div>${icon("image-off")}No front scan</div>`}<strong>${escapeHtml(result.sku)}</strong></article><div><span>${correcting ? "Operator-selected reference" : "SAM best candidate"}</span>${samReferenceCard(selected)}</div></div>${identityPanels}${economicsContext}${cardNumberEvidence}<div class="sam-evidence"><strong>${Math.round(Number(job.confidence || 0) * 100)}% overall ranking score · ${escapeHtml(samStateLabel(job.recognition_state))}</strong><p>${escapeHtml(job.evidence?.candidate_narrowing || "No candidate narrowing")} · ${job.evidence?.candidates_scored || 0} candidate(s) compared · engine ${escapeHtml(job.engine_version)}</p><div>${exceptions || `<span class="badge green">No exception flags</span>`}</div><small>Metadata: ${escapeHtml(selected?.metadata_provider || job.evidence?.provider_cache?.provider || "Local reference / Unknown provider")} · descriptive only; it cannot grant printing authority.</small></div>${provenance}${alternates ? `<details open><summary>Reference assets and alternate candidates</summary><div class="sam-alternates">${alternates}</div></details>` : ""}<details class="sam-find-match" ${state.samReferenceResults.length ? "open" : ""}><summary>Find Match</summary><form id="sam-reference-search-form"><label>Card number, name, or set<input name="q" autocomplete="off" placeholder="OP16-032 or card name"></label><button class="button secondary">${icon("search")}Search local references</button></form><div class="sam-search-results">${searchRows}</div></details>${correctionFields}<div class="sam-review-actions family-actions"><strong>Family</strong>${familyAction}<button class="button tertiary" data-action="leave-sam-unidentified" data-id="${escapeHtml(job.job_uuid)}" data-revision="${result.current_revision}">Leave Unidentified</button></div><div class="sam-review-actions printing-actions"><strong>Printing</strong>${printingAction}<button class="button tertiary" data-action="leave-sam-printing-unresolved" data-id="${escapeHtml(job.job_uuid)}" data-revision="${result.current_revision}">Leave Printing Unresolved</button><button class="button tertiary" data-action="mark-sam-printing-conflict" data-id="${escapeHtml(job.job_uuid)}" data-revision="${result.current_revision}">Mark Conflict</button></div><p class="help-text">SAM assigns identity only. Family may be confirmed without resolving printing. Phase 2 system evidence remains suggestion-only; exact printing is operator-only. Acquisition cost, basis, rip economics, sales economics, and market value never influence recognition confidence or authority.</p></div>`);
  const legacyConflicts = (inventoryIdentity.legacy_conflicts || []).map((item) => `<li><strong>${escapeHtml(titleCase(item.field || "legacy value"))} conflict:</strong> recorded ${escapeHtml(item.legacy_value || "Unknown")} · printing suggestion ${escapeHtml(item.proposed_value || "Unknown")}</li>`).join("");
  if (legacyConflicts) {
    document.querySelector(".sam-inventory-identity")?.insertAdjacentHTML("beforeend", `<div class="warning sam-legacy-conflict"><strong>Legacy identity conflict</strong><ul>${legacyConflicts}</ul><small>The recorded legacy value is preserved. The printing suggestion does not overwrite it.</small></div>`);
  }
  document.querySelector("#sam-reference-search-form")?.addEventListener("submit", searchSamReferences);
  document.querySelector("#sam-correction-reason")?.addEventListener("change", (event) => { state.samCorrectionDraft.reason_code = event.currentTarget.value; });
  document.querySelector("#sam-correction-notes")?.addEventListener("input", (event) => { state.samCorrectionDraft.notes = event.currentTarget.value; });
}

async function openSamReview(jobUuid) {
  try {
    state.samReview = await api(`/api/sam/recognitions/${encodeURIComponent(jobUuid)}`);
    state.samReviewEconomics = await api(`/api/jarvis/economics/cards/${encodeURIComponent(state.samReview.sku)}`).catch(() => null);
    state.samReviewSelection = state.samReview.top_candidate;
    state.samReferenceResults = [];
    state.samCorrectionDraft = { reason_code: "OPERATOR_IDENTIFICATION_CORRECTION", notes: "" };
    state.samCorrectionError = "";
    state.samDecisionPending = false;
    renderSamReviewModal();
  } catch (error) { toast(error.message, "error"); }
}

async function searchSamReferences(event) {
  event.preventDefault();
  const query = new URLSearchParams(new FormData(event.currentTarget));
  try {
    const result = await api(`/api/sam/references/search?${query.toString()}`);
    state.samReferenceResults = result.references || [];
    renderSamReviewModal();
  } catch (error) { toast(error.message, "error"); }
}

function selectSamReference(referenceId) {
  const all = [...(state.samReview?.candidates || []), ...(state.samReferenceResults || [])];
  state.samReviewSelection = all.find((item) => Number(item.id) === Number(referenceId)) || null;
  state.samCorrectionError = "";
  renderSamReviewModal();
}

function showSamCorrectionError(message) {
  state.samCorrectionError = message;
  const error = document.querySelector("#sam-correction-error");
  if (error) {
    error.textContent = message;
    error.hidden = false;
  }
}

async function decideSam(jobUuid, action, revision, referenceId = "", printingId = "") {
  if (state.samDecisionPending) return;
  const payload = { request_id: requestId(`SAM-${action}`), action, expected_revision: Number(revision) };
  if (referenceId) payload.reference_id = Number(referenceId);
  if (printingId) payload.printing_id = Number(printingId);
  if (action === "CORRECT" || action === "CORRECT_FAMILY" || action === "CORRECT_PRINTING") {
    const reason = document.querySelector("#sam-correction-reason")?.value?.trim() || "";
    const notes = document.querySelector("#sam-correction-notes")?.value?.trim() || "";
    state.samCorrectionDraft = { reason_code: reason, notes };
    if (!reason || !notes) {
      showSamCorrectionError("Choose a correction reason and enter an operator note before confirming.");
      toast("Correction not saved. Complete the highlighted correction details.", "error");
      document.querySelector(!reason ? "#sam-correction-reason" : "#sam-correction-notes")?.focus?.();
      return;
    }
    payload.reason_code = reason;
    payload.notes = notes;
  }
  const selectedNumber = state.samReviewSelection?.card_number || "the selected identity";
  const actionSelectors = { CORRECT: "correct-sam-match", CORRECT_FAMILY: "correct-sam-family", CONFIRM: "confirm-sam-match", CONFIRM_FAMILY: "confirm-sam-family", CONFIRM_PRINTING: "confirm-sam-printing", CORRECT_PRINTING: "correct-sam-printing", LEAVE_PRINTING_UNRESOLVED: "leave-sam-printing-unresolved", MARK_PRINTING_CONFLICT: "mark-sam-printing-conflict", LEAVE_UNIDENTIFIED: "leave-sam-unidentified" };
  const actionButton = document.querySelector(`[data-action="${actionSelectors[action] || ""}"]`);
  state.samDecisionPending = true;
  if (actionButton) { actionButton.disabled = true; actionButton.setAttribute("aria-busy", "true"); }
  try {
    state.samReview = await api(`/api/sam/recognitions/${encodeURIComponent(jobUuid)}/decision`, { method: "POST", body: JSON.stringify(payload) });
    const successMessage = action === "LEAVE_UNIDENTIFIED" ? "Scan left unidentified; no identity was guessed."
      : action === "LEAVE_PRINTING_UNRESOLVED" ? "Family preserved; exact printing remains unresolved."
      : action === "MARK_PRINTING_CONFLICT" ? "Printing conflict recorded; no exact printing was forced."
      : action === "CONFIRM_PRINTING" || action === "CORRECT_PRINTING" ? "Exact printing decision saved with append-only provenance."
      : action === "CORRECT" || action === "CORRECT_FAMILY" ? `Correction saved. ${selectedNumber} is now the authoritative identity; SAM's original suggestion remains in history. Exact printing remains independent.`
      : "Family confirmed. Exact printing remains independent.";
    toast(successMessage);
    closeModal();
    await loadDashboard();
    await renderSAM();
  } catch (error) {
    const isCorrection = action === "CORRECT" || action === "CORRECT_FAMILY" || action === "CORRECT_PRINTING";
    const message = `${isCorrection ? "Correction" : "Decision"} not saved: ${error.message}`;
    if (isCorrection) showSamCorrectionError(message);
    toast(message, "error");
  } finally {
    state.samDecisionPending = false;
    if (actionButton?.isConnected) { actionButton.disabled = false; actionButton.removeAttribute("aria-busy"); }
  }
}

async function samMatchCard(sku) {
  try {
    const result = await api(`/api/cards/${encodeURIComponent(sku)}/sam/recognize`, { method: "POST", body: JSON.stringify({ request_id: requestId("SAM-CARD") }) });
    toast(result.matched ? `${sku} auto-matched under conservative rules.` : `${sku}: ${samStateLabel(result.effective_state)}.`, result.matched ? "success" : "error");
    await loadDashboard();
    if (result.effective_state !== "AUTO_MATCHED") await openSamReview(result.job.job_uuid);
    else if (modal.open) await openEditCard(sku);
    else if (state.activeBatch) await renderBatch(state.activeBatch.batch.id);
  } catch (error) { toast(error.message, "error"); }
}

async function samMatchBatch(selectedOnly = false) {
  const batch = state.activeBatch?.batch;
  if (!batch) return;
  const skus = selectedOnly ? selectedBatchSkus() : [];
  if (selectedOnly && !skus.length) return toast("Select at least one card for SAM.", "error");
  try {
    toast(selectedOnly ? `SAM is matching ${skus.length} selected card(s)...` : "SAM is matching this batch...");
    const result = await api(`/api/batches/${batch.id}/sam/recognize`, { method: "POST", body: JSON.stringify({ request_id: requestId("SAM-BATCH"), skus }) });
    toast(`SAM matched ${result.matched || 0}; ${result.needs_review || 0} need review; ${result.unidentified || 0} unidentified.`);
    await loadDashboard(); await renderBatch(batch.id);
  } catch (error) { toast(error.message, "error"); }
}

async function undoLast() {
  if (!confirm("Undo the most recent supported inventory action?")) return;
  try {
    const result = await api("/api/undo", { method: "POST", body: "{}" });
    toast(`Undone: ${result.undone}`); await loadDashboard(); setView(state.view);
  } catch (error) { toast(error.message, "error"); }
}

async function renderLabels() {
  loading();
  try {
    await loadDashboard();
    const data = await api("/api/labels");
    state.labels = data.labels;
    state.selectedLabels = new Set(data.labels.map((card) => card.sku));
    const content = data.labels.length ? `<div class="view-stack">
      <div class="toolbar label-toolbar"><label><input id="select-all-labels" type="checkbox" checked> Select all</label><span class="filter-count">${data.labels.length} waiting</span><button class="button primary" data-action="print-labels">${icon("printer")}Print selected</button></div>
      <div class="label-grid" id="label-print-area">${data.labels.map(labelMarkup).join("")}</div></div>`
      : emptyState("badge-check", "Label queue is clear", "Finish an inbound batch to queue its sleeve labels.", `<button class="button primary" data-action="new-batch">${icon("plus")}New batch</button>`);
    app.innerHTML = content; refreshIcons();
  } catch (error) { showError(error); }
}

function labelMarkup(card) {
  const qr = `/api/qr?value=${encodeURIComponent(`DEX:${card.sku}`)}`;
  return `<div class="label-select selected" data-label="${escapeHtml(card.sku)}"><input type="checkbox" checked aria-label="Select ${escapeHtml(card.sku)}">
    <div class="thermal-label"><img src="${qr}" alt="QR code for ${escapeHtml(card.sku)}"><div><strong>${escapeHtml(card.sku)}</strong><span>${escapeHtml(card.game)} · ${escapeHtml(card.set_code)}</span></div></div>
  </div>`;
}

async function printLabels() {
  if (!state.selectedLabels.size) return toast("Select at least one label.", "error");
  window.print();
  try {
    await api("/api/labels/printed", { method: "POST", body: JSON.stringify({ skus: [...state.selectedLabels] }) });
    toast(`${state.selectedLabels.size} labels marked printed.`); await loadDashboard(); await renderLabels();
  } catch (error) { toast(error.message, "error"); }
}

function outboundPage() {
  return `<div class="view-stack"><div class="outbound-mode" role="group" aria-label="Outbound order type"><button class="button ${state.outboundMode === "CARD" ? "primary" : "secondary"}" data-action="outbound-mode" data-mode="CARD">Card sale</button><button class="button ${state.outboundMode === "SEALED" ? "primary" : "secondary"}" data-action="outbound-mode" data-mode="SEALED">Sealed-product sale</button></div><p class="acquisition-notice">Card and sealed-product orders are separate workflows in v2.1-test.</p><div class="outbound-layout">
    <section class="scan-zone"><div class="section-header"><div><h2>Scan sold cards</h2><p>QR code or typed SKU</p></div><button class="button secondary" data-action="start-camera">${icon("camera")}Use camera</button></div>
      <form class="scan-entry" id="sku-entry"><input name="sku" autocomplete="off" autocapitalize="characters" placeholder="PKM-B20260617-001"><button class="button primary">${icon("plus")}Add</button></form>
      <div class="camera-frame" id="camera-frame"><video id="camera-video" playsinline></video></div>
      <div class="scanned-list" id="scanned-list">${outboundItems()}</div>
    </section>
    <aside class="order-panel"><h3>Order details</h3><form id="outbound-form"><div class="form-grid">
      <label>Platform<select name="platform" required><option>TCGplayer</option><option>eBay</option></select></label>
      <label>Order number<input name="order_number" placeholder="Optional"></label>
      <label>Sold date<input name="sold_at" type="date" value="${localDateValue()}"></label>
      <label>Card subtotal<div class="money-input"><span>$</span><input name="subtotal" id="sale-subtotal" type="number" min="0" step=".01" value="0"></div></label>
      <label>Shipping collected<div class="money-input"><span>$</span><input name="shipping_collected" id="sale-shipping" type="number" min="0" step=".01" value="0"></div></label>
      <label>Platform fees<div class="money-input"><span>$</span><input name="platform_fees" id="sale-fees" type="number" min="0" step=".01" value="0"></div></label>
      <label>Postage cost<div class="money-input"><span>$</span><input name="postage_cost" id="sale-postage" type="number" min="0" step=".01" value="0"></div></label>
    </div><div class="net-preview"><span>Estimated net</span><strong id="net-value">$0.00</strong></div>
      <button class="button primary" style="width:100%" id="complete-sale" ${state.outboundCards.length ? "" : "disabled"}>${icon("check")}Complete outbound order</button>
    </form></aside>
  </div></div>`;
}

function sealedOutboundPage() {
  const batches = Array.isArray(state.sealedInventory?.batches) ? state.sealedInventory.batches : [];
  const available = batches.filter((batch) => batch.counts.remaining > 0);
  const options = available.map((batch) => `<option value="${batch.batch_id}">${escapeHtml(batch.batch_code)} · ${escapeHtml(batch.product_name)} · ${batch.counts.remaining} remaining</option>`).join("");
  const selected = available[0] || null;
  return `<div class="view-stack"><div class="outbound-mode" role="group" aria-label="Outbound order type"><button class="button secondary" data-action="outbound-mode" data-mode="CARD">Card sale</button><button class="button primary" data-action="outbound-mode" data-mode="SEALED">Sealed-product sale</button></div><p class="acquisition-notice">This creates a sealed-only order. Receipt groups are informational and do not allocate shared costs.</p>${available.length ? `<div class="outbound-layout">
    <section class="scan-zone sealed-sale-zone"><div class="section-header"><div><h2>Select sealed units</h2><p>DEX consumes the lowest available stable unit sequence unless exact unit IDs are supplied through the API.</p></div></div><div id="sealed-batch-summary">${sealedBatchSummary(selected)}</div></section>
    <aside class="order-panel"><h3>Sealed order details</h3><form id="sealed-outbound-form"><div class="form-grid">
      <label>Acquisition batch<select name="batch_id" required>${options}</select></label>
      <label>Quantity<input name="quantity" type="number" min="1" step="1" value="1" required></label>
      <label>Marketplace<select name="platform" required><option>TCGplayer</option><option>eBay</option><option>Other</option></select></label>
      <label>Order number<input name="order_number" placeholder="Optional"></label>
      <label>Sold date<input name="sold_at" type="date" value="${localDateValue()}"></label>
      <label>Gross merchandise sale<div class="money-input"><span>$</span><input name="merchandise_total" type="number" min="0" step=".01" value="0" required></div><span class="help-text">Merchandise revenue only; excludes marketplace-collected tax.</span></label>
      <label>Shipping collected<div class="money-input"><span>$</span><input name="shipping_collected" type="number" min="0" step=".01" value="0"></div></label>
      <label>Marketplace fees<div class="money-input"><span>$</span><input name="marketplace_fees" type="number" min="0" step=".01" value="0"></div></label>
      <label>Actual postage<div class="money-input"><span>$</span><input name="actual_postage" type="number" min="0" step=".01" value="0"></div></label>
      <label>Marketplace-collected sales tax<div class="money-input"><span>$</span><input name="marketplace_tax" type="number" min="0" step=".01" value="0"></div><span class="help-text">Recorded separately and excluded from revenue and P/L.</span></label>
      <label class="full">Notes<textarea name="notes"></textarea></label>
    </div><div class="sealed-economics-preview" id="sealed-economics-preview"><span>Enter order facts to preview backend-calculated economics.</span></div><button class="button primary" style="width:100%" id="complete-sealed-sale">${icon("check")}Complete sealed order</button></form></aside>
  </div>` : emptyState("package-x", "No sealed units available", "A trustworthy sealed acquisition must have at least one remaining unit. Opened, sold, and adjusted units cannot be sold again.")}</div>`;
}

function sealedBatchSummary(batch) {
  if (!batch) return "";
  const c = batch.counts;
  const pending = c.intake_pending || 0;
  return `<div class="sealed-batch-card"><h3>${escapeHtml(batch.product_name)}</h3><p><strong>${escapeHtml(batch.batch_code)}</strong> · ${escapeHtml(batch.receipt_group_reference || "No receipt group")}</p><div class="acquisition-facts-grid"><div><span>Acquired</span><strong>${batch.units_acquired}</strong></div><div><span>Remaining / available</span><strong>${c.remaining}</strong></div>${pending ? `<div><span>Intake undecided</span><strong>${pending}</strong></div>` : ""}<div><span>Opened</span><strong>${c.opened}</strong></div><div><span>Sold</span><strong>${c.sold}</strong></div><div><span>Corrected / adjusted</span><strong>${c.corrected_adjusted}</strong></div><div><span>Remaining basis</span><strong>${formatCents(batch.remaining_basis_cents)}</strong></div></div><p class="estimate-footnote">Reconciliation: ${batch.units_acquired} acquired = ${c.opened} opened + ${c.sold} sold + ${c.remaining} available + ${pending} intake undecided + ${c.corrected_adjusted} corrected/adjusted.</p></div>`;
}

function outboundItems() {
  if (!state.outboundCards.length) return emptyState("scan-qr-code", "Ready to scan", "Each scanned sleeve is added to this outbound order.");
  return state.outboundCards.map((card) => `<div class="scanned-item"><div><strong>${escapeHtml(card.name)}</strong><small>${escapeHtml(card.sku)} · ${escapeHtml(card.card_number)}</small></div><button class="icon-button" title="Remove" data-action="remove-outbound" data-sku="${escapeHtml(card.sku)}">${icon("x")}</button></div>`).join("");
}

async function renderOutbound() {
  if (state.outboundMode === "SEALED") {
    loading();
    try { state.sealedInventory = await api("/api/sealed-inventory"); }
    catch (error) { showError(error); return; }
    app.innerHTML = sealedOutboundPage(); refreshIcons();
    const form = document.querySelector("#sealed-outbound-form");
    if (form) {
      form.addEventListener("submit", completeSealedSale);
      form.addEventListener("input", debounce(() => previewSealedSale(form), 180));
      form.addEventListener("change", () => {
        const selected = state.sealedInventory.batches.find((batch) => String(batch.batch_id) === String(form.elements.batch_id.value));
        document.querySelector("#sealed-batch-summary").innerHTML = sealedBatchSummary(selected);
        previewSealedSale(form);
      });
      await previewSealedSale(form);
    }
    return;
  }
  app.innerHTML = outboundPage(); refreshIcons();
  document.querySelector("#sku-entry").addEventListener("submit", addOutboundSku);
  document.querySelector("#outbound-form").addEventListener("submit", completeSale);
  document.querySelectorAll("#outbound-form input[type=number]").forEach((input) => input.addEventListener("input", updateNet));
  setTimeout(() => document.querySelector('#sku-entry input')?.focus(), 80);
}

function sealedSalePayload(form) {
  return Object.fromEntries(new FormData(form).entries());
}

async function previewSealedSale(form) {
  if (!form?.isConnected) return;
  try {
    const preview = await api("/api/sealed-sales/preview", { method: "POST", body: JSON.stringify(sealedSalePayload(form)) });
    state.sealedSalePreview = preview;
    const target = document.querySelector("#sealed-economics-preview");
    if (!target) return;
    target.innerHTML = `<div><span>Exact units</span><strong>${preview.sealed_units.map((unit) => escapeHtml(unit.unit_code)).join(", ")}</strong></div><div><span>Sold basis</span><strong>${formatCents(preview.sold_basis_cents)}</strong></div><div><span>Net proceeds</span><strong>${formatCents(preview.net_proceeds_cents)}</strong></div><div><span>Realized P/L</span><strong>${formatCents(preview.realized_profit_loss_cents)}</strong></div>`;
  } catch (error) {
    state.sealedSalePreview = null;
    const target = document.querySelector("#sealed-economics-preview");
    if (target) target.innerHTML = `<span class="warning-text">${escapeHtml(error.message)}</span>`;
  }
}

async function completeSealedSale(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = sealedSalePayload(form);
  payload.request_id = requestId("SEALED-SALE");
  try {
    const order = await api("/api/sealed-sales", { method: "POST", body: JSON.stringify(payload) });
    toast(`${order.item_count} sealed unit(s) sold with exact basis.`);
    state.sealedSalePreview = null;
    await loadDashboard(); setView("sales");
  } catch (error) { toast(error.message, "error"); }
}

async function addOutboundSku(eventOrValue) {
  let raw;
  if (typeof eventOrValue === "string") raw = eventOrValue;
  else {
    eventOrValue.preventDefault();
    raw = new FormData(eventOrValue.currentTarget).get("sku");
    eventOrValue.currentTarget.reset();
  }
  const sku = String(raw || "").trim().toUpperCase().replace(/^DEX:/, "");
  if (!sku || state.outboundCards.some((card) => card.sku === sku)) return;
  try {
    const card = await api(`/api/cards/${encodeURIComponent(sku)}`);
    if (card.status === "SOLD") throw new Error(`${sku} is already sold.`);
    state.outboundCards.push(card);
    document.querySelector("#scanned-list").innerHTML = outboundItems();
    document.querySelector("#complete-sale").disabled = false;
    refreshIcons(); toast(`${sku} added.`);
  } catch (error) { toast(error.message, "error"); }
}

function updateNet() {
  const val = (id) => Number(document.querySelector(id)?.value || 0);
  const net = val("#sale-subtotal") + val("#sale-shipping") - val("#sale-fees") - val("#sale-postage");
  document.querySelector("#net-value").textContent = formatMoney(net, "$0.00");
}

async function completeSale(event) {
  event.preventDefault();
  if (!state.outboundCards.length) return;
  const payload = Object.fromEntries(new FormData(event.currentTarget).entries());
  payload.skus = state.outboundCards.map((card) => card.sku);
  try {
    await api("/api/sales", { method: "POST", body: JSON.stringify(payload) });
    toast(`${state.outboundCards.length} cards marked sold.`); state.outboundCards = [];
    await loadDashboard(); setView("sales");
  } catch (error) { toast(error.message, "error"); }
}

async function startCamera() {
  if (!window.isSecureContext) return toast("Camera access is blocked because Dex is using HTTP. Open Dex through HTTPS, or type the SKU.", "error");
  if (!navigator.mediaDevices?.getUserMedia) return toast("This browser does not provide camera access. You can type the SKU.", "error");
  if (!("BarcodeDetector" in window)) return toast("This browser cannot detect QR codes. You can type the SKU.", "error");
  try {
    const formats = await BarcodeDetector.getSupportedFormats();
    if (!formats.includes("qr_code")) throw new Error("QR detection is not supported by this browser.");
    state.cameraStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
    const video = document.querySelector("#camera-video");
    video.srcObject = state.cameraStream; await video.play();
    document.querySelector("#camera-frame").classList.add("active");
    const detector = new BarcodeDetector({ formats: ["qr_code"] });
    const scan = async () => {
      if (!state.cameraStream) return;
      const codes = await detector.detect(video).catch(() => []);
      if (codes[0]?.rawValue) { await addOutboundSku(codes[0].rawValue); await new Promise((r) => setTimeout(r, 900)); }
      requestAnimationFrame(scan);
    };
    scan();
  } catch (error) { toast(error.message, "error"); stopCamera(); }
}

function stopCamera() {
  state.cameraStream?.getTracks().forEach((track) => track.stop());
  state.cameraStream = null;
}

function postSaleEntryLabel(entry) {
  const labels = { MERCHANDISE: "Merchandise", SHIPPING: "Shipping collected", MARKETPLACE_FEES: "Marketplace fees", POSTAGE: "Actual postage", OTHER_NET: "Other net proceeds" };
  return `${labels[entry.component_type] || titleCase(entry.component_type)} ${formatCents(entry.amount_delta_cents)}`;
}

async function openSaleOrderDetails(orderId) {
  try {
    const [order, jarvis] = await Promise.all([
      api(`/api/sales/${encodeURIComponent(orderId)}`),
      api(`/api/jarvis/economics/sales/${encodeURIComponent(orderId)}`).catch(() => null),
    ]);
    const original = order.financials.original;
    const effective = order.financials.effective;
    const itemRows = (order.items || []).map((item) => `<tr><td><code>${escapeHtml(item.identifier)}</code><small>${escapeHtml(item.item_type.replace("_", " "))} · internal item #${item.sale_item_id}</small></td><td>${escapeHtml(item.batch_code)}</td><td>${formatCents(item.basis_cents)}</td><td>${item.returned ? `<span class="badge ${item.return_outcome === "DAMAGED_EXCLUDED" ? "coral" : "amber"}">${escapeHtml(titleCase(item.return_outcome))}</span>` : `<span class="badge neutral">Sold</span>`}</td></tr>`).join("");
    const eventRows = (order.events || []).length ? order.events.map((event) => `<li class="post-sale-event ${event.reversed ? "reversed" : ""}"><div><strong>${escapeHtml(titleCase(event.event_type))}</strong><small>${escapeHtml(event.event_id)} · effective ${formatDate(event.effective_at)} · recorded ${formatDate(event.recorded_at)}</small><span>${escapeHtml(event.reason_code)}${event.notes ? ` · ${escapeHtml(event.notes)}` : ""}</span>${event.entries.length ? `<span>${event.entries.map(postSaleEntryLabel).map(escapeHtml).join(" · ")}</span>` : ""}</div>${event.reversible && order.post_sale_eligible ? `<button class="button secondary" data-action="reverse-post-sale-event" data-id="${escapeHtml(event.event_id)}" data-order-id="${order.id}">${icon("rotate-ccw")}Reverse</button>` : `<span class="badge neutral">${event.reversed ? "Reversed" : "Retained"}</span>`}</li>`).join("") : `<li class="post-sale-event empty"><span>No post-sale events recorded.</span></li>`;
    const status = order.canceled_at
      ? `<div class="sealed-order-status canceled"><strong>Canceled / undone</strong><span>${formatDate(order.canceled_at)} · Original history retained.</span></div>`
      : `<div class="sealed-order-status active"><strong>Completed ${escapeHtml(titleCase(order.order_type))} order</strong><span>Original sale facts preserved</span></div>`;
    const undoAction = order.order_type === "SEALED" && order.undo_eligible ? `<button class="button danger" data-action="undo-sealed-order" data-id="${order.id}">${icon("undo-2")}Undo sealed sale</button>` : "";
    const actions = order.post_sale_eligible ? `<div class="post-sale-actions"><button class="button secondary" data-action="post-sale-form" data-kind="partial-refund" data-id="${order.id}">Partial refund</button><button class="button secondary" data-action="post-sale-form" data-kind="full-refund" data-id="${order.id}">Full refund</button><button class="button secondary" data-action="post-sale-form" data-kind="return" data-id="${order.id}">Customer return</button><button class="button secondary" data-action="post-sale-form" data-kind="chargeback" data-id="${order.id}">Chargeback</button><button class="button secondary" data-action="post-sale-form" data-kind="fee-credit" data-id="${order.id}">Fee credit</button><button class="button secondary" data-action="post-sale-form" data-kind="postage-refund" data-id="${order.id}">Postage refund</button><button class="button secondary" data-action="post-sale-form" data-kind="correction" data-id="${order.id}">Sale correction</button>${undoAction}</div>` : "";
    openModal(`${titleCase(order.order_type)} order ${escapeHtml(order.order_number || `#${order.id}`)}`, "Original sale facts, effective operational economics, exact item identities, and append-only post-sale history.", `<div class="sealed-order-detail post-sale-detail">${status}<div class="detail-list sealed-order-metadata"><div><span>Marketplace</span><strong>${escapeHtml(order.platform)}</strong></div><div><span>Sale date</span><strong>${formatDate(order.sold_at)}</strong></div><div><span>Order number</span><strong>${escapeHtml(order.order_number || "—")}</strong></div><div><span>Calculation version</span><strong>${escapeHtml(order.calculation_version)}</strong></div></div>${jarvisSalePanel(jarvis)}<h3>Exact sale items</h3><div class="table-wrap"><table><thead><tr><th>Identity</th><th>Batch</th><th>Basis</th><th>Current sale state</th></tr></thead><tbody>${itemRows}</tbody></table></div><h3>Original recorded facts</h3><div class="sealed-order-economics"><div><span>Merchandise</span><strong>${formatCents(original.merchandise_cents)}</strong></div><div><span>Shipping collected</span><strong>${formatCents(original.shipping_cents)}</strong></div><div><span>Marketplace fees</span><strong>${formatCents(original.marketplace_fees_cents)}</strong></div><div><span>Actual postage</span><strong>${formatCents(original.postage_cents)}</strong></div><div class="total"><span>Original net proceeds</span><strong>${formatCents(original.net_proceeds_cents)}</strong></div></div><h3>Effective Realized Economics</h3><div class="sealed-order-economics"><div><span>Effective merchandise</span><strong>${formatCents(effective.merchandise_cents)}</strong></div><div><span>Effective shipping</span><strong>${formatCents(effective.shipping_cents)}</strong></div><div><span>Effective fees</span><strong>${formatCents(effective.marketplace_fees_cents)}</strong></div><div><span>Effective postage</span><strong>${formatCents(effective.postage_cents)}</strong></div><div><span>Chargebacks / other net</span><strong>${formatCents(effective.other_net_cents)}</strong></div><div class="total"><span>Effective net proceeds</span><strong>${formatCents(effective.net_proceeds_cents)}</strong></div><div><span>Active sold basis</span><strong>${formatCents(order.sold_basis_cents)}</strong></div><div class="total"><span>Realized P/L</span><strong>${formatCents(order.realized_profit_loss_cents)}</strong></div></div><p class="help-text">${escapeHtml(order.original_sale_immutable_notice)} Refunds and chargebacks do not restore inventory. Postage remains spent unless a postage refund event exists.</p><h3>Post-sale history</h3><ul class="post-sale-events">${eventRows}</ul>${actions}<div class="form-actions"><button type="button" class="button secondary" data-action="close-modal">Close</button></div></div>`);
  } catch (error) { toast(error.message, "error"); }
}

async function openSealedOrderDetails(orderId) { return openSaleOrderDetails(orderId); }

function postSaleCommonFields(reasons) {
  return `<label>Reason<select name="reason_code">${reasons}</select></label><label>Effective date<input type="date" name="effective_at"></label><label class="full">Notes<textarea name="notes" placeholder="Add context; required for Other and manual corrections"></textarea></label>`;
}

async function openPostSaleForm(orderId, kind) {
  try {
    const order = await api(`/api/sales/${encodeURIComponent(orderId)}`);
    const forms = {
      "partial-refund": { title: "Partial refund", endpoint: "refunds", fields: `<label>Merchandise refund<div class="money-input"><span>$</span><input name="merchandise_amount" type="number" min="0" step=".01" value="0.00" required></div></label><label>Shipping refund<div class="money-input"><span>$</span><input name="shipping_amount" type="number" min="0" step=".01" value="0.00" required></div></label>${postSaleCommonFields(`<option value="CUSTOMER_REQUEST">Customer request</option><option value="ORDER_CANCELLATION">Order cancellation</option><option value="SERVICE_RECOVERY">Service recovery</option><option value="OTHER">Other</option>`)}` },
      "full-refund": { title: "Full remaining refund", endpoint: "full-refund", fields: `<p class="acquisition-notice">This refunds the backend-confirmed remaining merchandise and shipping amounts. It does not restore inventory, reverse fees, or refund postage.</p>${postSaleCommonFields(`<option value="CUSTOMER_REQUEST">Customer request</option><option value="ORDER_CANCELLATION">Order cancellation</option><option value="SERVICE_RECOVERY">Service recovery</option><option value="OTHER">Other</option>`)}` },
      "chargeback": { title: "Chargeback", endpoint: "chargebacks", fields: `<label>Chargeback amount<div class="money-input"><span>$</span><input name="amount" type="number" min=".01" step=".01" required></div></label>${postSaleCommonFields(`<option value="PAYMENT_DISPUTE">Payment dispute</option><option value="FRAUD">Fraud</option><option value="PROCESSING_ERROR">Processing error</option><option value="OTHER">Other</option>`)}` },
      "fee-credit": { title: "Marketplace fee credit", endpoint: "fee-credits", fields: `<label>Fee credit<div class="money-input"><span>$</span><input name="amount" type="number" min=".01" step=".01" required></div></label>${postSaleCommonFields(`<option value="MARKETPLACE_CREDIT">Marketplace credit</option><option value="FEE_REVERSAL">Fee reversal</option><option value="OTHER">Other</option>`)}` },
      "postage-refund": { title: "Postage refund", endpoint: "postage-refunds", fields: `<label>Actual refund<div class="money-input"><span>$</span><input name="amount" type="number" min=".01" step=".01" required></div></label>${postSaleCommonFields(`<option value="CARRIER_REFUND">Carrier refund</option><option value="VOIDED_LABEL">Voided label</option><option value="OTHER">Other</option>`)}` },
      "correction": { title: "Sale-level correction", endpoint: "corrections", fields: `<p class="help-text full">Enter signed changes only. Positive fee/postage changes increase expense; use the dedicated credit/refund actions when money was actually returned.</p><label>Merchandise change<div class="money-input"><span>$</span><input name="merchandise_delta" type="number" step=".01" value="0.00"></div></label><label>Shipping change<div class="money-input"><span>$</span><input name="shipping_delta" type="number" step=".01" value="0.00"></div></label><label>Fee change<div class="money-input"><span>$</span><input name="marketplace_fees_delta" type="number" step=".01" value="0.00"></div></label><label>Postage change<div class="money-input"><span>$</span><input name="postage_delta" type="number" step=".01" value="0.00"></div></label><label>Other net proceeds change<div class="money-input"><span>$</span><input name="other_net_delta" type="number" step=".01" value="0.00"></div></label>${postSaleCommonFields(`<option value="DATA_ENTRY_ERROR">Data-entry error</option><option value="MARKETPLACE_ADJUSTMENT">Marketplace adjustment</option><option value="OTHER">Other</option>`)}` },
    };
    if (kind === "return") return openReturnForm(order);
    const config = forms[kind];
    openModal(config.title, `Order ${escapeHtml(order.order_number || `#${order.id}`)} · original sale remains unchanged.`, `<form id="post-sale-form" data-id="${order.id}" data-endpoint="${config.endpoint}"><div class="form-grid">${config.fields}</div><div class="form-actions"><button type="button" class="button secondary" data-action="open-sale-order" data-id="${order.id}">Back</button><button class="button primary">Record immutable event</button></div></form>`);
    document.querySelector("#post-sale-form").addEventListener("submit", submitPostSaleForm);
  } catch (error) { toast(error.message, "error"); }
}

function openReturnForm(order) {
  const eligible = (order.items || []).filter((item) => !item.returned && item.status === "SOLD");
  const rows = eligible.map((item) => `<div class="return-item-row"><label class="checkbox-label"><input type="checkbox" name="return_item" value="${item.sale_item_id}" data-type="${escapeHtml(item.item_type)}"><span><strong>${escapeHtml(item.identifier)}</strong><small>${escapeHtml(item.batch_code)} · exact sale item #${item.sale_item_id}</small></span></label><label>Condition outcome<select data-return-outcome="${item.sale_item_id}"><option value="RESTOCKED">Sellable / restock</option><option value="DAMAGED_EXCLUDED">Damaged / Excluded</option></select></label></div>`).join("");
  openModal("Customer return", `Order ${escapeHtml(order.order_number || `#${order.id}`)} · inventory moves only after both confirmations.`, `<form id="post-sale-return-form" data-id="${order.id}"><div class="return-item-list">${rows || `<p class="acquisition-notice">No exact sold identities are currently eligible for return.</p>`}</div><div class="form-grid">${postSaleCommonFields(`<option value="CUSTOMER_RETURN">Customer return</option><option value="ORDER_CANCELLATION">Order cancellation</option><option value="OTHER">Other</option>`)}</div><div class="return-confirmations"><label class="checkbox-label"><input type="checkbox" name="physical_received_confirmed" required><span>I confirm the exact physical item(s) were received.</span></label><label class="checkbox-label"><input type="checkbox" name="condition_confirmed" required><span>I inspected and confirmed each selected condition outcome.</span></label></div><div class="form-actions"><button type="button" class="button secondary" data-action="open-sale-order" data-id="${order.id}">Back</button><button class="button primary" ${eligible.length ? "" : "disabled"}>Record return</button></div></form>`);
  document.querySelector("#post-sale-return-form").addEventListener("submit", submitReturnForm);
}

async function submitPostSaleForm(event) {
  event.preventDefault(); const form = event.currentTarget; const payload = Object.fromEntries(new FormData(form).entries());
  payload.request_id = requestId("POST-SALE");
  try { await api(`/api/sales/${form.dataset.id}/${form.dataset.endpoint}`, { method: "POST", body: JSON.stringify(payload) }); toast("Post-sale event recorded."); await renderSales(captureLogicalViewport()); await openSaleOrderDetails(form.dataset.id); } catch (error) { toast(error.message, "error"); }
}

async function submitReturnForm(event) {
  event.preventDefault(); const form = event.currentTarget; const data = new FormData(form); const selected = [...form.querySelectorAll('input[name="return_item"]:checked')];
  const payload = { request_id: requestId("RETURN"), reason_code: data.get("reason_code"), effective_at: data.get("effective_at"), notes: data.get("notes"), physical_received_confirmed: data.get("physical_received_confirmed") === "on", condition_confirmed: data.get("condition_confirmed") === "on", items: selected.map((input) => ({ item_type: input.dataset.type, sale_item_id: Number(input.value), outcome: form.querySelector(`[data-return-outcome="${input.value}"]`).value })) };
  try { await api(`/api/sales/${form.dataset.id}/returns`, { method: "POST", body: JSON.stringify(payload) }); toast("Exact returned inventory updated."); await loadDashboard(); await renderSales(captureLogicalViewport()); await openSaleOrderDetails(form.dataset.id); } catch (error) { toast(error.message, "error"); }
}

function openPostSaleReversal(eventId, orderId) {
  openModal("Reverse post-sale event", `The original ${eventId} remains immutable and visible.`, `<form id="post-sale-reversal-form" data-id="${escapeHtml(eventId)}" data-order-id="${orderId}"><label>Reason<select name="reason_code"><option value="DATA_ENTRY_ERROR">Data-entry error</option><option value="MARKETPLACE_ADJUSTMENT">Marketplace adjustment</option><option value="OTHER">Other</option></select></label><label>Effective date<input type="date" name="effective_at"></label><label>Required notes<textarea name="notes" required></textarea></label><div class="form-actions"><button type="button" class="button secondary" data-action="open-sale-order" data-id="${orderId}">Back</button><button class="button danger">Create linked inverse event</button></div></form>`);
  document.querySelector("#post-sale-reversal-form").addEventListener("submit", async (event) => { event.preventDefault(); const form = event.currentTarget; const payload = Object.fromEntries(new FormData(form).entries()); payload.request_id = requestId("POST-SALE-REVERSAL"); try { await api(`/api/post-sale-events/${encodeURIComponent(form.dataset.id)}/reverse`, { method: "POST", body: JSON.stringify(payload) }); toast("Linked inverse event recorded."); await loadDashboard(); await renderSales(captureLogicalViewport()); await openSaleOrderDetails(form.dataset.orderId); } catch (error) { toast(error.message, "error"); } });
}

async function undoSealedOrder(orderId) {
  if (!confirm("Undo this sealed sale? The exact consumed units will return to remaining inventory and the canceled order history will be retained.")) return;
  const viewport = captureLogicalViewport();
  try {
    const result = await api(`/api/sealed-sales/${encodeURIComponent(orderId)}/undo`, { method: "POST", body: "{}" });
    closeModal();
    toast(`Sealed sale undone. ${result.restored_unit_ids.length} exact unit(s) restored.`);
    await loadDashboard();
    await renderSales(viewport);
  } catch (error) { toast(error.message, "error"); }
}

async function renderSales(viewport = null) {
  loading();
  try {
    const data = await api("/api/sales");
    if (!data.sales.length) {
      app.innerHTML = emptyState("receipt-text", "No outbound orders yet", "Scan sold sleeves to create your first eBay or TCGplayer order.", `<button class="button primary" data-action="go-outbound">${icon("scan-qr-code")}Scan outbound</button>`);
    } else {
      app.innerHTML = `<div class="view-stack"><div class="section-header"><div><h2>Completed Orders</h2><p>Original sales remain visible. Refunds, returns, chargebacks, and corrections are append-only events.</p></div><button class="button secondary" data-action="export-sales">${icon("download")}Sales CSV</button></div><div class="table-wrap"><table><thead><tr><th>Date</th><th>Type</th><th>Platform</th><th>Order</th><th>Items</th><th>Effective merchandise</th><th>Effective shipping</th><th>Effective fees + postage</th><th>Net proceeds</th><th>Sold basis</th><th>Realized P/L</th><th>Actions</th></tr></thead><tbody>${data.sales.map((sale) => `<tr class="${sale.canceled_at ? "muted-row" : ""}" data-viewport-key="sale-order-${sale.id}"><td>${formatDate(sale.sold_at)}${sale.canceled_at ? `<small>Canceled / undone</small>` : sale.post_sale_event_count ? `<small>${sale.post_sale_event_count} post-sale event(s)</small>` : ""}</td><td><span class="badge ${sale.order_type === "SEALED" ? "blue" : "green"}">${escapeHtml(titleCase(sale.order_type))}</span></td><td><span class="badge ${sale.platform === "eBay" ? "blue" : "green"}">${escapeHtml(sale.platform)}</span></td><td>${sale.order_number ? (sale.order_type === "CARD" ? `<button class="link-button" data-action="search-sale-order" data-order="${escapeHtml(sale.order_number)}">${escapeHtml(sale.order_number)}</button>` : escapeHtml(sale.order_number)) : "—"}</td><td>${sale.item_count}</td><td>${formatCents(sale.merchandise_effective_cents)}</td><td>${formatCents(sale.shipping_effective_cents)}</td><td>${formatCents(sale.effective_fees_plus_postage_cents)}</td><td><strong>${formatCents(sale.net_proceeds_cents)}</strong></td><td>${formatCents(sale.sold_basis_cents)}</td><td>${formatCents(sale.realized_profit_loss_cents)}</td><td><button class="button secondary" data-action="${sale.order_type === "SEALED" ? "open-sealed-order" : "open-sale-order"}" data-id="${sale.id}">${icon("eye")}Details</button></td></tr>`).join("")}</tbody></table></div></div>`;
    }
    refreshIcons();
    restoreLogicalViewport(viewport);
  } catch (error) { showError(error); }
}

async function renderOperationalEconomics(viewport = null) {
  loading();
  try {
    const report = await api("/api/portfolio/economics");
    const summary = report.summary;
    const realized = report.realized;
    const remaining = report.remaining;
    const counts = report.inventory_counts;
    const warnings = (report.warnings || []).map((warning) => `<li class="portfolio-warning ${warning.severity}"><strong>${escapeHtml(titleCase(warning.code))}</strong><span>${escapeHtml(warning.message)}</span></li>`).join("");
    const batchRows = (report.batches || []).map((batch) => `<tr data-viewport-key="portfolio-batch-${batch.id}"><td><button class="link-button" data-action="open-batch" data-id="${batch.id}">${escapeHtml(batch.batch_code)}</button><small>${escapeHtml(batch.product_name || "Unnamed product")}</small></td><td>${escapeHtml(batch.receipt_group_reference || "—")}</td><td>${formatCents(batch.authoritative_cost_cents)}</td><td>${formatCents(batch.effective_realized_net_proceeds_cents)}</td><td>${formatCents(batch.known_remaining_market_value_cents)}<small>${batch.market_complete ? "Complete" : "Incomplete"}</small></td><td>${formatCents(batch.operational_loss_cents, "$0.00")}</td></tr>`).join("");
    const groupRows = (report.receipt_groups.groups || []).map((group) => `<li><strong>${escapeHtml(group.reference)}</strong><span>${group.batch_count} finalized batch(es): ${group.batch_codes.map(escapeHtml).join(", ")}</span></li>`).join("");
    const currentState = summary.current_position_complete ? "Complete" : "Incomplete — known values only";
    const listedState = summary.projected_listed_position_complete ? "Complete" : "Incomplete — known values only";
    app.innerHTML = `<div class="view-stack operational-economics" data-viewport-key="operational-economics">
      <section class="operational-hero"><div><span>Phase 7C &bull; Backend-calculated</span><h2>Operational Economics</h2><p>${escapeHtml(report.scope_notice)}</p></div><div><span class="badge ${report.reconciliation.materially_incomplete ? "amber" : "green"}">${report.reconciliation.materially_incomplete ? "Incomplete" : "Reconciled"}</span><button class="button secondary" data-action="export-portfolio-economics">${icon("download")}Portfolio CSV</button></div></section>
      ${report.reconciliation.materially_incomplete ? `<div class="economics-material-warning">${icon("triangle-alert")}<div><strong>Some portfolio figures are incomplete</strong><span>Unknown valuation, missing basis, or reconciliation warnings are shown below. Known dollar amounts are never presented as complete totals.</span></div></div>` : ""}
      <section class="portfolio-first-look" aria-label="Operational Economics summary">
        <article><span>What did this cost?</span><strong>${formatCents(summary.authoritative_acquisition_cost_cents, "$0.00")}</strong><small>Authoritative finalized acquisition cost</small></article>
        <article><span>How much have I recovered?</span><strong>${formatCents(summary.effective_realized_net_proceeds_cents, "$0.00")}</strong><small>Effective realized net proceeds · ${formatPercent(summary.cost_recovery_percent)}</small></article>
        <article><span>What remains?</span><strong>${formatCents(summary.known_remaining_market_value_cents, "$0.00")}</strong><small>${escapeHtml(remaining.market.coverage_label)} · ${escapeHtml(remaining.market.freshness_label)}</small></article>
        <article><span>Am I ahead or behind?</span><strong>${formatCents(summary.current_economic_position_cents, "$0.00")}</strong><small>${escapeHtml(currentState)}</small></article>
      </section>
      <div class="portfolio-authority-note"><strong>Authoritative facts</strong><span>Acquisition cost, effective proceeds, basis, realized P/L, and operational loss come from finalized source facts and immutable event ledgers.</span></div>
      <section class="portfolio-columns">
        <article class="portfolio-panel realized-panel"><div class="section-header"><div><span>Realized Economics</span><h3>Recovered proceeds and realized P/L</h3><p>Market and listed values are not realized profit.</p></div></div><div class="portfolio-metrics"><div><span>Effective merchandise</span><strong>${formatCents(realized.gross_merchandise_cents, "$0.00")}</strong></div><div><span>Shipping collected</span><strong>${formatCents(realized.shipping_collected_cents, "$0.00")}</strong></div><div><span>Marketplace fees</span><strong>${formatCents(realized.marketplace_fees_cents, "$0.00")}</strong></div><div><span>Actual postage</span><strong>${formatCents(realized.actual_postage_cents, "$0.00")}</strong></div><div><span>Chargebacks / other net</span><strong>${formatCents(realized.other_net_cents, "$0.00")}</strong></div><div class="total"><span>Effective net proceeds</span><strong>${formatCents(realized.net_proceeds_cents, "$0.00")}</strong></div><div><span>Active sold basis</span><strong>${formatCents(realized.sold_basis_cents)}</strong><small>${realized.sold_basis_known_count}/${realized.sold_basis_total_count} active sold items with basis</small></div><div class="total"><span>Realized P/L</span><strong>${formatCents(realized.realized_profit_loss_cents)}</strong><small>${escapeHtml(realized.realized_profit_loss_definition)}</small></div><div><span>Cost Recovery</span><strong>${formatPercent(realized.cost_recovery_percent)}</strong><small>${escapeHtml(realized.cost_recovery_definition)} · uncapped</small></div></div><p class="help-text">${escapeHtml(realized.marketplace_tax_treatment)}</p></article>
        <article class="portfolio-panel remaining-panel"><div class="section-header"><div><span>Unrealized / Remaining Value</span><h3>Known value with explicit coverage</h3><p>Missing market and listed values are never substituted for one another.</p></div></div><div class="portfolio-metrics"><div><span>Known market value</span><strong>${formatCents(remaining.market.known_value_cents, "$0.00")}</strong><small>${escapeHtml(remaining.market.coverage_label)} · ${escapeHtml(remaining.market.freshness_label)}</small></div><div><span>Known listed value</span><strong>${formatCents(remaining.listed.known_value_cents, "$0.00")}</strong><small>${escapeHtml(remaining.listed.coverage_label)} · ${escapeHtml(remaining.listed.freshness_label)}</small></div><div><span>Current Economic Position</span><strong>${formatCents(remaining.current_economic_position_cents, "$0.00")}</strong><small>${escapeHtml(currentState)} · ${escapeHtml(remaining.current_position_definition)}</small></div><div><span>Projected Listed Position</span><strong>${formatCents(remaining.projected_listed_position_cents, "$0.00")}</strong><small>${escapeHtml(listedState)} · ${escapeHtml(remaining.projected_listed_position_definition)}</small></div><div><span>Known remaining basis</span><strong>${formatCents(remaining.known_basis_cents, "$0.00")}</strong></div><div><span>Operational loss / disposition</span><strong>${formatCents(report.excluded.operational_loss_cents, "$0.00")}</strong><small>Separate from active value · operational reporting only</small></div></div></article>
      </section>
      <details class="portfolio-detail" open><summary>Inventory and valuation coverage</summary><div class="portfolio-counts"><div><span>Remaining cards</span><strong>${counts.remaining_cards}</strong><small>Market ${remaining.market.cards.valued_count}/${remaining.market.cards.total_count} · Listed ${remaining.listed.cards.valued_count}/${remaining.listed.cards.total_count}</small></div><div><span>Remaining sealed</span><strong>${counts.sealed_remaining}</strong><small>${escapeHtml(remaining.market.sealed.state)} · no authoritative sealed valuation fact</small></div><div><span>Active sold</span><strong>${counts.active_sold_cards} cards · ${counts.active_sold_sealed_units} sealed</strong></div><div><span>Confirmed active returns</span><strong>${counts.active_returned_cards} cards · ${counts.active_returned_sealed_units} sealed</strong></div><div><span>Sealed reconciliation</span><strong>${counts.sealed_acquired} acquired</strong><small>${counts.sealed_opened} opened · ${counts.sealed_sold} sold · ${counts.sealed_remaining} remaining · ${counts.sealed_corrected_adjusted} adjusted</small></div><div><span>Known bulk</span><strong>${counts.known_bulk_quantity}</strong><small>${counts.bulk_quantity_unknown ? "Additional quantity Unknown" : "Quantity known"}</small></div></div></details>
      <details class="portfolio-detail"><summary>Scope and Receipt/Acquisition Groups</summary><div class="portfolio-scope"><div class="portfolio-counts"><div><span>Finalized Economics</span><strong>${report.scope.finalized_batch_count}</strong></div><div><span>Authoritative, unfinished</span><strong>${report.scope.authoritative_unfinalized_batch_count}</strong><small>Excluded</small></div><div><span>Legacy estimates</span><strong>${report.scope.legacy_estimate_batch_count}</strong><small>Separate</small></div><div><span>Unique contributing orders</span><strong>${realized.unique_order_count}</strong></div></div><p class="acquisition-notice">${escapeHtml(report.receipt_groups.notice)}</p>${groupRows ? `<ul class="portfolio-groups">${groupRows}</ul>` : `<p class="economics-empty">No finalized batch has a Receipt/Acquisition Group reference.</p>`}</div></details>
      <details class="portfolio-detail"><summary>Batch contributions</summary>${batchRows ? `<div class="table-wrap"><table><thead><tr><th>Batch</th><th>Receipt group</th><th>Cost</th><th>Recovered</th><th>Known market value</th><th>Operational loss</th></tr></thead><tbody>${batchRows}</tbody></table></div>` : `<p class="economics-empty">No Finalized Economics batches are included.</p>`}</details>
      <details class="portfolio-detail" ${warnings ? "open" : ""}><summary>Reconciliation / Warnings</summary><div class="portfolio-reconciliation"><div><span>Cost reconciliation</span><strong>${formatCents(report.reconciliation.authoritative_cost.difference_cents, "$0.00")} difference</strong></div><div><span>Realized reconciliation</span><strong>${formatCents(report.reconciliation.realized_net.difference_cents, "$0.00")} difference</strong></div><div><span>Stable order attribution</span><strong>${report.reconciliation.stable_order_attribution.reconciled ? "Reconciled" : "Difference detected"}</strong><small>${report.reconciliation.stable_order_attribution.unique_order_count} unique orders · ${report.reconciliation.stable_order_attribution.attributed_item_count} exact items · ${report.reconciliation.stable_order_attribution.duplicate_attribution_count} duplicate attributions</small></div></div>${warnings ? `<ul class="portfolio-warnings">${warnings}</ul>` : `<p class="economics-empty">No portfolio warnings.</p>`}<p class="help-text">Calculation ${escapeHtml(report.calculation_version)} · generated ${escapeHtml(report.generated_at)}. ${escapeHtml(report.tax_notice)}</p></details>
    </div>`;
    refreshIcons();
    restoreLogicalViewport(viewport);
  } catch (error) { showError(error); }
}

function recycleRows(cards) {
  if (!cards.length) return `<p class="economics-empty">No recycled cards.</p>`;
  return `<div class="recycle-list">${cards.map((card) => { const protectedRecord = card.protected_sale || card.protected_economics; const restoreAction = card.active_return_order_id ? `<button class="button secondary" data-action="open-sale-order" data-id="${card.active_return_order_id}">${icon("receipt-text")}Open return event</button>` : card.active_disposition_event_id ? `<button class="button secondary" data-action="reverse-economic-event" data-id="${escapeHtml(card.active_disposition_event_id)}">${icon("rotate-ccw")}Reverse disposition</button>` : `<button class="button secondary" data-action="restore-card" data-sku="${escapeHtml(card.sku)}">${icon("rotate-ccw")}Restore</button>`; return `<article class="recycle-row">${card.front_image ? `<img class="card-thumb" src="/media/${encodeURI(card.front_image)}" alt="">` : `<span class="card-thumb placeholder">${icon("image")}</span>`}<div><strong>${escapeHtml(card.name)}</strong><small>${escapeHtml(card.sku)} · ${escapeHtml(card.game)} · ${escapeHtml(card.set_code)}</small></div><div><strong>${formatDate(card.recycled_at)}</strong><small>${escapeHtml(card.recycle_reason || "No reason provided")}</small></div><div><strong>${protectedRecord ? "Protected Record" : `${card.days_remaining ?? 0} Days`}</strong><small>${card.protected_sale ? "Sale history retained" : card.protected_economics ? "Economic/tombstone history retained" : "Until purge eligible"}</small></div><div class="batch-actions">${restoreAction}<button class="icon-button danger-icon" title="Permanently Delete" data-action="purge-card" data-sku="${escapeHtml(card.sku)}" ${protectedRecord ? "disabled" : ""}>${icon("trash-2")}</button></div></article>`; }).join("")}</div>`;
}

function recycledAcquisitionRows(acquisitions) {
  if (!acquisitions.length) return `<p class="economics-empty">No recycled acquisitions.</p>`;
  return `<div class="recycle-list">${acquisitions.map((acquisition) => `<article class="recycle-row acquisition-recycle-row"><span class="card-thumb placeholder">${icon("clipboard-x")}</span><div><strong>${escapeHtml(acquisition.acquisition_code)}</strong><small>${escapeHtml(acquisition.merchant_name || "Merchant not entered")} · ${acquisition.line_count || 0} product line(s)</small></div><div><strong>${formatDate(acquisition.recycled_at)}</strong><small>${escapeHtml(titleCase(acquisition.recycle_reason_code || "Removed"))}${acquisition.recycle_notes ? ` · ${escapeHtml(acquisition.recycle_notes)}` : ""}</small></div><div><strong>Durable tombstone</strong><small>${acquisition.document_count || 0} document record(s) retained · permanent purge unavailable</small></div><div class="batch-actions"><button class="button secondary" data-action="restore-acquisition" data-id="${acquisition.id}" data-revision="${acquisition.revision}" ${acquisition.removal?.can_restore ? "" : "disabled"}>${icon("rotate-ccw")}Restore acquisition</button></div></article>`).join("")}</div>`;
}

async function renderRecycle() {
  loading();
  try {
    await loadDashboard();
    app.innerHTML = `<div class="view-stack"><div class="section-header"><div><h2>Recycle Bin</h2><p>Restore eligible records. Acquisition tombstones are retained and cannot be permanently purged here.</p></div></div><div class="toolbar"><div class="search-box">${icon("search")}<input id="recycle-search" type="search" placeholder="Search acquisition, SKU, card, or batch"></div><span class="filter-count">${state.dashboard.recycle_total_count ?? state.dashboard.recycled_count ?? 0} item(s)</span></div><div id="recycle-results"><div class="skeleton"></div></div></div>`;
    refreshIcons();
    const load = async () => {
      const q = document.querySelector("#recycle-search")?.value || "";
      const data = await api(`/api/recycle?q=${encodeURIComponent(q)}`);
      const acquisitions = data.acquisitions || [];
      const cards = data.cards || [];
      document.querySelector("#recycle-results").innerHTML = !acquisitions.length && !cards.length
        ? emptyState("trash-2", "Recycle Bin Is Empty", "Removed acquisitions and cards remain recoverable here when eligible.")
        : `<section class="recycle-section"><h3>Acquisitions</h3>${recycledAcquisitionRows(acquisitions)}</section><section class="recycle-section"><h3>Cards</h3>${recycleRows(cards)}</section>`;
      refreshIcons();
    };
    document.querySelector("#recycle-search").addEventListener("input", debounce(load, 220));
    await load();
  } catch (error) { showError(error); }
}

async function restoreCard(sku) {
  try {
    await api(`/api/cards/${encodeURIComponent(sku)}/restore`, { method: "POST", body: "{}" });
    toast(`${sku} restored with its original identity.`); await renderRecycle();
  } catch (error) { toast(error.message, "error"); }
}

async function openRemoveAcquisition(acquisitionId, mode) {
  try {
    const data = state.activeAcquisition?.acquisition?.id === Number(acquisitionId)
      ? state.activeAcquisition
      : await api(`/api/acquisitions/${acquisitionId}`);
    const acquisition = data.acquisition;
    const recycle = mode === "recycle";
    const heading = recycle ? "Move acquisition to Recycle Bin" : "Cancel acquisition";
    const detail = recycle
      ? "This draft remains recoverable. Product lines, source documents, receipt intelligence, catalog provenance, and audit history are retained."
      : "This confirmed acquisition becomes read-only and canceled. Authoritative facts and audit history remain visible.";
    openModal(heading, acquisition.acquisition_code, `<form id="remove-acquisition-form" data-id="${acquisition.id}" data-mode="${escapeHtml(mode)}" data-revision="${acquisition.revision}"><p>${detail}</p><label>Reason<select name="reason_code" required><option value="">Choose reason</option><option value="DUPLICATE_ENTRY">Duplicate / entry error</option><option value="ORDER_CANCELED">Order canceled</option><option value="RETURNED_TO_VENDOR">Returned to vendor</option><option value="ACQUISITION_NOT_COMPLETED">Acquisition not completed</option><option value="TEST_OR_TRAINING_ENTRY">Test / training entry</option><option value="OTHER">Other</option></select></label><label>Operator note${recycle ? " (required for Other)" : " (required)"}<textarea name="notes" ${recycle ? "" : "required"} placeholder="Record why this action is appropriate"></textarea></label><p class="help-text">If downstream inventory or economic history exists, DEX will block this action and direct you to correction or reversal.</p><div class="form-actions"><button type="button" class="button secondary" data-action="close-modal">Keep acquisition</button><button class="button danger">${icon(recycle ? "trash-2" : "ban")}${heading}</button></div></form>`);
    document.querySelector("#remove-acquisition-form")?.addEventListener("submit", removeAcquisition);
  } catch (error) { toast(error.message, "error"); }
}

async function removeAcquisition(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const fields = Object.fromEntries(new FormData(form).entries());
  const endpoint = form.dataset.mode === "recycle" ? "recycle" : "cancel";
  try {
    await api(`/api/acquisitions/${form.dataset.id}/${endpoint}`, { method: "POST", body: JSON.stringify({ request_id: requestId(`ACQUISITION-${endpoint.toUpperCase()}`), expected_revision: Number(form.dataset.revision), reason_code: fields.reason_code, notes: fields.notes || "" }) });
    closeModal();
    state.activeAcquisition = null;
    toast(endpoint === "recycle" ? "Acquisition moved to Recycle Bin; history retained." : "Acquisition canceled; authoritative history retained.");
    await renderInbound();
  } catch (error) { toast(error.message, "error"); }
}

async function restoreAcquisition(acquisitionId, revision) {
  if (!confirm("Restore this acquisition as an incomplete resumable draft? Its recycle and restore events remain in history.")) return;
  try {
    await api(`/api/acquisitions/${acquisitionId}/restore`, { method: "POST", body: JSON.stringify({ request_id: requestId("ACQUISITION-RESTORE"), expected_revision: Number(revision) }) });
    toast("Acquisition restored as a resumable draft.");
    await renderRecycle();
  } catch (error) { toast(error.message, "error"); }
}

async function purgeCard(sku) {
  if (!confirm(`Permanently delete ${sku} and its scan images? This cannot be undone.`)) return;
  try {
    await api(`/api/cards/${encodeURIComponent(sku)}/purge`, { method: "POST", body: "{}" });
    toast(`${sku} permanently deleted.`); await renderRecycle();
  } catch (error) { toast(error.message, "error"); }
}

function showError(error) {
  app.innerHTML = emptyState("triangle-alert", "Dex hit a snag", error.message || "Something went wrong.", `<button class="button secondary" onclick="location.reload()">Try again</button>`);
  refreshIcons();
}

function debounce(fn, wait) {
  let timer;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), wait); };
}

document.querySelector("#primary-nav").addEventListener("click", (event) => {
  const button = event.target.closest("[data-view]");
  if (button) setView(button.dataset.view);
});
document.querySelector("#mobile-menu").addEventListener("click", () => document.body.classList.add("nav-open"));
document.querySelector("#scrim").addEventListener("click", () => document.body.classList.remove("nav-open"));
document.querySelector("#modal-close").addEventListener("click", closeModal);
document.querySelector("#quick-batch").addEventListener("click", () => setView("inbound", { newAcquisition: true }));
document.querySelector("#quick-outbound").addEventListener("click", () => setView("outbound"));

document.addEventListener("click", async (event) => {
  const actionEl = event.target.closest("[data-action]");
  if (actionEl) {
    event.stopPropagation();
    const action = actionEl.dataset.action;
    if (action === "new-acquisition") setView("inbound", { newAcquisition: true });
    if (action === "open-acquisition") setView("inbound", { acquisitionId: actionEl.dataset.id });
    if (action === "open-projected-batch") setView("inbound", { batchId: actionEl.dataset.id });
    if (action === "open-remove-acquisition") await openRemoveAcquisition(actionEl.dataset.id, actionEl.dataset.mode);
    if (action === "restore-acquisition") await restoreAcquisition(actionEl.dataset.id, actionEl.dataset.revision);
    if (action === "back-acquisitions") { state.activeAcquisition = null; state.upcScanStatus = null; state.pendingUnknownProduct = null; state.catalogSearchResults = []; renderInbound(); }
    if (action === "choose-acquisition-type" || action === "add-acquisition-line") {
      try {
        await enqueueAcquisitionMutation((current) => api(`/api/acquisitions/${current.acquisition.id}/lines`, { method: "POST", body: JSON.stringify({ request_id: requestId("LINE-ADD"), expected_revision: current.acquisition.revision, product_class: actionEl.dataset.productClass }) }));
        await moveWizardTo("PRODUCTS");
      } catch (error) { toast(error.message, "error"); }
    }
    if (action === "remove-acquisition-line") {
      if (confirm("Remove this draft product line? Its draft history will be retained.")) {
        try {
          const viewport = captureLogicalViewport();
          await enqueueAcquisitionMutation((current) => api(`/api/acquisition-lines/${actionEl.dataset.id}/cancel`, { method: "POST", body: JSON.stringify({ request_id: requestId("LINE-REMOVE"), expected_revision: current.acquisition.revision }) }));
          await renderAcquisitionWizard(state.activeAcquisition.acquisition.id, { data: state.activeAcquisition, viewport });
        } catch (error) { toast(error.message, "error"); }
      }
    }
    if (action === "unknown-search" && state.pendingUnknownProduct) {
      state.pendingUnknownProduct.mode = "search";
      state.catalogSearchResults = [];
      await renderAcquisitionWizard(state.activeAcquisition.acquisition.id, { data: state.activeAcquisition, viewport: captureLogicalViewport() });
    }
    if (action === "unknown-identify" && state.pendingUnknownProduct) {
      state.pendingUnknownProduct.mode = "identify";
      state.catalogSearchResults = [];
      await renderAcquisitionWizard(state.activeAcquisition.acquisition.id, { data: state.activeAcquisition, viewport: captureLogicalViewport() });
    }
    if (action === "cancel-unknown-scan") {
      state.pendingUnknownProduct = null;
      state.catalogSearchResults = [];
      await renderAcquisitionWizard(state.activeAcquisition.acquisition.id, { data: state.activeAcquisition, viewport: captureLogicalViewport() });
    }
    if (action === "select-unknown-catalog-product") {
      const remember = document.querySelector('.catalog-search-form[data-catalog-search-mode="unknown"] input[name="remember_mapping"]')?.checked ?? true;
      await identifyUnknownWithCatalog(actionEl.dataset.productId, remember);
    }
    if (action === "apply-catalog-product") await applyCatalogProduct(actionEl.dataset.lineId, actionEl.dataset.productId);
    if (action === "open-identifier-history") await openIdentifierHistory(actionEl.dataset.id);
    if (action === "take-source-photo") openSourceDocumentPicker("#source-document-camera");
    if (action === "upload-source-document") openSourceDocumentPicker("#source-document-files");
    if (action === "view-source-document") window.open(`/api/acquisition-documents/${encodeURIComponent(actionEl.dataset.id)}/content`, "_blank", "noopener,noreferrer");
    if (action === "extract-source-document") await extractSourceDocument(actionEl.dataset.id);
    if (action === "retry-receipt-extraction") await retryReceiptExtraction(actionEl.dataset.jobUuid);
    if (action === "select-receipt-manual-fallback") await selectReceiptManualFallback();
    if (action === "use-receipt-candidate") await useReceiptCandidate(actionEl.dataset.id);
    if (action === "reject-receipt-candidate") await rejectReceiptCandidate(actionEl.dataset.id);
    if (action === "accept-receipt-match") await acceptReceiptMatch(actionEl.dataset.id);
    if (action === "receipt-classify-choice") await chooseReceiptClassification(actionEl.dataset.id, actionEl.dataset.classification);
    if (action === "mark-semantic-unresolved") await markReceiptSemanticUnresolved(actionEl.dataset.semanticUuid);
    if (action === "generate-receipt-allocation") await generateReceiptAllocation();
    if (action === "retry-source-document") {
      openSourceDocumentPicker("#source-document-retry", actionEl.dataset.id);
    }
    if (action === "remove-source-document") await removeSourceDocument(actionEl.dataset.id);
    if (action === "wizard-step") await moveWizardTo(actionEl.dataset.step, { saveCurrent: true });
    if (action === "wizard-next") await moveWizardTo(actionEl.dataset.step, { saveCurrent: true });
    if (action === "new-batch") openNewBatch();
    if (action === "close-modal") closeModal();
    if (action === "open-batch") setView("inbound", { batchId: actionEl.dataset.id });
    if (action === "back-batches") { state.activeBatch = null; renderInbound(); }
    if (action === "complete-batch") completeBatch(actionEl.dataset.id);
    if (action === "reopen-batch") reopenBatch(actionEl.dataset.id);
    if (action === "change-group") openChangeGroup();
    if (action === "edit-acquisition") openAcquisitionEdit();
    if (action === "create-rip") openCreateRip();
    if (action === "activate-rip") activateRip(actionEl.dataset.id);
    if (action === "deactivate-rip") deactivateRipSession(actionEl.dataset.id);
    if (action === "finalize-rip") openFinalizeRip(actionEl.dataset.id);
    if (action === "correct-rip") openRipCorrection(actionEl.dataset.id);
    if (action === "correct-acquisition-cost") openAcquisitionCorrection();
    if (action === "transfer-basis") openBasisTransfer();
    if (action === "dispose-card") openCardDisposition(actionEl.dataset.sku);
    if (action === "reverse-economic-event") openEconomicEventReversal(actionEl.dataset.id);
    if (action === "edit-card") openEditCard(actionEl.dataset.sku);
    if (action === "reprint-label") reprintLabel(actionEl.dataset.sku);
    if (action === "copy-sku") copySku(actionEl.dataset.sku);
    if (action === "swap-images") swapCardImages(actionEl.dataset.sku);
    if (action === "open-recycle-card") openRecycleCard(actionEl.dataset.sku);
    if (action === "open-recycle-batch") openRecycleBatch(actionEl.dataset.id, actionEl.dataset.code, actionEl.dataset.count);
    if (action === "restore-card") restoreCard(actionEl.dataset.sku);
    if (action === "purge-card") purgeCard(actionEl.dataset.sku);
    if (action === "print-labels") printLabels();
    if (action === "go-outbound") setView("outbound");
    if (action === "outbound-mode") { state.outboundMode = actionEl.dataset.mode; state.sealedSalePreview = null; renderOutbound(); }
    if (action === "sell-sealed") { state.outboundMode = "SEALED"; setView("outbound"); }
    if (action === "adjust-sealed") openSealedAdjustment(actionEl.dataset.id, actionEl.dataset.code);
    if (action === "start-camera") startCamera();
    if (action === "export-csv") window.location.href = "/api/export/inventory.csv";
    if (action === "export-sales") window.location.href = "/api/export/sales.csv";
    if (action === "export-batch-economics") window.location.href = `/api/export/batch-economics.csv?batch_id=${encodeURIComponent(actionEl.dataset.id)}`;
    if (action === "export-portfolio-economics") window.location.href = "/api/export/portfolio-economics.csv";
    if (action === "open-sealed-order") openSealedOrderDetails(actionEl.dataset.id);
    if (action === "open-sale-order") openSaleOrderDetails(actionEl.dataset.id);
    if (action === "post-sale-form") openPostSaleForm(actionEl.dataset.id, actionEl.dataset.kind);
    if (action === "reverse-post-sale-event") openPostSaleReversal(actionEl.dataset.id, actionEl.dataset.orderId);
    if (action === "undo-sealed-order") undoSealedOrder(actionEl.dataset.id);
    if (action === "open-settings") openSettings();
    if (action === "undo-last") undoLast();
    if (action === "select-visible-batch") selectVisibleBatchCards();
    if (action === "clear-batch-selection") clearBatchSelection();
    if (action === "bulk-recycle") bulkRecycleCards();
    if (action === "bulk-reprint-labels") bulkReprintLabels();
    if (action === "bulk-edit") openBulkEdit();
    if (action === "rescan-source") rescanSource();
    if (action === "probe-sam-provider") probeSamProvider();
    if (action === "open-sam-review") openSamReview(actionEl.dataset.id);
    if (action === "run-sam-audited") runSamAudited(actionEl.dataset.sku);
    if (action === "open-sam-audited-result") openSamAuditedResult(actionEl.dataset.id);
    if (action === "select-sam-audited-family") selectSamAuditedFamily(actionEl.dataset.family, actionEl.dataset.name);
    if (action === "decide-sam-audited") decideSamAudited(actionEl.dataset.id, actionEl.dataset.decision);
    if (action === "select-sam-reference") selectSamReference(actionEl.dataset.id);
    if (action === "confirm-sam-match") decideSam(actionEl.dataset.id, "CONFIRM", actionEl.dataset.revision, actionEl.dataset.referenceId);
    if (action === "correct-sam-match") decideSam(actionEl.dataset.id, "CORRECT", actionEl.dataset.revision, actionEl.dataset.referenceId);
    if (action === "confirm-sam-family") decideSam(actionEl.dataset.id, "CONFIRM_FAMILY", actionEl.dataset.revision, actionEl.dataset.referenceId);
    if (action === "correct-sam-family") decideSam(actionEl.dataset.id, "CORRECT_FAMILY", actionEl.dataset.revision, actionEl.dataset.referenceId);
    if (action === "confirm-sam-printing") decideSam(actionEl.dataset.id, "CONFIRM_PRINTING", actionEl.dataset.revision, actionEl.dataset.referenceId, actionEl.dataset.printingId);
    if (action === "correct-sam-printing") decideSam(actionEl.dataset.id, "CORRECT_PRINTING", actionEl.dataset.revision, actionEl.dataset.referenceId, actionEl.dataset.printingId);
    if (action === "leave-sam-printing-unresolved") decideSam(actionEl.dataset.id, "LEAVE_PRINTING_UNRESOLVED", actionEl.dataset.revision);
    if (action === "mark-sam-printing-conflict") decideSam(actionEl.dataset.id, "MARK_PRINTING_CONFLICT", actionEl.dataset.revision);
    if (action === "leave-sam-unidentified") decideSam(actionEl.dataset.id, "LEAVE_UNIDENTIFIED", actionEl.dataset.revision);
    if (action === "sam-match-card") samMatchCard(actionEl.dataset.sku);
    if (action === "sam-match-batch") samMatchBatch(false);
    if (action === "sam-match-selected") samMatchBatch(true);
    if (action === "search-sale-order") {
      state.inventoryPreset = { q: actionEl.dataset.order || "", status: "SOLD", sort: "average_desc" };
      setView("inventory");
    }
    if (action === "remove-outbound") { state.outboundCards = state.outboundCards.filter((card) => card.sku !== actionEl.dataset.sku); renderOutbound(); }
  }
  const expandable = event.target.closest("tr[data-expand]");
  if (expandable && !event.target.closest("button")) {
    const detail = document.querySelector(`[data-expanded-row="${expandable.dataset.expand}"]`);
    detail.hidden = !detail.hidden;
    expandable.classList.toggle("open", !detail.hidden);
  }
  const batchCard = event.target.closest(".batch-card");
  if (batchCard && !event.target.closest("button, a, input, label")) {
    const selector = batchCard.querySelector("[data-batch-select]");
    if (selector) {
      selector.checked = !selector.checked;
      selector.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }
});

document.addEventListener("change", (event) => {
  if (event.target.matches("[data-batch-select]")) {
    const sku = event.target.dataset.batchSelect;
    event.target.checked ? state.selectedBatchCards.add(sku) : state.selectedBatchCards.delete(sku);
    renderBatch(state.activeBatch.batch.id);
    return;
  }
  if (event.target.matches("[data-label] input")) {
    const holder = event.target.closest("[data-label]");
    holder.classList.toggle("selected", event.target.checked);
    event.target.checked ? state.selectedLabels.add(holder.dataset.label) : state.selectedLabels.delete(holder.dataset.label);
  }
  if (event.target.id === "select-all-labels") {
    document.querySelectorAll("[data-label]").forEach((holder) => {
      holder.querySelector("input").checked = event.target.checked;
      holder.classList.toggle("selected", event.target.checked);
      event.target.checked ? state.selectedLabels.add(holder.dataset.label) : state.selectedLabels.delete(holder.dataset.label);
    });
  }
});

window.addEventListener("beforeunload", stopCamera);

async function boot() {
  refreshIcons();
  try {
    const health = await api("/api/health");
    const runtimeVersion = document.querySelector("[data-runtime-version]");
    if (runtimeVersion) runtimeVersion.textContent = health.version || "Version unavailable";
  } catch (error) {
    const runtimeVersion = document.querySelector("[data-runtime-version]");
    if (runtimeVersion) runtimeVersion.textContent = "Version unavailable";
  }
  try { await loadDashboard(); } catch (error) { /* Main view reports connection failures. */ }
  const requested = location.hash.slice(1);
  setView(titles[requested] ? requested : "inventory");
}

boot();
