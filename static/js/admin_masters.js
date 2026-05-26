/**
 * 管理者 — カテゴリ・ディーラー・メーカー・店舗・紐付け
 */
(function () {
  const SECTION_LABEL = { 1: "①材料", 2: "②販売" };

  let categoriesCache = [];
  let dealersCache = [];
  let makersCache = [];
  let storesCache = [];

  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("category-form")?.addEventListener("submit", saveCategoryNew);
    document.getElementById("dealer-form")?.addEventListener("submit", saveDealerNew);
    document.getElementById("maker-form")?.addEventListener("submit", saveMakerNew);
    document.getElementById("store-form")?.addEventListener("submit", saveStoreNew);
    document.getElementById("link-form")?.addEventListener("submit", saveLink);

    document.getElementById("category-edit-form")?.addEventListener("submit", saveCategoryEdit);
    document.getElementById("dealer-edit-form")?.addEventListener("submit", saveDealerEdit);
    document.getElementById("maker-edit-form")?.addEventListener("submit", saveMakerEdit);
    document.getElementById("store-edit-form")?.addEventListener("submit", saveStoreEdit);

    bindMasterModalClose();
    bindListDelegation();

    window.addEventListener("admin-ready", refreshMasters);
  });

  function bindMasterModalClose() {
    document.querySelectorAll(".master-modal-close").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.dataset.close;
        if (id) hideModal(id);
      });
    });
    [
      "category-edit-modal",
      "dealer-edit-modal",
      "maker-edit-modal",
      "store-edit-modal",
    ].forEach((id) => {
      document.getElementById(id)?.addEventListener("click", (e) => {
        if (e.target.id === id) hideModal(id);
      });
    });
  }

  function bindListDelegation() {
    document.getElementById("category-list")?.addEventListener("click", onCategoryListClick);
    document.getElementById("dealer-list")?.addEventListener("click", onDealerListClick);
    document.getElementById("maker-list")?.addEventListener("click", onMakerListClick);
    document.getElementById("store-list")?.addEventListener("click", onStoreListClick);
  }

  function showModal(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.hidden = false;
    el.style.display = "flex";
    document.body.style.overflow = "hidden";
  }

  function hideModal(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.hidden = true;
    el.style.display = "none";
    document.body.style.overflow = "";
    const err = el.querySelector(".error-msg");
    if (err) err.hidden = true;
  }

  function listActions(editLabel, deleteLabel) {
    return `<span class="master-list-actions">
      <button type="button" class="btn btn-ghost btn-sm" data-action="edit">${editLabel || "編集"}</button>
      <button type="button" class="btn btn-ghost btn-sm" data-action="delete">削除</button>
    </span>`;
  }

  async function refreshMasters() {
    await loadCategories();
    await loadDealers();
    await loadMakers();
    await loadStores();
    await loadLinks();
  }

  async function loadCategories() {
    categoriesCache = await Api.get("/api/categories?include_inactive=true");
    document.getElementById("category-list").innerHTML = categoriesCache
      .map((c) => {
        const sec = SECTION_LABEL[c.section] || c.section;
        return `<li data-id="${c.id}">
          <span class="master-list-label"><strong>${esc(c.name)}</strong> [${sec}] 順:${c.sort_order} ${c.is_active ? "" : "[無効]"}</span>
          ${listActions()}
        </li>`;
      })
      .join("");
  }

  function onCategoryListClick(e) {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const li = btn.closest("li[data-id]");
    if (!li) return;
    const id = parseInt(li.dataset.id, 10);
    const item = categoriesCache.find((c) => c.id === id);
    if (!item) return;
    if (btn.dataset.action === "edit") openCategoryModal(item);
    else if (btn.dataset.action === "delete") deleteCategory(item);
  }

  function openCategoryModal(c) {
    document.getElementById("edit-cat-id").value = c.id;
    document.getElementById("edit-cat-name").value = c.name;
    document.getElementById("edit-cat-section").value = String(c.section);
    showModal("category-edit-modal");
  }

  async function saveCategoryEdit(e) {
    e.preventDefault();
    const errEl = document.getElementById("category-edit-error");
    errEl.hidden = true;
    const id = parseInt(document.getElementById("edit-cat-id").value, 10);
    const current = categoriesCache.find((c) => c.id === id);
    if (!current) return;
    try {
      await Api.put(`/api/categories/${id}`, {
        name: document.getElementById("edit-cat-name").value.trim(),
        section: parseInt(document.getElementById("edit-cat-section").value, 10),
        sort_order: current.sort_order,
        is_active: current.is_active,
      });
      hideModal("category-edit-modal");
      await loadCategories();
      if (typeof window.loadMasters === "function") window.loadMasters();
    } catch (ex) {
      errEl.textContent = ex.message;
      errEl.hidden = false;
    }
  }

  async function deleteCategory(c) {
    if (!confirm("削除しますか？")) return;
    try {
      await Api.delete(`/api/categories/${c.id}`);
      window.location.reload();
    } catch (ex) {
      alert(ex.message);
    }
  }

  async function saveCategoryNew(e) {
    e.preventDefault();
    const body = {
      name: document.getElementById("cat-name").value.trim(),
      section: parseInt(document.getElementById("cat-section").value, 10),
      sort_order: parseInt(document.getElementById("cat-sort").value, 10) || 0,
      is_active: true,
    };
    await Api.post("/api/categories", body);
    e.target.reset();
    await loadCategories();
    if (typeof window.loadMasters === "function") window.loadMasters();
  }

  async function loadDealers() {
    dealersCache = await Api.get("/api/dealers/all");
    document.getElementById("dealer-list").innerHTML = dealersCache
      .map(
        (d) => `<li data-id="${d.id}">
          <span class="master-list-label">${esc(d.name)} ${esc(d.contact_info || "")} ${d.is_active ? "" : "[無効]"}</span>
          ${listActions()}
        </li>`
      )
      .join("");
    const sel = document.getElementById("link-dealer");
    if (sel) {
      sel.innerHTML = dealersCache
        .filter((d) => d.is_active)
        .map((d) => `<option value="${d.id}">${esc(d.name)}</option>`)
        .join("");
    }
  }

  function onDealerListClick(e) {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const li = btn.closest("li[data-id]");
    if (!li) return;
    const id = parseInt(li.dataset.id, 10);
    const item = dealersCache.find((d) => d.id === id);
    if (!item) return;
    if (btn.dataset.action === "edit") openDealerModal(item);
    else if (btn.dataset.action === "delete") deleteDealer(item);
  }

  function openDealerModal(d) {
    document.getElementById("edit-dealer-id").value = d.id;
    document.getElementById("edit-dealer-name").value = d.name;
    document.getElementById("edit-dealer-contact").value = d.contact_info || "";
    showModal("dealer-edit-modal");
  }

  async function saveDealerEdit(e) {
    e.preventDefault();
    const errEl = document.getElementById("dealer-edit-error");
    errEl.hidden = true;
    const id = parseInt(document.getElementById("edit-dealer-id").value, 10);
    const current = dealersCache.find((d) => d.id === id);
    try {
      await Api.put(`/api/dealers/${id}`, {
        name: document.getElementById("edit-dealer-name").value.trim(),
        contact_info: document.getElementById("edit-dealer-contact").value.trim() || null,
        is_active: current ? current.is_active : true,
      });
      hideModal("dealer-edit-modal");
      await loadDealers();
    } catch (ex) {
      errEl.textContent = ex.message;
      errEl.hidden = false;
    }
  }

  async function deleteDealer(d) {
    if (!confirm("削除しますか？")) return;
    try {
      await Api.delete(`/api/dealers/${d.id}`);
      window.location.reload();
    } catch (ex) {
      alert(ex.message);
    }
  }

  async function saveDealerNew(e) {
    e.preventDefault();
    await Api.post("/api/dealers", {
      name: document.getElementById("dealer-name").value.trim(),
      contact_info: document.getElementById("dealer-contact").value.trim() || null,
      is_active: true,
    });
    e.target.reset();
    await loadDealers();
  }

  async function loadMakers() {
    makersCache = await Api.get("/api/makers/all");
    document.getElementById("maker-list").innerHTML = makersCache
      .map(
        (m) => `<li data-id="${m.id}">
          <span class="master-list-label">${esc(m.name)} ${m.is_active ? "" : "[無効]"}</span>
          ${listActions()}
        </li>`
      )
      .join("");
    const sel = document.getElementById("link-maker");
    if (sel) {
      sel.innerHTML = makersCache
        .filter((m) => m.is_active)
        .map((m) => `<option value="${m.id}">${esc(m.name)}</option>`)
        .join("");
    }
  }

  function onMakerListClick(e) {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const li = btn.closest("li[data-id]");
    if (!li) return;
    const id = parseInt(li.dataset.id, 10);
    const item = makersCache.find((m) => m.id === id);
    if (!item) return;
    if (btn.dataset.action === "edit") openMakerModal(item);
    else if (btn.dataset.action === "delete") deleteMaker(item);
  }

  function openMakerModal(m) {
    document.getElementById("edit-maker-id").value = m.id;
    document.getElementById("edit-maker-name").value = m.name;
    showModal("maker-edit-modal");
  }

  async function saveMakerEdit(e) {
    e.preventDefault();
    const errEl = document.getElementById("maker-edit-error");
    errEl.hidden = true;
    const id = parseInt(document.getElementById("edit-maker-id").value, 10);
    const current = makersCache.find((m) => m.id === id);
    try {
      await Api.put(`/api/makers/${id}`, {
        name: document.getElementById("edit-maker-name").value.trim(),
        is_active: current ? current.is_active : true,
      });
      hideModal("maker-edit-modal");
      await loadMakers();
    } catch (ex) {
      errEl.textContent = ex.message;
      errEl.hidden = false;
    }
  }

  async function deleteMaker(m) {
    if (!confirm("削除しますか？")) return;
    try {
      await Api.delete(`/api/makers/${m.id}`);
      window.location.reload();
    } catch (ex) {
      alert(ex.message);
    }
  }

  async function saveMakerNew(e) {
    e.preventDefault();
    await Api.post("/api/makers", {
      name: document.getElementById("maker-name").value.trim(),
    });
    e.target.reset();
    await loadMakers();
  }

  async function loadStores() {
    storesCache = await Api.get("/api/stores/all");
    const el = document.getElementById("store-list");
    if (!el) return;
    el.innerHTML = storesCache
      .map(
        (s) => `<li data-id="${s.id}">
          <span class="master-list-label"><strong>${esc(s.name)}</strong> ${s.is_active ? "" : "[無効]"}</span>
          ${listActions()}
        </li>`
      )
      .join("");
  }

  function onStoreListClick(e) {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const li = btn.closest("li[data-id]");
    if (!li) return;
    const id = parseInt(li.dataset.id, 10);
    const item = storesCache.find((s) => s.id === id);
    if (!item) return;
    if (btn.dataset.action === "edit") openStoreModal(item);
    else if (btn.dataset.action === "delete") deleteStore(item);
  }

  function openStoreModal(s) {
    document.getElementById("edit-store-id").value = s.id;
    document.getElementById("edit-store-name").value = s.name;
    document.getElementById("edit-store-active").checked = s.is_active !== false;
    showModal("store-edit-modal");
  }

  async function saveStoreEdit(e) {
    e.preventDefault();
    const errEl = document.getElementById("store-edit-error");
    errEl.hidden = true;
    const id = parseInt(document.getElementById("edit-store-id").value, 10);
    try {
      await Api.put(`/api/stores/${id}`, {
        name: document.getElementById("edit-store-name").value.trim(),
        is_active: document.getElementById("edit-store-active").checked,
      });
      hideModal("store-edit-modal");
      await loadStores();
    } catch (ex) {
      errEl.textContent = ex.message;
      errEl.hidden = false;
    }
  }

  async function deleteStore(s) {
    if (!confirm("削除しますか？")) return;
    try {
      await Api.delete(`/api/stores/${s.id}`);
      window.location.reload();
    } catch (ex) {
      alert(ex.message);
    }
  }

  async function saveStoreNew(e) {
    e.preventDefault();
    await Api.post("/api/stores", {
      name: document.getElementById("store-name").value.trim(),
    });
    e.target.reset();
    await loadStores();
  }

  async function loadLinks() {
    const dealers = await Api.get("/api/dealers");
    let html = "";
    for (const d of dealers) {
      const links = await Api.get(`/api/dealers/${d.id}/makers`);
      links.forEach((l) => {
        html += `<li>${esc(l.dealer_name)} × ${esc(l.maker_name)}
          <button type="button" class="btn btn-ghost btn-sm" data-link-id="${l.id}">解除</button></li>`;
      });
    }
    const list = document.getElementById("link-list");
    if (!list) return;
    list.innerHTML = html || "<li>紐付けなし</li>";
    list.querySelectorAll("[data-link-id]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await Api.delete(`/api/dealers/links/${btn.dataset.linkId}`);
        await loadLinks();
      });
    });
  }

  async function saveLink(e) {
    e.preventDefault();
    await Api.post("/api/dealers/links", {
      dealer_id: parseInt(document.getElementById("link-dealer").value, 10),
      maker_id: parseInt(document.getElementById("link-maker").value, 10),
    });
    await loadLinks();
  }

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s ?? "";
    return d.innerHTML;
  }
})();
