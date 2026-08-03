# Backup and Restore

## バックアップの種類

- 手動SQLiteバックアップ: `var/backups/manual-database/`
- deploy前DBバックアップ: `var/backups/deploy-database/`
- KOT同期前バックアップ: `var/backups/kot-sync/`
- employee CSV置換前バックアップ: `data/backups/employee-csv/`
- 社員削除前バックアップ: `var/backups/employee-delete/`

バックアップファイルはGitへ追加しません。

## deploy前バックアップ

正式deployでは`database migrate`が既存DBの存在とschema versionを確認し、SQLite Backup APIで`var/backups/deploy-database/<timestamp>/division_overtime.sqlite3`へバックアップしてからスキーマ更新を実行します。DB不在、バックアップ失敗、マイグレーション失敗、更新後integrityエラーのいずれかではWeb再起動へ進みません。

`database migrate`は新規環境の初期化には使用しません。新規環境では明示的に`database init`を実行し、本番deployでは既存DBを暗黙作成しない運用を維持します。

deploy前DBバックアップは、バックアップ作成・マイグレーション・更新後integrity確認が成功した後に、認識可能な正常世代だけを対象として最新30世代を保持します。整理に失敗した場合は警告を記録し、次回deployで再試行します。

## 自動生成バックアップの保持

自動生成バックアップは次の保持方針です。保持数は共通定数で30に統一します。

- `var/backups/deploy-database/`: 最新30世代
- `var/backups/kot-sync/`: 最新30世代（現行動作を維持）
- `var/backups/employee-delete/`: 最新30世代
- `data/backups/employee-csv/`: 最新30ファイル

社員削除前バックアップはDBとCSVが揃った正常世代だけを対象にし、社員削除が成功した後に整理します。employee CSV置換前バックアップはCSVの安全な置換が成功した後に整理します。想定外のファイル・不完全世代・symlinkは自動削除しません。

`var/backups/manual-database/`、`var/backups/manual-restore/`、`var/backups/restore-test/`は自動削除の対象外です。

> 本番固有のインストールパス、service / timer名、実行ユーザー、バックアップ保存先、世代数はリポジトリ外の運用手順で管理してください。

## 稼働中SQLiteの手動バックアップ

```bash
cd <app-root>
.venv/bin/division-overtime --root . database backup
```

既定出力:

```text
var/backups/manual-database/<timestamp>/division_overtime.sqlite3
```

このコマンドはSQLite Backup APIで一貫したバックアップを一時ファイルへ作成し、`PRAGMA integrity_check`成功後に配置します。POSIX環境では権限を`0600`に設定します。

明示的な出力先:

```bash
.venv/bin/division-overtime --root . database backup \
  --output var/backups/manual-database/manual/division_overtime.sqlite3
```

稼働中DBのmainファイルだけを`cp`しないでください。WALに未チェックポイントの変更がある場合、不完全なコピーになります。

## バックアップ確認

```bash
BACKUP='var/backups/manual-database/<timestamp>/division_overtime.sqlite3'
stat -c '%a %U %G %n' "$BACKUP"
sqlite3 "$BACKUP" 'PRAGMA integrity_check;'
```

期待値:

- 権限`600`
- 所有者が実行ユーザー
- `integrity_check`が`ok`

## 復元前の原則

- 復元元を別パスで検査する
- 現在のDBとCSVを追加退避する
- DBとCSVを同一世代で扱う
- Webと通知serviceを停止してから置換する
- timerの次回起動時刻を確認する
- 復旧後に整合性、health、timerを確認する

## SQLite復元の確認

本番DBへ直接戻す前に別パスで確認します。

```bash
sqlite3 /path/to/backup.sqlite3 'PRAGMA integrity_check;'
sqlite3 /path/to/backup.sqlite3 \
  "SELECT key, value FROM schema_meta WHERE key='schema_version';"
```

主要テーブル件数も確認します。

```bash
sqlite3 /path/to/backup.sqlite3 \
  "SELECT 'employees', COUNT(*) FROM employees
   UNION ALL SELECT 'execution_runs', COUNT(*) FROM execution_runs
   UNION ALL SELECT 'notification_attempts', COUNT(*) FROM notification_attempts
   UNION ALL SELECT 'kot_sync_runs', COUNT(*) FROM kot_sync_runs;"
```

## 緊急復元

実施前に通知timerの次回起動まで十分な時間があることを確認します。

```bash
cd <app-root>

sudo systemctl stop <web-service>
sudo systemctl stop <notification-timer-1>
sudo systemctl stop <notification-timer-2>
sudo systemctl stop <health-timer>
sudo systemctl stop <consistency-timer>

.venv/bin/division-overtime --root . database backup
cp -a data/employeeKey.csv "data/employeeKey.csv.before-restore-$(date +%Y%m%d_%H%M%S)"
```

復元対象を配置した後:

```bash
chmod 600 var/division_overtime.sqlite3 data/employeeKey.csv
rm -f var/division_overtime.sqlite3-wal var/division_overtime.sqlite3-shm

.venv/bin/division-overtime --root . database status
.venv/bin/division-overtime --root . employees check-consistency
.venv/bin/division-overtime --root . health

sudo systemctl start <web-service>
sudo systemctl start <notification-timer-1>
sudo systemctl start <notification-timer-2>
sudo systemctl start <health-timer>
sudo systemctl start <consistency-timer>

curl -fsS <health-url>/api/system/health
systemctl list-timers --all | grep <timer-name-pattern>
```

不一致や整合性エラーがある場合はtimerを再開せず、退避した現状または別の正常世代へ戻します。
