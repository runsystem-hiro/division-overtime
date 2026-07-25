import { useCallback, useEffect, useState } from "react";

type NotificationRun = {
  runId: string;
  mode: string;
  startedAt: string;
  finishedAt: string | null;
  status: string;
  dryRun: boolean;
  source: "timer" | "manual" | "test" | "unknown";
  errorMessage: string | null;
  targetCount: number;
  attemptCount: number;
  sentCount: number;
  failedCount: number;
  skippedCount: number;
  pendingCount: number;
};

type NotificationAttempt = {
  id: number;
  dedupeKey: string;
  employeeCode: string;
  recipient: string;
  notificationType: string;
  thresholdPercent: number | null;
  status: string;
  attemptCount: number;
  slackTimestamp: string | null;
  errorMessage: string | null;
  createdAt: string;
  updatedAt: string;
};

type NotificationRunDetail = NotificationRun & {
  attempts: NotificationAttempt[];
};

async function responseError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string };
    return body.detail || `HTTP ${response.status}`;
  } catch {
    return `HTTP ${response.status}`;
  }
}

function formatDateTime(value: string | null): string {
  return value ? new Date(value).toLocaleString("ja-JP") : "—";
}

function statusClass(status: string): string {
  if (status === "succeeded" || status === "sent") return "badge-ok";
  if (status === "failed") return "badge-danger";
  return "badge-off";
}

export function NotificationHistory() {
  const [runs, setRuns] = useState<NotificationRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<NotificationRunDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const loadRuns = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/notification-runs?limit=50", {
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error(await responseError(response));
      setRuns((await response.json()) as NotificationRun[]);
    } catch (reason: unknown) {
      setRuns([]);
      setError(reason instanceof Error ? reason.message : "通知履歴を取得できませんでした");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  async function openDetail(runId: string) {
    setDetailLoading(true);
    setDetailError(null);
    setDetail(null);
    try {
      const response = await fetch(`/api/notification-runs/${encodeURIComponent(runId)}`, {
        credentials: "same-origin",
      });
      if (response.status === 404) throw new Error("指定した通知実行履歴が見つかりません");
      if (!response.ok) throw new Error(await responseError(response));
      setDetail((await response.json()) as NotificationRunDetail);
    } catch (reason: unknown) {
      setDetailError(reason instanceof Error ? reason.message : "通知履歴の詳細を取得できませんでした");
    } finally {
      setDetailLoading(false);
    }
  }

  function closeDetail() {
    setDetail(null);
    setDetailError(null);
    setDetailLoading(false);
  }

  return (
    <section className="employee-card notification-history-card" id="notification-history">
      <div className="sync-heading">
        <div>
          <p className="eyebrow">NOTIFICATION HISTORY</p>
          <h2>通知実行履歴</h2>
          <p className="muted">週次通知・閾値通知の実行結果を読み取り専用で確認できます。</p>
        </div>
        <button className="button-secondary" type="button" onClick={loadRuns} disabled={loading}>
          {loading ? "読込中…" : "再読込"}
        </button>
      </div>

      {error && <p className="error-message" role="alert">通知履歴の取得に失敗しました: {error}</p>}
      {loading && <p className="muted loading-line">通知履歴を読み込んでいます…</p>}

      {!loading && !error && (
        <div className="table-wrap">
          <table className="notification-history-table">
            <thead>
              <tr>
                <th>実行日時</th><th>種別</th><th>実行元</th><th>実行</th><th>状態</th><th>対象</th><th>送信</th><th>失敗</th><th />
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.runId}>
                  <td>{formatDateTime(run.startedAt)}</td>
                  <td><span className="mono">{run.mode}</span></td>
                  <td><span className="mono">{run.source}</span></td>
                  <td>{run.dryRun ? <span className="badge badge-off">dry-run</span> : <span className="badge badge-live">本番</span>}</td>
                  <td><span className={`badge ${statusClass(run.status)}`}>{run.status}</span></td>
                  <td>{run.targetCount}</td>
                  <td>{run.sentCount} / {run.attemptCount}</td>
                  <td className={run.failedCount > 0 ? "status-danger" : ""}>{run.failedCount}</td>
                  <td><button className="table-action" type="button" onClick={() => void openDetail(run.runId)}>詳細</button></td>
                </tr>
              ))}
              {runs.length === 0 && <tr><td colSpan={9} className="empty-row">通知実行履歴はありません。</td></tr>}
            </tbody>
          </table>
        </div>
      )}

      {(detailLoading || detailError || detail) && (
        <div className="modal-backdrop" role="presentation" onMouseDown={closeDetail}>
          <section className="modal notification-history-modal" role="dialog" aria-modal="true" aria-labelledby="notification-detail-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className="modal-heading">
              <div><p className="eyebrow">NOTIFICATION RUN</p><h2 id="notification-detail-title">通知実行詳細</h2></div>
              <button className="icon-button" type="button" onClick={closeDetail} aria-label="通知実行詳細を閉じる">×</button>
            </div>
            {detailLoading && <p className="muted">詳細を読み込んでいます…</p>}
            {detailError && <p className="error-message" role="alert">{detailError}</p>}
            {detail && (
              <>
                <dl className="notification-detail-grid">
                  <div><dt>run ID</dt><dd className="mono">{detail.runId}</dd></div>
                  <div><dt>実行日時</dt><dd>{formatDateTime(detail.startedAt)}</dd></div>
                  <div><dt>種別</dt><dd>{detail.mode}</dd></div>
                  <div><dt>実行元</dt><dd>{detail.source}</dd></div>
                  <div><dt>実行</dt><dd>{detail.dryRun ? "dry-run" : "本番"}</dd></div>
                  <div><dt>状態</dt><dd>{detail.status}</dd></div>
                  <div><dt>件数</dt><dd>対象 {detail.targetCount} / 試行 {detail.attemptCount} / 送信 {detail.sentCount} / 失敗 {detail.failedCount} / skip {detail.skippedCount} / pending {detail.pendingCount}</dd></div>
                </dl>
                {detail.errorMessage && <p className="error-message">実行エラー: {detail.errorMessage}</p>}
                <div className="table-wrap">
                  <table className="notification-attempt-table">
                    <thead><tr><th>社員番号</th><th>送信先</th><th>種別</th><th>状態</th><th>Slack timestamp</th><th>エラー</th></tr></thead>
                    <tbody>
                      {detail.attempts.map((attempt) => (
                        <tr key={attempt.id}>
                          <td className="mono">{attempt.employeeCode}</td>
                          <td>{attempt.recipient}</td>
                          <td>{attempt.notificationType}{attempt.thresholdPercent === null ? "" : ` ${attempt.thresholdPercent}%`}</td>
                          <td><span className={`badge ${statusClass(attempt.status)}`}>{attempt.status}</span></td>
                          <td className="mono">{attempt.slackTimestamp || "—"}</td>
                          <td>{attempt.errorMessage || "—"}</td>
                        </tr>
                      ))}
                      {detail.attempts.length === 0 && <tr><td colSpan={6} className="empty-row">送信試行はありません。</td></tr>}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </section>
        </div>
      )}
    </section>
  );
}
