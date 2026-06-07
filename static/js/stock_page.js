/**
 * 棚補充・使用（/stock/replenish | /stock/consume）
 */
function toJST(dateStr) {
  if (!dateStr) return "";
  if (typeof dateStr === "string" && /^\d{4}\/\d{2}\/\d{2}/.test(dateStr)) {
    return dateStr;
  }
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return String(dateStr);
  return date.toLocaleString("ja-JP", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** 本日一覧・編集モーダル用（API の recorded_at 優先） */
function formatLogRecordedAt(log) {
  if (log?.recorded_at) return toJST(log.recorded_at);
  if (log?.created_at) return toJST(log.created_at);
  return "—";
}

(function () {
  const boot = window.STOCK_PAGE || {};
  const PAGE = boot.page || "replenish";
  const IS_REPLENISH = PAGE === "replenish";
  const SUBMIT_URL = IS_REPLENISH ? "/api/stock/replenish" : "/api/stock/consume";
  const BULK_ACTION = IS_REPLENISH ? "restock" : "use";
  const LOG_TYPE = IS_REPLENISH ? "replenish" : "consume";
  const TODAY_LIST_LABEL = IS_REPLENISH ? "本日の補充一覧" : "本日の使用済み一覧";
  const DATETIME_LABEL = IS_REPLENISH ? "補充日時" : "使用日時";
  const REG_SETTING_IDS = {
    standardStock: "reg-standard-stock",
    warning: "reg-warning-threshold",
    critical: "reg-critical-threshold",
  };
  const BARCODE_MAX_LENGTH = 13;

  function applyBarcodeMaxLength(el) {
    if (el) el.maxLength = BARCODE_MAX_LENGTH;
  }

  let stores = [];
  let sections = [];
  let categories = [];
  let makers = [];
  let dealers = [];
  let brands = [];
  let products = [];
  let currentUser = null;
  let modalProductId = null;
  let modalUnit = "本";
  let modalCurrentQty = 0;
  let modalOnShelf = true;
  let pendingScanCode = null;
  let bulkPending = [];
  let html5QrBulk = null;
  let bulkCameraOn = false;
  let scanCooldown = false;
  let activeTab = "search";
  let modalSettingsSnapshot = null;

  const storeSelect = document.getElementById("store-select");
  const productGrid = document.getElementById("product-grid");

  document.addEventListener("DOMContentLoaded", init);

  function init() {
    loadBootstrap();
    bindTabs();
    bindFilters();
    bindStoreChange();
    bindModal();
    bindScanTab();
    bindLogHistory();
    bindBulkTab();
    if (IS_REPLENISH) {
      bindNewProductModal();
      bindDeliveryTab();
    } else bindNotOnShelfModal();

    setupStoreSelect();
    renderProducts();
    refreshTodayLogs();
    switchTab("search");
    applyBarcodeMaxLength(document.getElementById("scanner-input"));
    applyBarcodeMaxLength(document.getElementById("new-barcode"));
    if (typeof applyIosFormInputs === "function") applyIosFormInputs();

    Api.get("/api/auth/me")
      .then((user) => {
        currentUser = user;
        filterStoresForUser();
        setupStoreSelect();
        if (isTodayLogsModalOpen()) renderTodayLogs();
      })
      .catch(() => {});
  }

  /* ---------- タブ ---------- */
  function bindTabs() {
    document.querySelectorAll("#stock-tabs [data-tab]").forEach((btn) => {
      btn.addEventListener("click", () => switchTab(btn.dataset.tab));
    });
    if (IS_REPLENISH) {
      document
        .querySelector('#stock-tabs [data-tab="delivery"]')
        ?.addEventListener("click", () => {
          loadDeliveryList();
        });
    }
  }

  function getTabPanel(tab) {
    if (tab === "delivery") {
      return document.getElementById("delivery-tab-content");
    }
    return document.getElementById(`tab-${tab}`);
  }

  function switchTab(tab) {
    activeTab = tab;
    document.querySelectorAll(".stock-tab-content").forEach((el) => {
      el.style.display = "none";
    });
    const panel = getTabPanel(tab);
    if (panel) panel.style.display = "block";

    document.querySelectorAll("#stock-tabs [data-tab]").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.tab === tab);
    });

    if (tab !== "bulk" && bulkCameraOn) stopBulkCamera();
    if (tab === "scan") {
      document.getElementById("scanner-input")?.focus();
    }
    if (tab === "delivery" && IS_REPLENISH) {
      loadDeliveryList();
    }
  }

  /* ---------- 共通 ---------- */
  function loadBootstrap() {
    if (!boot || typeof boot !== "object") return;
    stores = boot.stores || [];
    sections = boot.sections || [];
    categories = boot.categories || [];
    makers = boot.makers || [];
    dealers = boot.dealers || [];
    brands = boot.brands || [];
    products = boot.products || [];
    initSearchFilters();
    if (boot.default_store_id && storeSelect) {
      storeSelect.value = String(boot.default_store_id);
    }
  }

  function getUserRole() {
    if (typeof USER_ROLE !== "undefined" && USER_ROLE) return USER_ROLE;
    return currentUser?.role || "";
  }

  function isSettingsAdmin() {
    return getUserRole() === "admin";
  }

  function filterStoresForUser() {
    if (currentUser?.role === "staff" && currentUser.store_id) {
      stores = stores.filter((s) => s.id === currentUser.store_id);
    }
  }

  function resetRegisterModalSettingsAccess() {
    ["reg-standard-stock", "reg-warning-threshold", "reg-critical-threshold"].forEach(
      (id) => {
        const el = document.getElementById(id);
        if (el) el.disabled = false;
      }
    );
    document.querySelectorAll(".settings-admin-lock-note").forEach((n) => n.remove());
  }

  function applyRegisterModalSettingsAccess() {
    if (isSettingsAdmin()) return;

    const std = document.getElementById("reg-standard-stock");
    const warn = document.getElementById("reg-warning-threshold");
    const crit = document.getElementById("reg-critical-threshold");
    [std, warn, crit].forEach((el) => {
      if (el) el.disabled = true;
    });

    const stdGroup = std?.closest(".form-group");
    if (stdGroup && !stdGroup.querySelector(".settings-admin-lock-note")) {
      const note = document.createElement("p");
      note.className = "help-text settings-admin-lock-note";
      note.style.color = "#c0392b";
      note.textContent = "🔒 発注目安の編集は管理者権限が必要です";
      stdGroup.appendChild(note);
    }
  }

  function setupStoreSelect() {
    if (!storeSelect) return;
    if (!stores.length) {
      storeSelect.innerHTML = '<option value="">店舗がありません</option>';
      return;
    }
    storeSelect.innerHTML = stores
      .map((s) => `<option value="${s.id}">${escapeHtml(s.name)}</option>`)
      .join("");
    if (currentUser?.store_id) {
      storeSelect.value = String(currentUser.store_id);
      if (currentUser.role === "staff") storeSelect.disabled = true;
    }
    updateStoreHint();
    updateBulkSubmitState();
    refreshTodayLogs();
  }

  function getStoreId() {
    return parseInt(storeSelect?.value, 10) || null;
  }

  function updateStoreHint() {
    const hint = document.getElementById("store-hint");
    if (hint) hint.style.display = getStoreId() ? "none" : "block";
  }

  function bindStoreChange() {
    storeSelect?.addEventListener("change", async () => {
      updateStoreHint();
      bulkPending = [];
      renderBulkLines();
      await reloadProducts();
      if (IS_REPLENISH && activeTab === "delivery") {
        loadDeliveryList();
      }
    });
  }

  function initSearchFilters() {
    const FH = window.FilterHelpers;
    if (!FH) return;
    const sectionEl = document.getElementById("filter-section");
    const categoryEl = document.getElementById("filter-category");
    if (sections.length && sectionEl) {
      FH.fillSectionSelect(sectionEl, sections);
    }
    FH.fillCategorySelect(categoryEl, categories, sectionEl?.value || "");
    const makerEl = document.getElementById("filter-maker");
    const brandEl = document.getElementById("filter-brand");
    FH.fillBrandSelect(brandEl, brands, makerEl?.value || "");
    if (sectionEl && !sectionEl.dataset.bound) {
      sectionEl.dataset.bound = "1";
      FH.bindShelfCategory(sectionEl, categoryEl, categories, renderProducts);
    }
    if (makerEl && !makerEl.dataset.brandBound) {
      makerEl.dataset.brandBound = "1";
      FH.bindMakerBrand(makerEl, brandEl, brands, renderProducts);
    }
  }

  function bindFilters() {
    ["filter-section", "filter-category", "filter-maker", "filter-brand", "filter-dealer", "filter-name"].forEach((id) => {
      const el = document.getElementById(id);
      el?.addEventListener("input", renderProducts);
      el?.addEventListener("change", renderProducts);
    });
    document.getElementById("btn-filter-reset")?.addEventListener("click", resetSearchFilters);
  }

  function resetSearchFilters() {
    const ids = ["filter-section", "filter-category", "filter-maker", "filter-brand", "filter-dealer"];
    ids.forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.value = "";
    });
    const nameEl = document.getElementById("filter-name");
    if (nameEl) nameEl.value = "";
    const FH = window.FilterHelpers;
    if (FH) {
      FH.fillCategorySelect(document.getElementById("filter-category"), categories, "", false);
    }
    renderProducts();
  }

  async function reloadProducts() {
    const storeId = getStoreId();
    if (!storeId) {
      products = [];
      renderProducts();
      return;
    }
    hideError();
    try {
      products = await Api.get(`/api/stock/products?store_id=${storeId}&page=${PAGE}`);
      renderProducts();
      await refreshTodayLogs();
    } catch (err) {
      showError(err.message);
    }
  }

  /* ---------- 本日の登録履歴（モーダル） ---------- */
  let todayLogsCache = [];
  let todayStoreName = "";

  function bindLogHistory() {
    document.getElementById("btn-today-logs")?.addEventListener("click", openTodayLogsModal);
    document.getElementById("today-logs-close")?.addEventListener("click", closeTodayLogsModal);
    document.getElementById("today-logs-modal")?.addEventListener("click", (e) => {
      if (e.target.id === "today-logs-modal") closeTodayLogsModal();
    });
    document.getElementById("today-logs-tbody")?.addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-edit-log]");
      if (!btn) return;
      if (currentUser?.role !== "admin") return;
      const id = parseInt(btn.dataset.editLog, 10);
      const log = todayLogsCache.find((x) => x.id === id);
      if (log) openLogEditModal(log);
    });
    document.getElementById("btn-today-logs-csv")?.addEventListener("click", downloadTodayLogsCsv);

    document.getElementById("log-edit-close")?.addEventListener("click", closeLogEditModal);
    document.getElementById("log-edit-cancel")?.addEventListener("click", closeLogEditModal);
    document.getElementById("log-edit-modal")?.addEventListener("click", (e) => {
      if (e.target.id === "log-edit-modal") closeLogEditModal();
    });
    document.getElementById("log-edit-form")?.addEventListener("submit", onSaveLogEdit);
  }

  function isTodayLogsModalOpen() {
    const el = document.getElementById("today-logs-modal");
    return el && el.style.display !== "none";
  }

  async function refreshTodayLogs() {
    const countEl = document.getElementById("today-logs-count");
    const storeId = getStoreId();
    if (!storeId) {
      todayLogsCache = [];
      todayStoreName = "";
      if (countEl) countEl.textContent = "0";
      return;
    }
    try {
      const data = await Api.get(
        `/api/stock/logs/today?store_id=${encodeURIComponent(storeId)}&type=${encodeURIComponent(LOG_TYPE)}`
      );
      todayLogsCache = Array.isArray(data.items) ? data.items : [];
      todayStoreName = data.store_name || "";
      const n = typeof data.count === "number" ? data.count : todayLogsCache.length;
      if (countEl) countEl.textContent = String(n);
      if (isTodayLogsModalOpen()) renderTodayLogs();
    } catch (err) {
      todayLogsCache = [];
      todayStoreName = "";
      if (countEl) countEl.textContent = "0";
      if (isTodayLogsModalOpen()) renderTodayLogs();
      console.error("本日の登録履歴の取得に失敗:", err);
    }
  }

  function logActionKind(log) {
    const a = String(log?.action ?? "").toLowerCase();
    return a === "use" ? "use" : "restock";
  }

  function signedQuantityText(log) {
    const sign = logActionKind(log) === "use" ? "-" : "+";
    const qty = log.quantity_change ?? log.quantity ?? 0;
    return `${sign}${qty}${escapeHtml(log.unit || "本")}`;
  }

  function signedQuantityPlain(log) {
    const sign = logActionKind(log) === "use" ? "-" : "+";
    const qty = log.quantity_change ?? log.quantity ?? 0;
    return `${sign}${qty}${log.unit || "本"}`;
  }

  function renderTodayLogs() {
    const tbody = document.getElementById("today-logs-tbody");
    if (!tbody) return;
    const title = document.getElementById("today-logs-title");
    if (title) {
      title.textContent = todayStoreName
        ? `${TODAY_LIST_LABEL}（${todayStoreName}）`
        : TODAY_LIST_LABEL;
    }
    if (!todayLogsCache.length) {
      tbody.innerHTML =
        '<tr><td colspan="4" class="empty-msg">本日の記録はありません</td></tr>';
      return;
    }
    const canEdit = currentUser?.role === "admin";
    tbody.innerHTML = todayLogsCache
      .map((log) => {
        const edited = !!log.is_edited;
        const editBadge = edited ? '<span class="log-edited-badge">✏️修正済</span>' : "";
        const rowClass = edited ? " stock-log-row-edited" : "";
        const isUse = logActionKind(log) === "use";
        const qtyClass = isUse
          ? "stock-log-qty stock-log-qty-minus"
          : "stock-log-qty stock-log-qty-plus";
        const timeStr = formatLogRecordedAt(log);
        const actionCell = canEdit
          ? `<button type="button" class="btn btn-ghost btn-sm" data-edit-log="${log.id}">編集</button>`
          : "";
        return `<tr class="stock-log-row${rowClass}" data-log-id="${log.id}">
          <td data-label="時刻">${timeStr}${editBadge}</td>
          <td data-label="商品名">${escapeHtml(log.product_name || "")}</td>
          <td data-label="数量"><span class="${qtyClass}">${signedQuantityText(log)}</span></td>
          <td data-label="操作">${actionCell}</td>
        </tr>`;
      })
      .join("");
  }

  async function openTodayLogsModal() {
    const storeId = getStoreId();
    if (!storeId) {
      showError("店舗を選択してください。");
      return;
    }
    await refreshTodayLogs();
    renderTodayLogs();
    showOverlay("today-logs-modal");
  }

  function closeTodayLogsModal() {
    hideOverlay("today-logs-modal");
  }

  function downloadTodayLogsCsv() {
    if (!todayLogsCache.length) {
      showToast("ダウンロードするデータがありません", 2000);
      return;
    }
    const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const header = ["時刻", "商品名", "数量", "修正済み"];
    const rows = todayLogsCache.map((log) => [
      formatLogRecordedAt(log),
      log.product_name || "",
      signedQuantityPlain(log),
      log.is_edited ? "はい" : "",
    ]);
    const bom = "\uFEFF";
    const csv =
      bom +
      [header, ...rows].map((row) => row.map(esc).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const date = new Date().toISOString().slice(0, 10);
    const suffix = IS_REPLENISH ? "replenish" : "consume";
    a.href = url;
    a.download = `${suffix}_${date}_store${getStoreId()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function openLogEditModal(log) {
    document.getElementById("log-edit-id").value = String(log.id);
    document.getElementById("log-edit-product").textContent = log.product_name || "";
    document.getElementById("log-edit-datetime").textContent = `登録日時：${formatLogRecordedAt(log)}`;
    document.getElementById("log-edit-current").textContent = String(log.quantity_change);
    document.getElementById("log-edit-quantity").value = String(log.quantity_change);
    document.getElementById("log-edit-reason").value = "";
    const err = document.getElementById("log-edit-error");
    if (err) err.style.display = "none";
    showOverlay("log-edit-modal");
  }

  function closeLogEditModal() {
    hideOverlay("log-edit-modal");
  }

  async function onSaveLogEdit(e) {
    e.preventDefault();
    const err = document.getElementById("log-edit-error");
    if (err) err.style.display = "none";
    const id = parseInt(document.getElementById("log-edit-id").value, 10);
    const quantity = parseInt(document.getElementById("log-edit-quantity").value, 10);
    const reason = (document.getElementById("log-edit-reason").value || "").trim();
    try {
      await Api.put(`/api/stock/logs/${id}`, { quantity, reason });
      closeLogEditModal();
      showToast("✓ 登録内容を修正しました", 2000);
      await reloadProducts();
      await refreshTodayLogs();
      resetScanInput();
    } catch (ex) {
      if (err) {
        err.textContent = ex.message || "修正できませんでした";
        err.style.display = "block";
      }
    }
  }

  function filteredProducts() {
    const section = document.getElementById("filter-section")?.value || "";
    const cat = document.getElementById("filter-category")?.value || "";
    const maker = document.getElementById("filter-maker")?.value || "";
    const brand = document.getElementById("filter-brand")?.value || "";
    const dealer = document.getElementById("filter-dealer")?.value || "";
    const nameQ = (document.getElementById("filter-name")?.value || "").trim().toLowerCase();
    const FH = window.FilterHelpers;

    return products.filter((p) => {
      if (section && FH && !FH.matchesSection(p.category_id, section, categories)) {
        return false;
      }
      if (cat && String(p.category_id) !== cat) return false;
      if (maker && String(p.maker_id || "") !== maker) return false;
      if (brand && FH && !FH.matchesBrand(p.brand_id, brand)) return false;
      if (brand && !FH && String(p.brand_id || "") !== brand) return false;
      if (dealer && String(p.dealer_id || "") !== dealer) return false;
      if (nameQ && !(p.product_name || "").toLowerCase().includes(nameQ)) return false;
      return true;
    });
  }

  function productBrandLabel(item) {
    const brand = (item.brand_name || "").trim();
    if (brand) return brand;
    return (item.maker_name || "").trim();
  }

  function standardStockQtyPart(item) {
    const std = item.standard_stock;
    const unit = item.unit || "本";
    if (std != null && std !== undefined && std !== 0) {
      return `<span class="qty-std">標準 ${std}${escapeHtml(unit)}</span>`;
    }
    return `<span class="qty-std qty-std-unset">未設定</span>`;
  }

  function renderProductCard(p) {
    const unit = p.unit || "本";
    const category = (p.category_name || "").trim();
    const brand = productBrandLabel(p);
    const badgeParts = [];
    if (category) {
      badgeParts.push(
        `<span class="stock-badge-category">${escapeHtml(category)}</span>`
      );
    }
    if (brand) {
      badgeParts.push(`<span class="stock-badge-brand">${escapeHtml(brand)}</span>`);
    }
    const badgesHtml = badgeParts.length
      ? `<div class="stock-card-badges">${badgeParts.join("")}</div>`
      : "";
    const shelfNote =
      IS_REPLENISH && !p.is_on_shelf
        ? '<span class="stock-card-shelf-note"> · 未配置</span>'
        : "";

    return `
      <button type="button" class="product-card stock-${p.stock_level}" data-product-id="${p.product_id}">
        <div class="stock-product-card">
          ${badgesHtml}
          <p class="stock-card-name">${escapeHtml(p.product_name)}</p>
          <p class="stock-card-qty">
            <span class="qty-num">${p.quantity}${escapeHtml(unit)}</span>
            <span class="qty-sep"> / </span>
            ${standardStockQtyPart(p)}
            ${shelfNote}
          </p>
        </div>
      </button>`;
  }

  function renderProducts() {
    const empty = document.getElementById("product-empty");
    if (!productGrid) return;
    const items = filteredProducts();
    if (!items.length) {
      productGrid.innerHTML = "";
      if (empty) empty.style.display = "block";
      return;
    }
    if (empty) empty.style.display = "none";
    productGrid.innerHTML = items.map((p) => renderProductCard(p)).join("");

    productGrid.querySelectorAll(".product-card").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = parseInt(btn.dataset.productId, 10);
        const item = products.find((x) => x.product_id === id);
        if (item) openRegisterModal(item);
      });
    });
  }

  /* ---------- 登録モーダル ---------- */
  function bindModal() {
    document.getElementById("reg-quantity")?.addEventListener("input", () => {
      if (!IS_REPLENISH) updateRegisterSubmitState();
    });
    document.getElementById("register-form")?.addEventListener("submit", onRegisterSubmit);
    document.getElementById("register-modal-close")?.addEventListener("click", closeRegisterModal);
    document.getElementById("register-modal-cancel")?.addEventListener("click", closeRegisterModal);
    document.getElementById("register-modal")?.addEventListener("click", (e) => {
      if (e.target.id === "register-modal") closeRegisterModal();
    });
  }

  async function openRegisterModal(item, scanCode) {
    if (!getStoreId()) {
      showError("店舗を選択してください。");
      return;
    }
    modalProductId = item.product_id;
    modalUnit = item.unit || "本";
    modalCurrentQty = item.quantity ?? 0;
    modalOnShelf = item.is_on_shelf !== false;

    document.getElementById("reg-product-id").value = item.product_id;
    document.getElementById("reg-product-name").textContent = item.product_name;
    document.getElementById("reg-barcode").textContent = item.barcode || scanCode || "—";
    document.getElementById("reg-quantity").value = "1";
    document.getElementById("reg-datetime").value = nowLocalDatetime();
    const errEl = document.getElementById("register-form-error");
    if (errEl) errEl.style.display = "none";
    resetRegisterModalSettingsAccess();
    showOverlay("register-modal");
    await refreshModalQty();
    applyRegisterModalSettingsAccess();
  }

  function closeRegisterModal() {
    hideOverlay("register-modal");
    resetRegisterModalSettingsAccess();
    modalProductId = null;
    modalCurrentQty = 0;
    modalSettingsSnapshot = null;
  }

  async function refreshModalQty() {
    const qtyEl = document.getElementById("reg-current-qty");
    const errEl = document.getElementById("register-form-error");
    if (!modalProductId || !getStoreId()) {
      if (qtyEl) qtyEl.textContent = "—";
      if (!IS_REPLENISH) updateRegisterSubmitState();
      return;
    }
    try {
      const storeId = getStoreId();
      const qtyData = await Api.get(
        `/api/stock/quantity?store_id=${storeId}&product_id=${modalProductId}`
      );
      const settingData = await StoreProductSettingsApi.fetchSetting(
        storeId,
        modalProductId
      );
      modalCurrentQty = qtyData.quantity;
      modalUnit = qtyData.unit || "本";
      modalOnShelf = qtyData.is_on_shelf !== false;
      const inv = products.find((x) => x.product_id === modalProductId);
      if (inv) inv.quantity = qtyData.quantity;

      if (!IS_REPLENISH && !modalOnShelf) {
        closeRegisterModal();
        openNotOnShelfModal();
        return;
      }

      if (qtyEl) qtyEl.textContent = `${qtyData.quantity}${modalUnit}`;
      modalSettingsSnapshot = StoreProductSettingsApi.applyToForm(
        settingData,
        REG_SETTING_IDS
      );
      applyRegisterModalSettingsAccess();
      if (!IS_REPLENISH) {
        applyConsumeQuantityLimits();
        if (errEl) errEl.style.display = "none";
        updateRegisterSubmitState();
      }
    } catch {
      if (qtyEl) qtyEl.textContent = "取得できませんでした";
      if (!IS_REPLENISH) updateRegisterSubmitState();
    }
  }

  function applyConsumeQuantityLimits() {
    const input = document.getElementById("reg-quantity");
    if (!input) return;
    const maxQ = Math.max(0, modalCurrentQty);
    input.max = maxQ;
    input.min = 0;
    if (maxQ < 1) {
      input.value = "0";
      input.disabled = true;
    } else {
      input.disabled = false;
      const v = parseInt(input.value, 10);
      if (!Number.isNaN(v) && v > maxQ) input.value = String(maxQ);
    }
  }

  function updateRegisterSubmitState() {
    const btn = document.getElementById("reg-submit-btn");
    if (!btn || IS_REPLENISH) return;
    const q = parseInt(document.getElementById("reg-quantity")?.value, 10) || 0;
    btn.disabled = !(
      getStoreId() &&
      modalOnShelf &&
      q >= 0 &&
      q <= modalCurrentQty
    );
  }

  async function onRegisterSubmit(e) {
    e.preventDefault();
    const errEl = document.getElementById("register-form-error");
    if (errEl) errEl.style.display = "none";

    const storeId = getStoreId();
    if (!storeId) {
      if (errEl) {
        errEl.textContent = "店舗を選択してください。";
        errEl.style.display = "block";
      }
      return;
    }

    const productId = parseInt(document.getElementById("reg-product-id").value, 10);
    const quantity = parseInt(document.getElementById("reg-quantity").value, 10) || 0;

    const currentSettings = isSettingsAdmin()
      ? StoreProductSettingsApi.readFromForm(REG_SETTING_IDS)
      : null;
    const settingsChanged =
      isSettingsAdmin() &&
      StoreProductSettingsApi.changed(modalSettingsSnapshot, currentSettings);

    if (quantity === 0 && !settingsChanged) {
      closeRegisterModal();
      return;
    }

    if (quantity < 0) {
      if (errEl) {
        errEl.textContent = "数量は0以上を指定してください。";
        errEl.style.display = "block";
      }
      return;
    }

    if (!IS_REPLENISH) {
      if (!modalOnShelf) {
        closeRegisterModal();
        openNotOnShelfModal();
        return;
      }
      if (quantity > modalCurrentQty) {
        if (errEl) {
          errEl.textContent = `在庫が不足しています。使用できる最大数：${modalCurrentQty}${modalUnit}。`;
          errEl.style.display = "block";
        }
        return;
      }
    }

    const recorded_at = datetimeToIso(document.getElementById("reg-datetime").value);

    const body = {
      store_id: storeId,
      product_id: productId,
      quantity,
      recorded_at,
    };

    if (isSettingsAdmin() && currentSettings && (settingsChanged || quantity === 0)) {
      const settingsError = StoreProductSettingsApi.validate(currentSettings);
      if (settingsError) {
        if (errEl) {
          errEl.textContent = settingsError;
          errEl.style.display = "block";
        }
        return;
      }
      body.standard_stock = currentSettings.standard_stock;
      body.warning_threshold = currentSettings.warning_threshold;
      body.critical_threshold = currentSettings.critical_threshold;
    }

    try {
      const res = await Api.post(SUBMIT_URL, body);
      closeRegisterModal();
      const toastMsg =
        quantity === 0
          ? res?.message || "発注目安を更新しました"
          : "✓ 登録しました";
      showToast(toastMsg, 2000);
      await reloadProducts();
      resetScanInput();
    } catch (err) {
      if (!IS_REPLENISH && errEl) {
        const msg = err.message || "";
        if (msg.includes("棚に") || msg.includes("不足")) {
          closeRegisterModal();
          openNotOnShelfModal();
          return;
        }
        errEl.textContent = msg;
        errEl.style.display = "block";
      } else if (errEl) {
        errEl.textContent = err.message;
        errEl.style.display = "block";
      }
    }
  }

  /* ---------- 発注中納品タブ（補充のみ） ---------- */
  function bindDeliveryTab() {
    document.addEventListener("click", async (e) => {
      if (!e.target.closest("#delivery-submit-btn")) return;
      await submitDelivery();
    });
  }

  async function loadDeliveryList() {
    const list = document.getElementById("delivery-list");
    if (!list) return;
    const storeId = getStoreId();
    if (!storeId) {
      list.innerHTML =
        '<p style="color:#aaa; text-align:center; padding:2rem;">店舗を選択してください</p>';
      return;
    }
    list.innerHTML =
      '<p style="color:#aaa; text-align:center; padding:2rem;">読み込み中...</p>';
    try {
      const items = await Api.get(
        `/api/ordering-items?store_id=${encodeURIComponent(storeId)}`
      );
      if (!items || !items.length) {
        list.innerHTML =
          '<p style="color:#aaa; text-align:center; padding:2rem;">発注中の商品はありません</p>';
        return;
      }
      list.innerHTML = items
        .map(
          (item) => `
        <div class="delivery-row">
          <input type="checkbox" class="delivery-check" value="${item.id}" checked>
          <span class="delivery-row-name">${escapeHtml(item.product_name)}${
            item.brand_name
              ? ` <span class="brand-pill delivery-brand-pill">${escapeHtml(item.brand_name)}</span>`
              : ""
          }</span>
          <span class="delivery-row-qty">発注中 ${item.ordered_quantity}本</span>
        </div>`
        )
        .join("");
    } catch (err) {
      list.innerHTML = `<p class="error-msg">${escapeHtml(err.message)}</p>`;
    }
  }

  async function submitDelivery() {
    const checked = [...document.querySelectorAll(".delivery-check:checked")].map((cb) =>
      parseInt(cb.value, 10)
    );
    if (!checked.length) {
      alert("納品登録する商品を選択してください");
      return;
    }
    if (
      !confirm(
        `${checked.length}件の商品を納品登録しますか？\n在庫数に発注中の本数が加算されます。`
      )
    ) {
      return;
    }
    const storeId = getStoreId();
    if (!storeId) {
      alert("店舗を選択してください。");
      return;
    }
    try {
      await Api.post("/api/ordering-items/deliver", {
        store_id: storeId,
        item_ids: checked,
      });
      alert("納品登録が完了しました！在庫数に反映されました。");
      await loadDeliveryList();
      localStorage.setItem("akemin:ordering-delivered", String(Date.now()));
      if (typeof loadInventory === "function") {
        await loadInventory();
      }
      await reloadProducts();
    } catch (err) {
      alert("エラーが発生しました: " + (err.message || "不明"));
    }
  }

  /* ---------- スキャンタブ ---------- */
  function bindScanTab() {
    const input = document.getElementById("scanner-input");
    const btn = document.getElementById("btn-scan-search");
    applyBarcodeMaxLength(input);

    const runSearch = async () => {
      if (!input) return;
      const code = input.value.trim();
      if (!code) return;
      if (code.length > BARCODE_MAX_LENGTH) {
        showError("バーコードは13文字以内で入力してください");
        return;
      }
      await handleScanCode(code);
    };

    btn?.addEventListener("click", runSearch);
    input?.addEventListener("keydown", async (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      await runSearch();
    });
  }

  function resetScanInput() {
    const input = document.getElementById("scanner-input");
    if (!input) return;
    input.value = "";
    if (activeTab === "scan") input.focus();
  }

  async function handleScanCode(code) {
    if (!getStoreId()) {
      showError("店舗を選択してください。");
      return;
    }
    hideError();
    try {
      const lookup = await Api.get(
        `/api/stock/lookup?store_id=${getStoreId()}&code=${encodeURIComponent(code)}`
      );
      if (lookup.found) {
        if (IS_REPLENISH) {
          const item = products.find((x) => x.product_id === lookup.product_id) || lookupToItem(lookup);
          await openRegisterModal(item, code);
        } else {
          if (!lookup.is_on_shelf) {
            openNotOnShelfModal();
            return;
          }
          const item = products.find((x) => x.product_id === lookup.product_id) || lookupToItem(lookup);
          await openRegisterModal(item, code);
        }
      } else if (IS_REPLENISH) {
        openNewProductModal(code);
      } else {
        openNotOnShelfModal();
      }
    } catch (err) {
      showError(err.message);
    }
  }

  function lookupToItem(lookup) {
    return {
      product_id: lookup.product_id,
      product_name: lookup.product_name,
      barcode: lookup.barcode,
      quantity: lookup.quantity,
      unit: lookup.unit || "本",
      is_on_shelf: lookup.is_on_shelf,
    };
  }

  /* ---------- 補充: 新規商品モーダル ---------- */
  function bindNewProductModal() {
    applyBarcodeMaxLength(document.getElementById("new-barcode"));
    document.getElementById("new-product-no")?.addEventListener("click", closeNewProductModal);
    document.getElementById("new-product-modal-close")?.addEventListener("click", closeNewProductModal);
    document.getElementById("new-product-modal")?.addEventListener("click", (e) => {
      if (e.target.id === "new-product-modal") closeNewProductModal();
    });
    document.getElementById("new-product-form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const errEl = document.getElementById("new-product-form-error");
      if (errEl) errEl.style.display = "none";

      const storeId = getStoreId();
      if (!storeId) {
        if (errEl) {
          errEl.textContent = "店舗を選択してください。";
          errEl.style.display = "block";
        }
        return;
      }

      const maker = document.getElementById("new-maker_id").value;
      const dealer = document.getElementById("new-dealer_id").value;
      const barcode = document.getElementById("new-barcode").value.trim();
      if (barcode.length > BARCODE_MAX_LENGTH) {
        if (errEl) {
          errEl.textContent = "バーコードは13文字以内で入力してください";
          errEl.style.display = "block";
        }
        return;
      }

      const product = {
        name: document.getElementById("new-name").value.trim(),
        barcode,
        jan_code: pendingScanCode || null,
        category_id: parseInt(document.getElementById("new-category_id").value, 10),
        unit: document.getElementById("new-unit").value.trim() || "本",
        warning_threshold: 4,
        critical_threshold: 2,
        maker_id: maker ? parseInt(maker, 10) : null,
        dealer_id: dealer ? parseInt(dealer, 10) : null,
      };
      const quantity = parseInt(document.getElementById("new-reg-quantity").value, 10) || 1;
      const recorded_at = datetimeToIso(document.getElementById("new-reg-datetime").value);

      try {
        const res = await Api.post("/api/stock/register-with-product", {
          store_id: storeId,
          action: "restock",
          quantity,
          recorded_at,
          product,
        });
        closeNewProductModal();
        showToast("✓ 登録しました", 2000);
        await reloadProducts();
        resetScanInput();
      } catch (err) {
        if (errEl) {
          errEl.textContent = err.message;
          errEl.style.display = "block";
        }
      }
    });
  }

  function openNewProductModal(code) {
    pendingScanCode = code;
    document.getElementById("new-scan-code").textContent = code;
    document.getElementById("new-barcode").value = code;
    document.getElementById("new-name").value = "";
    document.getElementById("new-reg-quantity").value = "1";
    document.getElementById("new-reg-datetime").value = nowLocalDatetime();
    const errEl = document.getElementById("new-product-form-error");
    if (errEl) errEl.style.display = "none";
    if (categories.length) {
      document.getElementById("new-category_id").value = String(categories[0].id);
    }
    showOverlay("new-product-modal");
  }

  function closeNewProductModal() {
    hideOverlay("new-product-modal");
    pendingScanCode = null;
  }

  /* ---------- 使用: 棚にないモーダル ---------- */
  function bindNotOnShelfModal() {
    document.getElementById("not-on-shelf-close")?.addEventListener("click", closeNotOnShelfModal);
    document.getElementById("not-on-shelf-modal-close")?.addEventListener("click", closeNotOnShelfModal);
    document.getElementById("not-on-shelf-modal")?.addEventListener("click", (e) => {
      if (e.target.id === "not-on-shelf-modal") closeNotOnShelfModal();
    });
  }

  function openNotOnShelfModal() {
    showOverlay("not-on-shelf-modal");
  }

  function closeNotOnShelfModal() {
    hideOverlay("not-on-shelf-modal");
  }

  /* ---------- 一括タブ ---------- */
  function bindBulkTab() {
    document.getElementById("btn-bulk-camera")?.addEventListener("click", toggleBulkCamera);
    document.getElementById("bulk-file")?.addEventListener("change", onBulkFile);
    document.getElementById("btn-bulk-submit")?.addEventListener("click", submitBulk);
  }

  function initBulkScanner() {
    if (typeof Html5Qrcode === "undefined") return null;
    const el = document.getElementById("reader-bulk");
    if (!el) return null;
    const formats = Html5QrcodeSupportedFormats
      ? [
          Html5QrcodeSupportedFormats.EAN_13,
          Html5QrcodeSupportedFormats.EAN_8,
          Html5QrcodeSupportedFormats.CODE_128,
          Html5QrcodeSupportedFormats.CODE_39,
          Html5QrcodeSupportedFormats.UPC_A,
        ]
      : undefined;
    return new Html5Qrcode("reader-bulk", { formatsToSupport: formats });
  }

  async function toggleBulkCamera() {
    if (!getStoreId()) {
      showError("店舗を選択してください。");
      return;
    }
    if (!html5QrBulk) html5QrBulk = initBulkScanner();
    if (!html5QrBulk) {
      showError("カメラライブラリが利用できません");
      return;
    }

    const reader = document.getElementById("reader-bulk");
    const btn = document.getElementById("btn-bulk-camera");

    if (bulkCameraOn) {
      await html5QrBulk.stop();
      bulkCameraOn = false;
      if (reader) reader.style.display = "none";
      if (btn) btn.textContent = "カメラ開始";
      return;
    }

    try {
      if (reader) reader.style.display = "block";
      await html5QrBulk.start(
        { facingMode: "environment" },
        { fps: 8, qrbox: { width: 250, height: 120 } },
        onBulkScan,
        () => {}
      );
      bulkCameraOn = true;
      if (btn) btn.textContent = "カメラ停止";
      hideError();
    } catch (err) {
      showError("カメラを起動できません: " + err.message);
    }
  }

  async function stopBulkCamera() {
    if (!html5QrBulk || !bulkCameraOn) return;
    try {
      await html5QrBulk.stop();
    } catch {
      /* ignore */
    }
    bulkCameraOn = false;
    const reader = document.getElementById("reader-bulk");
    if (reader) reader.style.display = "none";
    const btn = document.getElementById("btn-bulk-camera");
    if (btn) btn.textContent = "カメラ開始";
  }

  async function onBulkScan(code) {
    if (scanCooldown || !code) return;
    scanCooldown = true;
    setTimeout(() => {
      scanCooldown = false;
    }, 1500);

    if (!getStoreId()) return;
    try {
      const lookup = await Api.get(
        `/api/stock/lookup?store_id=${getStoreId()}&code=${encodeURIComponent(code.trim())}`
      );
      if (!lookup.found) return;
      if (!IS_REPLENISH && !lookup.is_on_shelf) return;
      mergeBulkLine({
        product_code: code.trim(),
        quantity: 1,
        matched: true,
        product_id: lookup.product_id,
        product_name: lookup.product_name,
        unit: lookup.unit || "本",
        current_quantity: lookup.quantity,
      });
    } catch {
      /* ignore single scan errors */
    }
  }

  async function onBulkFile(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !getStoreId()) {
      if (!getStoreId()) showError("店舗を選択してください。");
      return;
    }
    hideError();
    try {
      const res = await Api.upload(
        "/api/stock/bulk-parse",
        file,
        "file",
        `store_id=${getStoreId()}`
      );
      const noteEl = document.getElementById("bulk-parse-note");
      if (noteEl) {
        noteEl.textContent = res.note || "";
        noteEl.style.display = res.note ? "block" : "none";
      }
      bulkPending = (res.lines || []).filter((ln) => ln.matched);
      if (!IS_REPLENISH) {
        bulkPending = await filterBulkForConsume(bulkPending);
      }
      renderBulkLines();
    } catch (err) {
      showError(err.message);
    }
  }

  async function filterBulkForConsume(lines) {
    const out = [];
    for (const ln of lines) {
      if (!ln.product_id) continue;
      try {
        const q = await Api.get(
          `/api/stock/quantity?store_id=${getStoreId()}&product_id=${ln.product_id}`
        );
        if (q.is_on_shelf) out.push({ ...ln, current_quantity: q.quantity, unit: q.unit });
      } catch {
        /* skip */
      }
    }
    return out;
  }

  function mergeBulkLine(ln) {
    const existing = bulkPending.find((x) => x.product_id === ln.product_id);
    if (existing) {
      existing.quantity = (existing.quantity || 1) + (ln.quantity || 1);
    } else {
      bulkPending.push({
        ...ln,
        recorded_at: nowLocalDatetime(),
      });
    }
    renderBulkLines();
  }

  function renderBulkLines() {
    const wrap = document.getElementById("bulk-lines-wrap");
    const list = document.getElementById("bulk-lines");
    const empty = document.getElementById("bulk-empty");
    const dtLabel = DATETIME_LABEL;

    if (!bulkPending.length) {
      if (wrap) wrap.style.display = "none";
      if (empty) empty.style.display = "block";
      updateBulkSubmitState();
      return;
    }
    if (empty) empty.style.display = "none";
    if (wrap) wrap.style.display = "block";

    list.innerHTML = bulkPending
      .map((ln, idx) => {
        const maxAttr = !IS_REPLENISH ? ` max="${ln.current_quantity || 0}"` : ' max="999"';
        const disabled = !IS_REPLENISH && (ln.current_quantity || 0) < 1 ? " disabled" : "";
        return `
        <li class="bulk-line card" data-idx="${idx}">
          <div class="bulk-line-head">
            <strong>${escapeHtml(ln.product_name || ln.product_code)}</strong>
            <span class="bulk-line-meta">在庫 ${ln.current_quantity ?? 0}${escapeHtml(ln.unit || "本")}</span>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>数量</label>
              <input type="number" inputmode="numeric" pattern="[0-9]*" autocomplete="off" class="input-number bulk-qty" data-idx="${idx}" value="${ln.quantity || 1}" min="1"${maxAttr}${disabled}>
            </div>
            <div class="form-group">
              <label>${dtLabel}</label>
              <input type="datetime-local" class="input-text bulk-dt" data-idx="${idx}" value="${ln.recorded_at || nowLocalDatetime()}">
            </div>
          </div>
        </li>`;
      })
      .join("");

    if (typeof applyIosFormInputs === "function") applyIosFormInputs(list);

    list.querySelectorAll(".bulk-qty").forEach((inp) => {
      inp.addEventListener("input", (e) => {
        const i = parseInt(e.target.dataset.idx, 10);
        bulkPending[i].quantity = parseInt(e.target.value, 10) || 1;
        updateBulkSubmitState();
      });
    });
    list.querySelectorAll(".bulk-dt").forEach((inp) => {
      inp.addEventListener("change", (e) => {
        const i = parseInt(e.target.dataset.idx, 10);
        bulkPending[i].recorded_at = e.target.value;
      });
    });
    updateBulkSubmitState();
  }

  function updateBulkSubmitState() {
    const btn = document.getElementById("btn-bulk-submit");
    if (!btn) return;
    const ok =
      !!getStoreId() &&
      bulkPending.length > 0 &&
      bulkPending.every((ln) => {
        const q = ln.quantity || 1;
        if (IS_REPLENISH) return q >= 1;
        return q >= 1 && q <= (ln.current_quantity || 0);
      });
    btn.disabled = !ok;
  }

  async function submitBulk() {
    const storeId = getStoreId();
    if (!storeId || !bulkPending.length) return;

    const lines = bulkPending
      .filter((ln) => ln.product_id && ln.quantity >= 1)
      .map((ln) => ({
        product_id: ln.product_id,
        quantity: ln.quantity || 1,
        recorded_at: datetimeToIso(ln.recorded_at || nowLocalDatetime()),
      }));

    if (!lines.length) {
      showError("登録できる商品がありません。");
      return;
    }

    try {
      const res = await Api.post("/api/stock/bulk-register", {
        store_id: storeId,
        action: BULK_ACTION,
        lines,
      });
      showToast(`${res.count}件を登録しました`);
      bulkPending = [];
      renderBulkLines();
      await reloadProducts();
      if (activeTab === "bulk") await stopBulkCamera();
    } catch (err) {
      showError(err.message);
    }
  }

  /* ---------- UI ヘルパー ---------- */
  function showOverlay(id) {
    if (bulkCameraOn) {
      stopBulkCamera();
    }
    const el = document.getElementById(id);
    if (el) {
      el.style.display = "flex";
      document.body.style.overflow = "hidden";
    }
  }

  function hideOverlay(id) {
    const el = document.getElementById(id);
    if (el) {
      el.style.display = "none";
      document.body.style.overflow = "";
    }
  }

  function nowLocalDatetime() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  function datetimeToIso(val) {
    if (!val) return null;
    const d = new Date(val);
    return Number.isNaN(d.getTime()) ? null : d.toISOString();
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function showToast(msg, ms = 4000) {
    const el = document.getElementById("page-toast");
    if (!el) return;
    el.textContent = msg;
    el.style.display = "block";
    setTimeout(() => {
      el.style.display = "none";
    }, ms);
  }

  function showError(msg) {
    const el = document.getElementById("page-error");
    if (!el) return;
    el.textContent = msg;
    el.style.display = "block";
  }

  function hideError() {
    const el = document.getElementById("page-error");
    if (el) el.style.display = "none";
  }
})();
