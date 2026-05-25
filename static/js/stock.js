/**
 * 棚補充・使用画面（/stock/replenish | /stock/consume）
 */
(function () {
  const MODE = window.STOCK_MODE || "replenish";
  const ACTION = MODE === "replenish" ? "restock" : "use";
  const MODE_LABEL = MODE === "replenish" ? "補充" : "使用";
  const DATETIME_LABEL = MODE === "replenish" ? "補充日時" : "使用日時";

  let currentUser = null;
  let stores = [];
  let inventory = [];
  let categories = [];
  let makers = [];
  let dealers = [];
  let bulkPending = [];
  let html5QrBulk = null;
  let bulkCameraOn = false;
  let scanCooldown = false;
  let pendingScanCode = null;
  let registerModalProductId = null;
  let registerModalUnit = "本";
  let registerModalCurrentQty = 0;
  let registerModalOnShelf = true;

  const storeSelect = document.getElementById("store-select");
  const skuList = document.getElementById("sku-list");
  const stockToast = document.getElementById("stock-toast");
  const stockError = document.getElementById("stock-error");

  document.addEventListener("DOMContentLoaded", init);

  async function init() {
    const regLabel = document.getElementById("reg-datetime-label");
    if (regLabel) regLabel.textContent = DATETIME_LABEL;
    const newRegLabel = document.getElementById("new-reg-datetime-label");
    if (newRegLabel) newRegLabel.textContent = DATETIME_LABEL;
    const regSubmit = document.getElementById("reg-submit-btn");
    if (regSubmit) regSubmit.textContent = "登録する";

    document.querySelectorAll("[data-stock-tab]").forEach((btn) => {
      btn.addEventListener("click", () => switchTab(btn.dataset.stockTab));
    });

    storeSelect?.addEventListener("change", async () => {
      await loadInventory();
      bulkPending = [];
      renderBulkLines();
      updateStoreDependentUI();
    });

    ["filter-category", "filter-maker", "filter-dealer", "filter-name"].forEach((id) => {
      document.getElementById(id)?.addEventListener("input", renderSkuList);
      document.getElementById(id)?.addEventListener("change", renderSkuList);
    });

    bindRegisterModal();
    if (MODE === "replenish") bindNewProductModal();
    bindNotRegisteredModal();
    bindNotOnShelfModal();
    bindScanTab();
    bindBulkTab();

    applyPageBootstrapData();
    syncStoresFromDomIfNeeded();
    setupStoreSelect();
    fillFilters();
    fillNewProductMasters();
    switchTab("search");

    try {
      currentUser = await Api.get("/api/auth/me");
      filterStoresForUser();
      setupStoreSelect();
    } catch (err) {
      console.warn("auth/me:", err);
    }

    try {
      await loadMasterData();
      fillFilters();
      fillNewProductMasters();
    } catch (err) {
      showError(err.message || "マスタデータの取得に失敗しました。");
    }

    try {
      if (!inventory.length) applyInventoryBootstrap();
      await loadInventory();
    } catch (err) {
      if (!inventory.length) applyInventoryBootstrap();
      if (!inventory.length) {
        showError(err.message || "在庫一覧の取得に失敗しました。");
      }
    }

    updateStoreDependentUI();
  }

  function hasValidStoreId() {
    const id = getStoreId();
    return Number.isFinite(id) && id > 0;
  }

  function updateStoreDependentUI() {
    const ok = hasValidStoreId();
    const hint = document.getElementById("store-required-hint");
    if (hint) hint.hidden = ok;
    const modalOpen =
      document.getElementById("register-modal") &&
      !document.getElementById("register-modal").hidden;
    if (modalOpen) refreshRegisterModalStock();
    else {
      const regBtn = document.getElementById("reg-submit-btn");
      if (regBtn) regBtn.disabled = !ok;
    }
    const bulkBtn = document.getElementById("btn-bulk-submit");
    if (bulkBtn) bulkBtn.disabled = !ok || !bulkPending.length;
  }

  function stockShortageMessage(current, unit) {
    const u = unit || "本";
    return `在庫が不足しています。現在の在庫数：${current}${u}。使用できる最大数：${current}${u}。`;
  }

  async function fetchProductQuantity(productId) {
    if (!hasValidStoreId()) return null;
    const data = await Api.get(
      `/api/stock/quantity?store_id=${getStoreId()}&product_id=${productId}`
    );
    const invItem = inventory.find((x) => x.product_id === productId);
    if (invItem) invItem.quantity = data.quantity;
    return data;
  }

  async function refreshRegisterModalStock() {
    const qtyEl = document.getElementById("reg-current-qty");
    if (!registerModalProductId) return;

    if (!hasValidStoreId()) {
      registerModalCurrentQty = 0;
      if (qtyEl) qtyEl.textContent = "—（店舗を選択してください）";
      applyRegisterQuantityLimits();
      updateRegisterSubmitState();
      return;
    }

    try {
      const data = await fetchProductQuantity(registerModalProductId);
      registerModalCurrentQty = data.quantity;
      registerModalUnit = data.unit || "本";
      registerModalOnShelf = data.is_on_shelf !== false;
      if (qtyEl) {
        qtyEl.textContent = `${data.quantity}${registerModalUnit}`;
        if (MODE === "consume" && !registerModalOnShelf) {
          qtyEl.textContent += "（この店舗の棚に未配置）";
        }
      }
      if (MODE === "consume" && !registerModalOnShelf) {
        const errEl = document.getElementById("register-form-error");
        if (errEl) {
          errEl.textContent = "この店舗の棚にない商品です。";
          errEl.hidden = false;
        }
      }
      applyRegisterQuantityLimits();
      updateRegisterSubmitState();
    } catch {
      registerModalCurrentQty = 0;
      if (qtyEl) qtyEl.textContent = "取得できませんでした";
      updateRegisterSubmitState();
    }
  }

  function applyRegisterQuantityLimits() {
    const input = document.getElementById("reg-quantity");
    if (!input) return;
    if (MODE === "consume") {
      const maxQ = Math.max(0, registerModalCurrentQty);
      input.max = maxQ;
      input.min = maxQ > 0 ? 1 : 0;
      if (maxQ < 1) {
        input.value = "0";
        input.disabled = true;
      } else {
        input.disabled = false;
        const v = parseInt(input.value, 10) || 1;
        if (v > maxQ) input.value = String(maxQ);
        if (v < 1) input.value = "1";
      }
    } else {
      input.disabled = false;
      input.min = 1;
      input.max = 999;
    }
  }

  function updateRegisterSubmitState() {
    const btn = document.getElementById("reg-submit-btn");
    if (!btn) return;
    let ok = hasValidStoreId();
    const q = parseInt(document.getElementById("reg-quantity")?.value, 10) || 0;
    if (MODE === "consume") {
      ok =
        ok &&
        registerModalOnShelf &&
        registerModalCurrentQty > 0 &&
        q >= 1 &&
        q <= registerModalCurrentQty;
    } else {
      ok = ok && q >= 1;
    }
    btn.disabled = !ok;
  }

  function validateStoreForSubmit() {
    if (!hasValidStoreId()) return "店舗を選択してください。";
    return null;
  }

  function validateConsumeQuantity(current, quantity, unit) {
    if (quantity < 1) return "数量は1以上を指定してください。";
    if (current - quantity < 0) return stockShortageMessage(current, unit);
    return null;
  }

  /** テンプレート埋め込みデータ（stock.py から渡される） */
  function applyPageBootstrapData() {
    const boot = window.STOCK_PAGE_DATA;
    if (!boot || typeof boot !== "object") return;
    if (Array.isArray(boot.stores) && boot.stores.length) stores = boot.stores;
    if (Array.isArray(boot.categories) && boot.categories.length) categories = boot.categories;
    if (Array.isArray(boot.makers) && boot.makers.length) makers = boot.makers;
    if (Array.isArray(boot.dealers) && boot.dealers.length) dealers = boot.dealers;
    if (Array.isArray(boot.inventory)) inventory = boot.inventory;
    if (boot.default_store_id && storeSelect) {
      storeSelect.value = String(boot.default_store_id);
    }
  }

  function applyInventoryBootstrap() {
    const boot = window.STOCK_PAGE_DATA;
    if (!boot || !Array.isArray(boot.inventory) || !boot.inventory.length) return;
    const storeId = getStoreId();
    if (storeId && boot.default_store_id && storeId !== boot.default_store_id) return;
    inventory = boot.inventory;
    renderSkuList();
  }

  /** SSR 済みの店舗セレクトから stores を復元 */
  function syncStoresFromDomIfNeeded() {
    if (stores.length || !storeSelect) return;
    const parsed = [];
    storeSelect.querySelectorAll("option").forEach((opt) => {
      const id = parseInt(opt.value, 10);
      if (!id) return;
      parsed.push({ id, name: opt.textContent.trim() });
    });
    if (parsed.length) stores = parsed;
  }

  async function loadMasterData() {
    const tasks = [];
    if (!stores.length) tasks.push(Api.get("/api/stores").then((s) => { stores = s; }));
    if (!categories.length) {
      tasks.push(Api.get("/api/categories").then((c) => { categories = c; }));
    }
    if (!makers.length) tasks.push(Api.get("/api/makers").then((m) => { makers = m; }));
    if (!dealers.length) tasks.push(Api.get("/api/dealers").then((d) => { dealers = d; }));
    if (tasks.length) await Promise.all(tasks);
  }

  function filterStoresForUser() {
    if (currentUser?.role === "staff" && currentUser.store_id) {
      stores = stores.filter((s) => s.id === currentUser.store_id);
    }
  }

  function switchTab(tab) {
    if (!tab) return;
    document.querySelectorAll("[data-stock-tab]").forEach((b) => {
      b.classList.toggle("active", b.dataset.stockTab === tab);
    });
    ["search", "scan", "bulk"].forEach((name) => {
      const panel = document.getElementById(`stock-tab-${name}`);
      if (panel) panel.hidden = name !== tab;
    });
    if (tab !== "bulk" && bulkCameraOn) stopBulkCamera();
  }

  function setupStoreSelect() {
    if (!storeSelect) return;
    filterStoresForUser();
    if (!stores.length) {
      storeSelect.innerHTML = '<option value="">店舗がありません</option>';
      updateStoreDependentUI();
      return;
    }
    storeSelect.innerHTML = stores
      .map((s) => `<option value="${s.id}">${escapeHtml(s.name)}</option>`)
      .join("");
    if (currentUser?.store_id) {
      storeSelect.value = String(currentUser.store_id);
      if (currentUser.role === "staff") storeSelect.disabled = true;
    }
    updateStoreDependentUI();
  }

  function fillFilters() {
    const cat = document.getElementById("filter-category");
    if (cat) {
      cat.innerHTML =
        '<option value="">すべて</option>' +
        categories.map((c) => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join("");
    }
    const mk = document.getElementById("filter-maker");
    if (mk) {
      mk.innerHTML =
        '<option value="">すべて</option>' +
        makers.map((m) => `<option value="${m.id}">${escapeHtml(m.name)}</option>`).join("");
    }
    const dl = document.getElementById("filter-dealer");
    if (dl) {
      dl.innerHTML =
        '<option value="">すべて</option>' +
        dealers.map((d) => `<option value="${d.id}">${escapeHtml(d.name)}</option>`).join("");
    }
  }

  function fillNewProductMasters() {
    if (MODE !== "replenish") return;
    const catEl = document.getElementById("new-category_id");
    if (!catEl) return;
    catEl.innerHTML = categories
      .map((c) => `<option value="${c.id}">${escapeHtml(c.name)}</option>`)
      .join("");
    fillOptional("new-maker_id", makers);
    fillOptional("new-dealer_id", dealers);
  }

  function fillOptional(id, items) {
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML =
      '<option value="">—</option>' +
      items.map((i) => `<option value="${i.id}">${escapeHtml(i.name)}</option>`).join("");
  }

  async function loadInventory() {
    const storeId = getStoreId();
    if (!storeId) {
      inventory = [];
      if (skuList) skuList.innerHTML = "";
      const empty = document.getElementById("sku-empty");
      if (empty) empty.hidden = false;
      return;
    }
    hideError();
    if (skuList) skuList.innerHTML = '<li class="loading">読み込み中…</li>';
    const activeOnly = MODE === "replenish" ? "false" : "true";
    inventory = await Api.get(
      `/api/inventory/store/${storeId}?active_only=${activeOnly}`
    );
    renderSkuList();
  }

  function getStoreId() {
    return parseInt(storeSelect.value, 10) || null;
  }

  function filteredInventory() {
    const cat = document.getElementById("filter-category")?.value || "";
    const maker = document.getElementById("filter-maker")?.value || "";
    const dealer = document.getElementById("filter-dealer")?.value || "";
    const nameQ = (document.getElementById("filter-name")?.value || "").trim().toLowerCase();

    return inventory.filter((item) => {
      if (cat && String(item.category_id) !== cat) return false;
      if (maker && String(item.maker_id || "") !== maker) return false;
      if (dealer && String(item.dealer_id || "") !== dealer) return false;
      if (nameQ && !(item.product_name || "").toLowerCase().includes(nameQ)) return false;
      return true;
    });
  }

  function renderSkuList() {
    if (!skuList) return;
    const items = filteredInventory();
    const empty = document.getElementById("sku-empty");
    if (!items.length) {
      skuList.innerHTML = "";
      if (empty) empty.hidden = false;
      return;
    }
    if (empty) empty.hidden = true;
    skuList.innerHTML = items
      .map(
        (item) => `
      <li class="sku-item stock-${item.stock_level}">
        <button type="button" class="sku-btn" data-product-id="${item.product_id}">
          <span class="sku-name">${escapeHtml(item.product_name)}</span>
          <span class="sku-meta">${escapeHtml(item.barcode)} · 在庫 ${item.quantity}${escapeHtml(item.unit)}${MODE === "replenish" && !item.is_on_shelf ? " · 未配置" : ""}</span>
        </button>
      </li>`
      )
      .join("");

    skuList.querySelectorAll(".sku-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = parseInt(btn.dataset.productId, 10);
        const item = inventory.find((x) => x.product_id === id);
        if (item) void openRegisterModal(item);
      });
    });
  }

  function nowLocalDatetime() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  function datetimeToIso(val) {
    if (!val) return null;
    const d = new Date(val);
    if (Number.isNaN(d.getTime())) return null;
    return d.toISOString();
  }

  async function openRegisterModal(item, scanCode) {
    registerModalProductId = item.product_id;
    registerModalUnit = item.unit || "本";
    registerModalCurrentQty = item.quantity ?? 0;
    document.getElementById("reg-product-id").value = item.product_id;
    document.getElementById("reg-product-name").textContent = item.product_name;
    document.getElementById("reg-barcode").textContent = item.barcode || scanCode || "—";
    document.getElementById("reg-quantity").value = "1";
    document.getElementById("reg-datetime").value = nowLocalDatetime();
    document.getElementById("register-form-error").hidden = true;
    document.getElementById("register-modal").hidden = false;
    document.body.style.overflow = "hidden";
    await refreshRegisterModalStock();
  }

  function closeRegisterModal() {
    document.getElementById("register-modal").hidden = true;
    document.body.style.overflow = "";
    registerModalProductId = null;
    registerModalCurrentQty = 0;
    updateStoreDependentUI();
  }

  function bindRegisterModal() {
    document.getElementById("reg-quantity")?.addEventListener("input", () => {
      applyRegisterQuantityLimits();
      updateRegisterSubmitState();
    });

    document.getElementById("register-form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const errEl = document.getElementById("register-form-error");
      errEl.hidden = true;
      const storeErr = validateStoreForSubmit();
      if (storeErr) {
        errEl.textContent = storeErr;
        errEl.hidden = false;
        return;
      }
      const productId = parseInt(document.getElementById("reg-product-id").value, 10);
      const quantity = parseInt(document.getElementById("reg-quantity").value, 10) || 0;
      if (MODE === "consume") {
        if (!registerModalOnShelf) {
          errEl.textContent = "この店舗の棚にない商品です。";
          errEl.hidden = false;
          return;
        }
        const consumeErr = validateConsumeQuantity(
          registerModalCurrentQty,
          quantity,
          registerModalUnit
        );
        if (consumeErr) {
          errEl.textContent = consumeErr;
          errEl.hidden = false;
          return;
        }
      } else if (quantity < 1) {
        errEl.textContent = "数量は1以上を指定してください。";
        errEl.hidden = false;
        return;
      }
      const recorded_at = datetimeToIso(document.getElementById("reg-datetime").value);

      try {
        const res = await Api.post("/api/stock/register", {
          store_id: getStoreId(),
          product_id: productId,
          action: ACTION,
          quantity,
          recorded_at,
        });
        closeRegisterModal();
        showToast(res.message);
        await loadInventory();
        if (navigator.vibrate) navigator.vibrate(80);
      } catch (err) {
        errEl.textContent = err.message;
        errEl.hidden = false;
      }
    });
    document.getElementById("register-modal-close")?.addEventListener("click", closeRegisterModal);
    document.getElementById("register-modal-cancel")?.addEventListener("click", closeRegisterModal);
    document.getElementById("register-modal")?.addEventListener("click", (e) => {
      if (e.target.id === "register-modal") closeRegisterModal();
    });
  }

  function bindNewProductModal() {
    document.getElementById("new-product-form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const errEl = document.getElementById("new-product-form-error");
      errEl.hidden = true;
      const maker = document.getElementById("new-maker_id").value;
      const dealer = document.getElementById("new-dealer_id").value;
      const jan = document.getElementById("new-jan_code").value.trim();
      const product = {
        name: document.getElementById("new-name").value.trim(),
        barcode: document.getElementById("new-barcode").value.trim(),
        jan_code: jan || pendingScanCode || null,
        category_id: parseInt(document.getElementById("new-category_id").value, 10),
        unit: document.getElementById("new-unit").value.trim() || "本",
        warning_threshold: parseInt(document.getElementById("new-warning_threshold").value, 10),
        critical_threshold: parseInt(document.getElementById("new-critical_threshold").value, 10),
        maker_id: maker ? parseInt(maker, 10) : null,
        dealer_id: dealer ? parseInt(dealer, 10) : null,
      };
      const storeErr = validateStoreForSubmit();
      if (storeErr) {
        errEl.textContent = storeErr;
        errEl.hidden = false;
        return;
      }
      const quantity = parseInt(document.getElementById("new-reg-quantity").value, 10) || 1;
      const recorded_at = datetimeToIso(document.getElementById("new-reg-datetime").value);

      try {
        const res = await Api.post("/api/stock/register-with-product", {
          store_id: getStoreId(),
          action: ACTION,
          quantity,
          recorded_at,
          product,
        });
        closeNewProductModal();
        showToast(res.message);
        await loadInventory();
      } catch (err) {
        errEl.textContent = err.message;
        errEl.hidden = false;
      }
    });
    document.getElementById("new-product-no")?.addEventListener("click", closeNewProductModal);
    document.getElementById("new-product-modal-close")?.addEventListener("click", closeNewProductModal);
    document.getElementById("new-product-modal")?.addEventListener("click", (e) => {
      if (e.target.id === "new-product-modal") closeNewProductModal();
    });
  }

  function openNewProductModal(code) {
    pendingScanCode = code;
    document.getElementById("new-scan-code").textContent = code;
    document.getElementById("new-barcode").value = code;
    document.getElementById("new-jan_code").value = code;
    document.getElementById("new-name").value = "";
    document.getElementById("new-reg-quantity").value = "1";
    document.getElementById("new-reg-datetime").value = nowLocalDatetime();
    document.getElementById("new-product-form-error").hidden = true;
    if (categories.length) document.getElementById("new-category_id").value = categories[0].id;
    document.getElementById("new-product-modal").hidden = false;
    document.body.style.overflow = "hidden";
  }

  function closeNewProductModal() {
    const el = document.getElementById("new-product-modal");
    if (!el) return;
    el.hidden = true;
    document.body.style.overflow = "";
    pendingScanCode = null;
  }

  function openNotRegisteredModal(code) {
    const codeWrap = document.getElementById("not-registered-code-wrap");
    const codeEl = document.getElementById("not-registered-code");
    if (code && codeEl) {
      codeEl.textContent = code;
      if (codeWrap) codeWrap.hidden = false;
    } else if (codeWrap) {
      codeWrap.hidden = true;
    }
    document.getElementById("not-registered-modal").hidden = false;
    document.body.style.overflow = "hidden";
  }

  function closeNotRegisteredModal() {
    document.getElementById("not-registered-modal").hidden = true;
    document.body.style.overflow = "";
  }

  function bindNotRegisteredModal() {
    document.getElementById("not-registered-close")?.addEventListener("click", closeNotRegisteredModal);
    document.getElementById("not-registered-modal-close")?.addEventListener("click", closeNotRegisteredModal);
    document.getElementById("not-registered-modal")?.addEventListener("click", (e) => {
      if (e.target.id === "not-registered-modal") closeNotRegisteredModal();
    });
  }

  function openNotOnShelfModal(code) {
    const codeWrap = document.getElementById("not-on-shelf-code-wrap");
    const codeEl = document.getElementById("not-on-shelf-code");
    if (code && codeEl) {
      codeEl.textContent = code;
      if (codeWrap) codeWrap.hidden = false;
    } else if (codeWrap) codeWrap.hidden = true;
    document.getElementById("not-on-shelf-modal").hidden = false;
    document.body.style.overflow = "hidden";
  }

  function closeNotOnShelfModal() {
    document.getElementById("not-on-shelf-modal").hidden = true;
    document.body.style.overflow = "";
  }

  function bindNotOnShelfModal() {
    document.getElementById("not-on-shelf-close")?.addEventListener("click", closeNotOnShelfModal);
    document.getElementById("not-on-shelf-modal-close")?.addEventListener("click", closeNotOnShelfModal);
    document.getElementById("not-on-shelf-modal")?.addEventListener("click", (e) => {
      if (e.target.id === "not-on-shelf-modal") closeNotOnShelfModal();
    });
  }

  function handleUnregisteredProduct(code) {
    if (MODE === "consume") {
      openNotRegisteredModal(code);
      return;
    }
    openNewProductModal(code);
  }

  function handleConsumeProduct(lookup, code) {
    if (!lookup.is_on_shelf) {
      openNotOnShelfModal(code);
      return;
    }
    const item = inventory.find((x) => x.product_id === lookup.product_id) || {
      product_id: lookup.product_id,
      product_name: lookup.product_name,
      barcode: lookup.barcode,
      quantity: lookup.quantity,
      unit: lookup.unit || "本",
    };
    void openRegisterModal(item, code);
  }

  function bindScanTab() {
    const input = document.getElementById("scanner-input");
    const status = document.getElementById("scanner-status");

    document.getElementById("btn-bluetooth-focus")?.addEventListener("click", () => {
      input.focus();
      status.hidden = false;
      status.textContent = "スキャン待機中…（Bluetoothスキャナーで読み取ってください）";
    });

    input?.addEventListener("keydown", async (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      const code = input.value.trim();
      input.value = "";
      if (!code) return;
      await handleScanCode(code);
    });
  }

  async function handleScanCode(code) {
    hideError();
    try {
      const lookup = await Api.get(
        `/api/stock/lookup?store_id=${getStoreId()}&code=${encodeURIComponent(code)}`
      );
      if (lookup.found) {
        if (MODE === "consume") handleConsumeProduct(lookup, code);
        else {
          const item = inventory.find((x) => x.product_id === lookup.product_id) || {
            product_id: lookup.product_id,
            product_name: lookup.product_name,
            barcode: lookup.barcode,
            quantity: lookup.quantity,
            unit: lookup.unit || "本",
          };
          void openRegisterModal(item, code);
        }
      } else {
        handleUnregisteredProduct(code);
      }
    } catch (err) {
      showError(err.message);
    }
  }

  function bindBulkTab() {
    document.getElementById("btn-bulk-camera")?.addEventListener("click", toggleBulkCamera);
    document.getElementById("bulk-file")?.addEventListener("change", onBulkFile);
    document.getElementById("btn-bulk-submit")?.addEventListener("click", submitBulk);
  }

  async function toggleBulkCamera() {
    if (typeof Html5Qrcode === "undefined") {
      showError("カメラライブラリが読み込めません");
      return;
    }
    const readerId = "reader-bulk";
    const el = document.getElementById(readerId);
    if (!html5QrBulk) {
      html5QrBulk = new Html5Qrcode(readerId);
    }
    if (bulkCameraOn) {
      await html5QrBulk.stop();
      bulkCameraOn = false;
      el.hidden = true;
      document.getElementById("btn-bulk-camera").textContent = "カメラ開始";
      return;
    }
    el.hidden = false;
    try {
      await html5QrBulk.start(
        { facingMode: "environment" },
        { fps: 8, qrbox: { width: 250, height: 120 } },
        onBulkScan,
        () => {}
      );
      bulkCameraOn = true;
      document.getElementById("btn-bulk-camera").textContent = "カメラ停止";
    } catch (err) {
      showError("カメラを起動できません: " + err.message);
    }
  }

  async function stopBulkCamera() {
    if (html5QrBulk && bulkCameraOn) {
      try {
        await html5QrBulk.stop();
      } catch {
        /* ignore */
      }
      bulkCameraOn = false;
      document.getElementById("reader-bulk").hidden = true;
      document.getElementById("btn-bulk-camera").textContent = "カメラ開始";
    }
  }

  function onBulkScan(decodedText) {
    if (scanCooldown) return;
    scanCooldown = true;
    setTimeout(() => {
      scanCooldown = false;
    }, 1500);
    addBulkFromScan(decodedText.trim());
  }

  async function addBulkFromScan(code) {
    try {
      const lookup = await Api.get(
        `/api/stock/lookup?store_id=${getStoreId()}&code=${encodeURIComponent(code)}`
      );
      if (!lookup.found) {
        if (MODE === "consume") handleUnregisteredProduct(code);
        else showError(`未登録: ${code}`);
        return;
      }
      if (MODE === "consume" && !lookup.is_on_shelf) {
        openNotOnShelfModal(code);
        return;
      }
      mergeBulkLine({
        product_id: lookup.product_id,
        product_name: lookup.product_name,
        unit: lookup.unit || "本",
        quantity: 1,
        current_quantity: lookup.quantity,
        matched: true,
        product_code: code,
      });
    } catch (err) {
      showError(err.message);
    }
  }

  async function onBulkFile(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    hideError();
    try {
      const res = await Api.upload(
        `/api/stock/bulk-parse?store_id=${getStoreId()}`,
        file,
        "file"
      );
      const matched = (res.lines || []).filter((ln) => ln.matched);
      if (!matched.length) {
        showError(res.note || "一致する商品がありませんでした");
        return;
      }
      matched.forEach((ln) => mergeBulkLine(ln));
      const noteEl = document.getElementById("bulk-parse-note");
      if (res.note) {
        noteEl.textContent = res.note;
        noteEl.hidden = false;
      } else {
        noteEl.hidden = true;
      }
    } catch (err) {
      showError(err.message);
    }
  }

  function mergeBulkLine(ln) {
    const existing = bulkPending.find((x) => x.product_id === ln.product_id);
    if (existing) {
      existing.quantity += ln.quantity || 1;
    } else {
      bulkPending.push({
        product_id: ln.product_id,
        product_name: ln.product_name,
        unit: ln.unit || "本",
        quantity: ln.quantity || 1,
        current_quantity: ln.current_quantity ?? 0,
        product_code: ln.product_code || "",
      });
    }
    renderBulkLines();
  }

  function renderBulkLines() {
    const wrap = document.getElementById("bulk-lines-wrap");
    const list = document.getElementById("bulk-lines");
    const empty = document.getElementById("bulk-empty");

    if (!bulkPending.length) {
      wrap.hidden = true;
      empty.hidden = false;
      list.innerHTML = "";
      return;
    }
    empty.hidden = true;
    wrap.hidden = false;
    const dt = nowLocalDatetime();
    list.innerHTML = bulkPending
      .map(
        (ln, idx) => {
          const maxQ =
            MODE === "consume" ? Math.max(0, ln.current_quantity ?? 0) : 999;
          const minQ = MODE === "consume" && maxQ < 1 ? 0 : 1;
          const val =
            MODE === "consume" && maxQ > 0
              ? Math.min(ln.quantity || 1, maxQ)
              : ln.quantity || 1;
          return `
      <li class="bulk-line card" data-idx="${idx}">
        <div class="bulk-line-head">
          <strong>${escapeHtml(ln.product_name)}</strong>
          <span class="bulk-line-meta bulk-line-stock" data-idx="${idx}">在庫 ${ln.current_quantity}${escapeHtml(ln.unit)}</span>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>数量</label>
            <input type="number" class="input-number bulk-qty" data-idx="${idx}" value="${val}" min="${minQ}" max="${maxQ}" ${
            MODE === "consume" && maxQ < 1 ? "disabled" : ""
          }>
          </div>
          <div class="form-group">
            <label>${DATETIME_LABEL}</label>
            <input type="datetime-local" class="input-text bulk-dt" data-idx="${idx}" value="${dt}">
          </div>
          <button type="button" class="btn btn-ghost btn-sm bulk-remove" data-idx="${idx}">削除</button>
        </div>
      </li>`
      )
      .join("");

    list.querySelectorAll(".bulk-qty").forEach((inp) => {
      inp.addEventListener("change", () => {
        const i = parseInt(inp.dataset.idx, 10);
        bulkPending[i].quantity = parseInt(inp.value, 10) || 1;
      });
    });
    list.querySelectorAll(".bulk-dt").forEach((inp) => {
      inp.addEventListener("change", () => {
        const i = parseInt(inp.dataset.idx, 10);
        bulkPending[i].recorded_at = inp.value;
      });
    });
    list.querySelectorAll(".bulk-remove").forEach((btn) => {
      btn.addEventListener("click", () => {
        const i = parseInt(btn.dataset.idx, 10);
        bulkPending.splice(i, 1);
        renderBulkLines();
      });
    });
    updateStoreDependentUI();
  }

  async function refreshBulkLinesStock() {
    if (!hasValidStoreId() || !bulkPending.length) return;
    for (const ln of bulkPending) {
      try {
        const data = await fetchProductQuantity(ln.product_id);
        ln.current_quantity = data.quantity;
        ln.unit = data.unit || ln.unit;
      } catch {
        /* keep previous */
      }
    }
    renderBulkLines();
  }

  async function submitBulk() {
    const storeErr = validateStoreForSubmit();
    if (storeErr) {
      showError(storeErr);
      return;
    }
    if (!bulkPending.length) {
      showError("登録する商品がありません");
      return;
    }
    const lines = bulkPending.map((ln, idx) => {
      const row = document.querySelector(`.bulk-dt[data-idx="${idx}"]`);
      const dtVal = row?.value || ln.recorded_at || nowLocalDatetime();
      const qtyInp = document.querySelector(`.bulk-qty[data-idx="${idx}"]`);
      return {
        product_id: ln.product_id,
        quantity: parseInt(qtyInp?.value, 10) || ln.quantity,
        recorded_at: datetimeToIso(dtVal),
      };
    });

    if (MODE === "consume") {
      for (let i = 0; i < bulkPending.length; i++) {
        const ln = bulkPending[i];
        const qty = lines[i].quantity;
        const err = validateConsumeQuantity(ln.current_quantity ?? 0, qty, ln.unit);
        if (err) {
          showError(`${ln.product_name}: ${err}`);
          return;
        }
      }
    }

    try {
      const res = await Api.post("/api/stock/bulk-register", {
        store_id: getStoreId(),
        action: ACTION,
        lines,
      });
      bulkPending = [];
      renderBulkLines();
      showToast(`${res.count} 件を${MODE_LABEL}登録しました`);
      await loadInventory();
    } catch (err) {
      showError(err.message);
    }
  }

  function showToast(msg) {
    stockToast.textContent = msg;
    stockToast.classList.remove("error");
    stockToast.hidden = false;
    stockError.hidden = true;
    setTimeout(() => {
      stockToast.hidden = true;
    }, 5000);
  }

  function showError(msg) {
    stockError.textContent = msg;
    stockError.hidden = false;
    stockToast.hidden = true;
  }

  function hideError() {
    stockError.hidden = true;
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }
})();
