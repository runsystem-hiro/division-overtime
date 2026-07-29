# division-overtime

KING OF TIMEの月次勤怠データを取得し、部署ごとの残業状況をSlackへ通知する業務アプリです。Raspberry Pi上でsystemd timerにより定期実行し、Web管理UIから社員情報、KOT同期、通知履歴を管理できます。

## 主な機能

- 平日10:30の残業閾値通知
- 金曜21:30の週次残業レポート
- 部署・個人・既定値の優先順位による残業目安時間の判定
- Slack DMによる部署向け・本人向け通知
- ISO週単位の重複送信防止と失敗通知の再試行
- SQLiteによる実行履歴、残業スナップショット、通知試行の管理
- Web認証付き社員管理UI
- 社員一覧の検索条件表示、結果件数、条件別の空状態を備えたレスポンシブUI
- SQLiteから`employeeKey.csv`を生成する既存通知互換構成
- KING OF TIME社員同期のプレビュー、選択適用、履歴、反映前バックアップ
- 通知実行履歴の一覧・詳細・重複元追跡
- 稼働中SQLiteの安全な手動バックアップとDB観測
- systemd service / timer、ローカルhealth check、デプロイ後health check

## システム構成

```text
KING OF TIME
    |
    v
Python notification service ----> Slack DM
    |
    +---- SQLite execution history / notification history
    |
    +---- employeeKey.csv (notification input)

Web administration UI
    |
    +---- SQLite employee management
    +---- employeeKey.csv generation
    +---- KOT employee sync
    +---- notification history
```

社員管理の正本はSQLiteです。ただし既存通知処理は現在も`data/employeeKey.csv`を参照します。Webで社員情報を変更すると、SQLiteとCSVを整合性を保って更新します。

詳細は[アーキテクチャ](docs/architecture.md)を参照してください。

## 動作環境

### 本番

- Raspberry Pi 4B 64-bit
- systemdを利用できるLinux
- Python `>=3.11,<3.14`（本番確認環境はPython 3.13）
- Node.js `>=20.19.0,<25`
- npm `>=9.2.0`
- SQLite 3

本アプリはGUIやデスクトップセッションに依存しません。

### 開発

- Python 3.13推奨
- uv
- Node.js 22推奨
- npm

Python依存は`uv.lock`、frontend依存は`frontend/package-lock.json`で固定します。具体的な開発手順は[開発ガイド](docs/development.md)を参照してください。

## 導入

### 1. リポジトリを配置

```bash
cd /home/pi
git clone <repository-url> division-overtime
cd division-overtime
```

### 2. 実行環境用ファイルを作成

```bash
cp .env.example .env
cp config/production.toml.example config/production.toml
cp data/employeeKey.sample.csv data/employeeKey.csv
chmod 600 .env config/production.toml data/employeeKey.csv
```

`.env`にはトークン、Web管理者認証、セッション秘密鍵などの環境変数を設定します。KING OF TIME APIのベースURL、DBパス、残業目安、通知先などの非秘密設定はTOMLで管理します。

設定項目と優先順位は[設定ガイド](docs/configuration.md)を参照してください。

### 3. インストール

```bash
./scripts/install.sh
```

このスクリプトはPython仮想環境を作成し、Python依存とsystemd unitをインストールします。frontendの依存とbuildは正式デプロイ時に`deploy.sh`が行います。

### 4. 設定とDBを確認

```bash
.venv/bin/division-overtime --root . validate-config
.venv/bin/division-overtime --root . database init
.venv/bin/division-overtime --root . database status
.venv/bin/division-overtime --root . health
```

### 5. 通知内容をdry-runで確認

KING OF TIME API利用禁止時間帯を避けて実行します。

```bash
.venv/bin/division-overtime --root . run threshold --dry-run --source test
.venv/bin/division-overtime --root . run weekly --dry-run --source test
```

### 6. systemdを有効化

通知先、社員情報、dry-run結果を確認してから有効化します。

```bash
sudo systemctl enable --now division-overtime-threshold.timer
sudo systemctl enable --now division-overtime-weekly.timer
sudo systemctl enable --now division-overtime-health.timer
sudo systemctl enable --now division-overtime-employee-consistency.timer
sudo systemctl enable --now division-overtime-web.service
```

導入・移行時の詳細確認は[移行ガイド](docs/migration.md)を参照してください。

## 設定ファイル

| ファイル                  | 用途                                                      | Git管理 |
| ------------------------- | --------------------------------------------------------- | ------- |
| `.env`                    | 環境選択、外部サービスのトークン、Web認証・セッション設定 | 対象外  |
| `config/default.toml`     | 共通の非秘密設定                                          | 対象    |
| `config/production.toml`  | 本番の非秘密設定上書き                                    | 対象外  |
| `config/development.toml` | 開発環境の非秘密設定                                      | 対象    |
| `data/employeeKey.csv`    | 通知処理が参照する社員CSV                                 | 対象外  |

