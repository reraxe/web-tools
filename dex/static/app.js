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
  cameraStream: null,
  intakeDefaults: { rarity: "", variant: "Standard" },
  pendingBulkFiles: [],
  selectedBatchCards: new Set(),
  inventoryPreset: null,
};

const BULK_IMPORT_CHUNK_SIZE = 8;

const app = document.querySelector("#app");
const modal = document.querySelector("#modal");
const moneyFormat = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const dateFormat = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" });

const titles = {
  inventory: ["Inventory", "Every physical card, accounted for."],
  inbound: ["Inbound", "From scanner to labeled inventory."],
  labels: ["Labels", "Print queued 2 × 1 sleeve labels."],
  outbound: ["Outbound", "Scan sold cards into an order."],
  sales: ["Sales", "Order history and net proceeds."],
  recycle: ["Recycle Bin", "Restore removed cards or manage eligible permanent deletion."],
};

function icon(name, className = "") {
  return `<i data-lucide="${name}" class="${className}"></i>`;
}

function refreshIcons() {
  if (window.lucide) window.lucide.createIcons({ attrs: { "stroke-width": 1.8 } });
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
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
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
  if (view === "inbound") renderInbound(options.batchId);
  if (view === "labels") renderLabels();
  if (view === "outbound") renderOutbound();
  if (view === "sales") renderSales();
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
  document.querySelector("#nav-recycle-count").textContent = state.dashboard.recycled_count || 0;
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
    await loadDashboard();
    app.innerHTML = `<div class="view-stack">${summaryStrip()}${inventoryToolbar()}<div id="inventory-results"><div class="skeleton"></div></div></div>`;
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
      <label>Total cost<div class="money-input"><span>$</span><input name="total_cost" inputmode="decimal" type="number" min="0" step=".01" value="0"></div></label>
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

async function renderInbound(batchId) {
  loading();
  try {
    if (batchId) return renderBatch(Number(batchId));
    const data = await api("/api/batches");
    state.batches = data.batches;
    app.innerHTML = `<div class="view-stack"><div class="section-header"><div><h2>Inbound Batches</h2><p>Booster boxes, packs, trades, and existing stock.</p></div><button class="button primary" data-action="new-batch">${icon("plus")}New Batch</button></div>${batchRows(data.batches)}</div>`;
    refreshIcons();
  } catch (error) { showError(error); }
}

function imageDrop(side) {
  return `<label class="image-drop" id="${side}-drop">
    <input type="file" name="${side}" accept="image/jpeg,image/png,image/webp" required>
    <span>${icon(side === "front" ? "scan" : "image")}<b>${titleCase(side)}</b><br>Choose scanned image</span>
  </label>`;
}

function cardIngestForm(batch) {
  return `<div class="scan-form">
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
  return `<section class="batch-cards"><div class="batch-grid-head"><div><h3>Batch Cards</h3><p>${cards.length} Scanned - ${cards.length - review} Ready - ${review} Need Review</p></div><div class="batch-select-actions"><button class="button secondary" data-action="select-visible-batch">${icon("check-square")}Select All</button><button class="button secondary" data-action="clear-batch-selection" ${selected ? "" : "disabled"}>${icon("x")}Clear</button></div></div>
  <div class="bulk-action-bar ${selected ? "show" : ""}"><strong>${selected} Selected</strong><button class="button secondary" data-action="bulk-edit">${icon("square-pen")}Bulk Edit</button><button class="button secondary" data-action="bulk-reprint-labels">${icon("printer")}Print/Reprint Labels</button><button class="button danger" data-action="bulk-recycle">${icon("trash-2")}Move to Recycle Bin</button></div>
  <div class="batch-card-grid">${cards.slice().reverse().map((card) => `<article class="batch-card ${state.selectedBatchCards.has(card.sku) ? "selected" : ""}">
    <label class="batch-card-check" title="Select ${escapeHtml(card.sku)}"><input type="checkbox" data-batch-select="${escapeHtml(card.sku)}" ${state.selectedBatchCards.has(card.sku) ? "checked" : ""}></label>
    ${card.front_image ? `<img src="/media/${encodeURI(card.front_image)}" alt="">` : `<div class="batch-card-placeholder">${icon("image")}</div>`}
    <div class="batch-card-body"><strong>${escapeHtml(card.name)}</strong><small>${escapeHtml(card.card_number || "Identification pending")}</small><code>${escapeHtml(card.sku)}</code><div>${statusBadge(card.status)}</div></div>
    <div class="batch-card-actions"><button class="icon-button" title="Reprint label" data-action="reprint-label" data-sku="${escapeHtml(card.sku)}">${icon("printer")}</button><button class="icon-button" title="Edit card" data-action="edit-card" data-sku="${escapeHtml(card.sku)}">${icon("square-pen")}</button></div>
  </article>`).join("")}</div>${batch.status === "OPEN" ? `<div class="bottom-finish-bar"><div><strong>${cards.length} Cards In Batch</strong><small>${review} Need Review - ${cards.length} Labels Will Queue</small></div><button class="button primary" data-action="complete-batch" data-id="${batch.id}">${icon("printer")}Finish & Print Labels</button></div>` : ""}</section>`;
}

async function renderBatch(id) {
  loading();
  try {
    const data = await api(`/api/batches/${id}`);
    state.activeBatch = data;
    const b = data.batch;
    const validSkus = new Set(data.cards.map((card) => card.sku));
    state.selectedBatchCards = new Set([...state.selectedBatchCards].filter((sku) => validSkus.has(sku)));
    app.innerHTML = `<div class="view-stack">
      <div class="section-header"><div><button class="button secondary" data-action="back-batches">${icon("arrow-left")}All Batches</button></div>${b.status === "OPEN" ? `<button class="button primary" data-action="complete-batch" data-id="${b.id}">${icon("printer")}Finish & Print Labels</button>` : `<div class="batch-actions"><span class="badge green">Complete</span><button class="button primary" data-action="reopen-batch" data-id="${b.id}">${icon("plus")}Add More Cards</button></div>`}</div>
      <div class="batch-workspace">
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
  } catch (error) { showError(error); }
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

function editCardForm(card) {
  const evidence = (side) => card[`${side}_image`] ? `<a href="/media/${encodeURI(card[`${side}_image`])}" target="_blank" rel="noopener"><img src="/media/${encodeURI(card[`${side}_image`])}" alt="${titleCase(side)} scan for ${escapeHtml(card.sku)}"><span>${titleCase(side)} · Open Full Resolution</span></a>` : `<div class="missing-evidence">${icon("image-off")}<span>No ${titleCase(side)} Image</span></div>`;
  return `<form id="edit-card-form" data-sku="${escapeHtml(card.sku)}"><div class="card-evidence">${evidence("front")}${evidence("back")}</div><div class="evidence-actions"><button type="button" class="button secondary" data-action="swap-images" data-sku="${escapeHtml(card.sku)}">${icon("arrow-left-right")}Swap Front/Back</button></div><div class="form-grid">
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
  </div><div class="form-actions card-form-actions"><div><button type="button" class="button danger" data-action="open-recycle-card" data-sku="${escapeHtml(card.sku)}">${icon("trash-2")}Move to Recycle Bin</button><button type="button" class="button secondary" data-action="reprint-label" data-sku="${escapeHtml(card.sku)}">${icon("printer")}Reprint Label</button></div><div><button type="button" class="button secondary" data-action="close-modal">Cancel</button><button class="button primary">${icon("save")}Save Card</button></div></div></form>`;
}

async function openEditCard(sku) {
  try {
    const card = await api(`/api/cards/${encodeURIComponent(sku)}`);
    openModal(card.name, `${card.sku} · ${card.game} · ${card.set_code}`, editCardForm(card));
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
  return `<div class="outbound-layout">
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
  </div>`;
}

function outboundItems() {
  if (!state.outboundCards.length) return emptyState("scan-qr-code", "Ready to scan", "Each scanned sleeve is added to this outbound order.");
  return state.outboundCards.map((card) => `<div class="scanned-item"><div><strong>${escapeHtml(card.name)}</strong><small>${escapeHtml(card.sku)} · ${escapeHtml(card.card_number)}</small></div><button class="icon-button" title="Remove" data-action="remove-outbound" data-sku="${escapeHtml(card.sku)}">${icon("x")}</button></div>`).join("");
}

function renderOutbound() {
  app.innerHTML = outboundPage(); refreshIcons();
  document.querySelector("#sku-entry").addEventListener("submit", addOutboundSku);
  document.querySelector("#outbound-form").addEventListener("submit", completeSale);
  document.querySelectorAll("#outbound-form input[type=number]").forEach((input) => input.addEventListener("input", updateNet));
  setTimeout(() => document.querySelector('#sku-entry input')?.focus(), 80);
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

async function renderSales() {
  loading();
  try {
    const data = await api("/api/sales");
    if (!data.sales.length) {
      app.innerHTML = emptyState("receipt-text", "No outbound orders yet", "Scan sold sleeves to create your first eBay or TCGplayer order.", `<button class="button primary" data-action="go-outbound">${icon("scan-qr-code")}Scan outbound</button>`);
    } else {
      app.innerHTML = `<div class="view-stack"><div class="section-header"><div><h2>Completed Orders</h2><p>Sale amounts, shipping, fees, and postage.</p></div><button class="button secondary" data-action="export-sales">${icon("download")}Sales CSV</button></div><div class="table-wrap"><table><thead><tr><th>Date</th><th>Platform</th><th>Order</th><th>Cards</th><th>Subtotal</th><th>Shipping</th><th>Fees + postage</th><th>Net proceeds</th></tr></thead><tbody>${data.sales.map((sale) => `<tr><td>${formatDate(sale.sold_at)}</td><td><span class="badge ${sale.platform === "eBay" ? "blue" : "green"}">${escapeHtml(sale.platform)}</span></td><td>${sale.order_number ? `<button class="link-button" data-action="search-sale-order" data-order="${escapeHtml(sale.order_number)}">${escapeHtml(sale.order_number)}</button>` : "?"}</td><td>${sale.item_count}</td><td>${formatMoney(sale.subtotal)}</td><td>${formatMoney(sale.shipping_collected)}</td><td>${formatMoney(Number(sale.platform_fees) + Number(sale.postage_cost))}</td><td><strong>${formatMoney(sale.net_proceeds)}</strong></td></tr>`).join("")}</tbody></table></div></div>`;
    }
    refreshIcons();
  } catch (error) { showError(error); }
}

function recycleRows(cards) {
  if (!cards.length) return emptyState("trash-2", "Recycle Bin Is Empty", "Removed cards remain recoverable here during the retention period.");
  return `<div class="recycle-list">${cards.map((card) => `<article class="recycle-row">${card.front_image ? `<img class="card-thumb" src="/media/${encodeURI(card.front_image)}" alt="">` : `<span class="card-thumb placeholder">${icon("image")}</span>`}<div><strong>${escapeHtml(card.name)}</strong><small>${escapeHtml(card.sku)} · ${escapeHtml(card.game)} · ${escapeHtml(card.set_code)}</small></div><div><strong>${formatDate(card.recycled_at)}</strong><small>${escapeHtml(card.recycle_reason || "No reason provided")}</small></div><div><strong>${card.protected_sale ? "Protected Record" : `${card.days_remaining ?? 0} Days`}</strong><small>${card.protected_sale ? "Sale history retained" : "Until purge eligible"}</small></div><div class="batch-actions"><button class="button secondary" data-action="restore-card" data-sku="${escapeHtml(card.sku)}">${icon("rotate-ccw")}Restore</button><button class="icon-button danger-icon" title="Permanently Delete" data-action="purge-card" data-sku="${escapeHtml(card.sku)}" ${card.protected_sale ? "disabled" : ""}>${icon("trash-2")}</button></div></article>`).join("")}</div>`;
}

async function renderRecycle() {
  loading();
  try {
    await loadDashboard();
    app.innerHTML = `<div class="view-stack"><div class="section-header"><div><h2>Recycled Cards</h2><p>Restore entries or permanently delete eligible records.</p></div></div><div class="toolbar"><div class="search-box">${icon("search")}<input id="recycle-search" type="search" placeholder="Search SKU, card, number, or batch"></div><span class="filter-count">${state.dashboard.recycled_count || 0} Items</span></div><div id="recycle-results"><div class="skeleton"></div></div></div>`;
    refreshIcons();
    const load = async () => {
      const q = document.querySelector("#recycle-search")?.value || "";
      const data = await api(`/api/recycle?q=${encodeURIComponent(q)}`);
      document.querySelector("#recycle-results").innerHTML = recycleRows(data.cards); refreshIcons();
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
document.querySelector("#quick-batch").addEventListener("click", openNewBatch);
document.querySelector("#quick-outbound").addEventListener("click", () => setView("outbound"));

document.addEventListener("click", async (event) => {
  const actionEl = event.target.closest("[data-action]");
  if (actionEl) {
    event.stopPropagation();
    const action = actionEl.dataset.action;
    if (action === "new-batch") openNewBatch();
    if (action === "close-modal") closeModal();
    if (action === "open-batch") setView("inbound", { batchId: actionEl.dataset.id });
    if (action === "back-batches") { state.activeBatch = null; renderInbound(); }
    if (action === "complete-batch") completeBatch(actionEl.dataset.id);
    if (action === "reopen-batch") reopenBatch(actionEl.dataset.id);
    if (action === "change-group") openChangeGroup();
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
    if (action === "start-camera") startCamera();
    if (action === "export-csv") window.location.href = "/api/export/inventory.csv";
    if (action === "export-sales") window.location.href = "/api/export/sales.csv";
    if (action === "open-settings") openSettings();
    if (action === "undo-last") undoLast();
    if (action === "select-visible-batch") selectVisibleBatchCards();
    if (action === "clear-batch-selection") clearBatchSelection();
    if (action === "bulk-recycle") bulkRecycleCards();
    if (action === "bulk-reprint-labels") bulkReprintLabels();
    if (action === "bulk-edit") openBulkEdit();
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
  try { await loadDashboard(); } catch (error) { /* Main view reports connection failures. */ }
  const requested = location.hash.slice(1);
  setView(titles[requested] ? requested : "inventory");
}

boot();
