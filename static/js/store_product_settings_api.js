/**
 * 店舗別発注目安 — 全画面共通 API（/admin/store-settings/product）
 */
(function (global) {
  const URL = "/admin/store-settings/product";

  function normalizeStandardSnapshot(value) {
    if (value == null || value === "") return null;
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }

  function fetchSetting(storeId, productId) {
    return Api.get(
      `${URL}?store_id=${encodeURIComponent(storeId)}&product_id=${encodeURIComponent(productId)}`
    );
  }

  function saveSetting(body) {
    return Api.put(URL, body);
  }

  function applyToForm(data, ids) {
    const stdEl = document.getElementById(ids.standardStock);
    const warnEl = document.getElementById(ids.warning);
    const critEl = document.getElementById(ids.critical);
    const std = data.standard_stock;
    if (stdEl) stdEl.value = std != null && std !== "" ? String(std) : "";
    if (warnEl) warnEl.value = String(data.warning_threshold ?? "");
    if (critEl) critEl.value = String(data.critical_threshold ?? "");
    return {
      standard_stock: normalizeStandardSnapshot(std),
      warning_threshold: data.warning_threshold,
      critical_threshold: data.critical_threshold,
    };
  }

  function readFromForm(ids) {
    const stdRaw = (document.getElementById(ids.standardStock)?.value || "").trim();
    const standard_stock = stdRaw === "" ? null : parseInt(stdRaw, 10);
    const warning_threshold = parseInt(
      document.getElementById(ids.warning)?.value,
      10
    );
    const critical_threshold = parseInt(
      document.getElementById(ids.critical)?.value,
      10
    );
    return { standard_stock, warning_threshold, critical_threshold };
  }

  function changed(snapshot, current) {
    if (!snapshot) return false;
    return (
      current.standard_stock !== snapshot.standard_stock ||
      current.warning_threshold !== snapshot.warning_threshold ||
      current.critical_threshold !== snapshot.critical_threshold
    );
  }

  function validate(current) {
    if (
      current.standard_stock != null &&
      (!Number.isFinite(current.standard_stock) || current.standard_stock < 0)
    ) {
      return "標準在庫数は0以上の数値で入力してください。";
    }
    if (!Number.isFinite(current.warning_threshold) || !Number.isFinite(current.critical_threshold)) {
      return "黄・赤アラートは数値で入力してください。";
    }
    if (current.critical_threshold > current.warning_threshold) {
      return "赤アラートは黄アラート以下にしてください。";
    }
    return null;
  }

  function buildPutBody(storeId, productId, current) {
    return {
      store_id: storeId,
      product_id: productId,
      standard_stock: current.standard_stock,
      warning_threshold: current.warning_threshold,
      critical_threshold: current.critical_threshold,
    };
  }

  global.StoreProductSettingsApi = {
    URL,
    fetchSetting,
    saveSetting,
    applyToForm,
    readFromForm,
    changed,
    validate,
    buildPutBody,
    normalizeStandardSnapshot,
  };
})(window);
