import { useCallback, useEffect, useMemo, useState } from "react";
import {
  developmentNotificationRuns,
  getDevelopmentNotificationDetail,
  isDevelopmentNotificationMockEnabled,
} from "./notificationHistoryMock";

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
  duplicateOfAttemptId: number | null;
  duplicateOfRunId: string | null;
  duplicateOfStartedAt: string | null;
  duplicateOfSource: "timer" | "manual" | "test" | "unknown" | null;
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

function modeLabel(mode: string): string {
  if (mode === "threshold") return "閾値通知";
  if (mode === "weekly") return "週次通知";
  if (mode === "health") return "ヘルスチェック";
  return mode;
}

function sourceLabel(source: NotificationRun["source"] | null): string {
  if (source === "timer") return "定期実行";
  if (source === "manual") return "手動実行";
  if (source === "test") return "テスト";
  return "不明";
}

function runStatus(run: NotificationRun): { label: string; className: string } {
  if (run.dryRun) return { label: "dry-run", className: "badge-off" };
  if (run.failedCount > 0 && run.sentCount > 0) {
    return { label: "一部失敗", className: "badge-warning" };
  }
  if (run.status === "succeeded") return { label: "成功", className: "badge-ok" };
  if (run.status === "failed") return { label: "失敗", className: "badge-danger" };
  if (run.status === "running") return { label: "実行中", className: "badge-live" };
  return { label: run.status, className: "badge-off" };
}

function attemptStatus(status: string): { label: string; className: string } {
  if (status === "sent") return { label: "送信済み", className: "badge-ok" };
  if (status === "failed") return { label: "失敗", className: "badge-danger" };
  if (status === "skipped") return { label: "重複スキップ", className: "badge-off" };
  if (status === "pending") return { label: "保留", className: "badge-warning" };
  return { label: status, className: "badge-off" };
}

