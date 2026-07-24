import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type Health = {
  status: string;
  service: string;
  version: string;
  serverTime: string;
  timezone: string;
};

type CurrentUser = {
  username: string;
  expiresAt: string;
};

type Employee = {
  code: string;
  lastName: string;
  firstName: string;
  fullName: string;
  email: string;
  divisionCode: string;
  divisionName: string;
  personalTargetMinutes: number | null;
  isEnabled: boolean;
  disabledReason: string;
  note: string;
  kotExists: boolean;
  createdAt: string;
  updatedAt: string;
};


type SyncDifference = {
  code: string;
  action: "create" | "update" | "reactivate" | "disable" | "unchanged";
  current: Record<string, unknown> | null;
  proposed: Record<string, unknown> | null;
  warnings: string[];
  changedFields: string[];
};

type SyncPreview = {
  previewId: string;
  counts: Record<string, number>;
  differences: SyncDifference[];
  fetchedCount: number;
  targetCount: number;
  targetDivisionCodes: string[];
};

type KotSyncStatus = {
  running: boolean;
  blocked: boolean;
  lastRun: {
    executed_at: string;
    actor: string;
    fetched_count: number;
    created_count: number;
    updated_count: number;
    disabled_count: number;
    reactivated_count: number;
    unchanged_count: number;
    status: string;
    backup_path: string | null;
  } | null;
};

type KotSyncApplyResult = {
  status: "ok";
  counts: {
    created: number;
    updated: number;
    reactivated: number;
    disabled: number;
  };
  backupPath: string;
};

type EmployeeWriteResult = {
  employee: Employee;
  csv: {
    regenerated: true;
    status: "success";
    generatedAt: string;
    employeeCount: number;
    outputPath: string;
    backupPath: string | null;
  };
};

type EmployeeConsistency = {
  status: "ok" | "mismatch";
  databaseEmployees: number;
  csvEmployees: number;
  databaseOnlyCodes: string[];
  csvOnlyCodes: string[];
  fieldDifferences: { code: string; fields: string[] }[];
};

type EmployeeForm = {
  code: string;
  employeeKey: string;
  lastName: string;
  firstName: string;
  email: string;
  divisionCode: string;
  divisionName: string;
  personalTargetMinutes: string;
  isEnabled: boolean;
  disabledReason: string;
  note: string;
};

const emptyForm: EmployeeForm = {
  code: "",
  employeeKey: "",
  lastName: "",
  firstName: "",
  email: "",
  divisionCode: "",
  divisionName: "",
  personalTargetMinutes: "",
  isEnabled: true,
  disabledReason: "",
  note: "",
};

async function responseError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string };
    return body.detail || `HTTP ${response.status}`;
  } catch {
    return `HTTP ${response.status}`;
  }
}

