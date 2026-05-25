/**
 * 管理者 — カテゴリ・ディーラー・メーカー・店舗・紐付け
 */
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("category-form")?.addEventListener("submit", saveCategory);
  document.getElementById("dealer-form")?.addEventListener("submit", saveDealer);
  document.getElementById("maker-form")?.addEventListener("submit", saveMaker);
  document.getElementById("store-form")?.addEventListener("submit", saveStore);
  document.getElementById("link-form")?.addEventListener("submit", saveLink);

  window.addEventListener("admin-ready", refreshMasters);
});

async function refreshMasters() {
  await loadCategories();
  await loadDealers();
  await loadMakers();
  await loadStores();
  await loadLinks();
}

const SECTION_LABEL = { 1: "①材料", 2: "②販売" };

async function loadCategories() {
  const list = await Api.get("/api/categories?include_inactive=true");
  document.getElementById("category-list").innerHTML = list
    .map((c) => {
      const sec = SECTION_LABEL[c.section] || c.section;
      const safeName = c.name.replace(/'/g, "\\'");
      return `
    <li>
      <strong>${c.name}</strong> [${sec}] 順:${c.sort_order} ${c.is_active ? "" : "[無効]"}
      <button type="button" class="btn btn-ghost btn-sm"
        onclick="editCategory(${c.id},'${safeName}',${c.section},${c.sort_order})">編集</button>
      ${c.is_active ? `<button type="button" class="btn btn-ghost btn-sm" onclick="deactCategory(${c.id})">無効化</button>` : ""}
    </li>`;
    })
    .join("");
}

window.editCategory = (id, name, section, sort) => {
  document.getElementById("cat-id").value = id;
  document.getElementById("cat-name").value = name;
  document.getElementById("cat-section").value = String(section);
  document.getElementById("cat-sort").value = sort;
};

window.deactCategory = async (id) => {
  const c = (await Api.get("/api/categories?include_inactive=true")).find((x) => x.id === id);
  if (!c) return;
  await Api.put(`/api/categories/${id}`, {
    name: c.name,
    section: c.section,
    sort_order: c.sort_order,
    is_active: false,
  });
  await loadCategories();
};

async function saveCategory(e) {
  e.preventDefault();
  const id = document.getElementById("cat-id").value;
  const section = parseInt(document.getElementById("cat-section").value, 10);
  const body = {
    name: document.getElementById("cat-name").value.trim(),
    section,
    sort_order: parseInt(document.getElementById("cat-sort").value, 10) || 0,
    is_active: true,
  };
  if (id) await Api.put(`/api/categories/${id}`, body);
  else await Api.post("/api/categories", body);
  document.getElementById("category-form").reset();
  document.getElementById("cat-id").value = "";
  await loadCategories();
  if (window.loadMasters) window.loadMasters();
}

async function loadDealers() {
  const list = await Api.get("/api/dealers/all");
  document.getElementById("dealer-list").innerHTML = list
    .map(
      (d) => `<li>${d.name} ${d.contact_info || ""} ${d.is_active ? "" : "[無効]"}
      <button type="button" class="btn btn-ghost btn-sm" onclick="deactDealer(${d.id})">無効化</button></li>`
    )
    .join("");
  const sel = document.getElementById("link-dealer");
  if (sel) sel.innerHTML = list.filter((d) => d.is_active).map((d) => `<option value="${d.id}">${d.name}</option>`).join("");
}

window.deactDealer = async (id) => {
  const d = (await Api.get("/api/dealers/all")).find((x) => x.id === id);
  await Api.put(`/api/dealers/${id}`, { name: d.name, contact_info: d.contact_info, is_active: false });
  await loadDealers();
};

async function saveDealer(e) {
  e.preventDefault();
  const id = document.getElementById("dealer-edit-id").value;
  const body = {
    name: document.getElementById("dealer-name").value.trim(),
    contact_info: document.getElementById("dealer-contact").value.trim() || null,
    is_active: true,
  };
  if (id) await Api.put(`/api/dealers/${id}`, body);
  else await Api.post("/api/dealers", body);
  e.target.reset();
  await loadDealers();
}

async function loadMakers() {
  const list = await Api.get("/api/makers/all");
  document.getElementById("maker-list").innerHTML = list
    .map(
      (m) => `<li>${m.name} ${m.is_active ? "" : "[無効]"}
      <button type="button" class="btn btn-ghost btn-sm" onclick="deactMaker(${m.id})">無効化</button></li>`
    )
    .join("");
  const sel = document.getElementById("link-maker");
  if (sel) sel.innerHTML = list.filter((m) => m.is_active).map((m) => `<option value="${m.id}">${m.name}</option>`).join("");
}

window.deactMaker = async (id) => {
  const m = (await Api.get("/api/makers/all")).find((x) => x.id === id);
  await Api.put(`/api/makers/${id}`, { name: m.name, is_active: false });
  await loadMakers();
};

async function saveMaker(e) {
  e.preventDefault();
  const id = document.getElementById("maker-edit-id").value;
  const name = document.getElementById("maker-name").value.trim();
  if (id) await Api.put(`/api/makers/${id}`, { name, is_active: true });
  else await Api.post("/api/makers", { name });
  e.target.reset();
  await loadMakers();
}

async function loadStores() {
  const list = await Api.get("/api/stores/all");
  const el = document.getElementById("store-list");
  if (!el) return;
  el.innerHTML = list
    .map((s) => {
      const safeName = s.name.replace(/'/g, "\\'");
      const toggleBtn = s.is_active
        ? `<button type="button" class="btn btn-ghost btn-sm" onclick="toggleStore(${s.id}, false)">無効化</button>`
        : `<button type="button" class="btn btn-ghost btn-sm" onclick="toggleStore(${s.id}, true)">有効化</button>`;
      return `<li>
      <strong>${escHtml(s.name)}</strong> ${s.is_active ? "" : "[無効]"}
      <button type="button" class="btn btn-ghost btn-sm" onclick="editStore(${s.id},'${safeName}')">編集</button>
      ${toggleBtn}
    </li>`;
    })
    .join("");
}

window.editStore = (id, name) => {
  document.getElementById("store-edit-id").value = id;
  document.getElementById("store-name").value = name;
};

window.toggleStore = async (id, active) => {
  const s = (await Api.get("/api/stores/all")).find((x) => x.id === id);
  if (!s) return;
  await Api.put(`/api/stores/${id}`, { name: s.name, is_active: active });
  await loadStores();
};

async function saveStore(e) {
  e.preventDefault();
  const id = document.getElementById("store-edit-id").value;
  const name = document.getElementById("store-name").value.trim();
  if (id) {
    const current = (await Api.get("/api/stores/all")).find((x) => x.id === parseInt(id, 10));
    await Api.put(`/api/stores/${id}`, {
      name,
      is_active: current ? current.is_active : true,
    });
  } else {
    await Api.post("/api/stores", { name });
  }
  e.target.reset();
  document.getElementById("store-edit-id").value = "";
  await loadStores();
}

function escHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

async function loadLinks() {
  const dealers = await Api.get("/api/dealers");
  let html = "";
  for (const d of dealers) {
    const links = await Api.get(`/api/dealers/${d.id}/makers`);
    links.forEach((l) => {
      html += `<li>${l.dealer_name} × ${l.maker_name}
        <button type="button" class="btn btn-ghost btn-sm" onclick="removeLink(${l.id})">解除</button></li>`;
    });
  }
  document.getElementById("link-list").innerHTML = html || "<li>紐付けなし</li>";
}

window.removeLink = async (id) => {
  await Api.delete(`/api/dealers/links/${id}`);
  await loadLinks();
};

async function saveLink(e) {
  e.preventDefault();
  await Api.post("/api/dealers/links", {
    dealer_id: parseInt(document.getElementById("link-dealer").value, 10),
    maker_id: parseInt(document.getElementById("link-maker").value, 10),
  });
  await loadLinks();
}
