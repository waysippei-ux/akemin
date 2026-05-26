/**
 * 管理者 — マスタ管理 & 設定
 */
(function () {
  let products = [];
  let categories = [];
  let makers = [];
  let dealers = [];
  let adminStores = [];
  let editingId = null;
  let modalJanCode = null;

  document.addEventListener("DOMContentLoaded", async () => {
    try {
      const user = await Api.get("/api/auth/me");
      if (user.role !== "admin") {
        document.getElementById("admin-denied").hidden = false;
        return;
      }
      document.getElementById("admin-content").hidden = false;
      window.dispatchEvent(new Event("admin-ready"));
      await loadMasters();
      bindProductEvents();
      await loadProducts();
      document.querySelectorAll("[data-admin-tab]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const tab = btn.dataset.adminTab;
          document.querySelectorAll("[data-admin-tab]").forEach((b) =>
            b.classList.toggle("active", b === btn)
          );
          document.querySelectorAll(".admin-tab-panel").forEach((p) => {
            p.hidden = p.id !== `admin-tab-${tab}`;
          });
        });
      });
    } catch (e) {
      document.getElementById("admin-denied").textContent = e.message;
      document.getElementById("admin-denied").hidden = false;
    }
  });

  async function loadMasters() {
    [categories, makers, dealers, adminStores] = await Promise.all([
      Api.get("/api/categories"),
      Api.get("/api/makers"),
      Api.get("/api/dealers"),
      Api.get("/api/stores"),
    ]);
    document.getElementById("modal-category_id").innerHTML = categories
      .map((c) => `<option value="${c.id}">${c.name}</option>`)
      .join("");
    fillOptional("modal-maker_id", makers);
    fillOptional("modal-dealer_id", dealers);
    populateProductFilterSelects();
    renderStorePickList([]);
    document.getElementById("modal-expand-all-stores")?.addEventListener("change", onExpandAllChange);
  }

  function populateProductFilterSelects() {
    fillFilterSelect(
      "product-filter-category",
      categories.map((c) => ({ id: c.id, name: c.name }))
    );
    fillFilterSelect(
      "product-filter-maker",
      makers.map((m) => ({ id: m.id, name: m.name }))
    );
    fillFilterSelect(
      "product-filter-dealer",
      dealers.map((d) => ({ id: d.id, name: d.name }))
    );
  }

  function fillFilterSelect(elId, items) {
    const el = document.getElementById(elId);
    if (!el) return;
    const prev = el.value;
    el.innerHTML =
      '<option value="">すべて</option>' +
      items.map((i) => `<option value="${i.id}">${esc(i.name)}</option>`).join("");
    if ([...el.options].some((o) => o.value === prev)) el.value = prev;
    else el.value = "";
  }

  function getFilteredProducts() {
    const catId = document.getElementById("product-filter-category")?.value || "";
    const makerId = document.getElementById("product-filter-maker")?.value || "";
    const dealerId = document.getElementById("product-filter-dealer")?.value || "";
    const nameQ = (document.getElementById("product-filter-name")?.value || "")
      .trim()
      .toLowerCase();

    return products.filter((p) => {
      if (catId && String(p.category_id) !== catId) return false;
      if (makerId && String(p.maker_id || "") !== makerId) return false;
      if (dealerId && String(p.dealer_id || "") !== dealerId) return false;
      if (nameQ && !(p.name || "").toLowerCase().includes(nameQ)) return false;
      return true;
    });
  }

  function updateProductFilterCount(shown, total) {
    const el = document.getElementById("product-filter-count");
    if (!el) return;
    if (shown === total) {
      el.textContent = `全 ${total} 件を表示`;
    } else {
      el.textContent = `${total}件中 ${shown}件表示`;
    }
  }

  function applyProductFilters() {
    const filtered = getFilteredProducts();
    renderProductsTable(filtered);
    updateProductFilterCount(filtered.length, products.length);
  }

  function resetProductFilters() {
    const ids = [
      "product-filter-category",
      "product-filter-maker",
      "product-filter-dealer",
    ];
    ids.forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.value = "";
    });
    const nameEl = document.getElementById("product-filter-name");
    if (nameEl) nameEl.value = "";
    applyProductFilters();
  }

  function fillOptional(id, items) {
    const el = document.getElementById(id);
    el.innerHTML =
      '<option value="">—</option>' +
      items.map((i) => `<option value="${i.id}">${i.name}</option>`).join("");
  }

  function onExpandAllChange() {
    const expandAll = document.getElementById("modal-expand-all-stores").checked;
    const list = document.getElementById("modal-store-pick-list");
    if (list) list.hidden = expandAll;
  }

  function renderStorePickList(selectedIds) {
    const list = document.getElementById("modal-store-pick-list");
    if (!list) return;
    const selected = new Set(selectedIds || []);
    list.innerHTML = adminStores
      .map(
        (s) => `
      <label class="store-pick-item">
        <input type="checkbox" class="modal-store-cb" value="${s.id}" ${
          selected.has(s.id) ? "checked" : ""
        }>
        ${esc(s.name)}
      </label>`
      )
      .join("");
  }

  function getDeployment() {
    const expandAll = document.getElementById("modal-expand-all-stores").checked;
    const storeIds = expandAll
      ? []
      : [...document.querySelectorAll(".modal-store-cb:checked")].map((cb) =>
          parseInt(cb.value, 10)
        );
    if (!expandAll && !storeIds.length) {
      throw new Error("展開する店舗を1つ以上選択してください。");
    }
    return { expand_all_stores: expandAll, store_ids: storeIds };
  }

  function bindProductEvents() {
    document.getElementById("btn-add-product")?.addEventListener("click", openAddModal);
    document.getElementById("btn-refresh-page")?.addEventListener("click", () => {
      window.location.reload();
    });
    document.getElementById("product-modal-form")?.addEventListener("submit", onModalSave);
    document.getElementById("product-modal-cancel")?.addEventListener("click", closeModal);
    document.getElementById("product-modal-close")?.addEventListener("click", closeModal);
    document.getElementById("product-modal")?.addEventListener("click", (e) => {
      if (e.target.id === "product-modal") closeModal();
    });
    document.getElementById("btn-import-csv")?.addEventListener("click", onImportCsv);
    document.getElementById("btn-csv-template")?.addEventListener("click", downloadTemplate);
    document.getElementById("product-filter-category")?.addEventListener("change", applyProductFilters);
    document.getElementById("product-filter-maker")?.addEventListener("change", applyProductFilters);
    document.getElementById("product-filter-dealer")?.addEventListener("change", applyProductFilters);
    document.getElementById("product-filter-name")?.addEventListener("input", applyProductFilters);
    document.getElementById("btn-product-filter-reset")?.addEventListener("click", resetProductFilters);
  }

  function getModalFormData() {
    const maker = document.getElementById("modal-maker_id").value;
    const dealer = document.getElementById("modal-dealer_id").value;
    return {
      name: document.getElementById("modal-name").value.trim(),
      barcode: document.getElementById("modal-barcode").value.trim(),
      jan_code: modalJanCode,
      category_id: parseInt(document.getElementById("modal-category_id").value, 10),
      unit: document.getElementById("modal-unit").value.trim() || "本",
      warning_threshold: parseInt(document.getElementById("modal-warning_threshold").value, 10),
      critical_threshold: parseInt(document.getElementById("modal-critical_threshold").value, 10),
      maker_id: maker ? parseInt(maker, 10) : null,
      dealer_id: dealer ? parseInt(dealer, 10) : null,
      deployment: getDeployment(),
    };
  }

  function openModal() {
    document.getElementById("product-modal").hidden = false;
    document.body.style.overflow = "hidden";
  }

  function closeModal() {
    document.getElementById("product-modal").hidden = true;
    document.body.style.overflow = "";
    editingId = null;
    modalJanCode = null;
    document.getElementById("modal-form-error").hidden = true;
  }

  function resetModalDefaults() {
    document.getElementById("modal-product-id").value = "";
    document.getElementById("modal-name").value = "";
    document.getElementById("modal-barcode").value = "";
    document.getElementById("modal-unit").value = "本";
    document.getElementById("modal-warning_threshold").value = "4";
    document.getElementById("modal-critical_threshold").value = "2";
    if (categories.length) document.getElementById("modal-category_id").value = categories[0].id;
    document.getElementById("modal-maker_id").value = "";
    document.getElementById("modal-dealer_id").value = "";
    modalJanCode = null;
    const expandAll = document.getElementById("modal-expand-all-stores");
    if (expandAll) {
      expandAll.checked = true;
      onExpandAllChange();
    }
    renderStorePickList(adminStores.map((s) => s.id));
  }

  function openAddModal() {
    editingId = null;
    modalJanCode = null;
    document.getElementById("product-modal-title").textContent = "商品を追加";
    resetModalDefaults();
    openModal();
  }

  async function openEditModal(id) {
    const p =
      products.find((x) => x.id === id) ||
      (await Api.get(`/api/products/${id}`));
    editingId = id;
    modalJanCode = p.jan_code || null;
    document.getElementById("product-modal-title").textContent = "商品を編集";
    document.getElementById("modal-product-id").value = id;
    document.getElementById("modal-name").value = p.name;
    document.getElementById("modal-barcode").value = p.barcode;
    document.getElementById("modal-category_id").value = p.category_id;
    document.getElementById("modal-maker_id").value = p.maker_id || "";
    document.getElementById("modal-dealer_id").value = p.dealer_id || "";
    document.getElementById("modal-unit").value = p.unit;
    document.getElementById("modal-warning_threshold").value = p.warning_threshold;
    document.getElementById("modal-critical_threshold").value = p.critical_threshold;
    const expandAll = document.getElementById("modal-expand-all-stores");
    if (expandAll) {
      expandAll.checked = p.expand_all_stores !== false;
      onExpandAllChange();
    }
    renderStorePickList(p.active_store_ids || []);
    openModal();
  }

  async function loadProducts() {
    const loading = document.getElementById("products-loading");
    const wrap = document.getElementById("table-wrap");
    loading.hidden = false;
    wrap.hidden = true;
    products = await Api.get("/api/products");
    loading.hidden = true;
    document.getElementById("product-count").textContent = `(${products.length})`;
    applyProductFilters();
    wrap.hidden = false;
  }

  function renderProductsTable(list) {
    const tbody = document.getElementById("products-tbody");
    if (!list.length) {
      tbody.innerHTML =
        '<tr><td colspan="6" class="empty-msg">該当する商品がありません</td></tr>';
      return;
    }
    tbody.innerHTML = list
      .map(
        (p) => `
      <tr>
        <td data-label="商品名">${esc(p.name)}</td>
        <td data-label="コード"><code>${esc(p.barcode)}</code>${p.jan_code ? `<br><small>納品:${esc(p.jan_code)}</small>` : ""}</td>
        <td data-label="カテゴリ">${esc(p.category_name || "")}</td>
        <td data-label="店舗">${esc(p.deployment_label || formatDeploymentFallback(p))}</td>
        <td data-label="閾値">${p.warning_threshold}/${p.critical_threshold}</td>
        <td class="cell-actions">
          <button type="button" class="btn btn-ghost btn-sm" data-edit="${p.id}">編集</button>
          <button type="button" class="btn btn-ghost btn-sm" data-del="${p.id}">削除</button>
        </td>
      </tr>`
      )
      .join("");
    tbody.querySelectorAll("[data-edit]").forEach((b) =>
      b.addEventListener("click", () => openEditModal(+b.dataset.edit))
    );
    tbody.querySelectorAll("[data-del]").forEach((b) =>
      b.addEventListener("click", () => onDelete(+b.dataset.del))
    );
  }

  async function onModalSave(e) {
    e.preventDefault();
    const err = document.getElementById("modal-form-error");
    err.hidden = true;
    let data;
    try {
      data = getModalFormData();
    } catch (ex) {
      err.textContent = ex.message;
      err.hidden = false;
      return;
    }
    if (data.critical_threshold > data.warning_threshold) {
      err.textContent = "赤アラートは黄アラート以下にしてください。";
      err.hidden = false;
      return;
    }
    try {
      if (editingId) await Api.put(`/api/products/${editingId}`, data);
      else await Api.post("/api/products", data);
      closeModal();
      await loadProducts();
    } catch (ex) {
      err.textContent = ex.message;
      err.hidden = false;
    }
  }

  async function onDelete(id) {
    const p = products.find((x) => x.id === id);
    if (!p || !confirm(`「${p.name}」を削除しますか？`)) return;
    await Api.delete(`/api/products/${id}`);
    if (editingId === id) closeModal();
    await loadProducts();
  }

  async function onImportCsv() {
    const input = document.getElementById("csv-file");
    if (!input.files?.[0]) return alert("CSVを選択してください");
    const res = await Api.upload("/api/products/import/csv", input.files[0]);
    document.getElementById("import-result").hidden = false;
    document.getElementById("import-result").textContent = JSON.stringify(res, null, 2);
    await loadProducts();
  }

  function downloadTemplate() {
    const header =
      "name,barcode,unit,warning_threshold,critical_threshold,category_id,jan_code,stores," +
      "delivery_code_1,dealer_id_1,delivery_code_2,dealer_id_2,delivery_code_3,dealer_id_3," +
      "delivery_code_4,dealer_id_4,delivery_code_5,dealer_id_5";
    const csv =
      header +
      "\nサンプル,4901001000099,本,4,2,1,,all,DL001,1,,,,,,,\n";
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = "products_template.csv";
    a.click();
  }

  function formatDeploymentFallback(p) {
    if (p.expand_all_stores) return "全店舗";
    const names = p.active_store_names || [];
    if (!names.length) return "未配置";
    if (names.length === 1) return names[0];
    return `${names[0]} 他${names.length - 1}店舗`;
  }

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s ?? "";
    return d.innerHTML;
  }
})();
