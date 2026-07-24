# v2.1.0 リリースチェックリスト

## リリース範囲

v2.1.0は、本番通知処理と社員管理仕様を変更せず、フロントエンド開発基盤の更新を正式リリースとして区切る。

- React / React DOMを19.2系へ更新する
- Viteを8.1系、`@vitejs/plugin-react`を6系へ更新する
- Vitestを4.1系、TypeScriptを6.0系へ更新する
- Oxlint、Vitest、Testing LibraryをWindowsローカル検証とCIへ統合する
- Windowsでbuildした`frontend/dist`だけをRaspberry Piへ反映する開発確認手順を維持する
- 正式リリースは従来どおりRaspberry Pi上の`scripts/deploy.sh`で実行する
- 公開バージョンを2.1.0へ更新する
- CHANGELOG、README、operations、リリースチェックリスト、回帰テストを更新する

threshold、weekly、healthの通知条件・実行時刻・本番`employeeKey.csv`参照方式・本番SQLite社員データ・本番KOT同期判定は変更しない。

## Windows側の事前検証

```powershell
cd D:\_dev\division-overtime

.\scripts\verify.ps1
git status
```

問題の切り分けでは、次を個別実行する。

```powershell
uv sync --frozen --extra web --extra dev
uv run python .\scripts\check_version.py --root .
uv run ruff check .
uv run ruff format --check .
uv run pytest -q

cd frontend
npm ci
npm ls react react-dom vite vitest typescript @vitejs/plugin-react
npm audit
npm run lint
npm run test
npm run build
cd ..

git diff --check
```

合格条件:

- バージョン整合性が`version_check=ok version=2.1.0`
- `.\scripts\verify.ps1`が全工程成功で完了
- Ruff、pytest、Oxlint、Vitest、frontend buildが成功
- `npm audit`が`0 vulnerabilities`
- `npm ls`で依存関係の重複・不整合がない
- `git diff --check`が無出力
- 作業ツリーがclean

## Pull RequestとCI確認

- Pull Request本文に`Closes #Issue番号`がある
- GitHub ActionsのCI結果を確認している
- マージ方式がsquash mergeである
- マージ後の`main`と`origin/main`が一致している

ローカル検証を主たる品質確認とし、CIはクリーン環境での補助確認として扱う。CIはmergeの必須条件ではないが、失敗している場合は原因を確認し、未解決のままRaspberry Piへ反映しない。

## Raspberry Piへの反映

```bash
cd /home/pi/division-overtime
git switch main
git status --short
./scripts/deploy.sh
```

`deploy.sh`はソース更新、依存更新、フロントビルド、全検証、Web再起動、APIヘルスチェック、稼働バージョン一致確認まで実行する。

合格例:

```text
version_check=ok version=2.1.0
Deployment completed. version=2.1.0
```

## 実機確認

### バージョン・Web

```bash
curl -fsS http://127.0.0.1:8000/api/system/health
curl -fsS http://127.0.0.1:8000/api/version
systemctl status division-overtime-web.service --no-pager
```

- `status`が`ok`
- `version`が`2.1.0`
- `frontendBuilt`が`true`
- Webサービスが`active (running)`

### 通知処理の独立性

```bash
sudo systemctl stop division-overtime-web.service
systemctl list-timers --all | grep division-overtime
.venv/bin/division-overtime --root . health
sudo systemctl start division-overtime-web.service
curl -fsS http://127.0.0.1:8000/api/system/health
```

Web停止中もthreshold、weekly、health、employee-consistencyのtimerが`active (waiting)`であり、CLI healthが成功することを確認する。実通知サービスの手動実行は不要とし、直近のsystemd実行結果とjournalを確認する。

```bash
systemctl show division-overtime-threshold.service -p Result -p ExecMainStatus
systemctl show division-overtime-weekly.service -p Result -p ExecMainStatus
systemctl show division-overtime-health.service -p Result -p ExecMainStatus
```

### 本番Slack表示確認を伴う通知テスト

通知本文やSlack表示を確認するためにweeklyを実送信すると、その週・社員・受信者の重複防止キーが`notification_attempts`へ保存される。同じ週の正規weeklyでは、その受信者向けの対象社員が重複スキップされるため、実送信テスト後は必ず履歴を確認する。

実送信前にDBをバックアップする。

```bash
cd /home/pi/division-overtime
BACKUP="var/division_overtime-before-notification-test-$(date +%Y%m%d_%H%M%S).sqlite3"
sqlite3 var/division_overtime.sqlite3 ".backup '$BACKUP'"
chmod 600 "$BACKUP"
```

