# Operations

## 運用原則

- Windows側リポジトリを正本とし、変更はローカルで検証・コミット・pushする。
- Raspberry Pi側は`git pull`で反映し、実機固有設定はGitへ含めない。
- 定期実行はsystemd timerのみを使用し、cronと併用しない。
- 正常性のSlack通知は送信しない。正常時の通知は運用ノイズになるため、journalと終了コードで確認する。

## KING OF TIME API利用禁止時間帯

次の時間帯（JST）はAPIを呼び出さない。

- 毎日 08:30〜10:00
- 毎日 17:30〜18:30

定期実行は次のため禁止時間帯外である。

- threshold: 平日10:30
- weekly: 金曜21:30

手動の`run`および`--dry-run`も禁止時間帯を避ける。
healthはKING OF TIME APIを呼び出さない。

## 設定検証

```bash
cd /home/pi/division-overtime
.venv/bin/division-overtime --root . validate-config
.venv/bin/division-overtime --root . database status
```

実運用ファイル:

```text
.env
config/production.toml
data/employeeKey.csv
var/division_overtime.sqlite3
```

推奨権限:

```bash
chmod 600 .env config/production.toml data/employeeKey.csv
```

## Dry run

```bash
.venv/bin/division-overtime --root . run threshold --dry-run
.venv/bin/division-overtime --root . run weekly --dry-run
```

Dry runは次を行う。

- KING OF TIME APIからデータ取得
- 残業計算と通知候補の生成
- 実行履歴と残業スナップショットの保存

Dry runは次を行わない。

- Slack送信
- 通知重複防止キーの消費

ログの`recipient=`を確認し、想定外の通知先がないことを必ず確認する。

## タイマー確認

```bash
systemctl list-timers --all | grep division-overtime
systemctl status division-overtime-threshold.timer --no-pager
systemctl status division-overtime-weekly.timer --no-pager
systemctl status division-overtime-health.timer --no-pager
```

正常状態:

```text
Loaded: loaded (...; enabled; ...)
Active: active (waiting)
Trigger: 次回実行日時
```

タイマーの再配置・再有効化:

```bash
sudo cp systemd/*.service /etc/systemd/system/
sudo cp systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now \
  division-overtime-threshold.timer \
  division-overtime-weekly.timer \
  division-overtime-health.timer
```

## サービスの手動実行

```bash
sudo systemctl start division-overtime-threshold.service
sudo systemctl start division-overtime-weekly.service
sudo systemctl start division-overtime-health.service
```

各serviceは`Type=oneshot`のため、成功後は`inactive (dead)`になる。
正常性は以下で確認する。

```bash
systemctl show division-overtime-weekly.service \
  -p Result \
  -p ExecMainCode \
  -p ExecMainStatus \
  -p ActiveState \
  -p SubState
```

正常例:

```text
Result=success
ExecMainCode=1
ExecMainStatus=0
ActiveState=inactive
SubState=dead
```

## ログ確認

```bash
journalctl -u division-overtime-threshold.service -n 100 --no-pager --output=short-iso
journalctl -u division-overtime-weekly.service -n 100 --no-pager --output=short-iso
journalctl -u division-overtime-health.service -n 100 --no-pager --output=short-iso
```

直近起動分のみ:

```bash
journalctl -u division-overtime-threshold.service -b --no-pager
```

## ヘルスチェック

手動実行:

```bash
.venv/bin/division-overtime --root . health
echo $?
```

正常例:

```text
database_integrity=ok
employee_csv_exists=True
0
```

healthは軽量なローカル診断であり、次を行わない。

- KING OF TIME APIへのアクセス
- Slackへの正常通知
- Slackへの定期ヘルス通知

## SQLite確認

整合性とWAL:

```bash
sqlite3 var/division_overtime.sqlite3 'PRAGMA integrity_check;'
sqlite3 var/division_overtime.sqlite3 'PRAGMA journal_mode;'
```

期待値:

```text
ok
wal
```

実行履歴:

```bash
sqlite3 -header -column var/division_overtime.sqlite3 \
  "SELECT
     run_id,
     mode,
     status,
     dry_run,
     started_at,
     finished_at,
     error_message
   FROM execution_runs
   ORDER BY started_at DESC
   LIMIT 10;"
```

通知履歴:

