import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ModalLayer } from "./ModalLayer";
import {
  developmentNotificationRuns,
  getDevelopmentNotificationDetail,
  isDevelopmentNotificationMockEnabled,
} from "./notificationHistoryMock";

type SortDirection = "asc" | "desc";
type AttemptSortKey = "employee" | "type" | "recipient" | "status";

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
  employeeCode: string | null;
  employeeName: string | null;
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

type NotificationHistorySummary = {
  total: number;
  succeeded: number;
  attention: number;
  sent: number;
};

type NotificationRunPage = {
  items: NotificationRun[];
  total: number;
  limit: number;
  offset: number;
  summary: NotificationHistorySummary;
};

const HISTORY_PAGE_SIZE = 20;

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

const attemptSortLabels: Record<AttemptSortKey, string> = { employee: "社員", type: "種別", recipient: "送信先", status: "状態" };
const attemptCollator = new Intl.Collator("ja", { numeric: true, sensitivity: "base" });
const attemptStatusOrder: Record<string, number> = { failed: 0, sent: 1, skipped: 2, pending: 3 };

function attemptStatus(status: string): { label: string; className: string } {
  if (status === "sent") return { label: "送信済み", className: "badge-ok" };
  if (status === "failed") return { label: "失敗", className: "badge-danger" };
  if (status === "skipped") return { label: "重複スキップ", className: "badge-off" };
  if (status === "pending") return { label: "保留", className: "badge-warning" };
  return { label: status, className: "badge-off" };
}

