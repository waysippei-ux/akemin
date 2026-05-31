/**
 * iOS Safari 向け: 数値・バーコード入力欄の属性を統一
 */
(function (global) {
  function applyIosNumericInputAttrs(el) {
    if (!el || el.type !== "number") return;
    el.setAttribute("inputmode", "numeric");
    el.setAttribute("pattern", "[0-9]*");
    el.setAttribute("autocomplete", "off");
  }

  function applyIosNumericInputsIn(root) {
    const scope = root || document;
    scope.querySelectorAll('input[type="number"]').forEach(applyIosNumericInputAttrs);
  }

  function applyIosBarcodeTextInput(el) {
    if (!el || el.type !== "text") return;
    el.setAttribute("inputmode", "text");
    el.setAttribute("autocomplete", "off");
    el.setAttribute("maxlength", "13");
    el.maxLength = 13;
  }

  function applyIosFormInputs(root) {
    applyIosNumericInputsIn(root);
    const scope = root || document;
    scope
      .querySelectorAll("#modal-barcode, #new-barcode, #scanner-input, #barcode-input")
      .forEach(applyIosBarcodeTextInput);
  }

  document.addEventListener("DOMContentLoaded", () => applyIosFormInputs());

  global.applyIosNumericInputAttrs = applyIosNumericInputAttrs;
  global.applyIosNumericInputsIn = applyIosNumericInputsIn;
  global.applyIosFormInputs = applyIosFormInputs;
})(window);
