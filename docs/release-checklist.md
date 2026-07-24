# v2.0.2 リリースチェックリスト

## リリース範囲

v2.0.2は、本番通知処理と社員管理仕様を変更せず、WindowsローカルでのWeb UI開発を安全かつ効率的にする小規模リリースとする。

- development/production設定切替を追加
- 開発専用SQLite、`employeeKey.csv`、ダミー社員データを追加
- Viteホットリロードを利用するローカル開発手順を追加
- 開発環境ではKOT本番APIへの接続を停止
- `create`、`update`、`reactivate`、`disable`、`unchanged`を再現するダミーKOT同期プレビューを追加
- 公開バージョンを2.0.2へ更新
- CHANGELOG、README、リリースチェックリスト、回帰テストを更新

threshold、weekly、healthの通知条件・実行時刻・本番`employeeKey.csv`参照方式・本番SQLite社員データ・本番KOT同期判定は変更しない。

## Windows側の事前検証

```powershell
cd D:\_dev\division-overtime

python .\scripts\check_version.py --root .
ruff check .
ruff format --check .
pytest -q

cd frontend
npm ci
npm run build
cd ..

git diff --check
git status
```

合格条件:

- バージョン整合性が`version_check=ok version=2.0.2`
- Ruff、pytest、frontend buildが成功
- `git diff --check`が無出力
- 作業ツリーがclean

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
version_check=ok version=2.0.2
Deployment completed. version=2.0.2
```

## 実機確認

### バージョン・Web

```bash
curl -fsS http://127.0.0.1:8000/api/system/health
curl -fsS http://127.0.0.1:8000/api/version
systemctl status division-overtime-web.service --no-pager
```

- `status`が`ok`
- `version`が`2.0.2`
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

git tag -a v2.0.2 -m "division-overtime v2.0.2"
git push origin v2.0.2

gh release create v2.0.2 `
  --title "v2.0.2" `
  --generate-notes
```

リリース後にGitHub上のタグ、Release、mainのコミット、Raspberry Piの`/api/version`がすべて`2.0.2`を指すことを確認する。