export function NotificationHistory() {
  const [runs, setRuns] = useState<NotificationRun[]>([]);
  const [historySummary, setHistorySummary] = useState<NotificationHistorySummary>({ total: 0, succeeded: 0, attention: 0, sent: 0 });
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<NotificationRunDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [selectedError, setSelectedError] = useState<NotificationAttempt | null>(null);
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);
  const [attemptSort, setAttemptSort] = useState<{ key: AttemptSortKey; direction: SortDirection }>({ key: "employee", direction: "asc" });
  const errorDialogCloseRef = useRef<HTMLButtonElement | null>(null);
  const errorDialogTriggerRef = useRef<HTMLButtonElement | null>(null);
  const developmentMockEnabled = isDevelopmentNotificationMockEnabled();

  const totalPages = Math.max(1, Math.ceil(historySummary.total / HISTORY_PAGE_SIZE));
  const currentPage = Math.floor(offset / HISTORY_PAGE_SIZE) + 1;
  const rangeStart = historySummary.total === 0 ? 0 : offset + 1;
  const rangeEnd = historySummary.total === 0 ? 0 : Math.min(offset + runs.length, historySummary.total);

  const loadRuns = useCallback(async (requestedOffset: number) => {
    setLoading(true);
    setError(null);
    try {
      if (developmentMockEnabled) {
        const allRuns = developmentNotificationRuns as NotificationRun[];
        const items = allRuns.slice(requestedOffset, requestedOffset + HISTORY_PAGE_SIZE);
        setRuns(items);
        setHistorySummary({
          total: allRuns.length,
          succeeded: allRuns.filter((run) => run.status === "succeeded" && run.failedCount === 0).length,
          attention: allRuns.filter((run) => run.status === "failed" || run.failedCount > 0).length,
          sent: allRuns.reduce((total, run) => total + run.sentCount, 0),
        });
        setOffset(requestedOffset);
        return;
      }
      let response = await fetch(`/api/notification-runs?limit=${HISTORY_PAGE_SIZE}&offset=${requestedOffset}`, {
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error(await responseError(response));
      let page = (await response.json()) as NotificationRunPage;
      if (page.total > 0 && requestedOffset >= page.total) {
        const lastOffset = Math.floor((page.total - 1) / HISTORY_PAGE_SIZE) * HISTORY_PAGE_SIZE;
        response = await fetch(`/api/notification-runs?limit=${HISTORY_PAGE_SIZE}&offset=${lastOffset}`, {
          credentials: "same-origin",
        });
        if (!response.ok) throw new Error(await responseError(response));
        page = (await response.json()) as NotificationRunPage;
      }
      setRuns(page.items);
      setHistorySummary(page.summary);
      setOffset(page.offset);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "通知履歴を取得できませんでした");
    } finally {
      setLoading(false);
    }
  }, [developmentMockEnabled]);

  useEffect(() => {
    void loadRuns(0);
  }, [loadRuns]);

  async function openDetail(runId: string) {
    setAttemptSort({ key: "employee", direction: "asc" });
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
    setSelectedError(null);
    setCopyFeedback(null);
    setDetail(null);
    setDetailError(null);
    setDetailLoading(false);
  }

  async function copyText(value: string, label: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopyFeedback(`${label}をコピーしました`);
    } catch {
      setCopyFeedback(`${label}をコピーできませんでした`);
    }
  }

  function openErrorDetail(attempt: NotificationAttempt, trigger: HTMLButtonElement) {
    errorDialogTriggerRef.current = trigger;
    setCopyFeedback(null);
    setSelectedError(attempt);
  }

  function closeErrorDetail() {
    setSelectedError(null);
    setCopyFeedback(null);
    requestAnimationFrame(() => errorDialogTriggerRef.current?.focus());
  }

  useEffect(() => {
    if (selectedError) errorDialogCloseRef.current?.focus();
  }, [selectedError]);

  const sortedAttempts = useMemo(() => {
    if (!detail) return [];
    const direction = attemptSort.direction === "asc" ? 1 : -1;
    return [...detail.attempts].sort((left, right) => {
      let comparison = 0;
      if (attemptSort.key === "employee") {
        comparison = attemptCollator.compare(left.employeeCode || "", right.employeeCode || "") || attemptCollator.compare(left.employeeName || "", right.employeeName || "");
      }
      if (attemptSort.key === "type") {
        comparison = attemptCollator.compare(left.notificationType, right.notificationType) || (left.thresholdPercent ?? Number.POSITIVE_INFINITY) - (right.thresholdPercent ?? Number.POSITIVE_INFINITY);
      }
      if (attemptSort.key === "recipient") comparison = attemptCollator.compare(left.recipient, right.recipient);
      if (attemptSort.key === "status") comparison = (attemptStatusOrder[left.status] ?? 99) - (attemptStatusOrder[right.status] ?? 99);
      if (comparison === 0) comparison = attemptCollator.compare(left.employeeCode || "", right.employeeCode || "");
      return comparison * direction;
    });
  }, [attemptSort, detail]);

  function toggleAttemptSort(key: AttemptSortKey) {
    setAttemptSort((current) => ({ key, direction: current.key === key && current.direction === "asc" ? "desc" : "asc" }));
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
        <button className="button-secondary" type="button" onClick={() => void loadRuns(offset)} disabled={loading} aria-busy={loading}>
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

      {(!loading || runs.length > 0) && (!error || runs.length > 0) && (
        <>
          <section className="notification-summary" aria-label="通知履歴集計">
            <article><span>履歴件数</span><strong>{historySummary.total}</strong></article>
            <article><span>成功</span><strong>{historySummary.succeeded}</strong></article>
            <article><span>要確認</span><strong className={historySummary.attention > 0 ? "status-danger" : ""}>{historySummary.attention}</strong></article>
            <article><span>送信済み</span><strong>{historySummary.sent}</strong></article>
          </section>

          {runs.length === 0 ? (
            <div className="notification-empty-state">
              <strong>通知実行履歴はありません</strong>
              <span>threshold、weekly、healthを実行すると、ここに結果が表示されます。</span>
            </div>
          ) : (
            <>
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
            <nav className="notification-pagination" aria-label="通知履歴ページ">
              <span>表示中 {rangeStart}–{rangeEnd} / 全{historySummary.total}件</span>
              <div>
                <button className="button-secondary" type="button" disabled={loading || offset === 0} onClick={() => void loadRuns(Math.max(0, offset - HISTORY_PAGE_SIZE))}>前へ</button>
                <span aria-current="page">{currentPage} / {totalPages}</span>
                <button className="button-secondary" type="button" disabled={loading || offset + HISTORY_PAGE_SIZE >= historySummary.total} onClick={() => void loadRuns(offset + HISTORY_PAGE_SIZE)}>次へ</button>
              </div>
            </nav>
            </>
          )}
        </>
      )}

      {(detailLoading || detailError || detail) && (
        <ModalLayer closeOnBackdrop={false} onRequestClose={closeDetail}>
          <section className="modal notification-history-modal" role="dialog" aria-modal="true" aria-labelledby="notification-detail-title">
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
                    <>
                    <div className="mobile-sort-controls notification-attempt-sort-controls">
                      <label>
                        並び順
                        <select value={attemptSort.key} onChange={(event) => setAttemptSort((current) => ({ ...current, key: event.target.value as AttemptSortKey }))}>
                          {Object.entries(attemptSortLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                        </select>
                      </label>
                      <button className="button-secondary sort-direction-button" type="button" onClick={() => setAttemptSort((current) => ({ ...current, direction: current.direction === "asc" ? "desc" : "asc" }))}>
                        {attemptSort.direction === "asc" ? "昇順" : "降順"}
                      </button>
                    </div>
                    <div className="table-wrap">
                      <table className="notification-attempt-table">
                        <thead><tr>
                          {(["employee", "type", "recipient", "status"] as AttemptSortKey[]).map((key) => (
                            <th key={key} aria-sort={attemptSort.key === key ? (attemptSort.direction === "asc" ? "ascending" : "descending") : "none"}>
                              <button className="table-sort-button" type="button" onClick={() => toggleAttemptSort(key)} aria-label={`${attemptSortLabels[key]}で${attemptSort.key === key && attemptSort.direction === "asc" ? "降順" : "昇順"}に並べ替え`}>
                                <span>{attemptSortLabels[key]}</span><span className="sort-indicator" aria-hidden="true">{attemptSort.key === key ? (attemptSort.direction === "asc" ? "▲" : "▼") : "↕"}</span>
                              </button>
                            </th>
                          ))}
                          <th>試行</th><th>重複元</th><th>Slack timestamp</th><th>エラー</th></tr></thead>
                        <tbody>
                          {sortedAttempts.map((attempt) => {
                            const attemptOutcome = attemptStatus(attempt.status);
                            return (
                              <tr key={attempt.id}>
                                <td data-label="社員" className="notification-attempt-employee">
                                  <div className="notification-employee-identity">
                                    <span className="notification-employee-code">
                                      <small>社員番号</small>
                                      <span className="mono">{attempt.employeeCode || "—"}</span>
                                    </span>
                                    <span className="notification-employee-name">
                                      <small>氏名</small>
                                      <strong>{attempt.employeeName || "氏名不明"}</strong>
                                    </span>
                                  </div>
                                </td>
                                <td data-label="種別" className="notification-attempt-type">
                                  <span className="notification-attempt-type-content">
                                    <span>{modeLabel(attempt.notificationType)}</span>
                                    {attempt.thresholdPercent !== null && <small>{attempt.thresholdPercent}%</small>}
                                  </span>
                                </td>
                                <td data-label="送信先" className="notification-attempt-recipient" title={attempt.recipient}>{attempt.recipient}</td>
                                <td data-label="状態" className="notification-attempt-status"><span className={`badge ${attemptOutcome.className}`}>{attemptOutcome.label}</span></td>
                                <td data-label="試行" className="notification-attempt-count">{attempt.attemptCount}</td>
                                <td data-label="重複元" className="notification-attempt-duplicate">
                                  {attempt.duplicateOfRunId ? (
                                    <button className="table-action notification-duplicate-link" type="button" onClick={() => void openDetail(attempt.duplicateOfRunId!)}>
                                      <span>{formatDateTime(attempt.duplicateOfStartedAt)}</span>
                                      <small>{sourceLabel(attempt.duplicateOfSource)}</small>
                                    </button>
                                  ) : "—"}
                                </td>
                                <td data-label="Slack timestamp" className="mono notification-attempt-timestamp">
                                  {attempt.slackTimestamp ? (
                                    <button
                                      className="notification-copy-value"
                                      type="button"
                                      title={`${attempt.slackTimestamp} をコピー`}
                                      onClick={() => void copyText(attempt.slackTimestamp!, "Slack timestamp")}
                                    >
                                      {attempt.slackTimestamp.length > 13 ? `${attempt.slackTimestamp.slice(0, 13)}…` : attempt.slackTimestamp}
                                    </button>
                                  ) : "—"}
                                </td>
                                <td data-label="エラー" className="notification-error-cell notification-attempt-error">
                                  {attempt.errorMessage ? (
                                    <button className="notification-error-detail-button" type="button" onClick={(event) => openErrorDetail(attempt, event.currentTarget)}>詳細</button>
                                  ) : "—"}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                    </>
                  )}
                </>
              );
            })()}
          </section>
        </ModalLayer>
      )}

      {selectedError && (
        <ModalLayer closeOnBackdrop={false} onRequestClose={closeErrorDetail} className="notification-error-backdrop">
          <section className="modal notification-error-modal" role="dialog" aria-modal="true" aria-labelledby="notification-error-title">
            <div className="modal-heading">
              <div><p className="eyebrow">DELIVERY ERROR</p><h2 id="notification-error-title">送信エラー詳細</h2></div>
              <button ref={errorDialogCloseRef} className="icon-button" type="button" onClick={closeErrorDetail} aria-label="送信エラー詳細を閉じる">×</button>
            </div>
            <dl className="notification-error-meta">
              <div><dt>社員番号</dt><dd className="mono">{selectedError.employeeCode || "—"}</dd></div>
              <div><dt>氏名</dt><dd>{selectedError.employeeName || "氏名不明"}</dd></div>
              <div className="notification-error-meta-wide"><dt>送信先</dt><dd>{selectedError.recipient}</dd></div>
              <div><dt>種別</dt><dd>{modeLabel(selectedError.notificationType)}{selectedError.thresholdPercent === null ? "" : ` ${selectedError.thresholdPercent}%`}</dd></div>
              <div><dt>状態</dt><dd>{attemptStatus(selectedError.status).label}</dd></div>
              <div><dt>試行</dt><dd>{selectedError.attemptCount}</dd></div>
              <div><dt>実行日時</dt><dd>{formatDateTime(selectedError.updatedAt)}</dd></div>
            </dl>
            <div className="notification-error-message-heading">
              <h3>エラー全文</h3>
              <button className="button-secondary" type="button" onClick={() => void copyText(selectedError.errorMessage || "", "エラー全文")}>全文をコピー</button>
            </div>
            <pre className="notification-error-message-full">{selectedError.errorMessage}</pre>
            {copyFeedback && <p className="notification-copy-feedback" role="status">{copyFeedback}</p>}
          </section>
        </ModalLayer>
      )}
    </section>
  );
}
