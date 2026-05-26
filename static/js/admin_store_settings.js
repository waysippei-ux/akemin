/**
 * 店舗別発注目安設定（管理者）
 */
(function () {
  let stores = [];
  let rows = [];
  let currentStoreId = null;

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
      document.getElementById("filter-category")?.addEventListener("change", applyFilters);
      document.getElementById("filter-maker")?.addEventListener("change", applyFilters);
      document.getElementById("filter-dealer")?.addEventListener("change", applyFilters);
      document.getElementById("filter-name")?.addEventListener("input", applyFilters);
      document.getElementById("btn-filter-reset")?.addEventListener("click", resetFilters);
      await loadSettings();
    } catch (e) {
      document.getElementById("settings-denied").textContent = e.message;
      document.getElementById("settings-denied").hidden = false;
    }
  });

  function resetFilters() {
    document.getElementById("filter-category").value = "";
    document.getElementById("filter-maker").value = "";
    document.getElementById("filter-dealer").value = "";
    document.getElementById("filter-name").value = "";
    applyFilters();
  }

  function populateFilterOptions() {
    const categories = uniqueSorted(rows, "category_id", "category_name");
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

    fillFilterSelect("filter-category", categories);
    fillFilterSelect("filter-maker", makers);
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
    const catId = document.getElementById("filter-category").value;
    const makerId = document.getElementById("filter-maker").value;
    const dealerId = document.getElementById("filter-dealer").value;
    const nameQ = document.getElementById("filter-name").value.trim().toLowerCase();

    return rows.filter((r) => {
      if (catId && String(r.category_id) !== catId) return false;
      if (makerId && String(r.maker_id) !== makerId) return false;
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
    renderTable(currentStoreId, filtered);
    updateFilterCount(filtered.length, rows.length);
  }

  async function loadSettings() {
    const storeId = document.getElementById("store-select").value;
    if (!storeId) return;
    currentStoreId = storeId;
    const loading = document.getElementById("settings-loading");
    const wrap = document.getElementById("settings-table-wrap");
    loading.hidden = false;
    wrap.hidden = true;
    try {
      rows = await Api.get(`/api/stores/${storeId}/product-settings`);
      populateFilterOptions();
      resetFilters();
      loading.hidden = true;
      wrap.hidden = false;
    } catch (err) {
      loading.textContent = err.message;
    }
  }

  function renderTable(storeId, list) {
    const tbody = document.getElementById("settings-tbody");
    if (!list.length) {
      tbody.innerHTML =
        '<tr><td colspan="7" class="empty-msg">該当する商品がありません</td></tr>';
      return;
    }
    tbody.innerHTML = list
      .map((r) => {
        const customBadge = r.has_custom_setting
          ? '<span class="badge-pill badge-yellow">店舗設定</span>'
          : '<span class="badge-pill">デフォルト</span>';
        const warnVal =
          r.custom_warning_threshold != null
            ? r.custom_warning_threshold
            : r.default_warning_threshold;
        const critVal =
          r.custom_critical_threshold != null
            ? r.custom_critical_threshold
            : r.default_critical_threshold;
        return `
        <tr data-product-id="${r.product_id}">
          <td data-label="商品名">${esc(r.product_name)}</td>
          <td data-label="カテゴリ">${esc(r.category_name)}</td>
          <td data-label="デフォルト">${r.default_warning_threshold} / ${r.default_critical_threshold}</td>
          <td data-label="適用中">${r.effective_warning_threshold} / ${r.effective_critical_threshold} ${customBadge}</td>
          <td data-label="黄 ≤">
            <input type="number" class="input-number input-sm" min="0"
              data-field="warning" value="${warnVal}">
          </td>
          <td data-label="赤 ≤">
            <input type="number" class="input-number input-sm" min="0"
              data-field="critical" value="${critVal}">
          </td>
          <td class="cell-actions">
            <button type="button" class="btn btn-primary btn-sm" data-save="${r.product_id}">保存</button>
            ${
              r.has_custom_setting
                ? `<button type="button" class="btn btn-ghost btn-sm" data-reset="${r.product_id}">デフォルトに戻す</button>`
                : ""
            }
          </td>
        </tr>`;
      })
      .join("");

    tbody.querySelectorAll("[data-save]").forEach((btn) => {
      btn.addEventListener("click", () => saveRow(storeId, +btn.dataset.save));
    });
    tbody.querySelectorAll("[data-reset]").forEach((btn) => {
      btn.addEventListener("click", () => resetRow(storeId, +btn.dataset.reset));
    });
  }

  function getRowInputs(productId) {
    const tr = document.querySelector(`tr[data-product-id="${productId}"]`);
    if (!tr) return null;
    const warning = parseInt(tr.querySelector('[data-field="warning"]').value, 10);
    const critical = parseInt(tr.querySelector('[data-field="critical"]').value, 10);
    return { warning, critical };
  }

  function syncRowFromInputs(productId, warning, critical) {
    const row = rows.find((r) => r.product_id === productId);
    if (!row) return;
    row.custom_warning_threshold = warning;
    row.custom_critical_threshold = critical;
    row.has_custom_setting = true;
    row.effective_warning_threshold = warning;
    row.effective_critical_threshold = critical;
  }

  async function saveRow(storeId, productId) {
    const inputs = getRowInputs(productId);
    if (!inputs) return;
    const { warning, critical } = inputs;
    if (critical > warning) {
      return alert("危険閾値（赤）は警告閾値（黄）以下にしてください。");
    }
    try {
      const updated = await Api.put(`/api/stores/${storeId}/product-settings/${productId}`, {
        warning_threshold: warning,
        critical_threshold: critical,
      });
      const idx = rows.findIndex((r) => r.product_id === productId);
      if (idx >= 0) rows[idx] = { ...rows[idx], ...updated };
      applyFilters();
    } catch (err) {
      alert(err.message);
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