実送信後、対象の`run_id`、受信者、通知種別、Slack timestampを確認する。

```bash
sqlite3 -header -column var/division_overtime.sqlite3 "
SELECT
  er.run_id,
  er.mode,
  er.dry_run,
  er.started_at,
  na.recipient,
  na.notification_type,
  na.status,
  COUNT(*) AS records,
  MIN(na.slack_timestamp) AS slack_timestamp
FROM execution_runs AS er
JOIN notification_attempts AS na ON na.run_id = er.run_id
WHERE er.started_at >= datetime('now', '-1 day')
GROUP BY
  er.run_id, er.mode, er.dry_run, er.started_at,
  na.recipient, na.notification_type, na.status
ORDER BY er.started_at DESC;
"
```

正規weeklyより前に、テスト専用の実送信履歴を復旧する必要がある場合は、対象`run_id`と受信者を特定し、削除予定件数を先に確認する。対象を広く指定しない。

```bash
TEST_RUN_ID='<テスト実行のrun_id>'
TEST_RECIPIENT='<テスト受信者>'

sqlite3 -header -column var/division_overtime.sqlite3 "
SELECT id, dedupe_key, recipient, status, slack_timestamp, created_at
FROM notification_attempts
WHERE run_id = '$TEST_RUN_ID'
  AND recipient = '$TEST_RECIPIENT'
  AND notification_type = 'weekly'
ORDER BY id;
"
```

表示内容と件数がテスト送信分だけであることを確認してから、トランザクション内で対象行だけを削除する。

```bash
sqlite3 var/division_overtime.sqlite3 "
BEGIN IMMEDIATE;
DELETE FROM notification_attempts
WHERE run_id = '$TEST_RUN_ID'
  AND recipient = '$TEST_RECIPIENT'
  AND notification_type = 'weekly';
SELECT changes();
COMMIT;
"

sqlite3 var/division_overtime.sqlite3 'PRAGMA integrity_check;'
```

- 削除件数が事前確認件数と一致する
- `PRAGMA integrity_check`が`ok`
- 他の受信者やthreshold履歴を削除していない
- バックアップをGitへ追加しない

通常のリリース確認では、実通知サービスを手動実行せず、直近のsystemd実行結果とjournalを確認する。Slack表示確認が必要なリリースに限って、この手順を使用する。

### 社員データ

```bash
.venv/bin/division-overtime --root . employees check-consistency
sqlite3 var/division_overtime.sqlite3 'PRAGMA integrity_check;'
```

- SQLiteとCSVが一致
- `PRAGMA integrity_check`が`ok`
- 管理画面の社員数とCSV件数が一致

### KOT同期

API利用禁止時間帯を避け、管理画面で「KOTから取得」だけを実行する。

- プレビュー取得だけではSQLiteとCSVが変化しない
- create/update/reactivate/disable/unchangedの件数が妥当
- KOT退職済み未登録社員が候補に出ない
- KOT Keyとトークンが画面・APIへ出ない
- 不要な候補は選択しない

## バックアップ確認

```bash
find data/backups/employee-csv -maxdepth 1 -type f -printf '%f\n' | sort | tail
find var/backups/kot-sync -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort | tail
find var/backups/employee-delete -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort | tail
```

バックアップファイルの中身をGitへ追加しない。KOT同期とCSV置換前バックアップは最新30世代を維持する。

## ロールバック判断

次の場合は新しい社員操作やKOT反映を中止する。

- Web healthのバージョンが`VERSION`と一致しない
- SQLite integrity checkが`ok`でない
- SQLite/CSV整合性が不一致
- threshold、weekly、healthのtimerが停止している
- Web起動後に既存通知サービスの実行結果が悪化した

コードのみ戻す場合:

```bash
cd /home/pi/division-overtime
git log --oneline -n 5
git switch --detach <直前の正常コミット>
./scripts/deploy.sh
```

この方法は緊急確認用とし、恒久対応はWindows側でrevert用PRを作成してmainへ反映する。DB・CSVを戻す必要がある場合は、先に現状を退避してから`docs/operations.md`の復旧手順を使用する。

## リリース作成

全項目確認後、Windows側でタグを作成する。

```powershell
cd D:\_dev\division-overtime
git switch main
git fetch origin
git merge --ff-only origin/main
git status

git tag -a v2.1.0 -m "division-overtime v2.1.0"
git push origin v2.1.0

gh release create v2.1.0 `
  --title "v2.1.0" `
  --generate-notes
```

リリース後にGitHub上のタグ、Release、mainのコミット、Raspberry Piの`/api/system/health`がすべて`2.1.0`を指すことを確認する。
