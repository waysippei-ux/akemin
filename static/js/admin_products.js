/**
 * 管理者 — 商品管理
 */
(function () {
  let products = [];
  let categories = [];
  let editingId = null;

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
          document.querySelectorAll("[data-admin-tab]").forEach((b) => b.classList.toggle("active", b === btn));
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
    categories = await Api.get("/api/categories");
    const makers = await Api.get("/api/makers");
    const dealers = await Api.get("/api/dealers");
    const catSel = document.getElementById("category_id");
    catSel.innerHTML = categories.map((c) => `<option value="${c.id}">${c.name}</option>`).join("");
    fillOptional("maker_id", makers);
    fillOptional("dealer_id", dealers);
  }

  function fillOptional(id, items) {
    const el = document.getElementById(id);
    el.innerHTML = '<option value="">—</option>' + items.map((i) => `<option value="${i.id}">${i.name}</option>`).join("");
  }

  function bindProductEvents() {
    document.getElementById("product-form").addEventListener("submit", onSave);
    document.getElementById("btn-cancel").addEventListener("click", resetForm);
    document.getElementById("btn-import-csv").addEventListener("click", onImportCsv);
    document.getElementById("btn-csv-template").addEventListener("click", downloadTemplate);
  }

  function getFormData() {
    const maker = document.getElementById("maker_id").value;
    const dealer = document.getElementById("dealer_id").value;
    const jan = document.getElementById("jan_code").value.trim();
    return {
      name: document.getElementById("name").value.trim(),
      barcode: document.getElementById("barcode").value.trim(),
      jan_code: jan || null,
      category_id: parseInt(document.getElementById("category_id").value, 10),
      unit: document.getElementById("unit").value.trim() || "本",
      warning_threshold: parseInt(document.getElementById("warning_threshold").value, 10),
      critical_threshold: parseInt(document.getElementById("critical_threshold").value, 10),
      maker_id: maker ? parseInt(maker, 10) : null,
      dealer_id: dealer ? parseInt(dealer, 10) : null,
    };
  }

  async function loadProducts() {
    const loading = document.getElementById("products-loading");
    const wrap = document.getElementById("table-wrap");
    loading.hidden = false;
    wrap.hidden = true;
    products = await Api.get("/api/products");
    loading.hidden = true;
    document.getElementById("product-count").textContent = `(${products.length})`;
    document.getElementById("products-tbody").innerHTML = products
      .map(
        (p) => `
      <tr>
        <td data-label="商品名">${esc(p.name)}</td>
        <td data-label="コード"><code>${esc(p.barcode)}</code>${p.jan_code ? `<br><small>納品:${esc(p.jan_code)}</small>` : ""}</td>
        <td data-label="カテゴリ">${esc(p.category_name || "")}</td>
        <td data-label="閾値">${p.warning_threshold}/${p.critical_threshold}</td>
        <td class="cell-actions">
          <button type="button" class="btn btn-ghost btn-sm" data-edit="${p.id}">編集</button>
          <button type="button" class="btn btn-ghost btn-sm" data-del="${p.id}">削除</button>
        </td>
      </tr>`
      )
      .join("");
    wrap.hidden = false;
    document.querySelectorAll("[data-edit]").forEach((b) =>
      b.addEventListener("click", () => startEdit(+b.dataset.edit))
    );
    document.querySelectorAll("[data-del]").forEach((b) =>
      b.addEventListener("click", () => onDelete(+b.dataset.del))
    );
  }

  async function startEdit(id) {
    const p = products.find((x) => x.id === id) || (await Api.get(`/api/products/${id}`));
    editingId = id;
    document.getElementById("product-id").value = id;
    document.getElementById("name").value = p.name;
    document.getElementById("barcode").value = p.barcode;
    document.getElementById("jan_code").value = p.jan_code || "";
    document.getElementById("category_id").value = p.category_id;
    document.getElementById("maker_id").value = p.maker_id || "";
    document.getElementById("dealer_id").value = p.dealer_id || "";
    document.getElementById("unit").value = p.unit;
    document.getElementById("warning_threshold").value = p.warning_threshold;
    document.getElementById("critical_threshold").value = p.critical_threshold;
    document.getElementById("form-title").textContent = "商品を編集";
    document.getElementById("btn-cancel").hidden = false;
  }

  function resetForm() {
    editingId = null;
    document.getElementById("product-form").reset();
    document.getElementById("unit").value = "本";
    document.getElementById("warning_threshold").value = "4";
    document.getElementById("critical_threshold").value = "2";
    if (categories.length) document.getElementById("category_id").value = categories[0].id;
    document.getElementById("form-title").textContent = "商品を追加";
    document.getElementById("btn-cancel").hidden = true;
    document.getElementById("form-error").hidden = true;
  }

  async function onSave(e) {
    e.preventDefault();
    const err = document.getElementById("form-error");
    err.hidden = true;
    const data = getFormData();
    if (data.critical_threshold > data.warning_threshold) {
      err.textContent = "危険閾値は警告閾値以下にしてください。";
      err.hidden = false;
      return;
    }
    try {
      if (editingId) await Api.put(`/api/products/${editingId}`, data);
      else await Api.post("/api/products", data);
      resetForm();
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
    if (editingId === id) resetForm();
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
      "name,barcode,unit,warning_threshold,critical_threshold,category_id,jan_code," +
      "delivery_code_1,dealer_id_1,delivery_code_2,dealer_id_2,delivery_code_3,dealer_id_3," +
      "delivery_code_4,dealer_id_4,delivery_code_5,dealer_id_5";
    const csv =
      header +
      "\nサンプル,4901001000099,本,4,2,1,DL001,DL001,1,DL002,2,,,,,\n";
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = "products_template.csv";
    a.click();
  }

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s ?? "";
    return d.innerHTML;
  }
})();
