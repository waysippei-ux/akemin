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

  const storeSelect = document.getElementById("store-select");
  const skuList = document.getElementById("sku-list");
  const stockToast = document.getElementById("stock-toast");
  const stockError = document.getElementById("stock-error");

  document.addEventListener("DOMContentLoaded", init);

  async function init() {
    document.getElementById("reg-datetime-label").textContent = DATETIME_LABEL;
    document.getElementById("new-reg-datetime-label").textContent = DATETIME_LABEL;
    document.getElementById("reg-submit-btn").textContent = "登録する";

    document.querySelectorAll("[data-stock-tab]").forEach((btn) => {
      btn.addEventListener("click", () => switchTab(btn.dataset.stockTab));
    });

    storeSelect?.addEventListener("change", () => {
      loadInventory();
      bulkPending = [];
      renderBulkLines();
    });

    ["filter-category", "filter-maker", "filter-dealer", "filter-name"].forEach((id) => {
      document.getElementById(id)?.addEventListener("input", renderSkuList);
      document.getElementById(id)?.addEventListener("change", renderSkuList);
    });

    bindRegisterModal();
    if (MODE === "replenish") bindNewProductModal();
    bindNotRegisteredModal();
    bindScanTab();
    bindBulkTab();

    try {
      currentUser = await Api.get("/api/auth/me");
      [stores, categories, makers, dealers] = await Promise.all([
        Api.get("/api/stores"),
        Api.get("/api/categories"),
        Api.get("/api/makers"),
        Api.get("/api/dealers"),
      ]);
      setupStoreSelect();
      fillFilters();
      fillNewProductMasters();
      await loadInventory();
    } catch (err) {
      showError(err.message);
    }
  }

  function switchTab(tab) {
    document.querySelectorAll("[data-stock-tab]").forEach((b) => {
      b.classList.toggle("active", b.dataset.stockTab === tab);
    });
    document.querySelectorAll(".stock-tab-panel").forEach((p) => {
      const id = `stock-tab-${tab}`;
      p.hidden = p.id !== id;
    });
    if (tab !== "bulk" && bulkCameraOn) stopBulkCamera();
  }

  function setupStoreSelect() {
    storeSelect.innerHTML = stores
      .map((s) => `<option value="${s.id}">${escapeHtml(s.name)}</option>`)
      .join("");
    if (currentUser.store_id) {
      storeSelect.value = String(currentUser.store_id);
      if (currentUser.role === "staff") storeSelect.disabled = true;
    }
  }

  function fillFilters() {
    const cat = document.getElementById("filter-category");
    cat.innerHTML =
      '<option value="">すべて</option>' +
      categories.map((c) => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join("");
    const mk = document.getElementById("filter-maker");
    mk.innerHTML =
      '<option value="">すべて</option>' +
      makers.map((m) => `<option value="${m.id}">${escapeHtml(m.name)}</option>`).join("");
    const dl = document.getElementById("filter-dealer");
    dl.innerHTML =
      '<option value="">すべて</option>' +
      dealers.map((d) => `<option value="${d.id}">${escapeHtml(d.name)}</option>`).join("");
  }

  function fillNewProductMasters() {
    document.getElementById("new-category_id").innerHTML = categories
      .map((c) => `<option value="${c.id}">${escapeHtml(c.name)}</option>`)
      .join("");
    fillOptional("new-maker_id", makers);
    fillOptional("new-dealer_id", dealers);
  }

  function fillOptional(id, items) {
    const el = document.getElementById(id);
    el.innerHTML =
      '<option value="">—</option>' +
      items.map((i) => `<option value="${i.id}">${escapeHtml(i.name)}</option>`).join("");
  }

  async function loadInventory() {
    const storeId = getStoreId();
    if (!storeId) return;
    hideError();
    skuList.innerHTML = '<li class="loading">読み込み中…</li>';
    inventory = await Api.get(`/api/inventory/store/${storeId}`);
    renderSkuList();
  }

  function getStoreId() {
    return parseInt(storeSelect.value, 10) || null;
  }

  function filteredInventory() {
    const cat = document.getElementById("filter-category").value;
    const maker = document.getElementById("filter-maker").value;
    const dealer = document.getElementById("filter-dealer").value;
    const nameQ = (document.getElementById("filter-name").value || "").trim().toLowerCase();

    return inventory.filter((item) => {
      if (cat && String(item.category_id) !== cat) return false;
      if (maker && String(item.maker_id || "") !== maker) return false;
      if (dealer && String(item.dealer_id || "") !== dealer) return false;
      if (nameQ && !(item.product_name || "").toLowerCase().includes(nameQ)) return false;
      return true;
    });
  }

  function renderSkuList() {
    const items = filteredInventory();
    const empty = document.getElementById("sku-empty");
    if (!items.length) {
      skuList.innerHTML = "";
      empty.hidden = false;
      return;
    }
    empty.hidden = true;
    skuList.innerHTML = items
      .map(
        (item) => `
      <li class="sku-item stock-${item.stock_level}">
        <button type="button" class="sku-btn" data-product-id="${item.product_id}">
          <span class="sku-name">${escapeHtml(item.product_name)}</span>
          <span class="sku-meta">${escapeHtml(item.barcode)} · 在庫 ${item.quantity}${escapeHtml(item.unit)}</span>
        </button>
      </li>`
      )
      .join("");

    skuList.querySelectorAll(".sku-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = parseInt(btn.dataset.productId, 10);
        const item = inventory.find((x) => x.product_id === id);
        if (item) openRegisterModal(item);
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

  function openRegisterModal(item, scanCode) {
    document.getElementById("reg-product-id").value = item.product_id;
    document.getElementById("reg-product-name").textContent = item.product_name;
    document.getElementById("reg-barcode").textContent = item.barcode || scanCode || "—";
    document.getElementById("reg-current-qty").textContent = `${item.quantity}${item.unit || "本"}`;
    document.getElementById("reg-quantity").value = "1";
    document.getElementById("reg-datetime").value = nowLocalDatetime();
    document.getElementById("register-form-error").hidden = true;
    document.getElementById("register-modal").hidden = false;
    document.body.style.overflow = "hidden";
  }

  function closeRegisterModal() {
    document.getElementById("register-modal").hidden = true;
    document.body.style.overflow = "";
  }

  function bindRegisterModal() {
    document.getElementById("register-form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const errEl = document.getElementById("register-form-error");
      errEl.hidden = true;
      const productId = parseInt(document.getElementById("reg-product-id").value, 10);
      const quantity = parseInt(document.getElementById("reg-quantity").value, 10) || 1;
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

  function handleUnregisteredProduct(code) {
    if (MODE === "consume") {
      openNotRegisteredModal(code);
      return;
    }
    openNewProductModal(code);
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
        const item = inventory.find((x) => x.product_id === lookup.product_id) || {
          product_id: lookup.product_id,
          product_name: lookup.product_name,
          barcode: lookup.barcode,
          quantity: lookup.quantity,
          unit: lookup.unit || "本",
        };
        openRegisterModal(item, code);
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
        if (MODE === "consume") {
          handleUnregisteredProduct(code);
        } else {
          showError(`未登録: ${code}`);
        }
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
        (ln, idx) => `
      <li class="bulk-line card" data-idx="${idx}">
        <div class="bulk-line-head">
          <strong>${escapeHtml(ln.product_name)}</strong>
          <span class="bulk-line-meta">在庫 ${ln.current_quantity}${escapeHtml(ln.unit)}</span>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>数量</label>
            <input type="number" class="input-number bulk-qty" data-idx="${idx}" value="${ln.quantity}" min="1" max="999">
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
  }

  async function submitBulk() {
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
