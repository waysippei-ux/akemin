/**
 * 店舗別発注目安設定（管理者）
 */
(function () {
  let stores = [];
  let rows = [];

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
      await loadSettings();
    } catch (e) {
      document.getElementById("settings-denied").textContent = e.message;
      document.getElementById("settings-denied").hidden = false;
    }
  });

  async function loadSettings() {
    const storeId = document.getElementById("store-select").value;
    if (!storeId) return;
    const loading = document.getElementById("settings-loading");
    const wrap = document.getElementById("settings-table-wrap");
    loading.hidden = false;
    wrap.hidden = true;
    try {
      rows = await Api.get(`/api/stores/${storeId}/product-settings`);
      renderTable(storeId);
      loading.hidden = true;
      wrap.hidden = false;
    } catch (err) {
      loading.textContent = err.message;
    }
  }

  function renderTable(storeId) {
    const tbody = document.getElementById("settings-tbody");
    tbody.innerHTML = rows
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
    const warning = parseInt(tr.querySelector('[data-field="warning"]').value, 10);
    const critical = parseInt(tr.querySelector('[data-field="critical"]').value, 10);
    return { warning, critical };
  }

  async function saveRow(storeId, productId) {
    const { warning, critical } = getRowInputs(productId);
    if (critical > warning) {
      return alert("危険閾値（赤）は警告閾値（黄）以下にしてください。");
    }
    try {
      await Api.put(`/api/stores/${storeId}/product-settings/${productId}`, {
        warning_threshold: warning,
        critical_threshold: critical,
      });
      await loadSettings();
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
