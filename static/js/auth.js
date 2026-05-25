/**
 * ログイン画面
 */
document.addEventListener("DOMContentLoaded", () => {
  if (Api.isLoggedIn()) {
    window.location.href = "/dashboard";
    return;
  }

  const form = document.getElementById("login-form");
  const errorEl = document.getElementById("login-error");
  const btnLogin = document.getElementById("btn-login");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorEl.hidden = true;
    btnLogin.disabled = true;
    btnLogin.textContent = "ログイン中…";

    const username = document.getElementById("username").value.trim();
    const password = document.getElementById("password").value;

    try {
      const data = await Api.post("/api/auth/login", { username, password });
      Api.setToken(data.access_token);
      window.location.href = "/dashboard";
    } catch (err) {
      errorEl.textContent = err.message || "ログインに失敗しました";
      errorEl.hidden = false;
    } finally {
      btnLogin.disabled = false;
      btnLogin.textContent = "ログイン";
    }
  });
});
