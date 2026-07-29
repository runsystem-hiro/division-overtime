import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import packageJson from "../package.json";
import { App } from "../src/App";

afterEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState({}, "", "/");
  window.localStorage.clear();
});

describe("App", () => {
  it("未ログイン時に管理者ログイン画面を表示する", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ authenticated: false, user: null }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "管理者ログイン" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("ユーザー名")).toBeInTheDocument();
    expect(screen.getByLabelText("パスワード")).toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveClass("ambient-shell");
    expect(globalThis.fetch).toHaveBeenCalledWith("/api/auth/status", {
      credentials: "same-origin",
    });
  });

  it("認証後に共通ナビゲーションで主要画面を切り替える", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof Request
            ? input.url
            : input.toString();
      const responses: Record<string, unknown> = {
        "/api/auth/status": {
          authenticated: true,
          user: { username: "admin", expiresAt: "2026-07-28T18:00:00+09:00" },
        },
        "/api/system/health": {
          status: "ok",
          service: "division-overtime-web",
          version: packageJson.version,
          serverTime: "2026-07-28T17:00:00+09:00",
          timezone: "Asia/Tokyo",
          environment: "development",
          kotSyncEnabled: true,
          kotSyncMock: true,
        },
        "/api/employees?enabled=all": [],
        "/api/employees/consistency": {
          status: "ok",
          databaseEmployees: 0,
          csvEmployees: 0,
          databaseOnlyCodes: [],
          csvOnlyCodes: [],
          fieldDifferences: [],
        },
        "/api/kot-sync/status": {
          running: false,
          blocked: false,
          lastRun: null,
        },
      };
      return new Response(JSON.stringify(responses[url] ?? []), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "社員管理" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: "管理画面" }),
    ).toBeInTheDocument();
    expect(document.querySelector(".app-shell")).toHaveAttribute(
      "data-page",
      "employees",
    );
    expect(document.querySelector(".page-content")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: "同期" }));
    expect(
      screen.getByRole("heading", { name: "KOT社員同期" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "同期" })).toHaveClass("active");
    expect(window.location.pathname).toBe("/kot-sync");
    expect(document.querySelector(".app-shell")).toHaveAttribute(
      "data-page",
      "sync",
    );

    fireEvent.click(screen.getByRole("link", { name: "履歴" }));
    expect(
      screen.getByRole("heading", { name: "通知履歴", level: 1 }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/notifications");
  });

  it("ヘッダーからシステム状態とログアウトメニューを開ける", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof Request
            ? input.url
            : input.toString();
      const responses: Record<string, unknown> = {
        "/api/auth/status": {
          authenticated: true,
          user: { username: "admin", expiresAt: null },
        },
        "/api/system/health": {
          status: "ok",
          environment: "development",
          version: packageJson.version,
        },
        "/api/employees?enabled=all": [],
        "/api/employees/consistency": {
          status: "ok",
          databaseEmployees: 0,
          csvEmployees: 0,
          databaseOnlyCodes: [],
          csvOnlyCodes: [],
          fieldDifferences: [],
        },
        "/api/kot-sync/status": {
          running: false,
          blocked: false,
          lastRun: null,
        },
      };
      return new Response(JSON.stringify(responses[url] ?? []), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });

    render(<App />);

    expect(await screen.findByText("DEVELOPMENT")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: /正常/ }));
    expect(
      screen.getByRole("dialog", { name: "システム状態" }),
    ).toBeInTheDocument();
    expect(screen.getByText(packageJson.version)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "アカウントメニュー" }));
    expect(
      screen.queryByRole("dialog", { name: "システム状態" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("menuitem", { name: "ログアウト" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "アカウントメニュー" }).parentElement,
    ).toHaveClass("is-open");

    fireEvent.click(screen.getByRole("menuitem", { name: "ログアウト" }));
    expect(
      await screen.findByRole("heading", { name: "管理者ログイン" }),
    ).toBeInTheDocument();
    expect(globalThis.fetch).toHaveBeenCalledWith("/api/auth/logout", {
      method: "POST",
      credentials: "same-origin",
    });
  });

  it.each([
    ["production", "PRODUCTION", "environment-production"],
    ["development", "DEVELOPMENT", "environment-development"],
    ["test", "TEST", "environment-test"],
    ["staging", "UNKNOWN", "environment-unknown"],
  ])(
    "環境 %s を適切なバッジとして表示する",
    async (environment, label, className) => {
      vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
        const url =
          typeof input === "string"
            ? input
            : input instanceof Request
              ? input.url
              : input.toString();
        const responses: Record<string, unknown> = {
          "/api/auth/status": {
            authenticated: true,
            user: { username: "admin", expiresAt: null },
          },
          "/api/system/health": {
            status: "ok",
            environment,
            version: packageJson.version,
          },
          "/api/employees?enabled=all": [],
          "/api/employees/consistency": {
            status: "ok",
            databaseEmployees: 0,
            csvEmployees: 0,
            databaseOnlyCodes: [],
            csvOnlyCodes: [],
            fieldDifferences: [],
          },
          "/api/kot-sync/status": {
            running: false,
            blocked: false,
            lastRun: null,
          },
        };
        return new Response(JSON.stringify(responses[url] ?? []), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      });

      render(<App />);

      const badge = await screen.findByText(label);
      expect(badge).toHaveClass("environment-badge", className);
    },
  );

  it("社員一覧の検索条件を表示し、まとめて解除する", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof Request
            ? input.url
            : input.toString();
      const responses: Record<string, unknown> = {
        "/api/auth/status": {
          authenticated: true,
          user: { username: "admin", expiresAt: null },
        },
        "/api/system/health": { status: "ok", environment: "development" },
        "/api/employees?enabled=all": [],
        "/api/employees?enabled=disabled&query=%E9%96%8B%E7%99%BA": [],
        "/api/employees/consistency": {
          status: "ok",
          databaseEmployees: 0,
          csvEmployees: 0,
          databaseOnlyCodes: [],
          csvOnlyCodes: [],
          fieldDifferences: [],
        },
        "/api/kot-sync/status": {
          running: false,
          blocked: false,
          lastRun: null,
        },
      };
      return new Response(JSON.stringify(responses[url] ?? []), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });

    render(<App />);

    await screen.findByRole("heading", { name: "社員一覧" });
    fireEvent.change(screen.getByLabelText("検索"), {
      target: { value: "開発" },
    });
    fireEvent.change(screen.getByLabelText("状態"), {
      target: { value: "disabled" },
    });
    fireEvent.click(screen.getByRole("button", { name: "検索" }));

    expect(await screen.findByText("検索: 開発")).toBeInTheDocument();
    expect(screen.getByText("状態: 無効")).toBeInTheDocument();
    expect(
      screen.getByText("条件に一致する社員はいません"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "すべて解除" }));

    await waitFor(() => {
      expect(screen.queryByText("検索: 開発")).not.toBeInTheDocument();
    });
    expect(screen.getByLabelText("検索")).toHaveValue("");
    expect(screen.getByLabelText("状態")).toHaveValue("all");
  });
  it("KOT同期プレビューで表示中の差分を選択し、反映件数を確認できる", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof Request
            ? input.url
            : input.toString();
      const responses: Record<string, unknown> = {
        "/api/auth/status": {
          authenticated: true,
          user: { username: "admin", expiresAt: null },
        },
        "/api/system/health": {
          status: "ok",
          environment: "development",
          kotSyncEnabled: true,
          kotSyncMock: true,
        },
        "/api/employees?enabled=all": [],
        "/api/employees/consistency": {
          status: "ok",
          databaseEmployees: 0,
          csvEmployees: 0,
          databaseOnlyCodes: [],
          csvOnlyCodes: [],
          fieldDifferences: [],
        },
        "/api/kot-sync/status": {
          running: false,
          blocked: false,
          lastRun: null,
        },
        "/api/kot-sync/preview": {
          previewId: "preview-1",
          counts: {
            create: 1,
            update: 1,
            reactivate: 0,
            disable: 0,
            unchanged: 1,
          },
          fetchedCount: 3,
          targetCount: 3,
          targetDivisionCodes: ["156"],
          differences: [
            {
              code: "90001",
              action: "create",
              current: null,
              proposed: {
                lastName: "山田",
                firstName: "太郎",
                divisionName: "営業部",
              },
              warnings: [],
              changedFields: [],
            },
            {
              code: "90002",
              action: "update",
              current: {
                lastName: "佐藤",
                firstName: "花子",
                divisionName: "開発部",
              },
              proposed: {
                lastName: "佐藤",
                firstName: "花子",
                divisionName: "開発本部",
              },
              warnings: [],
              changedFields: ["divisionName"],
            },
            {
              code: "90003",
              action: "unchanged",
              current: {},
              proposed: {},
              warnings: [],
              changedFields: [],
            },
          ],
        },
      };
      return new Response(JSON.stringify(responses[url] ?? []), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });

    window.history.replaceState({}, "", "/kot-sync");
    render(<App />);

    await screen.findByRole("heading", { name: "KOT社員同期" });
    fireEvent.click(
      await screen.findByRole("button", { name: "ダミーKOTから取得" }),
    );

    expect(await screen.findByText("同期対象")).toBeInTheDocument();
    expect(screen.getAllByText("新規").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "表示中を選択" }));

    expect(screen.getByText("2件を選択中")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "選択した2件を反映" }),
    ).toBeEnabled();
    expect(
      screen.getByRole("checkbox", { name: "90001 新規を反映" }),
    ).toBeChecked();
    expect(
      screen.getByRole("checkbox", { name: "90002 更新を反映" }),
    ).toBeChecked();

    fireEvent.click(screen.getByText("山田太郎 / 営業部"));
    expect(
      screen.getByRole("checkbox", { name: "90001 新規を反映" }),
    ).not.toBeChecked();
    expect(screen.getByText("1件を選択中")).toBeInTheDocument();

    fireEvent.keyDown(screen.getByText("佐藤花子 / 開発部").closest("tr")!, {
      key: "Enter",
    });
    expect(
      screen.getByRole("checkbox", { name: "90002 更新を反映" }),
    ).not.toBeChecked();
    expect(screen.getByText("0件を選択中")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("checkbox", { name: "変更なし" }));
    expect(
      screen.getByRole("checkbox", { name: "90003 変更なしを反映" }),
    ).toBeDisabled();
  });

  it("閲覧専用ユーザーでは更新操作を無効にする", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (input) => {
        const url =
          typeof input === "string"
            ? input
            : input instanceof Request
              ? input.url
              : input.toString();
        const responses: Record<string, unknown> = {
          "/api/auth/status": {
            authenticated: true,
            user: { username: "viewer", role: "viewer", expiresAt: null },
          },
          "/api/system/health": {
            status: "ok",
            environment: "development",
            kotSyncEnabled: true,
            kotSyncMock: true,
          },
          "/api/employees?enabled=all": [
            {
              code: "00001",
              lastName: "田中",
              firstName: "太郎",
              fullName: "田中 太郎",
              email: "a@example.com",
              divisionCode: "300",
              divisionName: "営業部",
              personalTargetMinutes: null,
              isEnabled: true,
              disabledReason: "",
              note: "",
              kotExists: true,
              createdAt: "2026-07-29T10:00:00+09:00",
              updatedAt: "2026-07-29T10:00:00+09:00",
            },
          ],
          "/api/kot-sync/status": {
            running: false,
            blocked: false,
            lastRun: null,
          },
        };
        return new Response(JSON.stringify(responses[url] ?? []), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      });

    render(<App />);

    expect(
      await screen.findByRole("button", { name: "社員を追加" }),
    ).toBeDisabled();
    expect(await screen.findByRole("button", { name: "編集" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "再確認" })).toBeDisabled();
    expect(screen.getByText("閲覧のみ")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/employees/consistency",
      expect.anything(),
    );

    fireEvent.click(screen.getByRole("link", { name: "同期" }));
    expect(screen.getByRole("button", { name: "閲覧専用" })).toBeDisabled();
  });
});
