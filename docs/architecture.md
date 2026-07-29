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


### Web UI design tokens

Web管理UIは `frontend/src/styles.css` のCSSカスタムプロパティをデザイントークンとして利用する。色、サーフェス、境界線、角丸、影、フォーカスリング、モーション時間を共通化し、社員管理・KOT同期・通知履歴で同じ視覚ルールを適用する。`prefers-reduced-motion` を尊重し、業務操作を妨げるアニメーションは行わない。
KOT同期プレビューは取得件数・表示件数・選択件数を分離して表示し、判定別フィルター、一括選択、選択内訳、反映件数を同じ画面内で確認できる。プレビュー取得だけではデータを変更せず、選択した差分のみを反映する既存仕様を維持する。

社員管理画面は、検索語と有効状態を適用中の条件として明示し、結果件数と条件別の空状態を表示する。PCでは一覧性を優先したテーブル、狭い画面では同じ情報をラベル付きカードとして表示し、社員管理APIやSQLite / CSV整合性確認の仕様は変更しない。

通知履歴画面はexecution_runsとnotification_attemptsを読み取り専用で表示する。実行種別、実行元、dry-run、本番実行、成功、一部失敗、失敗を日本語ラベルで判別し、一覧集計と送信先別結果をPCではテーブル、狭い画面ではカードとして表示する。通知条件、重複防止、timer、送信処理は変更しない。
