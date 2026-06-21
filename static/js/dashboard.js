/**
 * 棚を見る — 2セクション → カテゴリ内一覧
 */
function toJST(dateStr) {
  const date = new Date(dateStr);
  return date.toLocaleTimeString("ja-JP", {
    timeZone: "Asia/Tokyo",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function toJSTDateTime(dateStr) {
  const date = new Date(dateStr);
  return date.toLocaleString("ja-JP", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

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

  function renderRareBadge(item, size = "11px") {
    if (!item.is_rare) return "";
    return `<span class="rare-badge" title="この店舗にしかない希少商品です">
      <i class="ti ti-star-filled" style="font-size:${size};" aria-hidden="true"></i>
      希少
    </span>`;
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
    const rareHtml = renderRareBadge(item);

    const unit = item.unit || "本";
    const std = item.standard_stock;
    const stdHtml =
      std != null && std !== undefined && std !== 0
        ? `<span class="stock-std">標準 ${std}本</span>`
        : `<span class="stock-std stock-std-unset">未設定</span>`;

    const orderedQty = item.ordered_quantity ?? 0;
    const orderingBadge =
      item.ordered_quantity && item.ordered_quantity > 0
        ? `<span class="ordering-badge">発注中 ${item.ordered_quantity}${escapeHtml(unit)}</span>`
        : "";

    const warningStock = item.warning_threshold ?? item.warning_stock;
    const criticalStock = item.critical_threshold ?? item.critical_stock;
    const thresholdHtml =
      warningStock || criticalStock
        ? `
<div class="alert-threshold-row">
  ${
    warningStock
      ? `<span class="threshold-badge threshold-warn">要発注 ${warningStock}本以下</span>`
      : ""
  }
  ${
    criticalStock
      ? `<span class="threshold-badge threshold-crit">至急 ${criticalStock}本以下</span>`
      : ""
  }
</div>`
        : "";

    return `
      <div class="product-card ${status.card}">
        <span class="status-badge ${status.badge}">${status.label}</span>
        ${chipHtml}
        ${rareHtml}
        <p class="product-name">${escapeHtml(item.product_name)}</p>
        <div class="card-divider"></div>
        <div class="stock-row">
          <span class="stock-num">${item.quantity}</span>
          <span class="stock-unit">${escapeHtml(unit)}</span>
          ${stdHtml}
        </div>
        ${thresholdHtml}
        ${orderingBadge}
      </div>`;
  }

  function setHidden(el, hidden) {
    if (el) el.hidden = hidden;
  }

  function isDetailView() {
    return viewDetail && !viewDetail.hidden;
  }

  const ORDER_PDF_DEFAULT_LABEL = "発注表一覧を作成";
  let orderingShelfId = null;

  function renderOrderingItems(items) {
    return items
      .map(
        (item) => `
    <div class="ordering-item-row" data-product-id="${item.product_id}"
      data-is-rare="${item.is_rare ? "true" : "false"}">
      <label class="ordering-item-label">
        <input type="checkbox" class="ordering-check" value="${item.product_id}" checked>
        <span class="ordering-item-name">
          ${escapeHtml(item.product_name)}
          ${
            item.brand_name
              ? `<span class="brand-pill ordering-brand-pill">${escapeHtml(item.brand_name)}</span>`
              : ""
          }
          ${renderRareBadge(item, "10px")}
        </span>
        <span class="ordering-item-needed">必要: ${item.needed}本</span>
        <input type="number" class="ordering-qty input-number" value="${item.needed}" min="0" max="999" inputmode="numeric">
      </label>
    </div>`
      )
      .join("");
  }

  function openOrderingModal() {
    const modal = $("ordering-modal");
    if (modal) {
      modal.hidden = false;
      document.body.style.overflow = "hidden";
    }
  }

  function closeOrderingModal() {
    const modal = $("ordering-modal");
    if (modal) {
      modal.hidden = true;
      document.body.style.overflow = "";
    }
    orderingShelfId = null;
    const body = $("ordering-modal-body");
    if (body) body.innerHTML = "";
  }

  async function showOrderingModal(shelfId, shelfName) {
    const storeId = getStoreId();
    if (!storeId) {
      alert("店舗を選択してください。");
      return;
    }
    orderingShelfId = shelfId;
    const title = $("ordering-modal-title");
    if (title) title.textContent = `発注中に登録 — ${shelfName}`;
    const body = $("ordering-modal-body");
    if (body) body.innerHTML = '<p class="loading">読み込み中…</p>';
    openOrderingModal();

    try {
      const items = await Api.get(
        `/api/ordering-items/candidates?store_id=${encodeURIComponent(storeId)}&shelf_id=${encodeURIComponent(shelfId)}`
      );
      if (!body) return;
      if (!items.length) {
        body.innerHTML =
          '<p class="empty-msg">黄アラート以下で発注が必要な商品はありません</p>';
        return;
      }
      body.innerHTML = renderOrderingItems(items);
    } catch (err) {
      if (body) body.innerHTML = `<p class="error-msg">${escapeHtml(err.message)}</p>`;
    }
  }

  async function saveOrderingItems() {
    const storeId = getStoreId();
    if (!storeId) {
      alert("店舗を選択してください。");
      return;
    }

    const checkedRows = document.querySelectorAll(
      ".ordering-item-row .ordering-check:checked"
    );
    const rareItems = [];
    checkedRows.forEach((cb) => {
      const row = cb.closest(".ordering-item-row");
      if (row?.dataset.isRare === "true") {
        const name =
          row.querySelector(".ordering-item-name")?.textContent.trim() ||
          row.textContent.trim();
        rareItems.push(name);
      }
    });

    if (rareItems.length > 0) {
      const confirmed = confirm(
        `以下の商品には希少バッジが付いています。\n` +
          `この店舗にしかない商品のため、在庫切れすると補充できません。\n\n` +
          `${rareItems.join("\n")}\n\n` +
          `個数の数は確認済みですか？\nよろしければOKを押してください。`
      );
      if (!confirmed) return;
    }

    const rows = [...document.querySelectorAll(".ordering-item-row")];
    const items = [];
    rows.forEach((row) => {
      const cb = row.querySelector(".ordering-check");
      if (!cb?.checked) return;
      const qty = parseInt(row.querySelector(".ordering-qty")?.value, 10) || 0;
      if (qty <= 0) return;
      items.push({
        product_id: parseInt(row.dataset.productId, 10),
        ordered_quantity: qty,
      });
    });
    if (!items.length) {
      alert("発注数を入力した商品を1つ以上選択してください。");
      return;
    }
    try {
      await Api.post("/api/ordering-items", { store_id: storeId, items });
      closeOrderingModal();
      if (isDetailView()) await loadCategoryDetail();
      else await loadCategoryCards();
      alert("発注中を登録しました");
    } catch (err) {
      alert(err.message || "登録に失敗しました");
    }
  }

  function bindOrderingButtons() {
    document.addEventListener("click", (e) => {
      const btn = e.target.closest(".btn-ordering");
      if (!btn) return;
      showOrderingModal(btn.dataset.shelfId, btn.dataset.shelfName || "棚");
    });
    $("ordering-modal-close")?.addEventListener("click", closeOrderingModal);
    $("ordering-modal-cancel")?.addEventListener("click", closeOrderingModal);
    $("ordering-modal-save")?.addEventListener("click", saveOrderingItems);
    $("ordering-modal")?.addEventListener("click", (e) => {
      if (e.target.id === "ordering-modal") closeOrderingModal();
    });
  }

  function bindOrderPdfButtons() {
    document.addEventListener("click", async (e) => {
      const btn = e.target.closest(".btn-order-pdf");
      if (!btn || btn.classList.contains("ready")) return;

      const shelfId = btn.dataset.shelfId;
      const storeId = getStoreId();
      if (!storeId) {
        alert("店舗を選択してください。");
        return;
      }
      if (!shelfId) return;

      btn.textContent = "作成中...";
      btn.disabled = true;

      try {
        const html = await Api.post(
          `/api/orders/create-pdf?store_id=${encodeURIComponent(storeId)}&shelf_id=${encodeURIComponent(shelfId)}`
        );
        if (typeof html !== "string" || !html.trim()) {
          throw new Error("発注表の取得に失敗しました");
        }
        const blob = new Blob([html], { type: "text/html;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        window.open(url, "_blank");
        setTimeout(() => URL.revokeObjectURL(url), 60000);
        btn.textContent = "ダウンロード";
        btn.disabled = false;
        btn.classList.add("ready");
      } catch (err) {
        btn.textContent = "作成失敗";
        setTimeout(() => {
          btn.textContent = ORDER_PDF_DEFAULT_LABEL;
          btn.disabled = false;
          btn.classList.remove("ready");
        }, 3000);
        console.error(err);
      }
    });
  }

  async function init() {
    $("btn-refresh")?.addEventListener("click", onRefresh);
    $("btn-back-categories")?.addEventListener("click", showCategories);
    bindOrderPdfButtons();
    bindOrderingButtons();
    bindProductNameFilter();
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
        resetProductNameFilters();
        openCategory(parseInt(card.dataset.id, 10), card.dataset.name);
      });
    });
  }

  function resetProductNameFilters() {
    document.querySelectorAll(".product-name-filter").forEach((el) => {
      el.value = "";
      el.dispatchEvent(new Event("input"));
    });
  }

  function bindProductNameFilter() {
    document.addEventListener("input", (e) => {
      if (!e.target.classList.contains("product-name-filter")) return;
      const keyword = e.target.value.trim().toLowerCase();
      const section = e.target.closest(".category-product-section");
      if (!section) return;
      const cards = section.querySelectorAll(".product-card");
      let visibleCount = 0;
      cards.forEach((card) => {
        const name =
          card.querySelector(".product-name")?.textContent.toLowerCase() || "";
        const brand =
          card.querySelector(".brand-pill")?.textContent.toLowerCase() || "";
        if (!keyword || name.includes(keyword) || brand.includes(keyword)) {
          card.style.display = "";
          visibleCount++;
        } else {
          card.style.display = "none";
        }
      });
      const emptyMsg = section.querySelector(".filter-empty-msg");
      if (emptyMsg) {
        emptyMsg.style.display = visibleCount === 0 ? "block" : "none";
      }
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
          <div class="shelf-title-row">
            <h2 class="shelf-title">${escapeHtml(sec.section_name)}</h2>
            <div class="shelf-actions">
              <button
                type="button"
                class="btn-order-pdf"
                data-shelf-id="${sec.section_id}"
                data-shelf-name="${escapeHtml(sec.section_name)}">
                発注表一覧を作成
              </button>
              <button
                type="button"
                class="btn-ordering"
                data-shelf-id="${sec.section_id}"
                data-shelf-name="${escapeHtml(sec.section_name)}">
                発注中に登録
              </button>
            </div>
          </div>
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

      const filterInput = document.querySelector(".product-name-filter");
      if (filterInput?.value) {
        filterInput.dispatchEvent(new Event("input"));
      }
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

  function refreshDashboardInventory() {
    const storeId = getStoreId();
    if (!storeId) return Promise.resolve();
    if (currentCategoryId) {
      return loadInventory(storeId, currentCategoryId);
    }
    return loadCategoryCards();
  }

  window.loadInventory = refreshDashboardInventory;

  window.addEventListener("storage", (e) => {
    if (e.key !== "akemin:ordering-delivered" || !e.newValue) return;
    refreshDashboardInventory();
  });

  window.addEventListener("pageshow", (e) => {
    if (!e.persisted) return;
    refreshDashboardInventory();
  });
})();
