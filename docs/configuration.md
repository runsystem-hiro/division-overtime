# Configuration

## 設定の読込順

1. `config/default.toml`
2. `DIVISION_OVERTIME_ENV`に対応する`config/development.toml`または`config/production.toml`
3. `.env`の環境変数

`DIVISION_OVERTIME_ENV`の既定値は`production`です。指定できる値は`development`と`production`です。

TOMLは非秘密設定、`.env`は環境選択、外部サービスの認証情報、Web認証・セッション設定を扱います。

## `.env`

主要項目:

```dotenv
DIVISION_OVERTIME_ENV=production
KINGOFTIME_TOKEN=replace_me
KOT_SYNC_DIVISION_CODES=100,200,300
SLACK_BOT_TOKEN=xoxb-replace_me

WEB_HOST=0.0.0.0
WEB_PORT=8000
WEB_LOG_LEVEL=INFO
WEB_ADMIN_USERNAME=admin
WEB_ADMIN_PASSWORD_HASH=replace_with_argon2_hash
WEB_VIEWER_USERNAME=viewer
WEB_VIEWER_PASSWORD_HASH=replace_with_argon2_hash
WEB_SESSION_SECRET=replace_with_at_least_32_random_characters
WEB_SESSION_COOKIE_NAME=division_overtime_session
WEB_SESSION_COOKIE_SECURE=false
WEB_SESSION_MAX_AGE_SECONDS=28800
WEB_LOGIN_MAX_ATTEMPTS=5
WEB_LOGIN_WINDOW_SECONDS=900
WEB_LOGIN_LOCKOUT_SECONDS=900
```

### 通知CLIに必須

- `KINGOFTIME_TOKEN`
- `SLACK_BOT_TOKEN`

### Web起動に必須

- `WEB_ADMIN_USERNAME`
- `WEB_ADMIN_PASSWORD_HASH`
- `WEB_VIEWER_USERNAME`（任意。閲覧専用ユーザー名）
- `WEB_VIEWER_PASSWORD_HASH`（任意。閲覧専用ユーザーのArgon2ハッシュ）
- `WEB_SESSION_SECRET`（32文字以上）

Web単体起動ではSlack tokenを必須としません。KOT同期は`KINGOFTIME_TOKEN`が未設定の場合、またはTOMLでKOTが無効の場合に利用できません。

パスワードハッシュ生成:

```bash
.venv/bin/division-overtime-web-hash-password
```

本番でHTTPSを終端する場合は`WEB_SESSION_COOKIE_SECURE=true`を設定します。

## `config/default.toml`

共通の非秘密設定を保存します。

- timezone
- SQLiteパス
- `employeeKey.csv`パス
- log level
- KING OF TIME API base URL / endpoint / timeout / retry
- 既定残業目安
- 通知閾値
- 部署別残業目安
- 本人通知設定
- 部署別通知先

KING OF TIME API base URLは`.env`ではなくTOMLで管理します。

## 環境別TOML

### production

`config/production.toml.example`をコピーして作成します。

```bash
cp config/production.toml.example config/production.toml
chmod 600 config/production.toml
```

`config/production.toml`はGit管理対象外です。

### development

`config/development.toml`は開発用DB、開発用CSV、KOT mock、通知抑止を設定します。実社員データや本番tokenを利用しません。

## 残業目安時間

決定順:

1. 社員の`personal_target_minutes`
2. `overtime.division_targets`の部署別値
3. `overtime.default_target_minutes`

`0`は未設定ではなく「目安0分」です。残業が発生した場合、100%超過相当として扱います。

## 通知先

```toml
[notifications]
enable_self_notify = true
self_notify_employee_codes = ["00001"]

[notifications.department_recipients]
ALL = ["admin@example.com"]
"100" = ["manager@example.com"]
```

- `ALL`: 全社員を対象とする受信者
- 部署コード: その部署だけを対象とする受信者
- 本人通知先: 社員CSVのメールアドレス

`notifications.department_recipients`は環境別TOMLでテーブル全体を置換します。sampleの宛先が本番に残らないよう、本番ファイルで必要な全宛先を定義してください。

## 実データファイル

- `.env`
- `config/production.toml`
- `data/employeeKey.csv`
- SQLite DB
- `var/backups/`

これらはGitへ追加しません。

## Web管理UIのロール

- `admin`: 社員追加・編集・削除、整合性の再確認、KOT取得・同期反映を含む全操作
- `viewer`: 社員一覧・検索・再読み込み、KOT同期画面の表示、通知履歴一覧・詳細の閲覧のみ

閲覧専用アカウントを使用する場合は、`WEB_VIEWER_USERNAME`と`WEB_VIEWER_PASSWORD_HASH`を両方設定します。片方だけ設定した場合、Webアプリは設定エラーとして起動しません。画面上のボタン無効化に加え、更新系APIはサーバー側でもHTTP 403で拒否します。

## Cloudflare Access

公開URLでviewer自動認証を使う場合は `CLOUDFLARE_ACCESS_ENABLED=true` とし、team domainとApplication Audienceを環境変数へ設定します。実値、メールアドレス、JWT、パスワードはリポジトリへ保存しません。`ADMIN_ELEVATION_MINUTES` の既定値は30です。
