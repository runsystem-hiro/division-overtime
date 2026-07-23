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
  action: "create" | "update" | "disable" | "unchanged";
  current: Record<string, unknown> | null;
  proposed: Record<string, unknown> | null;
  warnings: string[];
};

type SyncPreview = {
  previewId: string;
  counts: Record<string, number>;
  differences: SyncDifference[];
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
  const [query, setQuery] = useState("");
  const [enabledFilter, setEnabledFilter] = useState("all");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [loadingEmployees, setLoadingEmployees] = useState(false);
  const [editing, setEditing] = useState<Employee | null | undefined>(undefined);
  const [form, setForm] = useState<EmployeeForm>(emptyForm);
  const [syncPreview, setSyncPreview] = useState<SyncPreview | null>(null);
  const [selectedSyncCodes, setSelectedSyncCodes] = useState<string[]>([]);
  const [syncing, setSyncing] = useState(false);

  const loadCurrentUser = useCallback(async () => {
    const response = await fetch("/api/auth/me", { credentials: "same-origin" });
    if (response.status === 401) {
      setUser(null);
      return;
    }
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    setUser((await response.json()) as CurrentUser);
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
    ])
      .then(([healthResponse]) => setHealth(healthResponse))
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "情報を取得できませんでした");
      });
  }, [loadEmployees, user]);

  const counts = useMemo(() => ({
    all: employees.length,
    enabled: employees.filter((employee) => employee.isEnabled).length,
    disabled: employees.filter((employee) => !employee.isEnabled).length,
  }), [employees]);

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
    setSelectedSyncCodes(preview.differences
      .filter((item) => item.action !== "unchanged")
      .map((item) => item.code));
  }

  async function applyKotPreview() {
    if (!syncPreview || selectedSyncCodes.length === 0) return;
    if (!window.confirm(`${selectedSyncCodes.length}件をSQLiteとemployeeKey.csvへ反映します。`)) return;
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
    setNotice("KOT社員差分を反映し、employeeKey.csvを再生成しました。");
    setSyncPreview(null);
    setSelectedSyncCodes([]);
    await loadEmployees();
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
    setEditing(undefined);
    setNotice("社員情報と employeeKey.csv を更新しました。");
    await loadEmployees();
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
        <article><span>表示件数</span><strong>{counts.all}</strong></article>
        <article><span>有効</span><strong>{counts.enabled}</strong></article>
        <article><span>無効</span><strong>{counts.disabled}</strong></article>
        <article><span>Web状態</span><strong>{health?.status === "ok" ? "正常" : "確認中"}</strong></article>
      </section>

      <section className="employee-card">
        <div className="toolbar">
          <label className="search-field">検索<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="社員番号・氏名・部署" /></label>
          <label>状態<select value={enabledFilter} onChange={(event) => setEnabledFilter(event.target.value)}>
            <option value="all">すべて</option><option value="enabled">有効</option><option value="disabled">無効</option>
          </select></label>
          <button className="button-secondary" type="button" onClick={() => loadEmployees()}>再読込</button>
        </div>
        {notice && <p className="success-message" role="status">{notice}</p>}
        {error && editing === undefined && <p className="error-message" role="alert">{error}</p>}
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
          </div>
          <button className="button-secondary" type="button" onClick={loadKotPreview} disabled={syncing}>
            {syncing ? "取得中…" : "KOTから取得"}
          </button>
        </div>
        {syncPreview && (
          <>
            <div className="sync-counts">
              <span>新規 {syncPreview.counts.create ?? 0}</span>
              <span>更新 {syncPreview.counts.update ?? 0}</span>
              <span>無効化候補 {syncPreview.counts.disable ?? 0}</span>
              <span>変更なし {syncPreview.counts.unchanged ?? 0}</span>
            </div>
            <div className="table-wrap">
              <table className="sync-table">
                <thead><tr><th>反映</th><th>社員番号</th><th>判定</th><th>変更前</th><th>変更後</th><th>注意</th></tr></thead>
                <tbody>
                  {syncPreview.differences.map((item) => {
                    const selectable = item.action !== "unchanged";
                    const checked = selectedSyncCodes.includes(item.code);
                    const current = item.current as Record<string, string> | null;
                    const proposed = item.proposed as Record<string, string> | null;
                    return (
                      <tr key={item.code}>
                        <td><input type="checkbox" disabled={!selectable} checked={selectable && checked} onChange={(event) => setSelectedSyncCodes(event.target.checked ? [...selectedSyncCodes, item.code] : selectedSyncCodes.filter((code) => code !== item.code))} /></td>
                        <td className="mono">{item.code}</td>
                        <td>{item.action}</td>
                        <td>{current ? `${current.lastName ?? ""}${current.firstName ?? ""} / ${current.divisionName ?? current.divisionCode ?? ""}` : "—"}</td>
                        <td>{proposed ? `${proposed.lastName ?? ""}${proposed.firstName ?? ""} / ${proposed.divisionName ?? proposed.divisionCode ?? ""}` : "—"}</td>
                        <td>{item.warnings.join("、") || "—"}</td>
                      </tr>
                    );
                  })}
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
