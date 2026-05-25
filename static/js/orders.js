/**
 * 発注データ分析ページ
 */
(function () {
  const TAB_ENDPOINTS = {
    store: "/api/orders/by-store",
    section: "/api/orders/by-section",
    category: "/api/orders/by-category",
    dealer: "/api/orders/by-dealer",
    maker: "/api/orders/by-maker",
    history: "/api/orders/history",
    insights: "/api/orders/inventory-insights",
  };

  const TAB_LABELS = {
    store: "店舗別",
    section: "区分別",
    category: "カテゴリ別",
    dealer: "ディーラー別",
    maker: "メーカー別",
    history: "発注履歴",
    insights: "棚の動き",
  };

  let stores = [];
  let categories = [];
  let dealers = [];
  let makers = [];
  let parsedLines = [];
  let currentTab = "store";
  let hasData = false;
  const charts = {};

  document.addEventListener("DOMContentLoaded", init);

  async function init() {
    const now = new Date();
    const monthEl = document.getElementById("filter-month");
    monthEl.value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;

    document.getElementById("filter-period-mode").addEventListener("change", onPeriodModeChange);
    document.getElementById("filter-month").addEventListener("change", refreshAll);
    document.getElementById("filter-date-from").addEventListener("change", refreshAll);
    document.getElementById("filter-date-to").addEventListener("change", refreshAll);
    ["filter-store", "filter-section", "filter-category", "filter-dealer", "filter-maker"].forEach(
      (id) => document.getElementById(id).addEventListener("change", onFilterChange)
    );

    document.querySelectorAll(".orders-tabs .tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => switchTab(btn.dataset.tab));
    });
    document.querySelectorAll(".btn-tab-csv").forEach((btn) => {
      btn.addEventListener("click", () => downloadTabCsv(btn.dataset.tab));
    });
    document.getElementById("btn-export-all")?.addEventListener("click", () =>
      Api.download("/api/orders/export/all-csv", "AKEMIN_発注データ_全明細.csv")
    );
    document.getElementById("btn-show-import")?.addEventListener("click", () => {
      document.getElementById("import-section").open = true;
      document.getElementById("import-section").scrollIntoView({ behavior: "smooth" });
    });
    document.getElementById("modal-close")?.addEventListener("click", closeModal);
    document.getElementById("order-modal")?.addEventListener("click", (e) => {
      if (e.target.id === "order-modal") closeModal();
    });
    document.getElementById("btn-parse-invoice")?.addEventListener("click", parseInvoice);
    document.getElementById("btn-confirm-import")?.addEventListener("click", confirmImport);
    document.getElementById("import-dealer")?.addEventListener("change", rematchInvoiceLines);

    onPeriodModeChange();

    try {
      const user = await Api.get("/api/auth/me");
      stores = await Api.get("/api/stores");
      categories = await Api.get("/api/categories");
      dealers = await Api.get("/api/dealers");
      makers = await Api.get("/api/makers");

      fillStoreFilter(stores, user);
      fillMasterSelect("filter-dealer", dealers);
      fillMasterSelect("filter-maker", makers);
      fillCategoryOptions();
      fillSelect("import-store", stores);
      fillSelect("import-dealer", dealers);

      if (user.store_id) {
        const storeEl = document.getElementById("filter-store");
        storeEl.value = String(user.store_id);
        if (user.role === "staff") storeEl.disabled = true;
        const importStore = document.getElementById("import-store");
        importStore.value = String(user.store_id);
        if (user.role === "staff") importStore.disabled = true;
      }

      await refreshAll();
    } catch (err) {
      alert(err.message);
    }
  }

  function onPeriodModeChange() {
    const mode = document.getElementById("filter-period-mode").value;
    document.getElementById("filter-month").hidden = mode !== "month";
    document.getElementById("filter-range-wrap").hidden = mode !== "range";
    refreshAll();
  }

  function onFilterChange(e) {
    if (e.target.id === "filter-section") fillCategoryOptions();
    refreshAll();
  }

  function fillStoreFilter(items, user) {
    const el = document.getElementById("filter-store");
    const opts = ['<option value="">すべて</option>'];
    items.forEach((s) => opts.push(`<option value="${s.id}">${s.name}</option>`));
    el.innerHTML = opts.join("");
  }

  function fillMasterSelect(id, items) {
    const el = document.getElementById(id);
    const opts = ['<option value="">すべて</option>'];
    items.forEach((i) => opts.push(`<option value="${i.id}">${i.name}</option>`));
    el.innerHTML = opts.join("");
  }

  function fillSelect(id, items) {
    const el = document.getElementById(id);
    el.innerHTML = items.map((i) => `<option value="${i.id}">${i.name}</option>`).join("");
  }

  function fillCategoryOptions() {
    const section = document.getElementById("filter-section").value;
    const el = document.getElementById("filter-category");
    const prev = el.value;
    let list = categories;
    if (section) list = categories.filter((c) => String(c.section) === section);
    el.innerHTML =
      '<option value="">すべて</option>' +
      list.map((c) => `<option value="${c.id}">${c.name}</option>`).join("");
    if ([...el.options].some((o) => o.value === prev)) el.value = prev;
    else el.value = "";
  }

  function buildFilterQuery() {
    const p = new URLSearchParams();
    const mode = document.getElementById("filter-period-mode").value;
    if (mode === "month") {
      const [y, m] = document.getElementById("filter-month").value.split("-");
      if (y) p.set("year", y);
      if (m) p.set("month", String(parseInt(m, 10)));
    } else {
      const df = document.getElementById("filter-date-from").value;
      const dt = document.getElementById("filter-date-to").value;
      if (df) p.set("date_from", df);
      if (dt) p.set("date_to", dt);
    }
    const storeId = document.getElementById("filter-store").value;
    const section = document.getElementById("filter-section").value;
    const categoryId = document.getElementById("filter-category").value;
    const dealerId = document.getElementById("filter-dealer").value;
    const makerId = document.getElementById("filter-maker").value;
    if (storeId) p.set("store_id", storeId);
    if (section) p.set("section", section);
    if (categoryId) p.set("category_id", categoryId);
    if (dealerId) p.set("dealer_id", dealerId);
    if (makerId) p.set("maker_id", makerId);
    return p.toString();
  }

  function periodSuffix() {
    const mode = document.getElementById("filter-period-mode").value;
    if (mode === "month") {
      const v = document.getElementById("filter-month").value;
      return v || "all";
    }
    const df = document.getElementById("filter-date-from").value;
    const dt = document.getElementById("filter-date-to").value;
    if (df && dt) return `${df}_${dt}`;
    if (df) return df;
    return "all";
  }

  async function refreshAll() {
    const q = buildFilterQuery();
    try {
      const summary = await Api.get(`/api/orders/summary?${q}`);
      hasData = summary.has_data;
      document.getElementById("orders-empty").hidden = hasData || currentTab === "insights";
      document.getElementById("orders-main").hidden = !hasData && currentTab !== "insights";
      if (!hasData && currentTab !== "insights") {
        destroyCharts();
        return;
      }
      if (hasData) {
        document.getElementById("sum-amount").textContent =
          "¥" + summary.total_amount.toLocaleString();
        document.getElementById("sum-quantity").textContent =
          summary.total_quantity.toLocaleString();
        document.getElementById("sum-orders").textContent =
          summary.order_count.toLocaleString();
        document.getElementById("sum-sku").textContent = summary.sku_count.toLocaleString();
      }
      if (currentTab === "insights") await loadInsightsTab(q);
      else await loadTab(currentTab);
    } catch (err) {
      alert(err.message);
    }
  }

  function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll(".orders-tabs .tab-btn").forEach((b) =>
      b.classList.toggle("active", b.dataset.tab === tab)
    );
    document.querySelectorAll("[id^='panel-']").forEach((p) => {
      const active = p.id === `panel-${tab}`;
      p.hidden = !active;
      p.classList.toggle("active", active);
    });
    if (tab === "insights" || hasData) {
      if (tab === "insights") loadInsightsTab(buildFilterQuery());
      else loadTab(tab);
    }
  }

  async function loadInsightsTab(q) {
    const data = await Api.get(`/api/orders/inventory-insights?${q}`);
    const pop = document.getElementById("table-popularity");
    if (pop) {
      if (!data.popularity?.length) {
        pop.innerHTML = "<p class=\"empty-msg\">該当する使用ログがありません</p>";
      } else {
        pop.innerHTML = tableHtml(
          ["順位", "店舗", "商品", "使用回数", "使用数量"],
          data.popularity.map((r) => [
            r.rank,
            r.store_name,
            r.product_name,
            r.use_count.toLocaleString(),
            r.use_quantity.toLocaleString(),
          ])
        );
      }
    }
    const stag = document.getElementById("table-stagnant");
    if (stag) {
      if (!data.stagnant?.length) {
        stag.innerHTML = "<p class=\"empty-msg\">動きのない商品はありません</p>";
      } else {
        stag.innerHTML = tableHtml(
          ["店舗", "商品", "現在庫", "未変動日数"],
          data.stagnant.map((r) => [
            r.store_name,
            r.product_name,
            `${r.quantity}${r.unit}`,
            `${r.days_without_movement}日`,
          ])
        );
      }
    }
    const ass = document.getElementById("table-assortment");
    if (ass) {
      if (!data.assortment?.length) {
        ass.innerHTML = "<p class=\"empty-msg\">データがありません</p>";
      } else {
        ass.innerHTML = tableHtml(
          ["店舗", "棚SKU数", "カテゴリ内訳"],
          data.assortment.map((r) => [
            r.store_name,
            r.active_sku_count.toLocaleString(),
            Object.entries(r.category_breakdown || {})
              .map(([k, v]) => `${k}:${v}`)
              .join(" / ") || "—",
          ])
        );
      }
    }
  }

  async function loadTab(tab) {
    const q = buildFilterQuery();
    const res = await Api.get(`${TAB_ENDPOINTS[tab]}?${q}`);
    const items = res.items || [];
    switch (tab) {
      case "store":
        renderStoreTab(items);
        break;
      case "section":
        renderSectionTab(items);
        break;
      case "category":
        renderCategoryTab(items);
        break;
      case "dealer":
        renderDealerTab(items);
        break;
      case "maker":
        renderMakerTab(items);
        break;
      case "history":
        renderHistoryTab(items);
        break;
    }
  }

  function destroyCharts() {
    Object.keys(charts).forEach((k) => {
      if (charts[k]) {
        charts[k].destroy();
        delete charts[k];
      }
    });
  }

  function makeBarChart(canvasId, labels, amounts, quantities, labelAmount = "発注金額") {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    if (charts[canvasId]) charts[canvasId].destroy();
    charts[canvasId] = new Chart(ctx, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: labelAmount,
            data: amounts,
            backgroundColor: "rgba(92, 77, 122, 0.75)",
            yAxisID: "y",
          },
          {
            label: "発注数量",
            data: quantities,
            backgroundColor: "rgba(120, 160, 200, 0.6)",
            yAxisID: "y1",
          },
        ],
      },
      options: {
        responsive: true,
        scales: {
          y: { position: "left", beginAtZero: true },
          y1: { position: "right", beginAtZero: true, grid: { drawOnChartArea: false } },
        },
      },
    });
  }

  function renderStoreTab(items) {
    const labels = items.map((r) => r.store_name);
    makeBarChart(
      "chart-store",
      labels,
      items.map((r) => r.amount),
      items.map((r) => r.quantity)
    );
    document.getElementById("table-store").innerHTML = tableHtml(
      ["店舗名", "発注金額", "発注数量", "発注件数"],
      items.map((r) => [
        r.store_name,
        yen(r.amount),
        r.quantity.toLocaleString(),
        r.order_count,
      ])
    );
  }

  function renderSectionTab(items) {
    const labels = items.map((r) => r.section_name);
    const amounts = items.map((r) => r.amount);
    if (charts["chart-section-pie"]) charts["chart-section-pie"].destroy();
    charts["chart-section-pie"] = new Chart(document.getElementById("chart-section-pie"), {
      type: "pie",
      data: {
        labels,
        datasets: [
          {
            data: amounts,
            backgroundColor: ["#5c4d7a", "#78a0c8", "#c4a86a", "#8fbc8f"],
          },
        ],
      },
      options: { responsive: true },
    });
    makeBarChart("chart-section-bar", labels, amounts, items.map((r) => r.quantity));
    document.getElementById("table-section").innerHTML = tableHtml(
      ["区分名", "発注金額", "発注数量", "割合"],
      items.map((r) => [r.section_name, yen(r.amount), r.quantity.toLocaleString(), pct(r.ratio_percent)])
    );
  }

  function renderCategoryTab(items) {
    makeBarChart(
      "chart-category",
      items.map((r) => r.category_name),
      items.map((r) => r.amount),
      items.map((r) => r.quantity)
    );
    document.getElementById("table-category").innerHTML = tableHtml(
      ["カテゴリ名", "区分", "発注金額", "発注数量", "割合"],
      items.map((r) => [
        r.category_name,
        r.section_name,
        yen(r.amount),
        r.quantity.toLocaleString(),
        pct(r.ratio_percent),
      ])
    );
  }

  function renderDealerTab(items) {
    makeBarChart(
      "chart-dealer",
      items.map((r) => r.dealer_name),
      items.map((r) => r.amount),
      items.map((r) => r.quantity)
    );
    document.getElementById("table-dealer").innerHTML = tableHtml(
      ["ディーラー名", "発注金額", "発注数量", "取扱メーカー数", "割合"],
      items.map((r) => [
        r.dealer_name,
        yen(r.amount),
        r.quantity.toLocaleString(),
        r.maker_count,
        pct(r.ratio_percent),
      ])
    );
  }

  function renderMakerTab(items) {
    makeBarChart(
      "chart-maker",
      items.map((r) => r.maker_name),
      items.map((r) => r.amount),
      items.map((r) => r.quantity)
    );
    document.getElementById("table-maker").innerHTML = tableHtml(
      ["メーカー名", "ディーラー名", "発注金額", "発注数量", "割合"],
      items.map((r) => [
        r.maker_name,
        r.dealer_name,
        yen(r.amount),
        r.quantity.toLocaleString(),
        pct(r.ratio_percent),
      ])
    );
  }

  function renderHistoryTab(items) {
    const rows = items.map(
      (r) => `
      <tr>
        <td>${r.order_date}</td>
        <td>${esc(r.store_name)}</td>
        <td>${esc(r.dealer_name)}</td>
        <td>${r.item_count}</td>
        <td>${yen(r.total_amount)}</td>
        <td><button type="button" class="btn btn-secondary btn-sm" data-order-id="${r.order_id}">詳細</button></td>
      </tr>`
    );
    document.getElementById("table-history").innerHTML = `
      <table class="data-table">
        <thead><tr>
          <th>日付</th><th>店舗</th><th>ディーラー</th><th>商品点数</th><th>合計金額</th><th></th>
        </tr></thead>
        <tbody>${rows.join("")}</tbody>
      </table>`;
    document.getElementById("table-history").querySelectorAll("[data-order-id]").forEach((btn) => {
      btn.addEventListener("click", () => showOrderModal(btn.dataset.orderId));
    });
  }

  async function showOrderModal(orderId) {
    const po = await Api.get(`/api/orders/${orderId}`);
    document.getElementById("modal-meta").textContent =
      `${po.order_date} / ${po.store_name} / ${po.dealer_name}`;
    document.getElementById("modal-body").innerHTML = tableHtml(
      ["商品コード", "商品名", "数量", "単価", "金額"],
      po.items.map((i) => [
        i.barcode,
        i.product_name,
        i.quantity,
        i.unit_price != null ? yen(i.unit_price) : "—",
        i.unit_price != null ? yen(i.quantity * i.unit_price) : "—",
      ])
    );
    document.getElementById("order-modal").hidden = false;
  }

  function closeModal() {
    document.getElementById("order-modal").hidden = true;
  }

  function downloadTabCsv(tab) {
    const q = buildFilterQuery();
    const filename = `AKEMIN_発注データ_${TAB_LABELS[tab]}_${periodSuffix()}.csv`;
    Api.download(`/api/orders/export/csv?tab=${tab}&${q}`, filename);
  }

  function tableHtml(headers, rows) {
    const head = headers.map((h) => `<th>${h}</th>`).join("");
    const body = rows
      .map((cells) => `<tr>${cells.map((c) => `<td>${c}</td>`).join("")}</tr>`)
      .join("");
    return `<table class="data-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  }

  function yen(n) {
    return "¥" + Number(n).toLocaleString();
  }

  function pct(n) {
    return `${n}%`;
  }

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function renderImportTable(lines) {
    document.querySelector("#import-table tbody").innerHTML = lines
      .map(
        (l) => `
      <tr class="${l.match_status === "matched" ? "" : "row-unmatched"}">
        <td>${esc(l.product_code)}</td>
        <td>${l.match_status === "matched" ? "✅" : "❌"}</td>
        <td>${esc(l.matched_product_name || "—")}</td>
        <td>${l.quantity}</td>
      </tr>`
      )
      .join("");
  }

  function showImportNotice(notice) {
    const el = document.getElementById("import-notice");
    if (!el) return;
    if (notice) {
      el.textContent = notice;
      el.hidden = false;
    } else {
      el.hidden = true;
      el.textContent = "";
    }
  }

  async function rematchInvoiceLines() {
    if (!parsedLines.length) return;
    const dealerId = parseInt(document.getElementById("import-dealer").value, 10);
    if (!dealerId) return;
    const res = await Api.post("/api/orders/match-invoice-lines", {
      dealer_id: dealerId,
      lines: parsedLines.map((l) => ({
        product_code: l.product_code,
        quantity: l.quantity,
      })),
    });
    parsedLines = res.lines;
    renderImportTable(parsedLines);
    showImportNotice(res.notice);
  }

  async function parseInvoice() {
    const input = document.getElementById("invoice-file");
    if (!input.files?.[0]) return alert("ファイルを選択してください");
    const dealerId = document.getElementById("import-dealer")?.value;
    const query = dealerId ? `dealer_id=${dealerId}` : "";
    const res = await Api.upload("/api/orders/parse-invoice", input.files[0], "file", query);
    parsedLines = res.lines;
    if (res.order_date) document.getElementById("import-date").value = res.order_date;
    if (res.dealer_name) {
      const match = dealers.find(
        (d) => d.name.includes(res.dealer_name) || res.dealer_name.includes(d.name)
      );
      if (match) document.getElementById("import-dealer").value = match.id;
    }
    if (document.getElementById("import-dealer").value) {
      await rematchInvoiceLines();
    } else {
      renderImportTable(parsedLines);
      showImportNotice(res.notice);
    }
    document.getElementById("import-confirm-section").hidden = false;
    document.getElementById("import-section").open = true;
  }

  async function confirmImport() {
    const lines = parsedLines
      .filter((l) => l.matched_product_id)
      .map((l) => ({ product_id: l.matched_product_id, quantity: l.quantity }));
    if (!lines.length) return alert("照合できた商品がありません");
    await Api.post("/api/orders/confirm", {
      store_id: parseInt(document.getElementById("import-store").value, 10),
      dealer_id: parseInt(document.getElementById("import-dealer").value, 10),
      order_date: document.getElementById("import-date").value,
      lines,
    });
    const msg = document.getElementById("import-msg");
    msg.textContent = "在庫に反映しました。";
    msg.hidden = false;
    parsedLines = [];
    await refreshAll();
  }
})();
