/**
 * 棚に補充する（/stock/replenish）
 */
(function () {
  const PAGE = "replenish";
  let stores = [];
  let categories = [];
  let makers = [];
  let dealers = [];
  let products = [];
  let currentUser = null;
  let modalProductId = null;
  let modalUnit = "本";

  const storeSelect = document.getElementById("store-select");
  const productGrid = document.getElementById("product-grid");
  const pageToast = document.getElementById("page-toast");
  const pageError = document.getElementById("page-error");

  document.addEventListener("DOMContentLoaded", init);

  function init() {
    loadBootstrap();
    bindFilters();
    bindStoreChange();
    bindModal();

    setupStoreSelect();
    renderProducts();

    Api.get("/api/auth/me")
      .then((user) => {
        currentUser = user;
        filterStoresForUser();
        setupStoreSelect();
      })
      .catch(() => {});
  }

  function loadBootstrap() {
    const boot = window.STOCK_PAGE;
    if (!boot || typeof boot !== "object") return;
    stores = boot.stores || [];
    categories = boot.categories || [];
    makers = boot.makers || [];
    dealers = boot.dealers || [];
    products = boot.products || [];
    if (boot.default_store_id && storeSelect) {
      storeSelect.value = String(boot.default_store_id);
    }
  }

  function filterStoresForUser() {
    if (currentUser?.role === "staff" && currentUser.store_id) {
      stores = stores.filter((s) => s.id === currentUser.store_id);
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
  }

  function getStoreId() {
    return parseInt(storeSelect?.value, 10) || null;
  }

  function updateStoreHint() {
    const hint = document.getElementById("store-hint");
    if (hint) hint.hidden = !!getStoreId();
  }

  function bindStoreChange() {
    storeSelect?.addEventListener("change", async () => {
      updateStoreHint();
      await reloadProducts();
    });
  }

  function bindFilters() {
    ["filter-category", "filter-maker", "filter-dealer", "filter-name"].forEach((id) => {
      const el = document.getElementById(id);
      el?.addEventListener("input", renderProducts);
      el?.addEventListener("change", renderProducts);
    });
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
      products = await Api.get(
        `/api/stock/products?store_id=${storeId}&page=${PAGE}`
      );
      renderProducts();
    } catch (err) {
      showError(err.message);
    }
  }

  function filteredProducts() {
    const cat = document.getElementById("filter-category")?.value || "";
    const maker = document.getElementById("filter-maker")?.value || "";
    const dealer = document.getElementById("filter-dealer")?.value || "";
    const nameQ = (document.getElementById("filter-name")?.value || "").trim().toLowerCase();

    return products.filter((p) => {
      if (cat && String(p.category_id) !== cat) return false;
      if (maker && String(p.maker_id || "") !== maker) return false;
      if (dealer && String(p.dealer_id || "") !== dealer) return false;
      if (nameQ && !(p.product_name || "").toLowerCase().includes(nameQ)) return false;
      return true;
    });
  }

  function renderProducts() {
    const empty = document.getElementById("product-empty");
    if (!productGrid) return;
    const items = filteredProducts();
    if (!items.length) {
      productGrid.innerHTML = "";
      if (empty) empty.hidden = false;
      return;
    }
    if (empty) empty.hidden = true;
    productGrid.innerHTML = items
      .map(
        (p) => `
      <button type="button" class="product-card stock-${p.stock_level}" data-product-id="${p.product_id}">
        <span class="product-card-name">${escapeHtml(p.product_name)}</span>
        <span class="product-card-meta">${escapeHtml(p.category_name || "—")}</span>
        <span class="product-card-qty">在庫 ${p.quantity}${escapeHtml(p.unit)}${!p.is_on_shelf ? " · 未配置" : ""}</span>
      </button>`
      )
      .join("");

    productGrid.querySelectorAll(".product-card").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = parseInt(btn.dataset.productId, 10);
        const item = products.find((x) => x.product_id === id);
        if (item) openModal(item);
      });
    });
  }

  function bindModal() {
    document.getElementById("register-form")?.addEventListener("submit", onSubmit);
    document.getElementById("register-modal-close")?.addEventListener("click", closeModal);
    document.getElementById("register-modal-cancel")?.addEventListener("click", closeModal);
    document.getElementById("register-modal")?.addEventListener("click", (e) => {
      if (e.target.id === "register-modal") closeModal();
    });
  }

  async function openModal(item) {
    if (!getStoreId()) {
      showError("店舗を選択してください。");
      return;
    }
    modalProductId = item.product_id;
    modalUnit = item.unit || "本";
    document.getElementById("reg-product-id").value = item.product_id;
    document.getElementById("reg-product-name").textContent = item.product_name;
    document.getElementById("reg-barcode").textContent = item.barcode || "—";
    document.getElementById("reg-quantity").value = "1";
    document.getElementById("reg-datetime").value = nowLocalDatetime();
    document.getElementById("register-form-error").hidden = true;
    document.getElementById("register-modal").hidden = false;
    document.body.style.overflow = "hidden";
    await refreshModalQty();
  }

  function closeModal() {
    document.getElementById("register-modal").hidden = true;
    document.body.style.overflow = "";
    modalProductId = null;
  }

  async function refreshModalQty() {
    const qtyEl = document.getElementById("reg-current-qty");
    if (!modalProductId || !getStoreId()) {
      if (qtyEl) qtyEl.textContent = "—";
      return;
    }
    try {
      const data = await Api.get(
        `/api/stock/quantity?store_id=${getStoreId()}&product_id=${modalProductId}`
      );
      modalUnit = data.unit || "本";
      const inv = products.find((x) => x.product_id === modalProductId);
      if (inv) inv.quantity = data.quantity;
      if (qtyEl) qtyEl.textContent = `${data.quantity}${modalUnit}`;
    } catch {
      if (qtyEl) qtyEl.textContent = "取得できませんでした";
    }
  }

  async function onSubmit(e) {
    e.preventDefault();
    const errEl = document.getElementById("register-form-error");
    errEl.hidden = true;
    const storeId = getStoreId();
    if (!storeId) {
      errEl.textContent = "店舗を選択してください。";
      errEl.hidden = false;
      return;
    }
    const productId = parseInt(document.getElementById("reg-product-id").value, 10);
    const quantity = parseInt(document.getElementById("reg-quantity").value, 10) || 0;
    if (quantity < 1) {
      errEl.textContent = "数量は1以上を指定してください。";
      errEl.hidden = false;
      return;
    }
    const recorded_at = datetimeToIso(document.getElementById("reg-datetime").value);

    try {
      const res = await Api.post("/api/stock/replenish", {
        store_id: storeId,
        product_id: productId,
        quantity,
        recorded_at,
      });
      closeModal();
      showToast(res.message);
      await reloadProducts();
    } catch (err) {
      errEl.textContent = err.message;
      errEl.hidden = false;
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

  function showToast(msg) {
    if (!pageToast) return;
    pageToast.textContent = msg;
    pageToast.hidden = false;
    setTimeout(() => { pageToast.hidden = true; }, 4000);
  }

  function showError(msg) {
    if (!pageError) return;
    pageError.textContent = msg;
    pageError.hidden = false;
  }

  function hideError() {
    if (pageError) pageError.hidden = true;
  }
})();
