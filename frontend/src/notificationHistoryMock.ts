export type NotificationRunMock = {
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

export type NotificationAttemptMock = {
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

export type NotificationRunDetailMock = NotificationRunMock & {
  attempts: NotificationAttemptMock[];
};

const now = "2026-07-29T13:00:00+09:00";

export const developmentNotificationRuns: NotificationRunMock[] = [
  {
    runId: "dev-weekly-success",
    mode: "weekly",
    startedAt: "2026-07-29T09:30:00+09:00",
    finishedAt: "2026-07-29T09:30:08+09:00",
    status: "succeeded",
    dryRun: false,
    source: "timer",
    errorMessage: null,
    targetCount: 3,
    attemptCount: 3,
    sentCount: 3,
    failedCount: 0,
    skippedCount: 0,
    pendingCount: 0,
  },
  {
    runId: "dev-threshold-partial",
    mode: "threshold",
    startedAt: "2026-07-29T10:15:00+09:00",
    finishedAt: "2026-07-29T10:15:12+09:00",
    status: "failed",
    dryRun: false,
    source: "manual",
    errorMessage: "一部の送信先でSlack APIエラーが発生しました。",
    targetCount: 4,
    attemptCount: 4,
    sentCount: 2,
    failedCount: 1,
    skippedCount: 1,
    pendingCount: 0,
  },
  {
    runId: "dev-health-failed",
    mode: "health",
    startedAt: "2026-07-29T11:00:00+09:00",
    finishedAt: "2026-07-29T11:00:03+09:00",
    status: "failed",
    dryRun: false,
    source: "timer",
    errorMessage: "KING OF TIME APIへの接続確認がタイムアウトしました。",
    targetCount: 1,
    attemptCount: 1,
    sentCount: 0,
    failedCount: 1,
    skippedCount: 0,
    pendingCount: 0,
  },
  {
    runId: "dev-weekly-dry-run",
    mode: "weekly",
    startedAt: "2026-07-29T11:30:00+09:00",
    finishedAt: "2026-07-29T11:30:04+09:00",
    status: "succeeded",
    dryRun: true,
    source: "test",
    errorMessage: null,
    targetCount: 2,
    attemptCount: 2,
    sentCount: 0,
    failedCount: 0,
    skippedCount: 0,
    pendingCount: 2,
  },
  {
    runId: "dev-threshold-running",
    mode: "threshold",
    startedAt: "2026-07-29T12:55:00+09:00",
    finishedAt: null,
    status: "running",
    dryRun: false,
    source: "manual",
    errorMessage: null,
    targetCount: 2,
    attemptCount: 1,
    sentCount: 0,
    failedCount: 0,
    skippedCount: 0,
    pendingCount: 1,
  },
];

const details = new Map<string, NotificationRunDetailMock>([
  [
    "dev-weekly-success",
    {
      ...developmentNotificationRuns[0],
      attempts: [
        {
          id: 101,
          dedupeKey: "weekly:2026-W31:00101",
          employeeCode: "00101",
          recipient: "manager-alpha@example.com",
          notificationType: "weekly",
          thresholdPercent: null,
          status: "sent",
          attemptCount: 1,
          slackTimestamp: "1785294600.000101",
          errorMessage: null,
          createdAt: "2026-07-29T09:30:01+09:00",
          updatedAt: "2026-07-29T09:30:02+09:00",
          duplicateOfAttemptId: null,
          duplicateOfRunId: null,
          duplicateOfStartedAt: null,
          duplicateOfSource: null,
        },
        {
          id: 102,
          dedupeKey: "weekly:2026-W31:00102",
          employeeCode: "00102",
          recipient: "manager-beta-with-a-very-long-address@example.com",
          notificationType: "weekly",
          thresholdPercent: null,
          status: "sent",
          attemptCount: 1,
          slackTimestamp: "1785294601.000102",
          errorMessage: null,
          createdAt: "2026-07-29T09:30:02+09:00",
          updatedAt: "2026-07-29T09:30:03+09:00",
          duplicateOfAttemptId: null,
          duplicateOfRunId: null,
          duplicateOfStartedAt: null,
          duplicateOfSource: null,
        },
      ],
    },
  ],
  [
    "dev-threshold-partial",
    {
      ...developmentNotificationRuns[1],
      attempts: [
        {
          id: 201,
          dedupeKey: "threshold:2026-07:00201:80",
          employeeCode: "00201",
          recipient: "manager-gamma@example.com",
          notificationType: "threshold",
          thresholdPercent: 80,
          status: "sent",
          attemptCount: 1,
          slackTimestamp: "1785297300.000201",
          errorMessage: null,
          createdAt: "2026-07-29T10:15:01+09:00",
          updatedAt: "2026-07-29T10:15:02+09:00",
          duplicateOfAttemptId: null,
          duplicateOfRunId: null,
          duplicateOfStartedAt: null,
          duplicateOfSource: null,
        },
        {
          id: 202,
          dedupeKey: "threshold:2026-07:00202:100",
          employeeCode: "00202",
          recipient: "manager-delta@example.com",
          notificationType: "threshold",
          thresholdPercent: 100,
          status: "failed",
          attemptCount: 3,
          slackTimestamp: null,
          errorMessage: "Slack API returned HTTP 429 after retrying three times. Retry-Afterヘッダーに従って再試行しましたが送信できませんでした。",
          createdAt: "2026-07-29T10:15:02+09:00",
          updatedAt: "2026-07-29T10:15:11+09:00",
          duplicateOfAttemptId: null,
          duplicateOfRunId: null,
          duplicateOfStartedAt: null,
          duplicateOfSource: null,
        },
        {
          id: 203,
          dedupeKey: "threshold:2026-07:00203:80",
          employeeCode: "00203",
          recipient: "manager-epsilon@example.com",
          notificationType: "threshold",
          thresholdPercent: 80,
          status: "skipped",
          attemptCount: 0,
          slackTimestamp: null,
          errorMessage: null,
          createdAt: "2026-07-29T10:15:03+09:00",
          updatedAt: "2026-07-29T10:15:03+09:00",
          duplicateOfAttemptId: 101,
          duplicateOfRunId: "dev-weekly-success",
          duplicateOfStartedAt: "2026-07-29T09:30:00+09:00",
          duplicateOfSource: "timer",
        },
        {
          id: 204,
          dedupeKey: "threshold:2026-07:00204:80",
          employeeCode: "00204",
          recipient: "manager-zeta@example.com",
          notificationType: "threshold",
          thresholdPercent: 80,
          status: "pending",
          attemptCount: 0,
          slackTimestamp: null,
          errorMessage: null,
          createdAt: now,
          updatedAt: now,
          duplicateOfAttemptId: null,
          duplicateOfRunId: null,
          duplicateOfStartedAt: null,
          duplicateOfSource: null,
        },
      ],
    },
  ],
  ["dev-health-failed", { ...developmentNotificationRuns[2], attempts: [] }],
  [
    "dev-weekly-dry-run",
    {
      ...developmentNotificationRuns[3],
      attempts: [
        {
          id: 401,
          dedupeKey: "weekly:2026-W31:00401",
          employeeCode: "00401",
          recipient: "dry-run-recipient@example.com",
          notificationType: "weekly",
          thresholdPercent: null,
          status: "pending",
          attemptCount: 0,
          slackTimestamp: null,
          errorMessage: null,
          createdAt: "2026-07-29T11:30:01+09:00",
          updatedAt: "2026-07-29T11:30:01+09:00",
          duplicateOfAttemptId: null,
          duplicateOfRunId: null,
          duplicateOfStartedAt: null,
          duplicateOfSource: null,
        },
      ],
    },
  ],
  ["dev-threshold-running", { ...developmentNotificationRuns[4], attempts: [] }],
]);

export function isDevelopmentNotificationMockEnabled(): boolean {
  return import.meta.env.DEV && import.meta.env.VITE_NOTIFICATION_HISTORY_MOCK === "true";
}

export function getDevelopmentNotificationDetail(runId: string): NotificationRunDetailMock | null {
  return details.get(runId) ?? null;
}
