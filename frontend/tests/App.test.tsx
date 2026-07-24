import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/App";

afterEach(() => {
  vi.restoreAllMocks();
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
});
