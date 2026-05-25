/**
 * バーコードスキャン画面
 */
(function () {
  let currentUser = null;
  let stores = [];
  let currentAction = "use";
  let html5QrCode = null;
  let cameraRunning = false;
  let scanCooldown = false;

  const storeSelect = document.getElementById("store-select");
  const scanResult = document.getElementById("scan-result");
  const scanError = document.getElementById("scan-error");

  document.addEventListener("DOMContentLoaded", init);

  async function init() {
    setupActionToggle();
    document.getElementById("btn-manual-submit")?.addEventListener("click", onManualSubmit);
    document.getElementById("barcode-input")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") onManualSubmit();
    });
    document.getElementById("btn-toggle-camera")?.addEventListener("click", toggleCamera);

    try {
      currentUser = await Api.get("/api/auth/me");
      stores = await Api.get("/api/stores");
      setupStoreSelect();
      initScanner();
    } catch (err) {
      showError(err.message);
    }
  }

  function setupStoreSelect() {
    storeSelect.innerHTML = "";
    stores.forEach((s) => {
      const opt = document.createElement("option");
      opt.value = s.id;
      opt.textContent = s.name;
      storeSelect.appendChild(opt);
    });
    if (currentUser.store_id) {
      storeSelect.value = String(currentUser.store_id);
      if (currentUser.role === "staff") {
        storeSelect.disabled = true;
      }
    }
  }

  function setupActionToggle() {
    document.querySelectorAll(".toggle-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".toggle-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        currentAction = btn.dataset.action;
      });
    });
  }

  function initScanner() {
    if (typeof Html5Qrcode === "undefined") {
      console.warn("html5-qrcode が読み込めません。手入力をご利用ください。");
      return;
    }
    const formats = Html5QrcodeSupportedFormats
      ? [
          Html5QrcodeSupportedFormats.EAN_13,
          Html5QrcodeSupportedFormats.EAN_8,
          Html5QrcodeSupportedFormats.CODE_128,
          Html5QrcodeSupportedFormats.CODE_39,
          Html5QrcodeSupportedFormats.UPC_A,
        ]
      : undefined;
    html5QrCode = new Html5Qrcode("reader", { formatsToSupport: formats });
  }

  async function toggleCamera() {
    if (!html5QrCode) {
      showError("カメラライブラリが利用できません");
      return;
    }

    if (cameraRunning) {
      await html5QrCode.stop();
      cameraRunning = false;
      return;
    }

    try {
      await html5QrCode.start(
        { facingMode: "environment" },
        { fps: 10, qrbox: { width: 250, height: 120 } },
        onScanSuccess,
        () => {}
      );
      cameraRunning = true;
      hideError();
    } catch (err) {
      showError("カメラを起動できません: " + err.message);
    }
  }

  function onScanSuccess(decodedText) {
    if (scanCooldown) return;
    scanCooldown = true;
    setTimeout(() => {
      scanCooldown = false;
    }, 2000);

    submitScan(decodedText.trim());
  }

  function onManualSubmit() {
    const code = document.getElementById("barcode-input").value.trim();
    if (!code) {
      showError("バーコードを入力してください");
      return;
    }
    submitScan(code);
  }

  async function submitScan(barcode) {
    hideError();
    scanResult.hidden = true;

    const quantity = parseInt(document.getElementById("quantity").value, 10) || 1;
    const storeId = parseInt(storeSelect.value, 10);

    try {
      const res = await Api.post("/api/inventory/scan", {
        barcode,
        action: currentAction,
        quantity,
        store_id: storeId,
      });

      scanResult.textContent = res.message;
      scanResult.classList.remove("error");
      scanResult.hidden = false;
      document.getElementById("barcode-input").value = "";

      // 短い振動フィードバック（対応端末のみ）
      if (navigator.vibrate) navigator.vibrate(100);
    } catch (err) {
      showError(err.message);
    }
  }

  function showError(msg) {
    scanError.textContent = msg;
    scanError.hidden = false;
    scanResult.hidden = true;
  }

  function hideError() {
    scanError.hidden = true;
  }
})();
