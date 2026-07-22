import { useEffect, useState } from "react";

type Health = {
  status: string;
  service: string;
  version: string;
  serverTime: string;
  timezone: string;
  frontendBuilt: boolean;
};

export function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/system/health")
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json() as Promise<Health>;
      })
      .then(setHealth)
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "状態を取得できませんでした");
      });
  }, []);

  return (
    <main className="page-shell">
      <section className="hero">
        <p className="eyebrow">DIVISION OVERTIME</p>
        <h1>Web管理UI 基盤</h1>
        <p className="lead">
          既存の残業通知処理から分離された管理画面です。社員管理・認証・KOT同期は後続PRで追加します。
        </p>
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
