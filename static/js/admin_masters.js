/**
 * 管理者 — 棚・カテゴリ・ディーラー・メーカー・店舗・紐付け
 */
(function () {
  let categoriesCache = [];
  let sectionsCache = [];
  let dealersCache = [];
  let makersCache = [];
  let storesCache = [];
  let sectionEditMode = "edit";

  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("dealer-form")?.addEventListener("submit", saveDealerNew);
    document.getElementById("maker-form")?.addEventListener("submit", saveMakerNew);
    document.getElementById("store-form")?.addEventListener("submit", saveStoreNew);
    document.getElementById("link-form")?.addEventListener("submit", saveLink);

    document.getElementById("section-edit-form")?.addEventListener("submit", saveSectionEdit);
    document.getElementById("btn-add-shelf")?.addEventListener("click", openSectionAddModal);
    document.getElementById("category-edit-form")?.addEventListener("submit", saveCategoryEdit);

    bindMasterModalClose();
    bindListDelegation();
    document.getElementById("category-groups")?.addEventListener("click", onCategoryGroupsClick);

    window.addEventListener("admin-ready", refreshMasters);
  });

  function bindMasterModalClose() {
    document.querySelectorAll(".master-modal-close").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.dataset.close;
        if (id) hideModal(id);
      });
    });
    ["section-edit-modal", "category-edit-modal", "dealer-edit-modal", "maker-edit-modal", "store-edit-modal"].forEach(
      (id) => {
        document.getElementById(id)?.addEventListener("click", (e) => {
          if (e.target.id === id) hideModal(id);
        });
      }
    );
  }

  function bindListDelegation() {
    document.getElementById("dealer-list")?.addEventListener("click", onDealerListClick);
    document.getElementById("maker-list")?.addEventListener("click", onMakerListClick);
    document.getElementById("store-list")?.addEventListener("click", onStoreListClick);
    document.getElementById("shelf-cards")?.addEventListener("click", onShelfCardsClick);
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
    el.querySelectorAll(".error-msg").forEach((err) => {
      err.hidden = true;
    });
  }

  function listActions() {
    return `<span class="master-list-actions">
      <button type="button" class="btn btn-ghost btn-sm" data-action="edit">編集</button>
      <button type="button" class="btn btn-ghost btn-sm" data-action="delete">削除</button>
    </span>`;
  }

  function fillSectionSelect(selectEl, selectedId) {
    if (!selectEl) return;
    selectEl.innerHTML = sectionsCache
      .filter((s) => s.is_active)
      .map((s) => `<option value="${s.id}">${esc(s.name)}</option>`)
      .join("");
    if (selectedId) selectEl.value = String(selectedId);
  }

  async function refreshMasters() {
    await loadSections();
    await loadCategories();
    await loadDealers();
    await loadMakers();
    await loadStores();
    await loadLinks();
    if (typeof window.loadMasters === "function") window.loadMasters();
  }

  // ---------- 棚 ----------
  async function loadSections() {
    sectionsCache = await Api.get("/api/sections?include_inactive=true");
    renderShelfCards();
    fillSectionSelect(document.getElementById("edit-cat-section"));
  }

  function renderShelfCards() {
    const el = document.getElementById("shelf-cards");
    if (!el) return;
    if (!sectionsCache.length) {
      el.innerHTML = '<p class="empty-msg">棚がありません</p>';
      return;
    }
    el.innerHTML = sectionsCache
      .map(
        (s) => `
      <article class="shelf-card" data-id="${s.id}">
        <div class="shelf-card-preview" style="background:${esc(s.color)}"></div>
        <p class="shelf-card-name">${esc(s.name)}</p>
        <p class="shelf-card-meta">カテゴリ ${s.category_count} 件${s.is_active ? "" : " · 無効"}</p>
        <div class="shelf-card-actions">
          <button type="button" class="btn btn-ghost btn-sm" data-action="edit-shelf">編集</button>
          <button type="button" class="btn btn-ghost btn-sm" data-action="delete-shelf">削除</button>
        </div>
      </article>`
      )
      .join("");
  }

  function onShelfCardsClick(e) {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const card = btn.closest("[data-id]");
    if (!card) return;
    const id = parseInt(card.dataset.id, 10);
    const item = sectionsCache.find((s) => s.id === id);
    if (!item) return;
    if (btn.dataset.action === "edit-shelf") openSectionEditModal(item);
    else if (btn.dataset.action === "delete-shelf") deleteSection(item);
  }

  function openSectionAddModal() {
    sectionEditMode = "add";
    document.getElementById("section-modal-title").textContent = "棚を追加";
    document.getElementById("edit-section-id").value = "";
    document.getElementById("edit-section-name").value = "";
    document.getElementById("edit-section-color").value = "#eae9fd";
    showModal("section-edit-modal");
  }

  function openSectionEditModal(s) {
    sectionEditMode = "edit";
    document.getElementById("section-modal-title").textContent = "棚を編集";
    document.getElementById("edit-section-id").value = s.id;
    document.getElementById("edit-section-name").value = s.name;
    document.getElementById("edit-section-color").value = s.color || "#eae9fd";
    showModal("section-edit-modal");
  }

  async function saveSectionEdit(e) {
    e.preventDefault();
    const errEl = document.getElementById("section-edit-error");
    errEl.hidden = true;
    const name = document.getElementById("edit-section-name").value.trim();
    const color = document.getElementById("edit-section-color").value;
    if (!name) {
      errEl.textContent = "棚名を入力してください。";
      errEl.hidden = false;
      return;
    }
    try {
      if (sectionEditMode === "add") {
        await Api.post("/api/sections", { name, color });
      } else {
        const id = parseInt(document.getElementById("edit-section-id").value, 10);
        const current = sectionsCache.find((s) => s.id === id);
        await Api.put(`/api/sections/${id}`, {
          name,
          color,
          is_active: current ? current.is_active : true,
        });
      }
      hideModal("section-edit-modal");
      await loadSections();
      await loadCategories();
    } catch (ex) {
      errEl.textContent = ex.message;
      errEl.hidden = false;
    }
  }

  async function deleteSection(s) {
    if (!confirm("削除しますか？")) return;
    try {
      await Api.delete(`/api/sections/${s.id}`);
      window.location.reload();
    } catch (ex) {
      alert(ex.message);
    }
  }

  // ---------- カテゴリ ----------
  async function loadCategories() {
    categoriesCache = await Api.get("/api/categories?include_inactive=true");
    renderCategoryGroups();
  }

  function renderCategoryGroups() {
    const container = document.getElementById("category-groups");
    if (!container) return;

    const sections = sectionsCache.length
      ? sectionsCache
      : [{ id: 1, name: "材料の棚", color: "#eae9fd" }];

    container.innerHTML = sections
      .map((sec) => {
        const cats = categoriesCache
          .filter((c) => c.section === sec.id)
          .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
        const rows = cats.length
          ? cats.map(renderCategoryRow).join("")
          : '<p class="empty-msg">カテゴリがありません</p>';
        return `
        <div class="category-group" data-section-id="${sec.id}">
          <div class="category-group-header" style="background:${esc(sec.color)}">
            <h3>${esc(sec.name)}</h3>
          </div>
          ${rows}
          <button type="button" class="btn btn-ghost btn-sm btn-add-cat" data-section-id="${sec.id}">
            + このカテゴリを追加
          </button>
        </div>`;
      })
      .join("");
  }

  function renderCategoryRow(c) {
    const inactive = c.is_active ? "" : ' <span class="badge-pill">無効</span>';
    return `
      <div class="category-row" data-id="${c.id}">
        <span class="category-row-name">${esc(c.name)}${inactive}</span>
        <span class="category-row-actions">
          <button type="button" class="btn btn-ghost btn-sm btn-order" data-action="up" title="上へ">↑</button>
          <button type="button" class="btn btn-ghost btn-sm btn-order" data-action="down" title="下へ">↓</button>
          <button type="button" class="btn btn-ghost btn-sm" data-action="edit-cat">編集</button>
          <button type="button" class="btn btn-ghost btn-sm" data-action="delete-cat">削除</button>
        </span>
      </div>`;
  }

  function onCategoryGroupsClick(e) {
    const addBtn = e.target.closest(".btn-add-cat");
    if (addBtn) {
      openCategoryAddModal(parseInt(addBtn.dataset.sectionId, 10));
      return;
    }

    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const row = btn.closest(".category-row[data-id]");
    if (!row) return;
    const id = parseInt(row.dataset.id, 10);
    const item = categoriesCache.find((c) => c.id === id);
    if (!item) return;

    if (btn.dataset.action === "edit-cat") openCategoryEditModal(item);
    else if (btn.dataset.action === "delete-cat") deleteCategory(item);
    else if (btn.dataset.action === "up" || btn.dataset.action === "down") {
      reorderCategory(item, btn.dataset.action);
    }
  }

  function openCategoryAddModal(sectionId) {
    document.getElementById("category-modal-title").textContent = "カテゴリを追加";
    document.getElementById("edit-cat-id").value = "";
    document.getElementById("edit-cat-name").value = "";
    fillSectionSelect(document.getElementById("edit-cat-section"), sectionId);
    showModal("category-edit-modal");
  }

  function openCategoryEditModal(c) {
    document.getElementById("category-modal-title").textContent = "カテゴリを編集";
    document.getElementById("edit-cat-id").value = c.id;
    document.getElementById("edit-cat-name").value = c.name;
    fillSectionSelect(document.getElementById("edit-cat-section"), c.section);
    showModal("category-edit-modal");
  }

  async function saveCategoryEdit(e) {
    e.preventDefault();
    const errEl = document.getElementById("category-edit-error");
    errEl.hidden = true;
    const idVal = document.getElementById("edit-cat-id").value;
    const name = document.getElementById("edit-cat-name").value.trim();
    const section = parseInt(document.getElementById("edit-cat-section").value, 10);
    if (!name) {
      errEl.textContent = "カテゴリ名を入力してください。";
      errEl.hidden = false;
      return;
    }
    try {
      if (idVal) {
        const current = categoriesCache.find((c) => c.id === parseInt(idVal, 10));
        await Api.put(`/api/categories/${idVal}`, {
          name,
          section,
          sort_order: current ? current.sort_order : 0,
          is_active: current ? current.is_active : true,
        });
      } else {
        await Api.post("/api/categories", { name, section, sort_order: 0 });
      }
      hideModal("category-edit-modal");
      await loadCategories();
      if (typeof window.loadMasters === "function") window.loadMasters();
    } catch (ex) {
      errEl.textContent = ex.message;
      errEl.hidden = false;
    }
  }

  async function reorderCategory(c, direction) {
    try {
      await Api.put(`/api/categories/${c.id}/order`, { direction });
      await loadCategories();
    } catch (ex) {
      alert(ex.message);
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

  // ---------- ディーラー ----------
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

  // ---------- メーカー ----------
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
    await Api.post("/api/makers", { name: document.getElementById("maker-name").value.trim() });
    e.target.reset();
    await loadMakers();
  }

  // ---------- 店舗 ----------
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
    await Api.post("/api/stores", { name: document.getElementById("store-name").value.trim() });
    e.target.reset();
    await loadStores();
  }

  // ---------- 紐付け ----------
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

  // dealer/maker edit form bindings
  document.getElementById("dealer-edit-form")?.addEventListener("submit", saveDealerEdit);
  document.getElementById("maker-edit-form")?.addEventListener("submit", saveMakerEdit);
  document.getElementById("store-edit-form")?.addEventListener("submit", saveStoreEdit);

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s ?? "";
    return d.innerHTML;
  }
})();