```bash
sqlite3 -header -column var/division_overtime.sqlite3 \
  "SELECT
     employee_code,
     recipient,
     notification_type,
     threshold_percent,
     status,
     attempt_count,
     slack_timestamp,
     error_message,
     updated_at
   FROM notification_attempts
   ORDER BY id DESC
   LIMIT 20;"
```

重複防止確認:

```bash
sqlite3 -header -column var/division_overtime.sqlite3 \
  "SELECT recipient, status, attempt_count, COUNT(*) AS records
   FROM notification_attempts
   WHERE notification_type = 'weekly'
   GROUP BY recipient, status, attempt_count;"
```

## KOT同期バックアップと復旧

### バックアップ作成

管理画面で「選択した差分を反映」を実行すると、SQLite更新前に自動バックアップを作成する。

```text
var/backups/kot-sync/YYYYMMDD_HHMMSS_ffffff/
├── division_overtime.sqlite3
└── employeeKey.csv  # 反映前に存在する場合のみ
```

バックアップDBはSQLite Backup APIで作成し、`PRAGMA integrity_check`が`ok`になった場合だけ同期反映を続行する。バックアップに失敗した場合、SQLite社員情報と`data/employeeKey.csv`は変更しない。

バックアップ確認:

```bash
cd /home/pi/division-overtime
find var/backups/kot-sync -maxdepth 2 -type f -printf '%TY-%Tm-%Td %TH:%TM:%TS %p\n' | sort
```

バックアップDBの整合性確認:

```bash
BACKUP_DIR="var/backups/kot-sync/<対象日時>"
sqlite3 "$BACKUP_DIR/division_overtime.sqlite3" 'PRAGMA integrity_check;'
```

期待値:

```text
ok
```

### 復旧手順

DBとCSVは必ず同じバックアップ世代から復旧する。復旧中はWebから社員情報が更新されないようにWebサービスだけを停止する。threshold、weekly、healthのtimerは停止しない。

```bash
cd /home/pi/division-overtime
BACKUP_DIR="var/backups/kot-sync/<対象日時>"

sudo systemctl stop division-overtime-web.service

cp -a var/division_overtime.sqlite3 \
  "var/division_overtime.sqlite3.before-restore-$(date +%Y%m%d_%H%M%S)"

if [ -f data/employeeKey.csv ]; then
  cp -a data/employeeKey.csv \
    "data/employeeKey.csv.before-restore-$(date +%Y%m%d_%H%M%S)"
fi

cp -a "$BACKUP_DIR/division_overtime.sqlite3" var/division_overtime.sqlite3

if [ -f "$BACKUP_DIR/employeeKey.csv" ]; then
  cp -a "$BACKUP_DIR/employeeKey.csv" data/employeeKey.csv
else
  rm -f data/employeeKey.csv
fi

chmod 600 var/division_overtime.sqlite3
if [ -f data/employeeKey.csv ]; then
  chmod 600 data/employeeKey.csv
fi

sqlite3 var/division_overtime.sqlite3 'PRAGMA integrity_check;'
sudo systemctl start division-overtime-web.service
curl -fsS http://127.0.0.1:8000/api/system/health
echo
```

復旧後に次を確認する。

```bash
systemctl is-active \
  division-overtime-threshold.timer \
  division-overtime-weekly.timer \
  division-overtime-health.timer \
  division-overtime-web.service
```

- SQLite整合性が`ok`
- Web API healthが`status: ok`
- 4サービスが`active`
- 社員一覧と`employeeKey.csv`の内容が対象バックアップ世代と一致

## 更新手順

Windows側でRuff・pytest・差分確認・pushを完了した後、Piで実行する。

```bash
cd /home/pi/division-overtime
git pull
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest -q
systemd-analyze verify systemd/*.service systemd/*.timer
```

systemd定義に変更がある場合:

```bash
sudo cp systemd/*.service /etc/systemd/system/
sudo cp systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
```

## 障害時の確認順序

1. `systemctl list-timers --all | grep division-overtime`
2. 対象serviceのjournalを確認
3. `database status`と`PRAGMA integrity_check`を確認
4. `.env`、`production.toml`、社員CSVの存在と権限を確認
5. API利用禁止時間帯でないことを確認
6. `--dry-run`で通知候補と宛先を確認
7. 必要に応じてserviceを手動実行

実送信を再試行する前に、DBの`notification_attempts`を確認して重複送信を防ぐ。
