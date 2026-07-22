import { FormEvent, useCallback, useEffect, useState } from "react";

type Health = {
  status: string;
  service: string;
  version: string;
  serverTime: string;
  timezone: string;
  frontendBuilt: boolean;
};

type CurrentUser = {
  username: string;
  expiresAt: string;
};

export function App() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const loadCurrentUser = useCallback(async () => {
    const response = await fetch("/api/auth/me", { credentials: "same-origin" });
    if (response.status === 401) {
      setUser(null);
      return;
    }
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    setUser((await response.json()) as CurrentUser);
  }, []);

  useEffect(() => {
    loadCurrentUser()
      .catch(() => setUser(null))
      .finally(() => setCheckingAuth(false));
  }, [loadCurrentUser]);

  useEffect(() => {
    if (!user) return;
    fetch("/api/system/health", { credentials: "same-origin" })
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json() as Promise<Health>;
      })
      .then(setHealth)
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "状態を取得できませんでした");
      });
  }, [user]);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const response = await fetch("/api/auth/login", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: form.get("username"),
        password: form.get("password"),
      }),
    });
    setSubmitting(false);

    if (!response.ok) {
      setError(
        response.status === 429
          ? "ログイン試行回数が上限に達しました。しばらく待ってから再試行してください。"
          : "ユーザー名またはパスワードが正しくありません。",
      );
      return;
    }
    setUser((await response.json()) as CurrentUser);
    event.currentTarget.reset();
  }

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
    setUser(null);
    setHealth(null);
    setError(null);
  }

  if (checkingAuth) {
    return <main className="center-shell"><p className="muted">認証状態を確認しています…</p></main>;
  }

  if (!user) {
    return (
      <main className="login-shell">
        <section className="login-card">
          <p className="eyebrow">DIVISION OVERTIME</p>
          <h1>管理者ログイン</h1>
          <p className="lead">社員設定を管理するため、認証情報を入力してください。</p>
          <form className="login-form" onSubmit={handleLogin}>
            <label>
              ユーザー名
              <input name="username" autoComplete="username" required autoFocus />
            </label>
            <label>
              パスワード
              <input name="password" type="password" autoComplete="current-password" required />
            </label>
            {error && <p className="error-message" role="alert">{error}</p>}
            <button type="submit" disabled={submitting}>
              {submitting ? "ログイン中…" : "ログイン"}
            </button>
          </form>
        </section>
      </main>
    );
  }

  return (
    <main className="page-shell">
      <header className="topbar">
        <div><p className="eyebrow">DIVISION OVERTIME</p><strong>{user.username}</strong></div>
        <button className="button-secondary" type="button" onClick={handleLogout}>ログアウト</button>
      </header>
      <section className="hero">
        <h1>Web管理UI</h1>
        <p className="lead">認証済みの管理画面です。社員管理・KOT同期は後続PRで追加します。</p>
      </section>
      <section className="status-card" aria-live="polite">
        <div className="status-heading">
          <h2>システム状態</h2>
          <span className={`badge ${health?.status === "ok" ? "badge-ok" : ""}`}>
            {health?.status === "ok" ? "稼働中" : error ? "取得失敗" : "確認中"}
          </span>
        </div>
        {health && (
          <dl className="status-grid">
            <div><dt>サービス</dt><dd>{health.service}</dd></div>
            <div><dt>バージョン</dt><dd>{health.version}</dd></div>
            <div><dt>タイムゾーン</dt><dd>{health.timezone}</dd></div>
            <div><dt>サーバー時刻</dt><dd>{new Date(health.serverTime).toLocaleString("ja-JP")}</dd></div>
          </dl>
        )}
        {error && <p className="error-message">APIへの接続に失敗しました: {error}</p>}
      </section>
    </main>
  );
}
