import "@testing-library/jest-dom/vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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

beforeEach(() => {
  vi.stubEnv("VITE_NOTIFICATION_HISTORY_MOCK", "false");
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

describe("NotificationHistory", () => {

  it("初回読込では対象領域だけにスケルトンを表示する", async () => {
    let resolveResponse: ((value: Response) => void) | undefined;
    vi.spyOn(globalThis, "fetch").mockReturnValue(
      new Promise<Response>((resolve) => {
        resolveResponse = resolve;
      }),
    );

    render(<NotificationHistory />);

    expect(
      screen.getByRole("status", { name: "通知履歴を読み込んでいます" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "通知実行履歴" })).toBeInTheDocument();

    resolveResponse?.(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    expect(await screen.findByText("通知実行履歴はありません")).toBeInTheDocument();
  });

  it("開発用サンプルを有効にするとAPIを使わず一覧と詳細を表示する", async () => {
    vi.stubEnv("VITE_NOTIFICATION_HISTORY_MOCK", "true");
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    render(<NotificationHistory />);

    expect(await screen.findByText("開発用サンプル表示中")).toBeInTheDocument();
    expect(screen.getByText("一部失敗")).toBeInTheDocument();
    expect(screen.getAllByText("dry-run").length).toBeGreaterThan(0);
    expect(screen.getByText("実行中")).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();

    const detailButtons = screen.getAllByRole("button", { name: "詳細" });
    fireEvent.click(detailButtons[1]);

    expect(await screen.findByText("manager-delta@example.com")).toBeInTheDocument();
    expect(screen.getAllByText("重複スキップ").length).toBeGreaterThan(0);
    expect(screen.getAllByText("保留").length).toBeGreaterThan(0);
  });
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
                duplicateOfAttemptId: null,
                duplicateOfRunId: null,
                duplicateOfStartedAt: null,
                duplicateOfSource: null,
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

    expect(await screen.findByText("週次通知")).toBeInTheDocument();
    expect(screen.getByText("weekly")).toBeInTheDocument();
    expect(screen.getByText("定期実行")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "通知履歴集計" })).toHaveTextContent("表示中1");
    expect(screen.getByText("本番")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "詳細" }));

    expect(
      await screen.findByRole("heading", { name: "通知実行詳細" }),
    ).toBeInTheDocument();
    const dialog = screen.getByRole("dialog", { name: "通知実行詳細" });
    expect(dialog.closest(".modal-backdrop")?.parentElement).toBe(document.body);
    expect(screen.getAllByText("定期実行").length).toBeGreaterThan(0);
    expect(screen.getByText("manager@example.com")).toBeInTheDocument();
    expect(screen.getByText("123.456")).toBeInTheDocument();
  });

  it("重複スキップから重複元の詳細を開く", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url === "/api/notification-runs?limit=50") {
        return new Response(JSON.stringify([{ ...run, runId: "run-2", skippedCount: 1 }]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url === "/api/notification-runs/run-2") {
        return new Response(JSON.stringify({
          ...run,
          runId: "run-2",
          skippedCount: 1,
          attempts: [{
            id: 2,
            dedupeKey: "weekly:2026-W30:00524",
            employeeCode: "00524",
            recipient: "manager@example.com",
            notificationType: "weekly",
            thresholdPercent: null,
            status: "skipped",
            attemptCount: 0,
            slackTimestamp: null,
            errorMessage: null,
            createdAt: run.startedAt,
            updatedAt: run.finishedAt,
            duplicateOfAttemptId: 1,
            duplicateOfRunId: "run-1",
            duplicateOfStartedAt: "2026-07-24T20:30:08+09:00",
            duplicateOfSource: "test",
          }],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url === "/api/notification-runs/run-1") {
        return new Response(JSON.stringify({ ...run, attempts: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    render(<NotificationHistory />);
    fireEvent.click(await screen.findByRole("button", { name: "詳細" }));
    const originButton = await screen.findByRole("button", { name: /2026.*テスト/ });
    fireEvent.click(originButton);

    await waitFor(() => {
      expect(screen.getByText("run-1")).toBeInTheDocument();
    });
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
      await screen.findByText("通知実行履歴はありません"),
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
