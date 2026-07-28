# Architecture

## Runtime flow

1. systemd timer starts a one-shot notification service with `--source timer`.
2. Configuration is loaded from `config/default.toml`, an environment TOML, and `.env`.
3. The notification service validates `employeeKey.csv`.
4. KING OF TIME monthly data is fetched once per division and target month.
5. Execution metadata and overtime snapshots are stored in SQLite.
6. Notification candidates are reserved using a dedupe key.
7. Slack is called only for new candidates or previously failed candidates.
8. Success becomes `sent`, failure remains retryable as `failed`, and duplicates are saved as `skipped` with a reference to the original attempt.

## Components

- Notification CLI: threshold / weekly / health
- SQLite: execution, snapshot, notification, employee, KOT sync history
- Web backend: FastAPI
- Web frontend: React / TypeScript / Vite（History APIを使ったURLベースの画面遷移と共通レイアウト）
- Scheduler: systemd service / timer
- External services: KING OF TIME API, Slack API

## Employee data flow

```text
SQLite employees
    -> atomic employeeKey.csv generation
    -> existing notification service
```

The Web UI manages employees in SQLite. Notification runs intentionally continue to read `data/employeeKey.csv`.

## Execution modes

- `threshold`: weekday threshold evaluation
- `weekly`: Friday report regardless of overtime ratio
- `health`: local integrity and file checks only

`health` does not call KING OF TIME or Slack.

## Notification identity

- Threshold: `threshold:<ISO year>-W<ISO week>:<employee>:<threshold>`
- Weekly: `weekly:<ISO year>-W<ISO week>:<employee>`
- The recipient is part of the database uniqueness condition.
- Self notification uses a separate suffix.

Therefore, the same recipient and condition are deduplicated within an ISO week. A new ISO week produces a new key.

## SQLite durability

- WAL journal mode
- Foreign keys enabled
- 5-second busy timeout
- Explicit transactions
- Partial unique index for non-skipped attempts
- Dry-run does not reserve dedupe keys
- Backup API for consistent online backups

## Configuration

`config/default.toml` is deep-merged with the selected environment TOML. `notifications.department_recipients` is replaced as a whole instead of deep-merged. Secrets and Web authentication settings are loaded from `.env`.

## Web security

- Argon2 password hash
- Server-side in-memory session registry
- HTTP only / SameSite strict cookie
- Optional secure cookie
- Login attempt rate limiting
- KOT Key existing values are not returned to the browser


## Web frontend navigation

認証後の管理画面は共通サイドナビゲーションを持ち、次のURLへ分離しています。

- `/`: 社員管理
- `/kot-sync`: KING OF TIME社員同期
- `/notifications`: 通知実行履歴

画面遷移はブラウザのHistory APIを利用し、FastAPIのSPAフォールバックが各URLへの直接アクセスを`index.html`へ解決します。業務API、通知service、SQLiteスキーマには影響しません。