設定は`config/default.toml`を基準に、`DIVISION_OVERTIME_ENV`に対応するTOMLで上書きします。`notifications.department_recipients`は追加ではなくテーブル全体を置換します。

## 基本コマンド

```bash
# 設定検証
.venv/bin/division-overtime --root . validate-config

# 通知実行
.venv/bin/division-overtime --root . run threshold --source manual
.venv/bin/division-overtime --root . run weekly --source manual

# ローカルhealth
.venv/bin/division-overtime --root . health

# DB初期化・観測・バックアップ
.venv/bin/division-overtime --root . database init
.venv/bin/division-overtime --root . database status
.venv/bin/division-overtime --root . database backup

# SQLiteとCSVの整合性確認
.venv/bin/division-overtime --root . employees check-consistency
```

`database backup`はSQLite Backup APIを使い、既定では`var/backups/manual-database/<timestamp>/division_overtime.sqlite3`へ所有者限定権限で作成します。

## Web管理UI

Webサービスの既定URLは次です。

```text
http://<raspberry-pi>:8000/
```

主な機能:

- 開閉状態を保存できる共通サイドナビゲーションによる社員管理・KOT同期・通知履歴の画面遷移
- ログイン・ログアウト
- 社員一覧、検索、追加、編集
- 無効化、再有効化、削除
- SQLiteとCSVの整合性確認
- KING OF TIME社員同期のプレビューと選択適用
- KOT同期履歴とバックアップ先の確認
- KOT同期プレビューで判定別フィルター、表示中の一括選択、選択内訳、反映件数を確認
- 通知実行履歴の集計、成功・一部失敗・dry-runの判別、送信先別結果、重複元の確認

Web管理UIの起動には`.env`の管理者認証・セッション設定が必要です。画面URLは`/`（社員管理）、`/kot-sync`（KOT同期）、`/notifications`（通知履歴）です。FastAPIのSPAフォールバックにより各URLを直接開けます。
- 共通デザイントークンにより、配色・サーフェス・境界線・余白・フォーカス・軽量モーションを一元管理


## 通知とスケジュール

- threshold: 月曜〜金曜 10:30
- weekly: 金曜 21:30
- health: 起動10分後、その後1時間ごと
- employee consistency: 毎日 03:15

thresholdとweeklyの通知識別キーにはISO年・ISO週が含まれます。同じ週、社員、通知種別、到達閾値、受信者の組み合わせは重複送信しません。週が変わると新しい通知識別キーになります。

KING OF TIME API利用禁止時間帯（JST）:

- 08:30〜10:00
- 17:30〜18:30

手動実行とdry-runでもこの時間帯を避けます。healthはKING OF TIME APIとSlackを呼び出しません。

## 本番デプロイ

Windows側Gitリポジトリを正本とし、mainへsquash merge後、Raspberry Piで手動デプロイします。

```bash
cd /home/pi/division-overtime
./scripts/deploy.sh
```

デプロイ後の確認:

```bash
curl -fsS http://127.0.0.1:8000/api/system/health
```

期待する主要項目:

```json
{ "status": "ok", "version": "<VERSION>", "frontendBuilt": true }
```

詳細は[デプロイガイド](docs/deployment.md)を参照してください。

## ドキュメント

- [アーキテクチャ](docs/architecture.md)
- [設定ガイド](docs/configuration.md)
- [開発ガイド](docs/development.md)
- [デプロイガイド](docs/deployment.md)
- [運用ガイド](docs/operations.md)
- [バックアップ・復旧](docs/backup-restore.md)
- [Web API](docs/api.md)
- [旧版からの移行](docs/migration.md)
- [リリースチェックリスト](docs/release-checklist.md)
- [変更履歴](CHANGELOG.md)

## セキュリティ

Git、ZIP、patch、ログ、テスト出力へ次を含めないでください。

- `.env`
- 実社員を含む`employeeKey.csv`
- SQLite DB
- KING OF TIME API token
- Slack Bot Token
- Web管理者パスワードやセッション秘密鍵
- 本番バックアップ
- 実KING OF TIMEレスポンス

KOT KeyはWeb APIや画面へ既存値を返しません。バックアップと実データは所有者限定権限で管理します。

### 通知履歴UIのローカル表示確認

ローカル開発時に通知履歴の実データがない場合は、`frontend/.env.local` を作成して次を設定します。

```dotenv
VITE_NOTIFICATION_HISTORY_MOCK=true
```

`npm --prefix frontend run dev` で起動すると、成功・一部失敗・失敗・dry-run・実行中・重複スキップ・保留を含む読み取り専用サンプルが表示されます。`import.meta.env.DEV` のときだけ有効なため、production buildと本番SQLiteには影響しません。
