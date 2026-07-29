import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/App";

afterEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState({}, "", "/");
  window.localStorage.clear();
});

describe("App", () => {
  it("未ログイン時に管理者ログイン画面を表示する", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ authenticated: false, user: null }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    render(<App />);

    expect(await screen.findByRole("heading", { name: "管理者ログイン" })).toBeInTheDocument();
    expect(screen.getByLabelText("ユーザー名")).toBeInTheDocument();
    expect(screen.getByLabelText("パスワード")).toBeInTheDocument();
    expect(globalThis.fetch).toHaveBeenCalledWith("/api/auth/status", {
      credentials: "same-origin",
    });
  });

  it("認証後に共通ナビゲーションで主要画面を切り替える", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = typeof input === "string" ? input : input instanceof Request ? input.url : input.toString();
      const responses: Record<string, unknown> = {
        "/api/auth/status": {
          authenticated: true,
          user: { username: "admin", expiresAt: "2026-07-28T18:00:00+09:00" },
        },
        "/api/system/health": {
          status: "ok",
          service: "division-overtime-web",
          version: "2.1.0",
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
        "/api/kot-sync/status": { running: false, blocked: false, lastRun: null },
      };
      return new Response(JSON.stringify(responses[url] ?? []), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });

    render(<App />);

    expect(await screen.findByRole("heading", { name: "社員管理" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "管理画面" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: "KOT同期" }));
    expect(screen.getByRole("heading", { name: "KOT社員同期" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "KOT同期" })).toHaveClass("active");
    expect(window.location.pathname).toBe("/kot-sync");

    fireEvent.click(screen.getByRole("link", { name: "通知履歴" }));
    expect(screen.getByRole("heading", { name: "通知履歴", level: 1 })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/notifications");
  });

  it("ナビゲーションを折りたたみ、状態を保存する", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = typeof input === "string" ? input : input instanceof Request ? input.url : input.toString();
      const responses: Record<string, unknown> = {
        "/api/auth/status": { authenticated: true, user: { username: "admin", expiresAt: null } },
        "/api/system/health": { status: "ok", environment: "development" },
        "/api/employees?enabled=all": [],
        "/api/employees/consistency": { status: "ok", databaseEmployees: 0, csvEmployees: 0, databaseOnlyCodes: [], csvOnlyCodes: [], fieldDifferences: [] },
        "/api/kot-sync/status": { running: false, blocked: false, lastRun: null },
      };
      return new Response(JSON.stringify(responses[url] ?? []), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });

    const { container } = render(<App />);
    const toggle = await screen.findByRole("button", { name: "ナビゲーションを閉じる" });

    fireEvent.click(toggle);

    await waitFor(() => {
      expect(container.querySelector(".app-shell")).toHaveClass("sidebar-collapsed");
    });
    expect(screen.getByRole("button", { name: "ナビゲーションを開く" })).toBeInTheDocument();
    expect(window.localStorage.getItem("division-overtime-sidebar-collapsed")).toBe("true");
  });

  it("社員一覧の検索条件を表示し、まとめて解除する", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = typeof input === "string" ? input : input instanceof Request ? input.url : input.toString();
      const responses: Record<string, unknown> = {
        "/api/auth/status": { authenticated: true, user: { username: "admin", expiresAt: null } },
        "/api/system/health": { status: "ok", environment: "development" },
        "/api/employees?enabled=all": [],
        "/api/employees?enabled=disabled&query=%E9%96%8B%E7%99%BA": [],
        "/api/employees/consistency": { status: "ok", databaseEmployees: 0, csvEmployees: 0, databaseOnlyCodes: [], csvOnlyCodes: [], fieldDifferences: [] },
        "/api/kot-sync/status": { running: false, blocked: false, lastRun: null },
      };
      return new Response(JSON.stringify(responses[url] ?? []), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });

    render(<App />);

    await screen.findByRole("heading", { name: "社員一覧" });
    fireEvent.change(screen.getByLabelText("検索"), { target: { value: "開発" } });
    fireEvent.change(screen.getByLabelText("状態"), { target: { value: "disabled" } });
    fireEvent.click(screen.getByRole("button", { name: "検索" }));

    expect(await screen.findByText("検索: 開発")).toBeInTheDocument();
    expect(screen.getByText("状態: 無効")).toBeInTheDocument();
    expect(screen.getByText("条件に一致する社員はいません")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "すべて解除" }));

    await waitFor(() => {
      expect(screen.queryByText("検索: 開発")).not.toBeInTheDocument();
    });
    expect(screen.getByLabelText("検索")).toHaveValue("");
    expect(screen.getByLabelText("状態")).toHaveValue("all");
  });
});
