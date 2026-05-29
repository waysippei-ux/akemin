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

  document.addEventListener("DOMContentLoaded", init);

  function displayBrand(item) {
    const brand = (item.brand_name || "").trim();
    if (brand) return brand;
    return (item.maker_name || "").trim();
  }

  function cardStatus(item) {
    const qty = item.quantity ?? 0;
    const critical = item.critical_threshold ?? 0;
    const warning = item.warning_threshold ?? 0;
    if (qty <= critical) {
      return { card: "card-crit", badge: "badge-crit", label: "至急", sort: 0 };
    }
    if (qty <= warning) {
      return { card: "card-warn", badge: "badge-warn", label: "要発注", sort: 1 };
    }
    return { card: "card-ok", badge: "badge-ok", label: "十分", sort: 2 };
  }

  function renderInventoryCard(item) {
    const status = cardStatus(item);
    const brand = displayBrand(item);
    const chipHtml = brand ? `<span class="brand-pill">${escapeHtml(brand)}</span>` : "";

    const std = item.standard_stock ?? 0;
    const unit = item.unit || "本";
    const stdHtml = std
      ? `<span class="stock-std">標準 ${std}${escapeHtml(unit)}</span>`
      : "";

    return `
      <div class="product-card ${status.card}">
        <span class="status-badge ${status.badge}">${status.label}</span>
        ${chipHtml}
        <p class="product-name">${escapeHtml(item.product_name)}</p>
        <div class="card-divider"></div>
        <div class="stock-row">
          <span class="stock-num">${item.quantity}</span>
          <span class="stock-unit">${escapeHtml(unit)}</span>
          ${stdHtml}
        </div>
      </div>`;
  }

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
    const container = $("dashboard-sections");

    setHidden(loading, false);
    if (loading) loading.textContent = "読み込み中…";
    if (container) container.innerHTML = "";

    try {
      const data = await Api.get(`/api/dashboard/sections?store_id=${getStoreId()}`);
      setHidden(loading, true);

      if (!container) return;
      const sections = data.sections || [];
      if (!sections.length) {
        container.innerHTML = '<p class="empty-msg">棚がありません</p>';
        return;
      }

      container.innerHTML = sections
        .map((sec) => {
          const cards = sec.categories.length
            ? sec.categories.map(renderCard).join("")
            : '<p class="empty-msg">カテゴリがありません</p>';
          return `
        <section class="dashboard-section" style="background:${escapeHtml(sec.color)}">
          <h2 class="section-heading">${escapeHtml(sec.section_name)}</h2>
          <div class="category-cards" data-section-id="${sec.section_id}">${cards}</div>
        </section>`;
        })
        .join("");

      container.querySelectorAll(".category-cards").forEach((el) => bindCards(el));
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
      items.sort(
        (a, b) =>
          cardStatus(a).sort - cardStatus(b).sort ||
          a.product_name.localeCompare(b.product_name, "ja")
      );

      list.innerHTML = items.length
        ? items.map((item) => renderInventoryCard(item)).join("")
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
