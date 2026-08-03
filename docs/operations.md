# Operations

## 運用原則

- 通知serviceを止めない
- 本番データ変更前にpreview、対象、件数を確認する
- 外部APIの利用制限時間帯を避ける
- Web管理UIと通知処理は別プロセスとして扱う
- SQLiteと`employeeKey.csv`の整合性を維持する
- 本番確認でtoken、KOT Key、実社員情報をログやGitへ残さない
- 本番固有のホスト名、ポート、パス、unit名、実行時刻、通知先はリポジトリ外で管理する

## 定期実行

threshold、weekly、health、社員データ整合性確認はsystemd timerで実行します。具体的な時刻と外部APIの利用制限時間帯は環境ごとの設定および社内運用手順を正とします。

## 日常確認

公開ドキュメントでは環境固有値をプレースホルダーで表します。

```bash
APP_ROOT=<app-root>
HEALTH_URL=<health-url>
WEB_SERVICE=<web-service>
TIMER_PATTERN=<timer-name-pattern>

cd "$APP_ROOT"
curl -fsS "$HEALTH_URL/api/system/health"
.venv/bin/division-overtime --root . health
.venv/bin/division-overtime --root . database status
.venv/bin/division-overtime --root . employees check-consistency
systemctl status "$WEB_SERVICE" --no-pager
systemctl list-timers --all | grep "$TIMER_PATTERN"
```

ログ確認では、環境ごとのservice名を使用して`journalctl`を実行します。実際のunit一覧、確認件数、保管期間は社内運用手順で管理してください。

### 通知service定義の確認

unit名はコードと運用の対応関係を示すため公開し、ホスト名、配置先、実行時刻、通知先はリポジトリ外で管理します。正式デプロイ時に`/etc/systemd/system/`へ反映された定義を確認します。

```bash
systemctl cat division-overtime-threshold.service
systemctl cat division-overtime-weekly.service
```

## 手動実行

通知を伴うため、対象・時刻・重複キーへの影響を確認してから実行します。

```bash
.venv/bin/division-overtime --root . run threshold --dry-run --source test
.venv/bin/division-overtime --root . run weekly --dry-run --source test
```

本番送信を手動で行う場合は`--source manual`を使用します。検証履歴を明示したい場合は`--source test`を使用します。

## 重複通知

- threshold: ISO年・ISO週・社員・到達閾値・受信者
- weekly: ISO年・ISO週・社員・受信者
- 本人通知は部署通知と別の識別子

同じ識別条件は`skipped`として履歴に保存され、Web詳細画面から重複元runを確認できます。週が変わると新しい識別キーになります。

## 社員管理

当面の通知経路:

```text
SQLite -> employeeKey.csv -> notification service
```

- 一時停止、復帰予定あり: 無効化
- 退職、異動、恒久対象外: 削除
- KOT在籍中だが通知対象外: KOT同期のcreate候補を選択しない

Web保存はSQLiteとCSVを一体更新し、失敗時は元へ戻します。KOT Keyの既存値は画面やAPIへ返しません。

## KOT社員同期

1. 外部API利用可能時間帯に取得を実行
2. create / update / reactivate / disable / unchangedを確認
3. 反映対象だけを選択
4. 適用
5. 件数、履歴、バックアップ、SQLite/CSV整合性を確認

previewだけではSQLiteとCSVを変更しません。KOT退職済みかつSQLite未登録の社員は候補から除外されます。

## 通知履歴

Web管理UIで次を確認できます。

- 実行時刻、mode、source、dry-run、status
- 対象数、attempt数、sent / failed / skipped
- 受信者、通知種別、Slack timestamp、error
- dedupe key
- 重複元attempt / run / 実行時刻 / source

## 障害時の確認順

1. `/api/system/health`
2. Web service状態
3. timer状態
4. 直近service result / exit code
5. journal
6. `database status`
7. SQLite/CSV整合性
8. `.env`とTOML
9. 外部API利用時間帯と接続状況

具体的なホスト、unit、ログ保存場所、連絡先、復旧判断基準は社内運用手順で管理します。DBやCSVを変更する場合は[バックアップ・復旧](backup-restore.md)を参照してください。

## 通知履歴の確認

通知履歴一覧は最新順に20件ずつ表示します。画面下部の「前へ」「次へ」でページを移動し、表示範囲と全件数を確認します。再読込は現在ページを維持し、詳細画面は実行IDを基準に取得します。履歴件数が増えても一覧APIは必要なページだけをSQLiteから取得します。

## Cloudflare Access認証の確認

公開URLではGoogle認証後にviewerで表示されること、管理者モードの成功・失敗、閲覧者モードへの降格、Accessログアウトを確認します。ローカルURLでは従来のログイン画面が表示されることを確認します。JWTやパスワードをログへ出力しないでください。


## 社員件数の見方

検証ログでは、SQLiteに保持する社員総数と、既存通知処理が読む`employeeKey.csv`の件数を分けて表示します。

```text
employee_count.database_total=19
employee_count.database_enabled=18
employee_count.database_disabled=1
employee_count.csv_records=18
employee_consistency=ok mismatches=0
```

SQLiteには無効社員も保持するため、`database_total`と`csv_records`が異なるだけでは不整合ではありません。整合性比較はDBの有効社員とCSV実レコードを対象とし、`employee_consistency=ok mismatches=0`であれば正常です。CSVヘッダーは`csv_records`へ含めません。

## 自動生成バックアップの状態確認

バックアップを生成・削除せず、現在の世代数と保持状態だけを確認する。

```bash
.venv/bin/division-overtime --root . backups status
```

各種別について `count`、`retention`、`latest`、`ignored`、`status` を表示する。
`status=ok` は認識された世代が保持上限以内で、不正・未管理項目がない状態を示す。
`status=warning` は保持上限超過、symlink、不正な世代名、必要ファイル不足など、診断対象から除外した項目がある状態を示す。
ディレクトリが未作成で0件の場合は正常である。手動バックアップは自動生成バックアップの件数に含めない。
