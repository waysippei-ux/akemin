/**
 * 棚を見る — 2セクション → カテゴリ内一覧
 */
(function () {
  let currentUser = null;
  let currentCategoryId = null;

  const $ = (id) => document.getElementById(id);
  const viewCategories = $("view-categories");
  const viewDetail = $("view-detail");
  const storeSelect = $("store-select");

  const LEVEL_LABEL = { green: "十分", yellow: "要発注", red: "至急" };

  document.addEventListener("DOMContentLoaded", init);

  function setHidden(el, hidden) {
    if (el) el.hidden = hidden;
  }

  function isDetailView() {
    return viewDetail && !viewDetail.hidden;
  }

  async function init() {
    $("btn-refresh")?.addEventListener("click", onRefresh);
    $("btn-back-categories")?.addEventListener("click", showCategories);
    storeSelect?.addEventListener("change", () => {
      if (isDetailView()) loadCategoryDetail();
      else loadCategoryCards();
    });

    if (!viewCategories || !viewDetail) {
      const greeting = $("user-greeting");
      if (greeting) {
        greeting.textContent =
          "画面の読み込みが不完全です。Cmd+Shift+R で再読み込みしてください。";
      }
      return;
    }

    try {
      currentUser = await Api.get("/api/auth/me");
      $("user-greeting").textContent = `${currentUser.username} さん（${
        currentUser.role === "admin" ? "管理者" : "スタッフ"
      }）`;

      const stores = await Api.get("/api/stores");
      storeSelect.innerHTML = stores
        .map((s) => `<option value="${s.id}">${escapeHtml(s.name)}</option>`)
        .join("");

      if (currentUser.store_id) {
        storeSelect.value = String(currentUser.store_id);
        if (currentUser.role === "staff") storeSelect.disabled = true;
      }

      await loadCategoryCards();
    } catch (err) {
      $("user-greeting").textContent = err.message;
      showLoadError($("categories-loading"), err.message);
    }
  }

  function getStoreId() {
    return parseInt(storeSelect.value, 10);
  }

  function onRefresh() {
    if (isDetailView()) loadCategoryDetail();
    else loadCategoryCards();
  }

  function showLoadError(el, message) {
    if (!el) return;
    el.hidden = false;
    el.textContent = message;
  }

  function renderCard(c) {
    return `
      <button type="button" class="category-card" data-id="${c.category_id}" data-name="${escapeHtml(c.category_name)}">
        <h3 class="category-card-title">${escapeHtml(c.category_name)}</h3>
        <p class="category-card-stats">
          全 <strong>${c.total_sku}</strong> SKU
        </p>
        <p class="category-card-badges">
          <span class="badge-pill badge-yellow">要発注 ${c.yellow_count}品</span>
          <span class="badge-pill badge-red">至急 ${c.red_count}品</span>
        </p>
      </button>
    `;
  }

  function bindCards(container) {
    if (!container) return;
    container.querySelectorAll(".category-card").forEach((card) => {
      card.addEventListener("click", () => {
        openCategory(parseInt(card.dataset.id, 10), card.dataset.name);
      });
    });
  }

  async function loadCategoryCards() {
    const loading = $("categories-loading");
    const materialsEl = $("cards-materials");
    const retailEl = $("cards-retail");

    setHidden(loading, false);
    if (loading) loading.textContent = "読み込み中…";
    if (materialsEl) materialsEl.innerHTML = "";
    if (retailEl) retailEl.innerHTML = "";

    try {
      const data = await Api.get(`/api/dashboard/sections?store_id=${getStoreId()}`);
      setHidden(loading, true);

      if (materialsEl) {
        materialsEl.innerHTML = data.materials.length
          ? data.materials.map(renderCard).join("")
          : '<p class="empty-msg">カテゴリがありません</p>';
        bindCards(materialsEl);
      }

      if (retailEl) {
        retailEl.innerHTML = data.retail.length
          ? data.retail.map(renderCard).join("")
          : '<p class="empty-msg">カテゴリがありません</p>';
        bindCards(retailEl);
      }
    } catch (err) {
      showLoadError(loading, err.message);
    }
  }

  function openCategory(id, name) {
    currentCategoryId = id;
    const breadcrumb = $("breadcrumb-category");
    if (breadcrumb) breadcrumb.textContent = name;
    $("page-title").textContent = name;
    setHidden(viewCategories, true);
    setHidden(viewDetail, false);
    loadCategoryDetail();
  }

  function showCategories() {
    currentCategoryId = null;
    $("page-title").textContent = "棚を見る";
    setHidden(viewDetail, true);
    setHidden(viewCategories, false);
    loadCategoryCards();
  }

  async function loadCategoryDetail() {
    if (!currentCategoryId) return;
    await Promise.all([
      loadInventory(getStoreId(), currentCategoryId),
      loadAdvice(getStoreId(), currentCategoryId),
    ]);
  }

  async function loadInventory(storeId, categoryId) {
    const loading = $("inventory-loading");
    const list = $("inventory-list");
    if (!loading || !list) return;

    setHidden(loading, false);
    loading.textContent = "読み込み中…";
    setHidden(list, true);

    try {
      const items = await Api.get(
        `/api/inventory/store/${storeId}/category/${categoryId}`
      );
      const order = { red: 0, yellow: 1, green: 2 };
      items.sort(
        (a, b) =>
          order[a.stock_level] - order[b.stock_level] ||
          a.product_name.localeCompare(b.product_name, "ja")
      );

      list.innerHTML = items.length
        ? items
            .map(
              (item) => `
          <div class="inventory-item stock-${item.stock_level}">
            <span class="item-name">${escapeHtml(item.product_name)}</span>
            <span class="item-badge">${LEVEL_LABEL[item.stock_level]}</span>
            <span class="item-qty">${item.quantity} ${escapeHtml(item.unit)}</span>
          </div>
        `
            )
            .join("")
        : '<p class="empty-msg">このカテゴリに商品はありません</p>';

      setHidden(loading, true);
      setHidden(list, false);
    } catch (err) {
      showLoadError(loading, err.message);
    }
  }

  async function loadAdvice(storeId, categoryId) {
    const loading = $("advice-loading");
    const text = $("advice-text");
    if (!loading || !text) return;

    setHidden(loading, false);
    loading.textContent = "分析中…";
    setHidden(text, true);

    try {
      const data = await Api.get(
        `/api/analysis/store/${storeId}?category_id=${categoryId}`
      );
      setHidden(loading, true);
      text.textContent = data.advice;
      setHidden(text, false);
    } catch (err) {
      showLoadError(loading, "分析を取得できませんでした: " + err.message);
    }
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }
})();