export function NotificationHistory() {
  const [runs, setRuns] = useState<NotificationRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<NotificationRunDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const developmentMockEnabled = isDevelopmentNotificationMockEnabled();

  const summary = useMemo(
    () => ({
      total: runs.length,
      succeeded: runs.filter((run) => run.status === "succeeded" && run.failedCount === 0).length,
      attention: runs.filter((run) => run.status === "failed" || run.failedCount > 0).length,
      sent: runs.reduce((total, run) => total + run.sentCount, 0),
    }),
    [runs],
  );

  const loadRuns = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (developmentMockEnabled) {
        setRuns(developmentNotificationRuns as NotificationRun[]);
        return;
      }
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
  }, [developmentMockEnabled]);

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  async function openDetail(runId: string) {
    setDetailLoading(true);
    setDetailError(null);
    setDetail(null);
    try {
      if (developmentMockEnabled) {
        const mockDetail = getDevelopmentNotificationDetail(runId);
        if (!mockDetail) throw new Error("指定した通知実行履歴が見つかりません");
        setDetail(mockDetail as NotificationRunDetail);
        return;
      }
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
      <div className="sync-heading notification-history-heading">
        <div>
          <p className="eyebrow">NOTIFICATION HISTORY</p>
          <h2>通知実行履歴</h2>
          <p className="muted">週次通知・閾値通知・ヘルスチェックの実行結果を読み取り専用で確認できます。</p>
          {developmentMockEnabled && <span className="badge badge-warning notification-mock-badge">開発用サンプル表示中</span>}
        </div>
        <button className="button-secondary" type="button" onClick={loadRuns} disabled={loading} aria-busy={loading}>
          {loading ? "更新中…" : "再読込"}
        </button>
      </div>

      {error && <p className="error-message" role="alert">通知履歴の取得に失敗しました: {error}</p>}
      {loading && runs.length === 0 && (
        <div className="notification-skeleton" role="status" aria-label="通知履歴を読み込んでいます">
          <div className="skeleton-summary" aria-hidden="true">
            {Array.from({ length: 4 }, (_, index) => <span key={index} className="skeleton-card" />)}
          </div>
          <div className="skeleton-table" aria-hidden="true">
            {Array.from({ length: 5 }, (_, index) => <span key={index} className="skeleton-table-row" />)}
          </div>
        </div>
      )}

      {loading && runs.length > 0 && <div className="updating-indicator" role="status">通知履歴を更新中…</div>}

      {(!loading || runs.length > 0) && !error && (
        <>
          <section className="notification-summary" aria-label="通知履歴集計">
            <article><span>表示中</span><strong>{summary.total}</strong></article>
            <article><span>成功</span><strong>{summary.succeeded}</strong></article>
            <article><span>要確認</span><strong className={summary.attention > 0 ? "status-danger" : ""}>{summary.attention}</strong></article>
            <article><span>送信済み</span><strong>{summary.sent}</strong></article>
          </section>

          {runs.length === 0 ? (
            <div className="notification-empty-state">
              <strong>通知実行履歴はありません</strong>
              <span>threshold、weekly、healthを実行すると、ここに結果が表示されます。</span>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="notification-history-table">
                <thead>
                  <tr>
                    <th>実行日時</th><th>種別</th><th>実行元</th><th>実行</th><th>状態</th><th>対象</th><th>送信</th><th>失敗</th><th />
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => {
                    const outcome = runStatus(run);
                    return (
                      <tr key={run.runId} className={run.failedCount > 0 ? "notification-row-attention" : ""}>
                        <td data-label="実行日時">{formatDateTime(run.startedAt)}</td>
                        <td data-label="種別"><span className="notification-type">{modeLabel(run.mode)}</span><small className="mono notification-code">{run.mode}</small></td>
                        <td data-label="実行元">{sourceLabel(run.source)}</td>
                        <td data-label="実行">{run.dryRun ? <span className="badge badge-off">dry-run</span> : <span className="badge badge-live">本番</span>}</td>
                        <td data-label="状態"><span className={`badge ${outcome.className}`}>{outcome.label}</span></td>
                        <td data-label="対象">{run.targetCount}</td>
                        <td data-label="送信">{run.sentCount} / {run.attemptCount}</td>
                        <td data-label="失敗" className={run.failedCount > 0 ? "status-danger" : ""}>{run.failedCount}</td>
                        <td className="card-action"><button className="table-action" type="button" onClick={() => void openDetail(run.runId)}>詳細</button></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {(detailLoading || detailError || detail) && (
        <div className="modal-backdrop" role="presentation" onMouseDown={closeDetail}>
          <section className="modal notification-history-modal" role="dialog" aria-modal="true" aria-labelledby="notification-detail-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className="modal-heading">
              <div><p className="eyebrow">NOTIFICATION RUN</p><h2 id="notification-detail-title">通知実行詳細</h2></div>
              <button className="icon-button" type="button" onClick={closeDetail} aria-label="通知実行詳細を閉じる">×</button>
            </div>
            {detailLoading && <div className="notification-loading" role="status">詳細を読み込んでいます…</div>}
            {detailError && <p className="error-message" role="alert">{detailError}</p>}
            {detail && (() => {
              const outcome = runStatus(detail);
              return (
                <>
                  <div className="notification-detail-heading">
                    <div>
                      <span className={`badge ${outcome.className}`}>{outcome.label}</span>
                      <strong>{modeLabel(detail.mode)}</strong>
                      <span className="muted">{sourceLabel(detail.source)} / {detail.dryRun ? "dry-run" : "本番実行"}</span>
                    </div>
                    <span className="mono muted">{detail.runId}</span>
                  </div>
                  <dl className="notification-detail-grid">
                    <div><dt>開始日時</dt><dd>{formatDateTime(detail.startedAt)}</dd></div>
                    <div><dt>終了日時</dt><dd>{formatDateTime(detail.finishedAt)}</dd></div>
                    <div><dt>対象</dt><dd>{detail.targetCount}</dd></div>
                    <div><dt>試行</dt><dd>{detail.attemptCount}</dd></div>
                    <div><dt>送信済み</dt><dd>{detail.sentCount}</dd></div>
                    <div><dt>失敗</dt><dd className={detail.failedCount > 0 ? "status-danger" : ""}>{detail.failedCount}</dd></div>
                    <div><dt>スキップ</dt><dd>{detail.skippedCount}</dd></div>
                    <div><dt>保留</dt><dd>{detail.pendingCount}</dd></div>
                  </dl>
                  {detail.errorMessage && <p className="error-message">実行エラー: {detail.errorMessage}</p>}
                  <div className="notification-attempt-heading">
                    <div><p className="eyebrow">DELIVERY RESULTS</p><h3>送信先別結果</h3></div>
                    <span>{detail.attempts.length}件</span>
                  </div>
                  {detail.attempts.length === 0 ? (
                    <div className="notification-empty-state compact"><strong>送信試行はありません</strong></div>
                  ) : (
                    <div className="table-wrap">
                      <table className="notification-attempt-table">
                        <thead><tr><th>社員番号</th><th>送信先</th><th>種別</th><th>状態</th><th>試行</th><th>重複元</th><th>Slack timestamp</th><th>エラー</th></tr></thead>
                        <tbody>
                          {detail.attempts.map((attempt) => {
                            const attemptOutcome = attemptStatus(attempt.status);
                            return (
                              <tr key={attempt.id}>
                                <td data-label="社員番号" className="mono">{attempt.employeeCode || "—"}</td>
                                <td data-label="送信先">{attempt.recipient}</td>
                                <td data-label="種別">{modeLabel(attempt.notificationType)}{attempt.thresholdPercent === null ? "" : ` ${attempt.thresholdPercent}%`}</td>
                                <td data-label="状態"><span className={`badge ${attemptOutcome.className}`}>{attemptOutcome.label}</span></td>
                                <td data-label="試行">{attempt.attemptCount}</td>
                                <td data-label="重複元">
                                  {attempt.duplicateOfRunId ? (
                                    <button className="table-action" type="button" onClick={() => void openDetail(attempt.duplicateOfRunId!)}>
                                      {formatDateTime(attempt.duplicateOfStartedAt)} / {sourceLabel(attempt.duplicateOfSource)}
                                    </button>
                                  ) : "—"}
                                </td>
                                <td data-label="Slack timestamp" className="mono">{attempt.slackTimestamp || "—"}</td>
                                <td data-label="エラー" className="notification-error-cell">{attempt.errorMessage || "—"}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              );
            })()}
          </section>
        </div>
      )}
    </section>
  );
}
