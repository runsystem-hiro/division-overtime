import {
  type CSSProperties,
  type FormEvent,
  type MouseEvent,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { ConfirmDialog } from "./ConfirmDialog";
import { NotificationHistory } from "./NotificationHistory";
import { ModalLayer } from "./ModalLayer";
import { Toast } from "./Toast";

type Health = {
  status: string;
  service: string;
  version: string;
  serverTime: string;
  timezone: string;
  environment: string;
  kotSyncEnabled: boolean;
  kotSyncMock: boolean;
};

type EnvironmentPresentation = {
  label: "PRODUCTION" | "DEVELOPMENT" | "TEST" | "UNKNOWN";
  className: string;
};

function getEnvironmentPresentation(
  environment?: string,
): EnvironmentPresentation {
  switch (environment) {
    case "production":
      return { label: "PRODUCTION", className: "environment-production" };
    case "development":
      return { label: "DEVELOPMENT", className: "environment-development" };
    case "test":
      return { label: "TEST", className: "environment-test" };
    default:
      return { label: "UNKNOWN", className: "environment-unknown" };
  }
}

type CurrentUser = {
  username: string;
  role: "admin" | "viewer";
  expiresAt: string;
  identitySource?: "local" | "cloudflare_access";
  elevatedUntil?: string | null;
  logoutUrl?: string | null;
};

type AuthStatus = {
  authenticated: boolean;
  user: CurrentUser | null;
};

type SortDirection = "asc" | "desc";
type EmployeeSortKey = "code" | "name" | "division" | "target" | "status";

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

const employeeSortLabels: Record<EmployeeSortKey, string> = {
  code: "社員番号",
  name: "社員情報",
  division: "所属",
  target: "上限分",
  status: "状態",
};

const employeeCollator = new Intl.Collator("ja", { numeric: true, sensitivity: "base" });

const syncActionLabels = {
  create: "新規",
  update: "更新",
  reactivate: "再有効化",
  disable: "無効化",
  unchanged: "変更なし",
} as const;

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

type KotSyncDivision = {
  divisionCode: string;
  isEnabled: boolean;
  createdAt: string;
  updatedAt: string;
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

type EmployeeDeleteResult = {
  deletedEmployee: Employee;
  csv: EmployeeWriteResult["csv"];
  backupPath: string;
};

type EmployeeConsistency = {
  status: "ok" | "mismatch";
  databaseEmployees: number;
  csvEmployees: number;
  databaseOnlyCodes: string[];
  csvOnlyCodes: string[];
  fieldDifferences: { code: string; fields: string[] }[];
};

type ConfirmAction =
  | { kind: "sync"; title: string; description: string }
  | { kind: "delete"; title: string; description: string }
  | { kind: "division-delete"; title: string; description: string; divisionCode: string }
  | null;

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

function NavIcon({ name }: { name: "employees" | "sync" | "history" }) {
  const paths = {
    employees: (
      <>
        <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
        <circle cx="9" cy="7" r="4" />
        <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
        <path d="M16 3.13a4 4 0 0 1 0 7.75" />
      </>
    ),
    sync: (
      <>
        <path d="M20 7h-9" />
        <path d="m16 3 4 4-4 4" />
        <path d="M4 17h9" />
        <path d="m8 21-4-4 4-4" />
      </>
    ),
    history: (
      <>
        <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
        <path d="M3 3v5h5" />
        <path d="M12 7v5l3 2" />
      </>
    ),
  };
  return (
    <svg
      className="nav-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

function UtilityIcon({
  name,
}: {
  name: "logout" | "activity" | "shield" | "user" | "close";
}) {
  const paths = {
    logout: (
      <>
        <path d="M10 17l5-5-5-5" />
        <path d="M15 12H3" />
        <path d="M21 19V5a2 2 0 0 0-2-2h-6" />
      </>
    ),
    activity: (
      <>
        <path d="M3 12h4l2-7 4 14 2-7h6" />
      </>
    ),
    shield: (
      <>
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" />
        <path d="M9 12l2 2 4-4" />
      </>
    ),
    user: (
      <>
        <circle cx="12" cy="8" r="4" />
        <path d="M4 22c0-4 3.6-7 8-7s8 3 8 7" />
      </>
    ),
    close: (
      <>
        <path d="M6 6l12 12" />
        <path d="M18 6L6 18" />
      </>
    ),
  };
  return (
    <svg
      className="utility-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

export function App() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const isAdmin = user?.role !== "viewer";
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [health, setHealth] = useState<Health | null>(null);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [enabledFilter, setEnabledFilter] = useState("all");
  const [employeeSort, setEmployeeSort] = useState<{ key: EmployeeSortKey; direction: SortDirection }>({ key: "code", direction: "asc" });
  const [consistency, setConsistency] = useState<EmployeeConsistency | null>(
    null,
  );
  const [consistencyError, setConsistencyError] = useState<string | null>(null);
  const [loadingConsistency, setLoadingConsistency] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmAction, setConfirmAction] = useState<ConfirmAction>(null);
  const [submitting, setSubmitting] = useState(false);
  const [loadingEmployees, setLoadingEmployees] = useState(false);
  const [editing, setEditing] = useState<Employee | null | undefined>(
    undefined,
  );
  const [form, setForm] = useState<EmployeeForm>(emptyForm);
  const [syncPreview, setSyncPreview] = useState<SyncPreview | null>(null);
  const [selectedSyncCodes, setSelectedSyncCodes] = useState<string[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState<KotSyncStatus | null>(null);
  const [syncDivisions, setSyncDivisions] = useState<KotSyncDivision[]>([]);
  const [newDivisionCode, setNewDivisionCode] = useState("");
  const [divisionAdding, setDivisionAdding] = useState(false);
  const [divisionPendingCode, setDivisionPendingCode] = useState<string | null>(null);
  const [syncActions, setSyncActions] = useState({
    create: true,
    update: true,
    reactivate: true,
    disable: true,
    unchanged: false,
  });
  const [showNoAttendance, setShowNoAttendance] = useState(false);
  const [showOnLeave, setShowOnLeave] = useState(false);

  const [path, setPath] = useState(() => window.location.pathname);
  const [healthOpen, setHealthOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [elevationOpen, setElevationOpen] = useState(false);
  const [elevationSubmitting, setElevationSubmitting] = useState(false);
  const [elevationError, setElevationError] = useState<string | null>(null);
  const [healthPopoverStyle, setHealthPopoverStyle] = useState<CSSProperties>();
  const [accountPopoverStyle, setAccountPopoverStyle] = useState<CSSProperties>();
  const healthTriggerRef = useRef<HTMLButtonElement>(null);
  const accountTriggerRef = useRef<HTMLButtonElement>(null);
  const healthPopoverRef = useRef<HTMLElement>(null);
  const accountPopoverRef = useRef<HTMLDivElement>(null);
  const logoutButtonRef = useRef<HTMLButtonElement>(null);
  const elevationTriggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const handlePopState = () => setPath(window.location.pathname);
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    if (!elevationOpen) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !elevationSubmitting) {
        setElevationOpen(false);
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [elevationOpen, elevationSubmitting]);

  useEffect(() => {
    if (!elevationOpen) elevationTriggerRef.current?.focus();
  }, [elevationOpen]);

  useLayoutEffect(() => {
    if (!healthOpen && !accountOpen) return;

    const placePopover = (
      trigger: HTMLElement | null,
      width: number,
      setStyle: (style: CSSProperties) => void,
      placement: "below-end" | "below-start",
    ) => {
      if (!trigger) return;
      const rect = trigger.getBoundingClientRect();
      const viewportPadding = 16;
      const availableWidth = Math.max(0, window.innerWidth - viewportPadding * 2);
      const actualWidth = Math.min(width, availableWidth);
      const preferredLeft =
        placement === "below-start"
          ? rect.left - actualWidth - 10
          : rect.right - actualWidth;
      const left = Math.min(
        Math.max(viewportPadding, preferredLeft),
        Math.max(
          viewportPadding,
          window.innerWidth - actualWidth - viewportPadding,
        ),
      );
      setStyle({ top: rect.bottom + 10, left, width: actualWidth });
    };

    const updatePositions = () => {
      if (healthOpen)
        placePopover(
          healthTriggerRef.current,
          250,
          setHealthPopoverStyle,
          "below-start",
        );
      if (accountOpen)
        placePopover(
          accountTriggerRef.current,
          168,
          setAccountPopoverStyle,
          "below-end",
        );
    };

    updatePositions();
    window.addEventListener("resize", updatePositions);
    window.addEventListener("scroll", updatePositions, true);
    return () => {
      window.removeEventListener("resize", updatePositions);
      window.removeEventListener("scroll", updatePositions, true);
    };
  }, [healthOpen, accountOpen]);

  useEffect(() => {
    if (!healthOpen && !accountOpen) return;

    const closePopovers = (restoreFocus: boolean) => {
      const trigger = accountOpen
        ? accountTriggerRef.current
        : healthTriggerRef.current;
      setHealthOpen(false);
      setAccountOpen(false);
      if (restoreFocus) window.requestAnimationFrame(() => trigger?.focus());
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !elevationOpen) closePopovers(true);
    };
    const handlePointerDown = (event: PointerEvent) => {
      if (elevationOpen) return;
      const target = event.target as Node;
      const insideHealth =
        healthTriggerRef.current?.contains(target) ||
        healthPopoverRef.current?.contains(target);
      const insideAccount =
        accountTriggerRef.current?.contains(target) ||
        accountPopoverRef.current?.contains(target);
      if (!insideHealth && !insideAccount) closePopovers(false);
    };

    document.addEventListener("keydown", handleKeyDown);
    document.addEventListener("pointerdown", handlePointerDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("pointerdown", handlePointerDown);
    };
  }, [healthOpen, accountOpen, elevationOpen]);

  useEffect(() => {
    if (accountOpen) logoutButtonRef.current?.focus();
  }, [accountOpen, accountPopoverStyle]);

  function navigate(event: MouseEvent<HTMLAnchorElement>, nextPath: string) {
    event.preventDefault();
    if (window.location.pathname === nextPath) return;

    const updatePath = () => {
      window.history.pushState({}, "", nextPath);
      setPath(nextPath);
      setNotice(null);
      setError(null);
    };
    const transitionDocument = document as Document & {
      startViewTransition?: (callback: () => void) => void;
    };
    if (transitionDocument.startViewTransition) {
      transitionDocument.startViewTransition(updatePath);
      return;
    }
    updatePath();
  }

  const loadCurrentUser = useCallback(async () => {
    const response = await fetch("/api/auth/status", {
      credentials: "same-origin",
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const status = (await response.json()) as AuthStatus;
    setUser(status.authenticated ? status.user : null);
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
      setConsistencyError(
        reason instanceof Error
          ? reason.message
          : "整合性を確認できませんでした",
      );
    } finally {
      setLoadingConsistency(false);
    }
  }, []);

  const loadKotSyncStatus = useCallback(async () => {
    const response = await fetch("/api/kot-sync/status", {
      credentials: "same-origin",
    });
    if (response.status === 403 || response.status === 503) {
      setSyncStatus(null);
      return;
    }
    if (!response.ok) throw new Error(await responseError(response));
    setSyncStatus((await response.json()) as KotSyncStatus);
  }, []);

  const loadSyncDivisions = useCallback(async () => {
    if (!isAdmin) {
      setSyncDivisions([]);
      return;
    }
    const response = await fetch("/api/settings/kot-sync-divisions", {
      credentials: "same-origin",
    });
    if (response.status === 403) {
      setSyncDivisions([]);
      return;
    }
    if (!response.ok) throw new Error(await responseError(response));
    setSyncDivisions((await response.json()) as KotSyncDivision[]);
  }, [isAdmin]);

  const loadEmployees = useCallback(async () => {
    setLoadingEmployees(true);
    const params = new URLSearchParams({ enabled: enabledFilter });
    if (query.trim()) params.set("query", query.trim());
    const response = await fetch(`/api/employees?${params}`, {
      credentials: "same-origin",
    });
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
    if (user?.identitySource !== "cloudflare_access") return;
    const timer = window.setInterval(() => {
      loadCurrentUser().catch(() => setUser(null));
    }, 60_000);
    return () => window.clearInterval(timer);
  }, [loadCurrentUser, user?.identitySource]);

  useEffect(() => {
    if (!user) return;
    Promise.all([
      fetch("/api/system/health", { credentials: "same-origin" }).then(
        async (response) => {
          if (!response.ok) throw new Error(await responseError(response));
          return response.json() as Promise<Health>;
        },
      ),
      loadEmployees(),
      ...(isAdmin ? [loadConsistency(), loadSyncDivisions()] : []),
      loadKotSyncStatus(),
    ])
      .then(([healthResponse]) => setHealth(healthResponse))
      .catch((reason: unknown) => {
        setError(
          reason instanceof Error
            ? reason.message
            : "情報を取得できませんでした",
        );
      });
  }, [isAdmin, loadConsistency, loadEmployees, loadKotSyncStatus, loadSyncDivisions, user]);

  const counts = useMemo(
    () => ({
      all: employees.length,
      enabled: employees.filter((employee) => employee.isEnabled).length,
      disabled: employees.filter((employee) => !employee.isEnabled).length,
    }),
    [employees],
  );

  const sortedEmployees = useMemo(() => {
    const direction = employeeSort.direction === "asc" ? 1 : -1;
    return [...employees].sort((left, right) => {
      let comparison = 0;
      if (employeeSort.key === "code") comparison = employeeCollator.compare(left.code, right.code);
      if (employeeSort.key === "name") comparison = employeeCollator.compare(left.fullName, right.fullName);
      if (employeeSort.key === "division") comparison = employeeCollator.compare(left.divisionName || left.divisionCode, right.divisionName || right.divisionCode);
      if (employeeSort.key === "target") comparison = (left.personalTargetMinutes ?? Number.POSITIVE_INFINITY) - (right.personalTargetMinutes ?? Number.POSITIVE_INFINITY);
      if (employeeSort.key === "status") comparison = Number(right.isEnabled) - Number(left.isEnabled);
      if (comparison === 0) comparison = employeeCollator.compare(left.code, right.code);
      return comparison * direction;
    });
  }, [employeeSort, employees]);

  const hasEmployeeFilters = query !== "" || enabledFilter !== "all";

  function toggleEmployeeSort(key: EmployeeSortKey) {
    setEmployeeSort((current) => ({
      key,
      direction: current.key === key && current.direction === "asc" ? "desc" : "asc",
    }));
  }

  function clearEmployeeFilters() {
    setQueryInput("");
    setQuery("");
    setEnabledFilter("all");
  }

  const visibleSyncDifferences = useMemo(() => {
    if (!syncPreview) return [];
    return syncPreview.differences.filter((item) => {
      if (!syncActions[item.action]) return false;
      if (!showNoAttendance && item.warnings.includes("勤怠管理なし"))
        return false;
      if (!showOnLeave && item.warnings.includes("休職中")) return false;
      return true;
    });
  }, [showNoAttendance, showOnLeave, syncActions, syncPreview]);

  const selectableVisibleCodes = useMemo(
    () =>
      visibleSyncDifferences
        .filter((item) => item.action !== "unchanged")
        .map((item) => item.code),
    [visibleSyncDifferences],
  );

  const hiddenSelectedCount = selectedSyncCodes.filter(
    (code) => !selectableVisibleCodes.includes(code),
  ).length;

  const selectedSyncCounts = useMemo(() => {
    const selected =
      syncPreview?.differences.filter((item) =>
        selectedSyncCodes.includes(item.code),
      ) ?? [];
    return {
      create: selected.filter((item) => item.action === "create").length,
      update: selected.filter((item) => item.action === "update").length,
      reactivate: selected.filter((item) => item.action === "reactivate")
        .length,
      disable: selected.filter((item) => item.action === "disable").length,
    };
  }, [selectedSyncCodes, syncPreview]);

  const allVisibleSelected =
    selectableVisibleCodes.length > 0 &&
    selectableVisibleCodes.every((code) => selectedSyncCodes.includes(code));

  const warningCounts = useMemo(() => {
    const differences = syncPreview?.differences ?? [];
    return {
      noAttendance: differences.filter((item) =>
        item.warnings.includes("勤怠管理なし"),
      ).length,
      onLeave: differences.filter((item) => item.warnings.includes("休職中"))
        .length,
    };
  }, [syncPreview]);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const loginFormElement = event.currentTarget;
    const loginForm = new FormData(loginFormElement);
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
      setError(
        response.status === 429
          ? "ログイン試行回数が上限に達しました。しばらく待ってから再試行してください。"
          : "ユーザー名またはパスワードが正しくありません。",
      );
      return;
    }
    setUser((await response.json()) as CurrentUser);
    loginFormElement.reset();
  }

  async function handleLogout() {
    const logoutUrl = user?.logoutUrl;
    await fetch("/api/auth/logout", {
      method: "POST",
      credentials: "same-origin",
    });
    if (logoutUrl) {
      window.location.assign(logoutUrl);
      return;
    }
    setUser(null);
    setHealth(null);
    setEmployees([]);
    setError(null);
    setNotice(null);
    setConfirmAction(null);
  }

  async function handleElevation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setElevationSubmitting(true);
    setElevationError(null);
    const form = new FormData(event.currentTarget);
    const response = await fetch("/api/auth/elevate", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: form.get("password") }),
    });
    setElevationSubmitting(false);
    if (!response.ok) {
      setElevationError(
        response.status === 429
          ? "認証試行回数が上限に達しました。しばらく待ってから再試行してください。"
          : "管理者パスワードが正しくありません。閲覧者モードを継続します。",
      );
      return;
    }
    setUser((await response.json()) as CurrentUser);
    setElevationOpen(false);
    setAccountOpen(false);
    setNotice("管理者モードへ切り替えました。");
  }

  async function handleDowngrade() {
    const response = await fetch("/api/auth/downgrade", {
      method: "POST",
      credentials: "same-origin",
    });
    if (!response.ok) {
      setError(await responseError(response));
      return;
    }
    setUser((await response.json()) as CurrentUser);
    setAccountOpen(false);
    setNotice("閲覧者モードへ切り替えました。");
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

  async function addSyncDivision(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setDivisionAdding(true);
    setError(null);
    const response = await fetch("/api/settings/kot-sync-divisions", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ divisionCode: newDivisionCode }),
    });
    setDivisionAdding(false);
    if (!response.ok) {
      setError(await responseError(response));
      return;
    }
    const created = (await response.json()) as KotSyncDivision;
    setNewDivisionCode("");
    setSyncPreview(null);
    setNotice(`部門コード ${created.divisionCode} を同期対象として追加しました。`);
    await loadSyncDivisions();
  }

  async function setSyncDivisionEnabled(item: KotSyncDivision, isEnabled: boolean) {
    setDivisionPendingCode(item.divisionCode);
    setError(null);
    const response = await fetch(
      `/api/settings/kot-sync-divisions/${encodeURIComponent(item.divisionCode)}`,
      {
        method: "PUT",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ isEnabled }),
      },
    );
    setDivisionPendingCode(null);
    if (!response.ok) {
      setError(await responseError(response));
      return;
    }
    setSyncPreview(null);
    setNotice(
      `部門コード ${item.divisionCode} を${isEnabled ? "有効化" : "無効化"}しました。`,
    );
    await loadSyncDivisions();
  }

  function confirmDeleteSyncDivision(item: KotSyncDivision) {
    setConfirmAction({
      kind: "division-delete",
      divisionCode: item.divisionCode,
      title: "同期対象部門を削除しますか",
      description: [
        `部門コード「${item.divisionCode}」を同期対象設定から削除します。`,
        "次回以降のKOT同期では対象外になります。",
        "既存の社員データ、同期履歴、バックアップ、通知履歴は削除されません。",
      ].join("\n"),
    });
  }

  async function executeDeleteSyncDivision() {
    if (!confirmAction || confirmAction.kind !== "division-delete") return;
    const divisionCode = confirmAction.divisionCode;
    setConfirmAction(null);
    setDivisionPendingCode(divisionCode);
    setError(null);
    const response = await fetch(
      `/api/settings/kot-sync-divisions/${encodeURIComponent(divisionCode)}`,
      { method: "DELETE", credentials: "same-origin" },
    );
    setDivisionPendingCode(null);
    if (!response.ok) {
      setError(await responseError(response));
      return;
    }
    setSyncPreview(null);
    setNotice(`部門コード ${divisionCode} を同期対象設定から削除しました。`);
    await loadSyncDivisions();
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
      reactivate: selected.filter((item) => item.action === "reactivate")
        .length,
      disable: selected.filter((item) => item.action === "disable").length,
    };
    const description = [
      `${selectedSyncCodes.length}件をSQLiteとemployeeKey.csvへ反映します。`,
      `新規 ${detail.create}件 / 更新 ${detail.update}件 / 再有効化 ${detail.reactivate}件 / 無効化 ${detail.disable}件`,
      detail.reactivate > 0 ? "再有効化した社員は通知対象へ戻ります。" : "",
    ]
      .filter(Boolean)
      .join("\n");
    setConfirmAction({
      kind: "sync",
      title: "KOT社員差分を反映しますか",
      description,
    });
  }

  async function executeKotPreview() {
    if (!syncPreview || selectedSyncCodes.length === 0) return;
    setConfirmAction(null);
    setSyncing(true);
    setError(null);
    const response = await fetch("/api/kot-sync/apply", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        previewId: syncPreview.previewId,
        employeeCodes: selectedSyncCodes,
      }),
    });
    setSyncing(false);
    if (!response.ok) {
      setError(await responseError(response));
      return;
    }
    const result = (await response.json()) as KotSyncApplyResult;
    setNotice(
      `KOT社員差分を反映し、employeeKey.csvを再生成しました。再有効化 ${result.counts.reactivated}件。反映前バックアップを ${result.backupPath} へ保存しました。`,
    );
    setSyncPreview(null);
    setSelectedSyncCodes([]);
    await Promise.all([
      loadEmployees(),
      ...(isAdmin ? [loadConsistency(), loadSyncDivisions()] : []),
      loadKotSyncStatus(),
    ]);
  }

  async function deleteEmployee() {
    if (!editing) return;
    const description = [
      `社員 ${editing.code} ${editing.fullName} を社員管理から削除します。`,
      "削除後はemployeeKey.csvから除外されます。",
      "KOTに在籍中の場合は、次回同期で新規候補として再表示されることがあります。",
    ].join("\n");
    setConfirmAction({
      kind: "delete",
      title: "社員を削除しますか",
      description,
    });
  }

  async function executeDeleteEmployee() {
    if (!editing) return;
    setConfirmAction(null);
    setSubmitting(true);
    setError(null);
    setNotice(null);
    const response = await fetch(`/api/employees/${editing.code}`, {
      method: "DELETE",
      credentials: "same-origin",
    });
    setSubmitting(false);
    if (!response.ok) {
      setError(await responseError(response));
      return;
    }
    const result = (await response.json()) as EmployeeDeleteResult;
    setEditing(undefined);
    setSyncPreview(null);
    setSelectedSyncCodes([]);
    setNotice(
      `社員 ${result.deletedEmployee.code} ${result.deletedEmployee.fullName} を削除しました。` +
        ` employeeKey.csvは有効社員${result.csv.employeeCount}件で再生成済みです。` +
        ` 削除前バックアップを ${result.backupPath} へ保存しました。`,
    );
    await Promise.all([
      loadEmployees(),
      ...(isAdmin ? [loadConsistency(), loadSyncDivisions()] : []),
      loadKotSyncStatus(),
    ]);
  }

  async function saveEmployee(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setNotice(null);
    const payload = {
      ...form,
      employeeKey: form.employeeKey || null,
      personalTargetMinutes:
        form.personalTargetMinutes === ""
          ? null
          : Number(form.personalTargetMinutes),
    };
    const isCreate = editing === null;
    const response = await fetch(
      isCreate ? "/api/employees" : `/api/employees/${editing?.code}`,
      {
        method: isCreate ? "POST" : "PUT",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
    );
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
    return (
      <main className="center-shell">
        <p className="muted">認証状態を確認しています…</p>
      </main>
    );
  }

  if (!user) {
    return (
      <main className="login-shell ambient-shell">
        <section className="login-card">
          <p className="eyebrow">DIVISION OVERTIME</p>
          <h1>管理者ログイン</h1>
          <p className="lead">
            社員設定を管理するため、認証情報を入力してください。
          </p>
          <form className="login-form" onSubmit={handleLogin}>
            <label>
              ユーザー名
              <input
                name="username"
                autoComplete="username"
                required
                autoFocus
              />
            </label>
            <label>
              パスワード
              <input
                name="password"
                type="password"
                autoComplete="current-password"
                required
              />
            </label>
            {error && (
              <p className="error-message" role="alert">
                {error}
              </p>
            )}
            <button type="submit" disabled={submitting} aria-busy={submitting}>
              {submitting ? "ログイン中…" : "ログイン"}
            </button>
          </form>
        </section>
      </main>
    );
  }

  const environmentPresentation = getEnvironmentPresentation(
    health?.environment,
  );
  const environmentLabel = environmentPresentation.label;
  const healthLabel = health?.status === "ok" ? "正常" : "確認中";

  return (
    <div className="app-shell ambient-shell" data-page={path === "/" ? "employees" : path === "/kot-sync" ? "sync" : path === "/notifications" ? "history" : "unknown"}>
      <header className="app-topbar">
        <div className="header-brand" aria-label="division overtime">
          <strong>division overtime</strong>
          <span
            className={`environment-badge ${environmentPresentation.className}`}
          >
            {environmentLabel}
          </span>
        </div>

        <nav className="app-nav" aria-label="管理画面">
          <a
            className={path === "/" ? "active" : ""}
            href="/"
            onClick={(event) => navigate(event, "/")}
          >
            <NavIcon name="employees" />
            <span>社員</span>
          </a>
          <a
            className={path === "/kot-sync" ? "active" : ""}
            href="/kot-sync"
            onClick={(event) => navigate(event, "/kot-sync")}
          >
            <NavIcon name="sync" />
            <span>同期</span>
          </a>
          <a
            className={path === "/notifications" ? "active" : ""}
            href="/notifications"
            onClick={(event) => navigate(event, "/notifications")}
          >
            <NavIcon name="history" />
            <span>履歴</span>
          </a>
        </nav>

        <div className="header-actions">
          <div className="header-popover-wrap">
            <button
              ref={healthTriggerRef}
              className="health-trigger"
              type="button"
              aria-expanded={healthOpen}
              aria-haspopup="dialog"
              onClick={() => {
                setHealthOpen((open) => !open);
                setAccountOpen(false);
              }}
            >
              <span
                className={`status-dot ${health?.status === "ok" ? "status-dot-ok" : ""}`}
              />
              <span>{healthLabel}</span>
            </button>
            {healthOpen &&
              healthPopoverStyle &&
              createPortal(
                <section
                  ref={healthPopoverRef}
                  className="header-popover health-popover header-popover-portal"
                  style={healthPopoverStyle}
                  role="dialog"
                  aria-label="システム状態"
                >
                  <div className="popover-heading">
                    <UtilityIcon name="activity" />
                    <strong>システム状態</strong>
                  </div>
                  <dl>
                    <div>
                      <dt>状態</dt>
                      <dd>{healthLabel}</dd>
                    </div>
                    <div>
                      <dt>環境</dt>
                      <dd>{environmentLabel}</dd>
                    </div>
                    <div>
                      <dt>Version</dt>
                      <dd>{health?.version ?? "-"}</dd>
                    </div>
                    <div>
                      <dt>Frontend</dt>
                      <dd>{health?.status === "ok" ? "Built" : "-"}</dd>
                    </div>
                    <div>
                      <dt>API</dt>
                      <dd>{health?.status === "ok" ? "OK" : "確認中"}</dd>
                    </div>
                  </dl>
                </section>,
                document.body,
              )}
          </div>
          <strong className="header-user">{user.username}</strong>
          <div className="header-popover-wrap">
            <button
              ref={accountTriggerRef}
              className="icon-button power-button"
              type="button"
              aria-label="アカウントメニュー"
              aria-expanded={accountOpen}
              aria-haspopup="menu"
              onClick={() => {
                setAccountOpen((open) => !open);
                setHealthOpen(false);
              }}
            >
              <UtilityIcon name="user" />
            </button>
            {accountOpen &&
              accountPopoverStyle &&
              createPortal(
                <div
                  ref={accountPopoverRef}
                  className="header-popover account-menu header-popover-portal"
                  style={accountPopoverStyle}
                  role="menu"
                >
                  <div className="account-menu-identity">
                    <strong>{user.role}</strong>
                    <span>{user.username}</span>
                  </div>
                  <div className="account-menu-divider" />
                  {user.identitySource === "cloudflare_access" &&
                    (user.role === "viewer" ? (
                      <button
                        ref={elevationTriggerRef}
                        type="button"
                        role="menuitem"
                        onClick={() => {
                          setElevationError(null);
                          setElevationOpen(true);
                        }}
                      >
                        <UtilityIcon name="shield" />
                        <span>管理者モード</span>
                      </button>
                    ) : (
                      <button
                        type="button"
                        role="menuitem"
                        onClick={handleDowngrade}
                      >
                        <UtilityIcon name="user" />
                        <span>閲覧者モード</span>
                      </button>
                    ))}
                  <button
                    ref={logoutButtonRef}
                    type="button"
                    role="menuitem"
                    onClick={handleLogout}
                  >
                    <UtilityIcon name="logout" />
                    <span>ログアウト</span>
                  </button>
                </div>,
                document.body,
              )}
          </div>
        </div>
      </header>

      <main className="app-main">
        <div className="page-shell">
          <div className="app-toast-region" aria-label="通知">
            {notice && (
              <Toast
                kind="success"
                message={notice}
                duration={5000}
                onClose={() => setNotice(null)}
              />
            )}
            {error && editing === undefined && (
              <Toast
                kind="error"
                message={error}
                onClose={() => setError(null)}
              />
            )}
          </div>
          <div key={path} className="page-content">
          {path === "/" && (
            <>
              <section className="hero compact-hero">
                <div>
                  <p className="eyebrow">EMPLOYEE MANAGEMENT</p>
                  <h1>社員管理</h1>
                  <p className="lead">
                    SQLiteを正として社員情報を管理し、保存時に通知用CSVを安全に再生成します。
                  </p>
                </div>
                <button
                  className="button-primary"
                  type="button"
                  onClick={openCreate}
                  disabled={!isAdmin}
                  title={
                    !isAdmin
                      ? "閲覧専用ユーザーは社員を追加できません"
                      : undefined
                  }
                >
                  社員を追加
                </button>
              </section>

              <section className="summary-grid" aria-label="集計">
                <article>
                  <span>検索結果</span>
                  <strong>{counts.all}</strong>
                </article>
                <article>
                  <span>結果内の有効</span>
                  <strong>{counts.enabled}</strong>
                </article>
                <article>
                  <span>結果内の無効</span>
                  <strong>{counts.disabled}</strong>
                </article>
                <article>
                  <span>社員データ整合性</span>
                  <strong
                    className={
                      consistency?.status === "mismatch"
                        ? "status-danger"
                        : "status-ok"
                    }
                  >
                    {!isAdmin
                      ? "閲覧のみ"
                      : loadingConsistency
                        ? "確認中"
                        : consistency?.status === "ok"
                          ? "一致"
                          : consistency?.status === "mismatch"
                            ? "不一致"
                            : "確認失敗"}
                  </strong>
                </article>
              </section>

              <section className="employee-card">
                <div className="employee-list-heading">
                  <div>
                    <p className="eyebrow">EMPLOYEES</p>
                    <h2>社員一覧</h2>
                    <p className="muted">
                      社員番号、氏名、メール、部署から対象を検索できます。
                    </p>
                  </div>
                  <span className="employee-result-count" aria-live="polite">
                    {loadingEmployees ? "読込中" : `${counts.all}件`}
                  </span>
                </div>
                <form
                  className="toolbar employee-toolbar"
                  onSubmit={(event) => {
                    event.preventDefault();
                    setQuery(queryInput.trim());
                  }}
                >
                  <label className="search-field">
                    検索
                    <input
                      value={queryInput}
                      onChange={(event) => setQueryInput(event.target.value)}
                      placeholder="社員番号・氏名・メール・部署"
                    />
                  </label>
                  <label>
                    状態
                    <select
                      value={enabledFilter}
                      onChange={(event) => setEnabledFilter(event.target.value)}
                    >
                      <option value="all">すべて</option>
                      <option value="enabled">有効</option>
                      <option value="disabled">無効</option>
                    </select>
                  </label>
                  <div className="employee-toolbar-actions">
                    <button className="button-primary" type="submit">
                      検索
                    </button>
                    <button
                      className="button-secondary"
                      type="button"
                      onClick={clearEmployeeFilters}
                      disabled={!hasEmployeeFilters && queryInput === ""}
                    >
                      条件クリア
                    </button>
                    <button
                      className="button-secondary"
                      type="button"
                      onClick={() => {
                        setEmployeeSort({ key: "code", direction: "asc" });
                        void Promise.all([loadEmployees(), loadConsistency()]);
                      }}
                      disabled={loadingEmployees || loadingConsistency}
                      aria-busy={loadingEmployees || loadingConsistency}
                    >
                      {loadingEmployees || loadingConsistency ? "更新中…" : "再読込"}
                    </button>
                  </div>
                </form>
                {hasEmployeeFilters && (
                  <div className="active-filter-summary" role="status">
                    <span>絞り込み中</span>
                    {query && <strong>検索: {query}</strong>}
                    {enabledFilter !== "all" && (
                      <strong>
                        状態: {enabledFilter === "enabled" ? "有効" : "無効"}
                      </strong>
                    )}
                    <button type="button" onClick={clearEmployeeFilters}>
                      すべて解除
                    </button>
                  </div>
                )}
                <div
                  className={`consistency-panel ${consistency?.status === "mismatch" ? "consistency-panel-danger" : ""}`}
                >
                  <div>
                    <strong>SQLite / employeeKey.csv</strong>
                    {consistency?.status === "ok" && (
                      <p>
                        整合しています（SQLite {consistency.databaseEmployees}件
                        / CSV {consistency.csvEmployees}件）。
                      </p>
                    )}
                    {consistency?.status === "mismatch" && (
                      <p>
                        不一致があります（SQLiteのみ{" "}
                        {consistency.databaseOnlyCodes.length}件 / CSVのみ{" "}
                        {consistency.csvOnlyCodes.length}件 / 項目差分{" "}
                        {consistency.fieldDifferences.length}件）。
                      </p>
                    )}
                    {consistencyError && <p>確認失敗: {consistencyError}</p>}
                    {!consistency && !consistencyError && (
                      <p>整合性を確認しています。</p>
                    )}
                  </div>
                  <button
                    className="button-secondary"
                    type="button"
                    onClick={loadConsistency}
                    disabled={!isAdmin || loadingConsistency}
                    aria-busy={loadingConsistency}
                    title={
                      !isAdmin
                        ? "閲覧専用ユーザーは整合性を再確認できません"
                        : undefined
                    }
                  >
                    {loadingConsistency ? "確認中…" : "再確認"}
                  </button>
                  {consistency?.status === "mismatch" && (
                    <details className="consistency-details">
                      <summary>差分対象を表示</summary>
                      {consistency.databaseOnlyCodes.length > 0 && (
                        <p>
                          SQLiteのみ: {consistency.databaseOnlyCodes.join(", ")}
                        </p>
                      )}
                      {consistency.csvOnlyCodes.length > 0 && (
                        <p>CSVのみ: {consistency.csvOnlyCodes.join(", ")}</p>
                      )}
                      {consistency.fieldDifferences.map((item) => (
                        <p key={item.code}>
                          項目差分 {item.code}: {item.fields.join(", ")}
                        </p>
                      ))}
                    </details>
                  )}
                </div>
                <div className="mobile-sort-controls employee-sort-controls">
                  <label>
                    並び順
                    <select value={employeeSort.key} onChange={(event) => setEmployeeSort((current) => ({ ...current, key: event.target.value as EmployeeSortKey }))}>
                      {Object.entries(employeeSortLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                    </select>
                  </label>
                  <button className="button-secondary sort-direction-button" type="button" onClick={() => setEmployeeSort((current) => ({ ...current, direction: current.direction === "asc" ? "desc" : "asc" }))}>
                    {employeeSort.direction === "asc" ? "昇順" : "降順"}
                  </button>
                </div>
                <div className="table-wrap">
                  <table className="employee-table">
                    <thead>
                      <tr>
                        {(["code", "name", "division", "target", "status"] as EmployeeSortKey[]).map((key) => (
                          <th key={key} aria-sort={employeeSort.key === key ? (employeeSort.direction === "asc" ? "ascending" : "descending") : "none"}>
                            <button className="table-sort-button" type="button" onClick={() => toggleEmployeeSort(key)} aria-label={`${employeeSortLabels[key]}で${employeeSort.key === key && employeeSort.direction === "asc" ? "降順" : "昇順"}に並べ替え`}>
                              <span>{key === "status" ? "状態・操作" : employeeSortLabels[key]}</span>
                              <span className="sort-indicator" aria-hidden="true">{employeeSort.key === key ? (employeeSort.direction === "asc" ? "▲" : "▼") : "↕"}</span>
                            </button>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {loadingEmployees && employees.length === 0 &&
                        Array.from({ length: 5 }, (_, index) => (
                          <tr key={`employee-skeleton-${index}`} className="skeleton-row" aria-hidden="true">
                            <td><span className="skeleton-block skeleton-code" /></td>
                            <td><span className="skeleton-block skeleton-name" /></td>
                            <td><span className="skeleton-block skeleton-email" /></td>
                            <td><span className="skeleton-block skeleton-division" /></td>
                            <td><span className="skeleton-block skeleton-action" /></td>
                          </tr>
                        ))}
                      {sortedEmployees.map((employee) => (
                        <tr key={employee.code}>
                          <td
                            className="mono employee-code"
                            data-label="社員番号"
                          >
                            {employee.code}
                          </td>
                          <td
                            className="employee-identity"
                            data-label="社員情報"
                          >
                            <strong>{employee.fullName}</strong>
                            <span>{employee.email || "—"}</span>
                          </td>
                          <td className="employee-meta" data-label="所属">
                            <strong>
                              {employee.divisionName ||
                                employee.divisionCode ||
                                "—"}
                            </strong>
                            {employee.divisionName && employee.divisionCode && (
                              <span>{employee.divisionCode}</span>
                            )}
                          </td>
                          <td className="employee-target" data-label="上限分">
                            {employee.personalTargetMinutes ?? "—"}
                          </td>
                          <td data-label="状態・操作">
                            <div className="employee-actions">
                              <span
                                className={`badge ${employee.isEnabled ? "badge-ok" : "badge-off"}`}
                              >
                                {employee.isEnabled ? "有効" : "無効"}
                              </span>
                              <button
                                className="table-action"
                                type="button"
                                onClick={() => openEdit(employee)}
                                disabled={!isAdmin}
                                title={
                                  !isAdmin
                                    ? "閲覧専用ユーザーは社員を編集できません"
                                    : undefined
                                }
                              >
                                編集
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                      {!loadingEmployees && employees.length === 0 && (
                        <tr>
                          <td colSpan={5} className="empty-row">
                            <div className="employee-empty-state">
                              <strong>
                                {hasEmployeeFilters
                                  ? "条件に一致する社員はいません"
                                  : "社員が登録されていません"}
                              </strong>
                              <span>
                                {hasEmployeeFilters
                                  ? "検索条件を変更するか、すべて解除してください。"
                                  : "「社員を追加」から最初の社員を登録できます。"}
                              </span>
                              {hasEmployeeFilters && (
                                <button
                                  className="button-secondary"
                                  type="button"
                                  onClick={clearEmployeeFilters}
                                >
                                  検索条件を解除
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
                {loadingEmployees && employees.length > 0 && (
                  <p className="muted loading-line updating-indicator" role="status">
                    社員一覧を更新中…
                  </p>
                )}
              </section>
            </>
          )}
          {path === "/kot-sync" && (
            <>
              <section className="hero">
                <p className="eyebrow">KING OF TIME</p>
                <h1>KOT社員同期</h1>
                <p className="lead">
                  差分を確認し、選択した変更だけを社員管理へ安全に反映します。
                </p>
              </section>
              {isAdmin && (
                <section className="employee-card sync-division-card">
                  <div className="sync-heading">
                    <div>
                      <p className="eyebrow">SYNC SETTINGS</p>
                      <h2>同期対象部門</h2>
                      <p className="muted">
                        有効な部門だけを次回のKOT取得・プレビュー対象にします。
                      </p>
                    </div>
                    <form className="sync-division-form" onSubmit={addSyncDivision}>
                      <input
                        aria-label="追加する部門コード"
                        inputMode="numeric"
                        placeholder="部門コード"
                        value={newDivisionCode}
                        onChange={(event) => setNewDivisionCode(event.target.value)}
                        disabled={divisionAdding}
                      />
                      <button
                        className="button-secondary"
                        type="submit"
                        disabled={divisionAdding || newDivisionCode.trim() === ""}
                      >
                        {divisionAdding ? "追加中…" : "追加"}
                      </button>
                    </form>
                  </div>
                  <div className="sync-division-list">
                    {syncDivisions.map((item) => {
                      const isPending = divisionPendingCode === item.divisionCode;
                      return (
                        <article
                          key={item.divisionCode}
                          className={`sync-division-item ${item.isEnabled ? "is-enabled" : "is-disabled"}`}
                        >
                          <div className="sync-division-item-heading">
                            <div>
                              <span className="sync-division-label">部門コード</span>
                              <strong>{item.divisionCode}</strong>
                            </div>
                            <button
                              className="sync-division-delete"
                              type="button"
                              disabled={isPending}
                              onClick={() => confirmDeleteSyncDivision(item)}
                            >
                              削除
                            </button>
                          </div>
                          <div className="sync-division-state-row">
                            <span className="sync-division-state-copy">
                              {item.isEnabled ? "同期対象" : "同期対象外"}
                            </span>
                            <button
                              className={`sync-division-toggle ${item.isEnabled ? "is-enabled" : "is-disabled"}`}
                              type="button"
                              aria-pressed={item.isEnabled}
                              aria-label={`部門コード ${item.divisionCode} を${item.isEnabled ? "無効" : "有効"}にする`}
                              disabled={isPending}
                              onClick={() => setSyncDivisionEnabled(item, !item.isEnabled)}
                            >
                              {isPending ? "更新中…" : item.isEnabled ? "有効" : "無効"}
                            </button>
                          </div>
                        </article>
                      );
                    })}
                  </div>
                </section>
              )}
              <section className="employee-card sync-card">
                <div className="sync-heading">
                  <div>
                    <p className="eyebrow">KING OF TIME</p>
                    <h2>社員同期</h2>
                    <p className="muted">
                      取得とプレビューだけでは本番データを変更しません。
                    </p>
                    {health?.kotSyncMock && (
                      <p className="muted">
                        開発用ダミーKOTデータを使用します。本番APIには接続しません。
                      </p>
                    )}
                    {health && !health.kotSyncEnabled && (
                      <p className="muted">
                        この環境ではKOT同期を停止しています。
                      </p>
                    )}
                    {syncStatus?.blocked && (
                      <p className="error-message">
                        API利用禁止時間帯です（08:30〜10:00、17:30〜18:30）。
                      </p>
                    )}
                    {syncStatus?.running && (
                      <p className="muted">同期処理を実行中です。</p>
                    )}
                    {syncStatus?.lastRun && (
                      <div className="muted">
                        <p>
                          最終実行:{" "}
                          {new Date(
                            syncStatus.lastRun.executed_at,
                          ).toLocaleString("ja-JP")}{" "}
                          / 新規 {syncStatus.lastRun.created_count} / 更新{" "}
                          {syncStatus.lastRun.updated_count} / 再有効化{" "}
                          {syncStatus.lastRun.reactivated_count} / 無効化{" "}
                          {syncStatus.lastRun.disabled_count}
                        </p>
                        {syncStatus.lastRun.backup_path && (
                          <p>バックアップ: {syncStatus.lastRun.backup_path}</p>
                        )}
                      </div>
                    )}
                  </div>
                  <button
                    className="button-secondary"
                    type="button"
                    onClick={loadKotPreview}
                    disabled={
                      !isAdmin ||
                      !health?.kotSyncEnabled ||
                      syncing ||
                      syncStatus?.running ||
                      syncStatus?.blocked
                    }
                  >
                    {!isAdmin
                      ? "閲覧専用"
                      : !health?.kotSyncEnabled
                        ? "この環境では無効"
                        : syncing || syncStatus?.running
                          ? "実行中…"
                          : health.kotSyncMock
                            ? "ダミーKOTから取得"
                            : "KOTから取得"}
                  </button>
                </div>
                {syncPreview && (
                  <>
                    <div
                      className="sync-summary"
                      aria-label="KOT同期プレビュー集計"
                    >
                      <div className="sync-summary-primary">
                        <article>
                          <span>同期対象</span>
                          <strong>{syncPreview.targetCount}</strong>
                        </article>
                        <article>
                          <span>表示中</span>
                          <strong>{visibleSyncDifferences.length}</strong>
                        </article>
                        <article>
                          <span>選択中</span>
                          <strong>{selectedSyncCodes.length}</strong>
                        </article>
                      </div>
                      <div className="sync-counts">
                        <span>全社取得 {syncPreview.fetchedCount}</span>
                        <span>
                          対象部署 {syncPreview.targetDivisionCodes.join(", ")}
                        </span>
                        <span>新規 {syncPreview.counts.create ?? 0}</span>
                        <span>更新 {syncPreview.counts.update ?? 0}</span>
                        <span>
                          再有効化候補 {syncPreview.counts.reactivate ?? 0}
                        </span>
                        <span>
                          無効化候補 {syncPreview.counts.disable ?? 0}
                        </span>
                        <span>
                          変更なし {syncPreview.counts.unchanged ?? 0}
                        </span>
                        <span>勤怠管理なし {warningCounts.noAttendance}</span>
                        <span>休職中 {warningCounts.onLeave}</span>
                      </div>
                    </div>
                    <div className="sync-filter-panel">
                      <div>
                        <p className="eyebrow">FILTERS</p>
                        <h3>表示する差分</h3>
                      </div>
                      <div
                        className="sync-filters"
                        aria-label="KOT同期プレビューフィルタ"
                      >
                        {(
                          [
                            "create",
                            "update",
                            "reactivate",
                            "disable",
                            "unchanged",
                          ] as const
                        ).map((action) => (
                          <label key={action}>
                            <input
                              type="checkbox"
                              checked={syncActions[action]}
                              onChange={(event) =>
                                setSyncActions({
                                  ...syncActions,
                                  [action]: event.target.checked,
                                })
                              }
                            />
                            <span className={`sync-badge sync-badge-${action}`}>
                              {syncActionLabels[action]}
                            </span>
                          </label>
                        ))}
                        <label>
                          <input
                            type="checkbox"
                            checked={showNoAttendance}
                            onChange={(event) =>
                              setShowNoAttendance(event.target.checked)
                            }
                          />
                          勤怠管理なしを表示
                        </label>
                        <label>
                          <input
                            type="checkbox"
                            checked={showOnLeave}
                            onChange={(event) =>
                              setShowOnLeave(event.target.checked)
                            }
                          />
                          休職中を表示
                        </label>
                      </div>
                    </div>
                    <div className="sync-selection-tools">
                      <div
                        className="sync-selection-status"
                        role="status"
                        aria-live="polite"
                      >
                        <strong>{selectedSyncCodes.length}件を選択中</strong>
                        <span>
                          新規 {selectedSyncCounts.create} / 更新{" "}
                          {selectedSyncCounts.update} / 再有効化{" "}
                          {selectedSyncCounts.reactivate} / 無効化{" "}
                          {selectedSyncCounts.disable}
                        </span>
                      </div>
                      <div className="sync-selection-buttons">
                        <button
                          className="button-secondary"
                          type="button"
                          onClick={() =>
                            setSelectedSyncCodes(
                              Array.from(
                                new Set([
                                  ...selectedSyncCodes,
                                  ...selectableVisibleCodes,
                                ]),
                              ),
                            )
                          }
                          disabled={
                            selectableVisibleCodes.length === 0 ||
                            allVisibleSelected
                          }
                        >
                          {allVisibleSelected
                            ? "表示中は選択済み"
                            : "表示中を選択"}
                        </button>
                        <button
                          className="button-secondary"
                          type="button"
                          onClick={() =>
                            setSelectedSyncCodes(
                              selectedSyncCodes.filter(
                                (code) =>
                                  !selectableVisibleCodes.includes(code),
                              ),
                            )
                          }
                          disabled={selectableVisibleCodes.length === 0}
                        >
                          表示中を解除
                        </button>
                      </div>
                      {hiddenSelectedCount > 0 && (
                        <span className="warning-text">
                          フィルターで非表示の選択が {hiddenSelectedCount}
                          件あります
                        </span>
                      )}
                    </div>
                    <div className="table-wrap">
                      <table className="sync-table">
                        <thead>
                          <tr>
                            <th>反映</th>
                            <th>社員番号</th>
                            <th>判定</th>
                            <th>変更前</th>
                            <th>変更後</th>
                            <th>変更項目</th>
                            <th>注意</th>
                          </tr>
                        </thead>
                        <tbody>
                          {visibleSyncDifferences.map((item) => {
                            const selectable = item.action !== "unchanged";
                            const checked = selectedSyncCodes.includes(
                              item.code,
                            );
                            const current = item.current as Record<
                              string,
                              string
                            > | null;
                            const proposed = item.proposed as Record<
                              string,
                              string
                            > | null;
                            const changedLabels: Record<string, string> = {
                              lastName: "氏",
                              firstName: "名",
                              email: "メール",
                              divisionCode: "部署コード",
                              divisionName: "部署名",
                              kotExists: "KOT存在状態",
                              kotKey: "KOT Key変更あり",
                            };
                            const toggleSelection = () => {
                              if (!selectable) return;
                              setSelectedSyncCodes(
                                checked
                                  ? selectedSyncCodes.filter(
                                      (code) => code !== item.code,
                                    )
                                  : [...selectedSyncCodes, item.code],
                              );
                            };
                            return (
                              <tr
                                key={item.code}
                                className={`sync-row sync-row-${item.action}${checked ? " sync-row-selected" : ""}${selectable ? " sync-row-selectable" : ""}`}
                                aria-selected={selectable ? checked : undefined}
                                tabIndex={selectable ? 0 : undefined}
                                onClick={(event) => {
                                  if (
                                    (event.target as HTMLElement).closest(
                                      "input, button, a",
                                    )
                                  )
                                    return;
                                  toggleSelection();
                                }}
                                onKeyDown={(event) => {
                                  if (
                                    !selectable ||
                                    (event.key !== "Enter" && event.key !== " ")
                                  )
                                    return;
                                  event.preventDefault();
                                  toggleSelection();
                                }}
                              >
                                <td data-label="反映">
                                  <input
                                    aria-label={`${item.code} ${syncActionLabels[item.action]}を反映`}
                                    type="checkbox"
                                    disabled={!selectable}
                                    checked={selectable && checked}
                                    onChange={toggleSelection}
                                  />
                                </td>
                                <td className="mono" data-label="社員番号">
                                  {item.code}
                                </td>
                                <td data-label="判定">
                                  <span
                                    className={`sync-badge sync-badge-${item.action}`}
                                  >
                                    {syncActionLabels[item.action]}
                                  </span>
                                </td>
                                <td data-label="変更前">
                                  {current
                                    ? `${current.lastName ?? ""}${current.firstName ?? ""} / ${current.divisionName ?? current.divisionCode ?? ""}`
                                    : "—"}
                                </td>
                                <td data-label="変更後">
                                  {proposed
                                    ? `${proposed.lastName ?? ""}${proposed.firstName ?? ""} / ${proposed.divisionName ?? proposed.divisionCode ?? ""}`
                                    : "—"}
                                </td>
                                <td data-label="変更項目">
                                  {item.changedFields
                                    .map(
                                      (field) => changedLabels[field] ?? field,
                                    )
                                    .join("、") || "—"}
                                </td>
                                <td data-label="注意">
                                  {item.warnings.join("、") || "—"}
                                </td>
                              </tr>
                            );
                          })}
                          {visibleSyncDifferences.length === 0 && (
                            <tr>
                              <td colSpan={7} className="empty-row">
                                <div className="sync-empty-state">
                                  <strong>
                                    条件に一致する差分はありません
                                  </strong>
                                  <span>
                                    判定や注意条件の表示設定を変更してください。
                                  </span>
                                </div>
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                    <div className="sync-actions">
                      <div>
                        <strong>{selectedSyncCodes.length}件を反映</strong>
                        <p className="muted">
                          選択した差分だけをSQLiteとemployeeKey.csvへ反映します。
                        </p>
                      </div>
                      <button
                        className="button-primary"
                        type="button"
                        disabled={syncing || selectedSyncCodes.length === 0}
                        aria-busy={syncing}
                        onClick={applyKotPreview}
                      >
                        {syncing
                          ? "反映中…"
                          : selectedSyncCodes.length === 0
                            ? "差分を選択してください"
                            : `選択した${selectedSyncCodes.length}件を反映`}
                      </button>
                    </div>
                  </>
                )}
              </section>
            </>
          )}
          {path === "/notifications" && (
            <>
              <section className="hero">
                <p className="eyebrow">NOTIFICATION HISTORY</p>
                <h1>通知履歴</h1>
                <p className="lead">
                  threshold・weekly・healthの実行結果と送信状況を確認します。
                </p>
              </section>
              <NotificationHistory />
            </>
          )}
          {!["/", "/kot-sync", "/notifications"].includes(path) && (
            <section className="empty-state" role="status">
              <p className="eyebrow">NOT FOUND</p>
              <h1>ページが見つかりません</h1>
              <p className="lead">
                ナビゲーションから管理画面へ戻ってください。
              </p>
              <a
                className="button-primary inline-link"
                href="/"
                onClick={(event) => navigate(event, "/")}
              >
                社員管理へ戻る
              </a>
            </section>
          )}
          </div>
          {elevationOpen && (
            <ModalLayer
              className="elevation-modal-layer"
              onRequestClose={() =>
                !elevationSubmitting && setElevationOpen(false)
              }
            >
              <section
                className="modal elevation-modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby="elevation-title"
              >
                <div className="modal-heading">
                  <div>
                    <p className="eyebrow">PRIVILEGE ELEVATION</p>
                    <h2 id="elevation-title">管理者モード</h2>
                  </div>
                  <button
                    type="button"
                    className="modal-close elevation-modal-close"
                    aria-label="閉じる"
                    onClick={() => setElevationOpen(false)}
                    disabled={elevationSubmitting}
                  >
                    <UtilityIcon name="close" />
                  </button>
                </div>
                <form className="login-form" onSubmit={handleElevation}>
                  <p className="muted">
                    管理操作を有効にするため、管理者パスワードを入力してください。
                  </p>
                  <label>
                    管理者パスワード
                    <input
                      name="password"
                      type="password"
                      autoComplete="current-password"
                      required
                      autoFocus
                    />
                  </label>
                  {elevationError && (
                    <p className="error-message" role="alert">
                      {elevationError}
                    </p>
                  )}
                  <div className="form-actions">
                    <button
                      type="button"
                      className="button-secondary"
                      onClick={() => setElevationOpen(false)}
                      disabled={elevationSubmitting}
                    >
                      キャンセル
                    </button>
                    <button
                      type="submit"
                      className="button-primary"
                      disabled={elevationSubmitting}
                      aria-busy={elevationSubmitting}
                    >
                      {elevationSubmitting ? "認証中…" : "切り替える"}
                    </button>
                  </div>
                </form>
              </section>
            </ModalLayer>
          )}
          {confirmAction && (
            <ConfirmDialog
              title={confirmAction.title}
              description={confirmAction.description}
              confirmLabel={
                confirmAction.kind === "sync" ? "反映する" : "削除する"
              }
              tone={confirmAction.kind === "sync" ? "primary" : "danger"}
              busy={submitting || syncing || divisionAdding || divisionPendingCode !== null}
              onCancel={() => setConfirmAction(null)}
              onConfirm={
                confirmAction.kind === "delete"
                  ? executeDeleteEmployee
                  : confirmAction.kind === "division-delete"
                    ? executeDeleteSyncDivision
                    : executeKotPreview
              }
            />
          )}
          {editing !== undefined && (
            <ModalLayer
              closeOnBackdrop={false}
              onRequestClose={() => !submitting && setEditing(undefined)}
            >
              <section
                className="modal employee-modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby="employee-form-title"
              >
                <div className="modal-heading">
                  <div>
                    <p className="eyebrow">EMPLOYEE</p>
                    <h2 id="employee-form-title">
                      {editing === null ? "社員を追加" : "社員を編集"}
                    </h2>
                  </div>
                  <button
                    className="icon-button"
                    type="button"
                    onClick={() => setEditing(undefined)}
                  >
                    ×
                  </button>
                </div>
                <form className="employee-form" onSubmit={saveEmployee}>
                  <div className="form-grid">
                    <label>
                      社員番号
                      <input
                        value={form.code}
                        onChange={(e) =>
                          setForm({ ...form, code: e.target.value })
                        }
                        required
                        disabled={editing !== null}
                      />
                    </label>
                    <label>
                      KOT Key
                      <input
                        type="password"
                        value={form.employeeKey}
                        onChange={(e) =>
                          setForm({ ...form, employeeKey: e.target.value })
                        }
                        required={editing === null}
                        placeholder={editing ? "変更時のみ入力" : "必須"}
                        autoComplete="off"
                      />
                    </label>
                    <label>
                      氏
                      <input
                        value={form.lastName}
                        onChange={(e) =>
                          setForm({ ...form, lastName: e.target.value })
                        }
                        required
                      />
                    </label>
                    <label>
                      名
                      <input
                        value={form.firstName}
                        onChange={(e) =>
                          setForm({ ...form, firstName: e.target.value })
                        }
                        required
                      />
                    </label>
                    <label>
                      部署コード
                      <input
                        value={form.divisionCode}
                        onChange={(e) =>
                          setForm({ ...form, divisionCode: e.target.value })
                        }
                        required
                      />
                    </label>
                    <label>
                      部署名
                      <input
                        value={form.divisionName}
                        onChange={(e) =>
                          setForm({ ...form, divisionName: e.target.value })
                        }
                      />
                    </label>
                    <label className="wide">
                      メールアドレス
                      <input
                        type="email"
                        value={form.email}
                        onChange={(e) =>
                          setForm({ ...form, email: e.target.value })
                        }
                      />
                    </label>
                    <label>
                      個人別残業上限分
                      <input
                        type="number"
                        min="0"
                        value={form.personalTargetMinutes}
                        onChange={(e) =>
                          setForm({
                            ...form,
                            personalTargetMinutes: e.target.value,
                          })
                        }
                      />
                    </label>
                    <label className="switch-label">
                      <input
                        type="checkbox"
                        checked={form.isEnabled}
                        onChange={(e) =>
                          setForm({
                            ...form,
                            isEnabled: e.target.checked,
                            disabledReason: e.target.checked
                              ? ""
                              : form.disabledReason,
                          })
                        }
                      />
                      有効社員
                    </label>
                    {!form.isEnabled && (
                      <label className="wide">
                        無効理由
                        <input
                          value={form.disabledReason}
                          onChange={(e) =>
                            setForm({ ...form, disabledReason: e.target.value })
                          }
                          required
                        />
                      </label>
                    )}
                    <label className="wide">
                      管理メモ
                      <textarea
                        value={form.note}
                        onChange={(e) =>
                          setForm({ ...form, note: e.target.value })
                        }
                        rows={3}
                      />
                    </label>
                  </div>
                  <p className="security-note">
                    KOT
                    Keyは保存専用です。画面・APIレスポンスには表示されません。
                  </p>
                  {error && (
                    <p className="error-message" role="alert">
                      {error}
                    </p>
                  )}
                  <div className="form-actions">
                    {editing && (
                      <button
                        className="button-danger"
                        type="button"
                        onClick={deleteEmployee}
                        disabled={submitting}
                      >
                        {submitting ? "処理中…" : "社員を削除"}
                      </button>
                    )}
                    <span className="form-actions-spacer" />
                    <button
                      className="button-secondary"
                      type="button"
                      onClick={() => setEditing(undefined)}
                      disabled={submitting}
                    >
                      キャンセル
                    </button>
                    <button
                      className="button-primary"
                      type="submit"
                      disabled={submitting}
                    >
                      {submitting ? "保存中…" : "保存してCSV再生成"}
                    </button>
                  </div>
                </form>
              </section>
            </ModalLayer>
          )}
        </div>
      </main>
    </div>
  );
}
