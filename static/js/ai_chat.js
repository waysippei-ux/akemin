/**
 * アケミンに相談 — AI チャット
 */
(function () {
  function getStoreId() {
    const el = document.getElementById("ai-store-select");
    return parseInt(el?.value, 10) || null;
  }

  function escapeHtml(str) {
    return String(str ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatReply(text) {
    return escapeHtml(text).replace(/\n/g, "<br>");
  }

  function scrollMessages() {
    const messages = document.getElementById("ai-chat-messages");
    if (messages) messages.scrollTop = messages.scrollHeight;
  }

  function appendUserMessage(message) {
    const messages = document.getElementById("ai-chat-messages");
    if (!messages) return;
    const row = document.createElement("div");
    row.className = "user-msg-row";
    row.innerHTML = `<div class="user-bubble">${escapeHtml(message)}</div>`;
    messages.appendChild(row);
  }

  function appendAiMessage(html, extraClass) {
    const messages = document.getElementById("ai-chat-messages");
    if (!messages) return;
    const row = document.createElement("div");
    row.className = "ai-msg-row";
    row.innerHTML = `
      <div class="ai-msg-avatar-wrap">
        <img src="/static/img/akemin_icon.png" class="ai-msg-icon" alt="アケミンAI"
             onerror="this.style.display='none'; this.nextElementSibling.style.display='flex'">
        <div class="ai-msg-icon-fallback">AI</div>
      </div>
      <div class="ai-bubble${extraClass ? " " + extraClass : ""}">${html}</div>
    `;
    messages.appendChild(row);
    return row;
  }

  function showLoading() {
    const row = appendAiMessage("考え中...", "ai-loading");
    if (row) row.id = "loading-msg";
    scrollMessages();
  }

  function removeLoading() {
    document.getElementById("loading-msg")?.remove();
  }

  async function sendMessage() {
    const input = document.getElementById("ai-chat-input");
    const sendBtn = document.getElementById("ai-send-btn");
    const message = (input?.value || "").trim();
    if (!message) return;

    const storeId = getStoreId();
    if (!storeId) {
      alert("店舗を選択してください。");
      return;
    }

    appendUserMessage(message);
    if (input) input.value = "";
    if (sendBtn) {
      sendBtn.disabled = true;
      sendBtn.textContent = "送信中...";
    }
    showLoading();

    try {
      const data = await Api.post("/api/ai-chat", {
        message,
        store_id: storeId,
      });
      removeLoading();
      appendAiMessage(formatReply(data.reply || ""));
    } catch (err) {
      removeLoading();
      appendAiMessage(
        escapeHtml(err.message || "エラーが発生しました。もう一度お試しください。"),
        "ai-error"
      );
    }

    if (sendBtn) {
      sendBtn.disabled = false;
      sendBtn.textContent = "送信";
    }
    scrollMessages();
  }

  function sendSuggest(text) {
    const input = document.getElementById("ai-chat-input");
    if (input) input.value = text;
    sendMessage();
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("ai-send-btn")?.addEventListener("click", sendMessage);
    document.querySelectorAll("[data-suggest]").forEach((btn) => {
      btn.addEventListener("click", () => sendSuggest(btn.textContent.trim()));
    });
    document.getElementById("ai-chat-input")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
  });

  window.sendMessage = sendMessage;
  window.sendSuggest = (btn) => sendSuggest(btn.textContent.trim());
})();
