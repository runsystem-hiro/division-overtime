import "@testing-library/jest-dom/vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NotificationHistory } from "../src/NotificationHistory";

const run = {
  runId: "run-1",
  mode: "weekly",
  startedAt: "2026-07-24T21:30:08+09:00",
  finishedAt: "2026-07-24T21:30:16+09:00",
  status: "succeeded",
  dryRun: false,
  source: "timer",
  errorMessage: null,
  targetCount: 14,
  attemptCount: 1,
  sentCount: 1,
  failedCount: 0,
  skippedCount: 0,
  pendingCount: 0,
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("NotificationHistory", () => {
  it("通知履歴一覧から詳細を表示する", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url === "/api/notification-runs?limit=50") {
        return new Response(JSON.stringify([run]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url === "/api/notification-runs/run-1") {
        return new Response(
          JSON.stringify({
            ...run,
            attempts: [
              {
                id: 1,
                dedupeKey: "weekly:2026-W30:00524",
                employeeCode: "00524",
                recipient: "manager@example.com",
                notificationType: "weekly",
                thresholdPercent: null,
                status: "sent",
                attemptCount: 1,
                slackTimestamp: "123.456",
                errorMessage: null,
                createdAt: run.startedAt,
                updatedAt: run.finishedAt,
              },
            ],
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    render(<NotificationHistory />);

    expect(await screen.findByText("weekly")).toBeInTheDocument();
    expect(screen.getByText("timer")).toBeInTheDocument();
    expect(screen.getByText("本番")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "詳細" }));

    expect(
      await screen.findByRole("heading", { name: "通知実行詳細" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("timer").length).toBeGreaterThan(0);
    expect(screen.getByText("manager@example.com")).toBeInTheDocument();
    expect(screen.getByText("123.456")).toBeInTheDocument();
  });

  it("一覧が空の場合に空状態を表示する", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    render(<NotificationHistory />);

    expect(
      await screen.findByText("通知実行履歴はありません。"),
    ).toBeInTheDocument();
  });

  it("一覧APIエラーを表示する", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "error" }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      }),
    );

    render(<NotificationHistory />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "通知履歴の取得に失敗しました: error",
    );
  });

  it("詳細が見つからない場合に404状態を表示する", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("?limit=50")) {
        return new Response(JSON.stringify([run]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify({ detail: "Not Found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    });

    render(<NotificationHistory />);
    fireEvent.click(await screen.findByRole("button", { name: "詳細" }));

    await waitFor(() => {
      const dialog = screen.getByRole("dialog", { name: "通知実行詳細" });
      expect(within(dialog).getByRole("alert")).toHaveTextContent(
        "指定した通知実行履歴が見つかりません",
      );
    });
  });
});
