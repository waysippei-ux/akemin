/**
 * API 共通処理（認証トークン・fetch ラッパー）
 */
const Api = {
  TOKEN_KEY: "access_token",

  getToken() {
    return localStorage.getItem(this.TOKEN_KEY);
  },

  setToken(token) {
    localStorage.setItem(this.TOKEN_KEY, token);
  },

  clearToken() {
    localStorage.removeItem(this.TOKEN_KEY);
  },

  isLoggedIn() {
    return !!this.getToken();
  },

  /**
   * 認証付き fetch
   * @param {string} path - /api/... から始まるパス
   * @param {object} options - fetch オプション
   */
  async request(path, options = {}) {
    const headers = {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    };

    const token = this.getToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const res = await fetch(path, {
      ...options,
      headers,
    });

    if (res.status === 401) {
      this.clearToken();
      if (!window.location.pathname.includes("/login")) {
        window.location.href = "/login";
      }
      throw new Error("認証の有効期限が切れました");
    }

    const text = await res.text();
    let data = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = text;
      }
    }

    if (!res.ok) {
      const msg =
        (data && data.detail) ||
        (typeof data === "string" ? data : null) ||
        `エラー (${res.status})`;
      const detail = Array.isArray(msg)
        ? msg.map((e) => e.msg || e).join(", ")
        : msg;
      throw new Error(detail);
    }

    return data;
  },

  get(path) {
    return this.request(path);
  },

  post(path, body) {
    const opts = { method: "POST" };
    if (body !== undefined) {
      opts.body = JSON.stringify(body);
    }
    return this.request(path, opts);
  },

  put(path, body) {
    return this.request(path, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },

  delete(path) {
    return this.request(path, { method: "DELETE" });
  },

  /** CSV などファイルダウンロード */
  async download(path, filename) {
    const headers = {};
    const token = this.getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const res = await fetch(path, { headers });
    if (res.status === 401) {
      this.clearToken();
      window.location.href = "/login";
      throw new Error("認証の有効期限が切れました");
    }
    if (!res.ok) {
      const text = await res.text();
      let detail = text;
      try {
        const j = JSON.parse(text);
        detail = j.detail || text;
      } catch {
        /* ignore */
      }
      throw new Error(typeof detail === "string" ? detail : "ダウンロードに失敗しました");
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },

  /** CSV などファイルアップロード（Content-Type は自動） */
  async upload(path, file, fieldName = "file", query = "") {
    const formData = new FormData();
    formData.append(fieldName, file);

    const headers = {};
    const token = this.getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const url = query ? `${path}?${query}` : path;
    const res = await fetch(url, { method: "POST", headers, body: formData });

    if (res.status === 401) {
      this.clearToken();
      window.location.href = "/login";
      throw new Error("認証の有効期限が切れました");
    }

    const text = await res.text();
    let data = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = text;
      }
    }

    if (!res.ok) {
      const msg = (data && data.detail) || `エラー (${res.status})`;
      throw new Error(Array.isArray(msg) ? msg.join(", ") : msg);
    }
    return data;
  },

  logout() {
    this.clearToken();
    window.location.href = "/login";
  },
};

// ログアウトボタン（base.html）
document.addEventListener("DOMContentLoaded", () => {
  const btnLogout = document.getElementById("btn-logout");
  if (btnLogout) {
    btnLogout.addEventListener("click", () => Api.logout());
  }

  const navToggle = document.getElementById("nav-toggle");
  const mainNav = document.getElementById("main-nav");
  if (navToggle && mainNav) {
    navToggle.addEventListener("click", () => {
      mainNav.classList.toggle("open");
    });
  }

  // 保護ページ: 未ログインならログインへ
  const protectedPaths = ["/dashboard", "/scan", "/stock", "/admin", "/orders"];
  if (
    protectedPaths.some((p) => window.location.pathname.startsWith(p)) &&
    !Api.isLoggedIn()
  ) {
    window.location.href = "/login";
  }

  // ナビ: 管理者専用リンクはスタッフにはアラート表示
  if (Api.isLoggedIn()) {
    Api.get("/api/auth/me")
      .then((user) => {
        const isAdmin = user.role === "admin";
        ["nav-orders-analytics", "nav-admin"].forEach((id) => {
          const link = document.getElementById(id);
          if (!link) return;
          if (isAdmin) return;
          link.href = "#";
          link.addEventListener("click", (e) => {
            e.preventDefault();
            showAdminAlert();
          });
        });
      })
      .catch(() => {});
  }
});
