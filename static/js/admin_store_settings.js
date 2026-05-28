/**
 * 店舗別発注目安設定（管理者）
 */
(function () {
  let stores = [];
  let sections = [];
  let categories = [];
  let brands = [];
  let rows = [];
  let currentStoreId = null;
  let currentStoreName = "";
  let filtersReady = false;
  let editingRow = null;
  const SETTING_IDS = {
    standardStock: "setting-edit-standard-stock",
    warning: "setting-edit-warning",
    critical: "setting-edit-critical",
  };

  document.addEventListener("DOMContentLoaded", async () => {
    try {
      const user = await Api.get("/api/auth/me");
      if (user.role !== "admin") {
        document.getElementById("settings-denied").hidden = false;
        return;
      }
      document.getElementById("settings-content").hidden = false;
      stores = await Api.get("/api/stores/all");
      const sel = document.getElementById("store-select");
      sel.innerHTML = stores
        .filter((s) => s.is_active)
        .map((s) => `<option value="${s.id}">${s.name}</option>`)
        .join("");
      sel.addEventListener("change", loadSettings);
      document.getElementById("btn-reload")?.addEventListener("click", loadSettings);
      document.getElementById("btn-refresh-page")?.addEventListener("click", () => {
        window.location.reload();
      });
      [sections, categories, brands] = await Promise.all([
        Api.get("/api/sections"),
        Api.get("/api/categories"),
        Api.get("/api/brands"),
      ]);
      setupShelfFilter();
      setupMakerBrandFilter();
      document.getElementById("filter-section")?.addEventListener("change", onSectionFilterChange);
      document.getElementById("filter-brand")?.addEventListener("change", applyFilters);
      document.getElementById("filter-category")?.addEventListener("change", applyFilters);
      document.getElementById("filter-maker")?.addEventListener("change", applyFilters);
      document.getElementById("filter-dealer")?.addEventListener("change", applyFilters);
      document.getElementById("filter-name")?.addEventListener("input", applyFilters);
      document.getElementById("btn-filter-reset")?.addEventListener("click", resetFilters);

      bindEditModal();

      filtersReady = true;
      await loadSettings();
    } catch (e) {
      document.getElementById("settings-denied").textContent = e.message;
      document.getElementById("settings-denied").hidden = false;
    }
  });

  function bindEditModal() {
    document.getElementById("setting-edit-close")?.addEventListener("click", closeEditModal);
    document.getElementById("setting-edit-cancel")?.addEventListener("click", closeEditModal);
    document.getElementById("setting-edit-modal")?.addEventListener("click", (e) => {
      if (e.target.id === "setting-edit-modal") closeEditModal();
    });
    document.getElementById("setting-edit-form")?.addEventListener("submit", onSaveEditModal);
  }

  function setupShelfFilter() {
    const FH = window.FilterHelpers;
    if (!FH) return;
    FH.fillSectionSelect(document.getElementById("filter-section"), sections);
  }

  function setupMakerBrandFilter() {
    const FH = window.FilterHelpers;
    if (!FH) return;
    const makerEl = document.getElementById("filter-maker");
    const brandEl = document.getElementById("filter-brand");
    FH.fillBrandSelect(brandEl, brands, makerEl?.value || "");
    if (makerEl && !makerEl.dataset.brandBound) {
      makerEl.dataset.brandBound = "1";
      FH.bindMakerBrand(makerEl, brandEl, brands, applyFilters);
    }
  }

  function onSectionFilterChange() {
    const FH = window.FilterHelpers;
    const sectionId = document.getElementById("filter-section")?.value || "";
    if (FH) {
      const rowCats = uniqueSorted(rows, "category_id", "category_name");
      const filteredMaster = categories.filter(
        (c) => !sectionId || String(c.section) === String(sectionId)
      );
      const allowedIds = new Set(filteredMaster.map((c) => c.id));
      const list = rowCats.filter((c) => allowedIds.has(c.id));
      fillFilterSelect("filter-category", list);
    }
    applyFilters();
  }

  function resetFilters() {
    document.getElementById("filter-section").value = "";
    document.getElementById("filter-category").value = "";
    document.getElementById("filter-maker").value = "";
    document.getElementById("filter-brand").value = "";
    document.getElementById("filter-dealer").value = "";
    document.getElementById("filter-name").value = "";
    populateFilterOptions();
    applyFilters();
  }

  function populateFilterOptions() {
    const sectionId = document.getElementById("filter-section")?.value || "";
    let rowCats = uniqueSorted(rows, "category_id", "category_name");
    if (sectionId) {
      const allowed = new Set(
        categories.filter((c) => String(c.section) === String(sectionId)).map((c) => c.id)
      );
      rowCats = rowCats.filter((c) => allowed.has(c.id));
    }
    const makers = uniqueSorted(
      rows.filter((r) => r.maker_id),
      "maker_id",
      "maker_name"
    );
    const dealers = uniqueSorted(
      rows.filter((r) => r.dealer_id),
      "dealer_id",
      "dealer_name"
    );

    fillFilterSelect("filter-category", rowCats);
    fillFilterSelect("filter-maker", makers);
    const FH = window.FilterHelpers;
    if (FH) {
      FH.fillBrandSelect(
        document.getElementById("filter-brand"),
        brands,
        document.getElementById("filter-maker")?.value || ""
      );
    }
    fillFilterSelect("filter-dealer", dealers);
  }

  function uniqueSorted(list, idKey, nameKey) {
    const map = new Map();
    list.forEach((r) => {
      const id = r[idKey];
      if (id == null) return;
      map.set(id, r[nameKey] || String(id));
    });
    return [...map.entries()]
      .sort((a, b) => String(a[1]).localeCompare(String(b[1]), "ja"))
      .map(([id, name]) => ({ id, name }));
  }

  function fillFilterSelect(elId, items) {
    const el = document.getElementById(elId);
    const prev = el.value;
    el.innerHTML =
      '<option value="">すべて</option>' +
      items.map((i) => `<option value="${i.id}">${esc(i.name)}</option>`).join("");
    if ([...el.options].some((o) => o.value === prev)) el.value = prev;
    else el.value = "";
  }

  function getFilteredRows() {
    const sectionId = document.getElementById("filter-section")?.value || "";
    const catId = document.getElementById("filter-category").value;
    const makerId = document.getElementById("filter-maker").value;
    const brandId = document.getElementById("filter-brand").value;
    const dealerId = document.getElementById("filter-dealer").value;
    const nameQ = document.getElementById("filter-name").value.trim().toLowerCase();
    const FH = window.FilterHelpers;

    return rows.filter((r) => {
      if (sectionId && FH && !FH.matchesSection(r.category_id, sectionId, categories)) {
        return false;
      }
      if (catId && String(r.category_id) !== catId) return false;
      if (makerId && String(r.maker_id) !== makerId) return false;
      if (brandId && String(r.brand_id || "") !== brandId) return false;
      if (dealerId && String(r.dealer_id) !== dealerId) return false;
      if (nameQ && !(r.product_name || "").toLowerCase().includes(nameQ)) return false;
      return true;
    });
  }

  function updateFilterCount(shown, total) {
    const el = document.getElementById("filter-count");
    if (!el) return;
    if (shown === total) {
      el.textContent = `全 ${total} 件を表示`;
    } else {
      el.textContent = `${total}件中 ${shown}件表示`;
    }
  }

  function applyFilters() {
    if (!currentStoreId) return;
    const filtered = getFilteredRows();
    renderTable(filtered);
    updateFilterCount(filtered.length, rows.length);
  }

  async function loadSettings() {
    const storeId = document.getElementById("store-select").value;
    if (!storeId) return;
    currentStoreId = storeId;
    const store = stores.find((s) => String(s.id) === String(storeId));
    currentStoreName = store?.name || "";
    const loading = document.getElementById("settings-loading");
    const wrap = document.getElementById("settings-table-wrap");
    loading.hidden = false;
    wrap.hidden = true;
    try {
      rows = await Api.get(`/api/stores/${storeId}/product-settings`);
      populateFilterOptions();
      if (filtersReady) applyFilters();
      else resetFilters();
      loading.hidden = true;
      wrap.hidden = false;
    } catch (err) {
      loading.textContent = err.message;
    }
  }

  function renderStandardStockCell(r) {
    const unit = esc(r.unit || "本");
    if (r.custom_standard_stock != null) {
      return `<span class="standard-stock-badge standard-stock-store">📦 ${r.custom_standard_stock}${unit}</span>`;
    }
    const def = r.default_standard_stock ?? 0;
    if (def > 0) {
      return `<span class="standard-stock-badge standard-stock-default">📦 ${def}${unit}</span>`;
    }
    return '<span class="standard-stock-unset">未設定</span>';
  }

  function renderTable(list) {
    const tbody = document.getElementById("settings-tbody");
    if (!list.length) {
      tbody.innerHTML =
        '<tr><td colspan="5" class="empty-msg">該当する商品がありません</td></tr>';
      return;
    }
    tbody.innerHTML = list
      .map((r) => {
        const customBadge = r.has_custom_setting
          ? ' <span class="badge-pill badge-yellow">店舗</span>'
          : "";
        return `
        <tr data-product-id="${r.product_id}">
          <td data-label="商品名">${esc(r.product_name)}</td>
          <td data-label="標準在庫">${renderStandardStockCell(r)}</td>
          <td data-label="黄アラート">≤ ${r.effective_warning_threshold}${customBadge}</td>
          <td data-label="赤アラート">≤ ${r.effective_critical_threshold}${customBadge}</td>
          <td class="cell-actions">
            <button type="button" class="btn btn-ghost btn-sm" data-edit="${r.product_id}">編集</button>
            ${
              r.has_custom_setting
                ? `<button type="button" class="btn btn-ghost btn-sm" data-reset="${r.product_id}">デフォルトに戻す</button>`
                : ""
            }
          </td>
        </tr>`;
      })
      .join("");

    tbody.querySelectorAll("[data-edit]").forEach((btn) => {
      btn.addEventListener("click", () => openEditModal(+btn.dataset.edit));
    });
    tbody.querySelectorAll("[data-reset]").forEach((btn) => {
      btn.addEventListener("click", () => resetRow(currentStoreId, +btn.dataset.reset));
    });
  }

  async function openEditModal(productId) {
    const row = rows.find((r) => r.product_id === productId);
    if (!row || !currentStoreId) return;
    editingRow = row;

    document.getElementById("setting-edit-product-id").value = String(productId);
    document.getElementById("setting-edit-product-name").textContent = row.product_name || "";
    document.getElementById("setting-edit-store-name").textContent = `店舗：${currentStoreName}`;

    const err = document.getElementById("setting-edit-error");
    if (err) err.style.display = "none";

    const modal = document.getElementById("setting-edit-modal");
    if (modal) modal.style.display = "flex";

    try {
      const data = await StoreProductSettingsApi.fetchSetting(currentStoreId, productId);
      StoreProductSettingsApi.applyToForm(data, SETTING_IDS);
      const defStd = data.default_standard_stock ?? 0;
      const hint = document.getElementById("setting-edit-standard-hint");
      if (hint) {
        hint.textContent =
          defStd > 0
            ? `デフォルト: 商品マスタ ${defStd}${data.unit || "本"}`
            : "デフォルト: 商品マスタ未設定";
      }
    } catch (ex) {
      if (err) {
        err.textContent = ex.message || "設定を取得できませんでした";
        err.style.display = "block";
      }
    }
  }

  function closeEditModal() {
    const modal = document.getElementById("setting-edit-modal");
    if (modal) modal.style.display = "none";
    editingRow = null;
  }

  async function onSaveEditModal(e) {
    e.preventDefault();
    if (!currentStoreId || !editingRow) return;

    const err = document.getElementById("setting-edit-error");
    if (err) err.style.display = "none";

    const productId = parseInt(document.getElementById("setting-edit-product-id").value, 10);
    const warning = parseInt(document.getElementById("setting-edit-warning").value, 10);
    const critical = parseInt(document.getElementById("setting-edit-critical").value, 10);
    const stdRaw = document.getElementById("setting-edit-standard-stock").value.trim();

    if (critical > warning) {
      if (err) {
        err.textContent = "危険閾値（赤）は警告閾値（黄）以下にしてください。";
        err.style.display = "block";
      }
      return;
    }

    const current = {
      standard_stock: stdRaw === "" ? null : parseInt(stdRaw, 10),
      warning_threshold: warning,
      critical_threshold: critical,
    };
    const validateErr = StoreProductSettingsApi.validate(current);
    if (validateErr) {
      if (err) {
        err.textContent = validateErr;
        err.style.display = "block";
      }
      return;
    }

    try {
      await StoreProductSettingsApi.saveSetting(
        StoreProductSettingsApi.buildPutBody(currentStoreId, productId, current)
      );
      closeEditModal();
      await loadSettings();
    } catch (ex) {
      if (err) {
        err.textContent = ex.message || "保存できませんでした";
        err.style.display = "block";
      }
    }
  }

  async function resetRow(storeId, productId) {
    if (!confirm("この商品の店舗別設定を削除し、デフォルトに戻しますか？")) return;
    try {
      await Api.delete(`/api/stores/${storeId}/product-settings/${productId}`);
      await loadSettings();
    } catch (err) {
      alert(err.message);
    }
  }

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s ?? "";
    return d.innerHTML;
  }
})();