export function App() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [health, setHealth] = useState<Health | null>(null);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [enabledFilter, setEnabledFilter] = useState("all");
  const [consistency, setConsistency] = useState<EmployeeConsistency | null>(null);
  const [consistencyError, setConsistencyError] = useState<string | null>(null);
  const [loadingConsistency, setLoadingConsistency] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [loadingEmployees, setLoadingEmployees] = useState(false);
  const [editing, setEditing] = useState<Employee | null | undefined>(undefined);
  const [form, setForm] = useState<EmployeeForm>(emptyForm);
  const [syncPreview, setSyncPreview] = useState<SyncPreview | null>(null);
  const [selectedSyncCodes, setSelectedSyncCodes] = useState<string[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState<KotSyncStatus | null>(null);
  const [syncActions, setSyncActions] = useState({
    create: true,
    update: true,
    reactivate: true,
    disable: true,
    unchanged: false,
  });
  const [showNoAttendance, setShowNoAttendance] = useState(false);
  const [showOnLeave, setShowOnLeave] = useState(false);

  const loadCurrentUser = useCallback(async () => {
    const response = await fetch("/api/auth/me", { credentials: "same-origin" });
    if (response.status === 401) {
      setUser(null);
      return;
    }
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    setUser((await response.json()) as CurrentUser);
  }, []);

  const loadConsistency = useCallback(async () => {
    setLoadingConsistency(true);
    setConsistencyError(null);
    try {
      const response = await fetch("/api/employees/consistency", {
        credentials: "same-origin",
      });
      if (response.status === 401) {
        setUser(null);
        return;
      }
      if (!response.ok) throw new Error(await responseError(response));
      setConsistency((await response.json()) as EmployeeConsistency);
    } catch (reason: unknown) {
      setConsistency(null);
      setConsistencyError(reason instanceof Error ? reason.message : "整合性を確認できませんでした");
    } finally {
      setLoadingConsistency(false);
    }
  }, []);


  const loadKotSyncStatus = useCallback(async () => {
    const response = await fetch("/api/kot-sync/status", { credentials: "same-origin" });
    if (response.status === 503) {
      setSyncStatus(null);
      return;
    }
    if (!response.ok) throw new Error(await responseError(response));
    setSyncStatus((await response.json()) as KotSyncStatus);
  }, []);

  const loadEmployees = useCallback(async () => {
    setLoadingEmployees(true);
    const params = new URLSearchParams({ enabled: enabledFilter });
    if (query.trim()) params.set("query", query.trim());
    const response = await fetch(`/api/employees?${params}`, { credentials: "same-origin" });
    setLoadingEmployees(false);
    if (response.status === 401) {
      setUser(null);
      return;
    }
    if (!response.ok) throw new Error(await responseError(response));
    setEmployees((await response.json()) as Employee[]);
  }, [enabledFilter, query]);

  useEffect(() => {
    loadCurrentUser()
      .catch(() => setUser(null))
      .finally(() => setCheckingAuth(false));
  }, [loadCurrentUser]);

  useEffect(() => {
    if (!user) return;
    Promise.all([
      fetch("/api/system/health", { credentials: "same-origin" }).then(async (response) => {
        if (!response.ok) throw new Error(await responseError(response));
        return response.json() as Promise<Health>;
      }),
      loadEmployees(),
      loadConsistency(),
      loadKotSyncStatus(),
    ])
      .then(([healthResponse]) => setHealth(healthResponse))
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "情報を取得できませんでした");
      });
  }, [loadConsistency, loadEmployees, loadKotSyncStatus, user]);

  const counts = useMemo(() => ({
    all: employees.length,
    enabled: employees.filter((employee) => employee.isEnabled).length,
    disabled: employees.filter((employee) => !employee.isEnabled).length,
  }), [employees]);

  const visibleSyncDifferences = useMemo(() => {
    if (!syncPreview) return [];
    return syncPreview.differences.filter((item) => {
      if (!syncActions[item.action]) return false;
      if (!showNoAttendance && item.warnings.includes("勤怠管理なし")) return false;
      if (!showOnLeave && item.warnings.includes("休職中")) return false;
      return true;
    });
  }, [showNoAttendance, showOnLeave, syncActions, syncPreview]);

  const selectableVisibleCodes = useMemo(
    () => visibleSyncDifferences
      .filter((item) => item.action !== "unchanged")
      .map((item) => item.code),
    [visibleSyncDifferences],
  );

  const hiddenSelectedCount = selectedSyncCodes.filter(
    (code) => !selectableVisibleCodes.includes(code),
  ).length;

  const warningCounts = useMemo(() => {
    const differences = syncPreview?.differences ?? [];
    return {
      noAttendance: differences.filter((item) => item.warnings.includes("勤怠管理なし")).length,
      onLeave: differences.filter((item) => item.warnings.includes("休職中")).length,
    };
  }, [syncPreview]);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const loginForm = new FormData(event.currentTarget);
    const response = await fetch("/api/auth/login", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: loginForm.get("username"),
        password: loginForm.get("password"),
      }),
    });
    setSubmitting(false);
    if (!response.ok) {
      setError(response.status === 429
        ? "ログイン試行回数が上限に達しました。しばらく待ってから再試行してください。"
        : "ユーザー名またはパスワードが正しくありません。");
      return;
    }
    setUser((await response.json()) as CurrentUser);
    event.currentTarget.reset();
  }

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
    setUser(null);
    setHealth(null);
    setEmployees([]);
    setError(null);
  }

  function openCreate() {
    setEditing(null);
    setForm(emptyForm);
    setError(null);
    setNotice(null);
  }

  function openEdit(employee: Employee) {
    setEditing(employee);
    setForm({
      code: employee.code,
      employeeKey: "",
      lastName: employee.lastName,
      firstName: employee.firstName,
      email: employee.email,
      divisionCode: employee.divisionCode,
      divisionName: employee.divisionName,
      personalTargetMinutes: employee.personalTargetMinutes?.toString() ?? "",
      isEnabled: employee.isEnabled,
      disabledReason: employee.disabledReason,
      note: employee.note,
    });
    setError(null);
    setNotice(null);
  }

  async function loadKotPreview() {
    setSyncing(true);
    setError(null);
    setNotice(null);
    const response = await fetch("/api/kot-sync/preview", {
      method: "POST",
      credentials: "same-origin",
    });
    setSyncing(false);
    if (!response.ok) {
      setError(await responseError(response));
      return;
    }
    const preview = (await response.json()) as SyncPreview;
    setSyncPreview(preview);
    setSelectedSyncCodes([]);
    await loadKotSyncStatus();
  }

  async function applyKotPreview() {
    if (!syncPreview || selectedSyncCodes.length === 0) return;
    const selected = syncPreview.differences.filter((item) =>
      selectedSyncCodes.includes(item.code),
    );
    const detail = {
      create: selected.filter((item) => item.action === "create").length,
      update: selected.filter((item) => item.action === "update").length,
      reactivate: selected.filter((item) => item.action === "reactivate").length,
      disable: selected.filter((item) => item.action === "disable").length,
    };
    const message = [
      `${selectedSyncCodes.length}件をSQLiteとemployeeKey.csvへ反映します。`,
      `新規 ${detail.create}件 / 更新 ${detail.update}件 / 再有効化 ${detail.reactivate}件 / 無効化 ${detail.disable}件`,
      detail.reactivate > 0 ? "再有効化した社員は通知対象へ戻ります。" : "",
    ].filter(Boolean).join("\n");
    if (!window.confirm(message)) return;
    setSyncing(true);
    setError(null);
    const response = await fetch("/api/kot-sync/apply", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ previewId: syncPreview.previewId, employeeCodes: selectedSyncCodes }),
    });
    setSyncing(false);
    if (!response.ok) {
      setError(await responseError(response));
      return;
    }
    const result = (await response.json()) as KotSyncApplyResult;
    setNotice(`KOT社員差分を反映し、employeeKey.csvを再生成しました。再有効化 ${result.counts.reactivated}件。反映前バックアップを ${result.backupPath} へ保存しました。`);
    setSyncPreview(null);
    setSelectedSyncCodes([]);
    await Promise.all([loadEmployees(), loadConsistency(), loadKotSyncStatus()]);
  }

  async function saveEmployee(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setNotice(null);
    const payload = {
      ...form,
      employeeKey: form.employeeKey || null,
      personalTargetMinutes: form.personalTargetMinutes === ""
        ? null
        : Number(form.personalTargetMinutes),
    };
    const isCreate = editing === null;
    const response = await fetch(isCreate ? "/api/employees" : `/api/employees/${editing?.code}`, {
      method: isCreate ? "POST" : "PUT",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setSubmitting(false);
    if (!response.ok) {
      setError(await responseError(response));
      return;
    }
    const result = (await response.json()) as EmployeeWriteResult;
    const saved = result.employee;
    setEditing(undefined);
    setNotice(
      isCreate
        ? `社員 ${saved.code} ${saved.fullName} を追加しました。employeeKey.csvは有効社員${result.csv.employeeCount}件で再生成済みです。${result.csv.backupPath ? ` 更新前CSVを ${result.csv.backupPath} へ保存しました。` : " 初回生成のため更新前バックアップはありません。"}`
        : `社員 ${saved.code} ${saved.fullName} を更新しました。employeeKey.csvは有効社員${result.csv.employeeCount}件で再生成済みです。${result.csv.backupPath ? ` 更新前CSVを ${result.csv.backupPath} へ保存しました。` : " 更新前バックアップはありません。"}`,
    );
    await Promise.all([loadEmployees(), loadConsistency()]);
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
            <label>ユーザー名<input name="username" autoComplete="username" required autoFocus /></label>
            <label>パスワード<input name="password" type="password" autoComplete="current-password" required /></label>
            {error && <p className="error-message" role="alert">{error}</p>}
            <button type="submit" disabled={submitting}>{submitting ? "ログイン中…" : "ログイン"}</button>
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

      <section className="hero compact-hero">
        <div>
          <h1>社員管理</h1>
          <p className="lead">SQLiteを正として社員情報を管理し、保存時に通知用CSVを安全に再生成します。</p>
        </div>
        <button className="button-primary" type="button" onClick={openCreate}>社員を追加</button>
      </section>

      <section className="summary-grid" aria-label="集計">
        <article><span>検索結果</span><strong>{counts.all}</strong></article>
        <article><span>結果内の有効</span><strong>{counts.enabled}</strong></article>
        <article><span>結果内の無効</span><strong>{counts.disabled}</strong></article>
        <article><span>Web状態</span><strong>{health?.status === "ok" ? "正常" : "確認中"}</strong></article>
        <article>
          <span>社員データ整合性</span>
          <strong className={consistency?.status === "mismatch" ? "status-danger" : "status-ok"}>
            {loadingConsistency ? "確認中" : consistency?.status === "ok" ? "一致" : consistency?.status === "mismatch" ? "不一致" : "確認失敗"}
          </strong>
        </article>
      </section>

      <section className="employee-card">
        <form className="toolbar" onSubmit={(event) => { event.preventDefault(); setQuery(queryInput.trim()); }}>
          <label className="search-field">検索<input value={queryInput} onChange={(event) => setQueryInput(event.target.value)} placeholder="社員番号・氏名・部署" /></label>
          <label>状態<select value={enabledFilter} onChange={(event) => setEnabledFilter(event.target.value)}>
            <option value="all">すべて</option><option value="enabled">有効</option><option value="disabled">無効</option>
          </select></label>
          <button className="button-primary" type="submit">検索</button>
          <button className="button-secondary" type="button" onClick={() => { setQueryInput(""); setQuery(""); setEnabledFilter("all"); }}>条件クリア</button>
          <button className="button-secondary" type="button" onClick={() => Promise.all([loadEmployees(), loadConsistency()])}>再読込</button>
        </form>
        {notice && <p className="success-message" role="status">{notice}</p>}
        {error && editing === undefined && <p className="error-message" role="alert">{error}</p>}
        <div className={`consistency-panel ${consistency?.status === "mismatch" ? "consistency-panel-danger" : ""}`}>
          <div>
            <strong>SQLite / employeeKey.csv</strong>
            {consistency?.status === "ok" && <p>整合しています（SQLite {consistency.databaseEmployees}件 / CSV {consistency.csvEmployees}件）。</p>}
            {consistency?.status === "mismatch" && (
              <p>
                不一致があります（SQLiteのみ {consistency.databaseOnlyCodes.length}件 / CSVのみ {consistency.csvOnlyCodes.length}件 / 項目差分 {consistency.fieldDifferences.length}件）。
              </p>
            )}
            {consistencyError && <p>確認失敗: {consistencyError}</p>}
            {!consistency && !consistencyError && <p>整合性を確認しています。</p>}
          </div>
          <button className="button-secondary" type="button" onClick={loadConsistency} disabled={loadingConsistency}>
            {loadingConsistency ? "確認中…" : "再確認"}
          </button>
          {consistency?.status === "mismatch" && (
            <details className="consistency-details">
              <summary>差分対象を表示</summary>
              {consistency.databaseOnlyCodes.length > 0 && <p>SQLiteのみ: {consistency.databaseOnlyCodes.join(", ")}</p>}
              {consistency.csvOnlyCodes.length > 0 && <p>CSVのみ: {consistency.csvOnlyCodes.join(", ")}</p>}
              {consistency.fieldDifferences.map((item) => <p key={item.code}>項目差分 {item.code}: {item.fields.join(", ")}</p>)}
            </details>
          )}
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>社員番号</th><th>氏名</th><th>部署</th><th>メール</th><th>上限分</th><th>状態</th><th /></tr></thead>
            <tbody>
              {employees.map((employee) => (
                <tr key={employee.code}>
                  <td className="mono">{employee.code}</td>
                  <td><strong>{employee.fullName}</strong></td>
                  <td>{employee.divisionName || employee.divisionCode}</td>
                  <td>{employee.email || "—"}</td>
                  <td>{employee.personalTargetMinutes ?? "—"}</td>
                  <td><span className={`badge ${employee.isEnabled ? "badge-ok" : "badge-off"}`}>{employee.isEnabled ? "有効" : "無効"}</span></td>
                  <td><button className="table-action" type="button" onClick={() => openEdit(employee)}>編集</button></td>
                </tr>
              ))}
              {!loadingEmployees && employees.length === 0 && <tr><td colSpan={7} className="empty-row">該当する社員はいません。</td></tr>}
            </tbody>
          </table>
        </div>
        {loadingEmployees && <p className="muted loading-line">読み込み中…</p>}
      </section>


      <section className="employee-card sync-card">
        <div className="sync-heading">
          <div>
            <p className="eyebrow">KING OF TIME</p>
            <h2>社員同期</h2>
            <p className="muted">取得とプレビューだけでは本番データを変更しません。</p>
            {syncStatus?.blocked && <p className="error-message">API利用禁止時間帯です（08:30〜10:00、17:30〜18:30）。</p>}
            {syncStatus?.running && <p className="muted">同期処理を実行中です。</p>}
            {syncStatus?.lastRun && (
              <div className="muted">
                <p>最終実行: {new Date(syncStatus.lastRun.executed_at).toLocaleString("ja-JP")} / 新規 {syncStatus.lastRun.created_count} / 更新 {syncStatus.lastRun.updated_count} / 再有効化 {syncStatus.lastRun.reactivated_count} / 無効化 {syncStatus.lastRun.disabled_count}</p>
                {syncStatus.lastRun.backup_path && <p>バックアップ: {syncStatus.lastRun.backup_path}</p>}
              </div>
            )}
          </div>
          <button className="button-secondary" type="button" onClick={loadKotPreview} disabled={syncing || syncStatus?.running || syncStatus?.blocked}>
            {syncing || syncStatus?.running ? "実行中…" : "KOTから取得"}
          </button>
        </div>
        {syncPreview && (
          <>
            <div className="sync-counts">
              <span>全社取得 {syncPreview.fetchedCount}</span>
              <span>同期対象 {syncPreview.targetCount}</span>
              <span>表示中 {visibleSyncDifferences.length}</span>
              <span>対象部署 {syncPreview.targetDivisionCodes.join(", ")}</span>
              <span>新規 {syncPreview.counts.create ?? 0}</span>
              <span>更新 {syncPreview.counts.update ?? 0}</span>
              <span>再有効化候補 {syncPreview.counts.reactivate ?? 0}</span>
              <span>無効化候補 {syncPreview.counts.disable ?? 0}</span>
              <span>変更なし {syncPreview.counts.unchanged ?? 0}</span>
              <span>勤怠管理なし {warningCounts.noAttendance}</span>
              <span>休職中 {warningCounts.onLeave}</span>
            </div>
            <div className="sync-filters" aria-label="KOT同期プレビューフィルタ">
              {(["create", "update", "reactivate", "disable", "unchanged"] as const).map((action) => (
                <label key={action}>
                  <input
                    type="checkbox"
                    checked={syncActions[action]}
                    onChange={(event) => setSyncActions({
                      ...syncActions,
                      [action]: event.target.checked,
                    })}
                  />
                  {action}
                </label>
              ))}
              <label>
                <input
                  type="checkbox"
                  checked={showNoAttendance}
                  onChange={(event) => setShowNoAttendance(event.target.checked)}
                />
                勤怠管理なしを表示
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={showOnLeave}
                  onChange={(event) => setShowOnLeave(event.target.checked)}
                />
                休職中を表示
              </label>
            </div>
            <div className="sync-selection-tools">
              <button
                className="button-secondary"
                type="button"
                onClick={() => setSelectedSyncCodes(Array.from(new Set([
                  ...selectedSyncCodes,
                  ...selectableVisibleCodes,
                ])))}
                disabled={selectableVisibleCodes.length === 0}
              >
                表示中を選択
              </button>
              <button
                className="button-secondary"
                type="button"
                onClick={() => setSelectedSyncCodes(
                  selectedSyncCodes.filter((code) => !selectableVisibleCodes.includes(code)),
                )}
                disabled={selectableVisibleCodes.length === 0}
              >
                表示中を解除
              </button>
              {hiddenSelectedCount > 0 && (
                <span className="warning-text">非表示の選択 {hiddenSelectedCount}件</span>
              )}
            </div>
            <div className="table-wrap">
              <table className="sync-table">
                <thead><tr><th>反映</th><th>社員番号</th><th>判定</th><th>変更前</th><th>変更後</th><th>変更項目</th><th>注意</th></tr></thead>
                <tbody>
                  {visibleSyncDifferences.map((item) => {
                    const selectable = item.action !== "unchanged";
                    const checked = selectedSyncCodes.includes(item.code);
                    const current = item.current as Record<string, string> | null;
                    const proposed = item.proposed as Record<string, string> | null;
                    const changedLabels: Record<string, string> = {
                      lastName: "氏",
                      firstName: "名",
                      email: "メール",
                      divisionCode: "部署コード",
                      divisionName: "部署名",
                      kotExists: "KOT存在状態",
                      kotKey: "KOT Key変更あり",
                    };
                    return (
                      <tr key={item.code} className={`sync-row sync-row-${item.action}`}>
                        <td><input type="checkbox" disabled={!selectable} checked={selectable && checked} onChange={(event) => setSelectedSyncCodes(event.target.checked ? [...selectedSyncCodes, item.code] : selectedSyncCodes.filter((code) => code !== item.code))} /></td>
                        <td className="mono">{item.code}</td>
                        <td><span className={`sync-badge sync-badge-${item.action}`}>{item.action}</span></td>
                        <td>{current ? `${current.lastName ?? ""}${current.firstName ?? ""} / ${current.divisionName ?? current.divisionCode ?? ""}` : "—"}</td>
                        <td>{proposed ? `${proposed.lastName ?? ""}${proposed.firstName ?? ""} / ${proposed.divisionName ?? proposed.divisionCode ?? ""}` : "—"}</td>
                        <td>{item.changedFields.map((field) => changedLabels[field] ?? field).join("、") || "—"}</td>
                        <td>{item.warnings.join("、") || "—"}</td>
                      </tr>
                    );
                  })}
                  {visibleSyncDifferences.length === 0 && (
                    <tr><td colSpan={7} className="empty-row">条件に一致する差分はありません。</td></tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="sync-actions">
              <span className="muted">選択 {selectedSyncCodes.length}件</span>
              <button className="button-primary" type="button" disabled={syncing || selectedSyncCodes.length === 0} onClick={applyKotPreview}>選択した差分を反映</button>
            </div>
          </>
        )}
      </section>

      {editing !== undefined && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => !submitting && setEditing(undefined)}>
          <section className="modal" role="dialog" aria-modal="true" aria-labelledby="employee-form-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className="modal-heading"><div><p className="eyebrow">EMPLOYEE</p><h2 id="employee-form-title">{editing === null ? "社員を追加" : "社員を編集"}</h2></div><button className="icon-button" type="button" onClick={() => setEditing(undefined)}>×</button></div>
            <form className="employee-form" onSubmit={saveEmployee}>
              <div className="form-grid">
                <label>社員番号<input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} required disabled={editing !== null} /></label>
                <label>KOT Key<input type="password" value={form.employeeKey} onChange={(e) => setForm({ ...form, employeeKey: e.target.value })} required={editing === null} placeholder={editing ? "変更時のみ入力" : "必須"} autoComplete="off" /></label>
                <label>氏<input value={form.lastName} onChange={(e) => setForm({ ...form, lastName: e.target.value })} required /></label>
                <label>名<input value={form.firstName} onChange={(e) => setForm({ ...form, firstName: e.target.value })} required /></label>
                <label>部署コード<input value={form.divisionCode} onChange={(e) => setForm({ ...form, divisionCode: e.target.value })} required /></label>
                <label>部署名<input value={form.divisionName} onChange={(e) => setForm({ ...form, divisionName: e.target.value })} /></label>
                <label className="wide">メールアドレス<input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
                <label>個人別残業上限分<input type="number" min="0" value={form.personalTargetMinutes} onChange={(e) => setForm({ ...form, personalTargetMinutes: e.target.value })} /></label>
                <label className="switch-label"><input type="checkbox" checked={form.isEnabled} onChange={(e) => setForm({ ...form, isEnabled: e.target.checked, disabledReason: e.target.checked ? "" : form.disabledReason })} />有効社員</label>
                {!form.isEnabled && <label className="wide">無効理由<input value={form.disabledReason} onChange={(e) => setForm({ ...form, disabledReason: e.target.value })} required /></label>}
                <label className="wide">管理メモ<textarea value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} rows={3} /></label>
              </div>
              <p className="security-note">KOT Keyは保存専用です。画面・APIレスポンスには表示されません。</p>
              {error && <p className="error-message" role="alert">{error}</p>}
              <div className="form-actions"><button className="button-secondary" type="button" onClick={() => setEditing(undefined)} disabled={submitting}>キャンセル</button><button className="button-primary" type="submit" disabled={submitting}>{submitting ? "保存中…" : "保存してCSV再生成"}</button></div>
            </form>
          </section>
        </div>
      )}
    </main>
  );
}
