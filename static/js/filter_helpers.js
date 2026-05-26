/**
 * 棚・カテゴリ絞り込みの共通ヘルパー
 */
window.FilterHelpers = (function () {
  const DIRECT_DEALER_NAME = "メーカー直";
  const DIRECT_DEALER_LABEL = "直取引";

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s ?? "";
    return d.innerHTML;
  }

  function fillSectionSelect(el, sections, includeAll = true) {
    if (!el) return;
    const prev = el.value;
    const opts = includeAll ? ['<option value="">すべて</option>'] : [];
    (sections || [])
      .filter((s) => s.is_active !== false)
      .sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0) || a.id - b.id)
      .forEach((s) => {
        opts.push(`<option value="${s.id}">${esc(s.name)}</option>`);
      });
    el.innerHTML = opts.join("");
    if ([...el.options].some((o) => o.value === prev)) el.value = prev;
    else el.value = "";
  }

  function fillCategorySelect(el, categories, sectionId, keepValue = true) {
    if (!el) return;
    const prev = el.value;
    let list = categories || [];
    if (sectionId) {
      list = list.filter((c) => String(c.section) === String(sectionId));
    }
    el.innerHTML =
      '<option value="">すべて</option>' +
      list.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("");
    if (keepValue && [...el.options].some((o) => o.value === prev)) el.value = prev;
    else el.value = "";
  }

  function bindShelfCategory(sectionEl, categoryEl, categories, onFilterChange) {
    sectionEl?.addEventListener("change", () => {
      fillCategorySelect(categoryEl, categories, sectionEl.value);
      onFilterChange?.();
    });
  }

  function matchesSection(categoryId, sectionId, categories) {
    if (!sectionId) return true;
    const cat = (categories || []).find(
      (c) => c.id === categoryId || String(c.id) === String(categoryId)
    );
    return cat && String(cat.section) === String(sectionId);
  }

  function dealerDisplayName(dealerName) {
    if (dealerName === DIRECT_DEALER_NAME) return DIRECT_DEALER_LABEL;
    return dealerName;
  }

  function fillBrandSelect(el, brands, makerId, includeAll = true, includeEmpty = false) {
    if (!el) return;
    const prev = el.value;
    let list = brands || [];
    if (makerId) {
      list = list.filter((b) => String(b.maker_id) === String(makerId));
    } else {
      list = [];
    }
    const opts = [];
    if (includeAll) opts.push('<option value="">すべて</option>');
    else if (includeEmpty) opts.push('<option value="">—</option>');
    list
      .sort(
        (a, b) =>
          (a.sort_order || 0) - (b.sort_order || 0) ||
          String(a.name).localeCompare(String(b.name), "ja")
      )
      .forEach((b) => {
        opts.push(`<option value="${b.id}">${esc(b.name)}</option>`);
      });
    el.innerHTML = opts.join("");
    if ([...el.options].some((o) => o.value === prev)) el.value = prev;
    else el.value = "";
  }

  function bindMakerBrand(makerEl, brandEl, brands, onFilterChange) {
    makerEl?.addEventListener("change", () => {
      fillBrandSelect(brandEl, brands, makerEl.value, true, false);
      onFilterChange?.();
    });
  }

  function matchesBrand(productBrandId, brandId) {
    if (!brandId) return true;
    return String(productBrandId || "") === String(brandId);
  }

  return {
    DIRECT_DEALER_NAME,
    DIRECT_DEALER_LABEL,
    fillSectionSelect,
    fillCategorySelect,
    fillBrandSelect,
    bindShelfCategory,
    bindMakerBrand,
    matchesSection,
    matchesBrand,
    dealerDisplayName,
    esc,
  };
})();
