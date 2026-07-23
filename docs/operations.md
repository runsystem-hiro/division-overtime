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

### KOT同期バックアップの権限

KOT同期反映前に新規作成するバックアップは、既定umaskに依存せず次の権限に設定する。

```text
var/backups/kot-sync/<timestamp>/  0700
division_overtime.sqlite3          0600
employeeKey.csv                    0600
```

既存バックアップの権限は自動変更しない。必要に応じて運用者が個別に確認する。

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

## SQLiteとemployeeKey.csvの整合性確認

通知処理の参照先をSQLiteへ切り替える前段として、SQLiteの有効社員と`data/employeeKey.csv`が一致していることを読み取り専用で確認する。

```bash
cd /home/pi/division-overtime
.venv/bin/division-overtime --root . employees check-consistency
echo "exit_code=$?"
```

監視や運用スクリプトで利用する場合はJSON形式で出力する。

```bash
.venv/bin/division-overtime --root . employees check-consistency --json
echo "exit_code=$?"
```

JSONには社員数、SQLite側のみ・CSV側のみの社員コード、内容不一致の社員コードと差分項目名だけを含める。KOT Key、メールアドレス、氏名などの値は出力しない。

一致時の例:

```text
employee_data_consistency=ok database_employees=10 csv_employees=10
exit_code=0
```

不一致時は終了コード`1`となり、次の形式で差分概要を表示する。

```text
employee_data_consistency=mismatch database_employees=10 csv_employees=9
database_only employee_code=00001
csv_only employee_code=00002
field_mismatch employee_code=00003 fields=kot_key,email
exit_code=1
```

- KOT Keyを含む各項目の実値は表示しない
- SQLiteとCSVは変更しない
- 不一致時は通知処理の参照先を切り替えず、社員管理画面またはKOT同期で原因を解消して再確認する
- threshold、weekly、healthは引き続き`data/employeeKey.csv`を参照する

## shadow readの運用確認

threshold・weekly実行時は、通知処理が正として使用する`data/employeeKey.csv`と、SQLiteの有効社員を比較するshadow readを実行する。比較結果はログ出力だけに使用し、通知対象、通知条件、通知本文、通知先、送信可否には影響させない。SQLiteの読み込みや比較に失敗した場合も、CSVによる通知処理を継続する。health処理は社員データを読み込まないため対象外とする。

### 手動確認

KING OF TIME API利用禁止時間帯を避けて実行する。`--dry-run`でもKING OF TIME APIへアクセスする。

```bash
cd /home/pi/division-overtime

.venv/bin/division-overtime --root . run threshold --dry-run 2>&1 |
  grep employee_shadow_read

.venv/bin/division-overtime --root . run weekly --dry-run 2>&1 |
  grep employee_shadow_read
```

一致時の例:

```text
employee_shadow_read=ok csv_employees=14 sqlite_employees=14
```

定期実行のログを確認する場合:

```bash
journalctl \
  -u division-overtime-threshold.service \
  --since "7 days ago" \
  --no-pager |
  grep employee_shadow_read

journalctl \
  -u division-overtime-weekly.service \
  --since "30 days ago" \
  --no-pager |
  grep employee_shadow_read
```

### 確認タイミング

次のタイミングで、最初に`employees check-consistency`を実行し、その後にthresholdまたはweeklyのshadow readを確認する。

- Raspberry Piへのデプロイ後
- KOT社員同期の反映後
- 社員の追加、更新、無効化後
- `employeeKey.csv`の手動変更後
- SQLiteまたはCSVのバックアップ復旧後
- shadow readの不一致または比較失敗を検出した場合

### 不一致時の一次対応

不一致ログには社員コードと差分種別だけを出力し、KOT Key、メールアドレス、社員名などの値は出力しない。

主な差分種別と確認事項:

- CSV側のみ: SQLiteへの取込漏れ、SQLite側の無効化、CSVだけの手動更新
- SQLite側のみ: CSV再生成失敗、SQLiteだけの直接更新、古いCSVの復旧
- 内容不一致: 部署コード、メールアドレス、個人別残業上限分、KOT Keyなどの片側更新
- 比較失敗: SQLiteの読み込み、DB状態、ファイル権限、ディスク容量

一次対応では、次の順序で状態を確認する。

```bash
cd /home/pi/division-overtime

date
git log -3 --oneline

.venv/bin/division-overtime --root . employees check-consistency
echo "consistency_exit=$?"

systemctl is-active \
  division-overtime-threshold.timer \
  division-overtime-weekly.timer \
  division-overtime-health.timer \
  division-overtime-web.service

journalctl \
  -u division-overtime-threshold.service \
  -u division-overtime-weekly.service \
  --since "24 hours ago" \
  --no-pager
```

原因を特定してCSVとSQLiteの一致を回復するまで、CSVを正とする現在の運用を維持する。shadow readの不一致や失敗だけを理由に通知処理を停止したり、SQLiteへ切り替えたりしない。

### SQLite切替前の最低条件

通知処理の参照先をSQLiteへ切り替える場合は、別Issueと小さなPRで実施し、最低限、次の条件を満たすことを確認する。

- thresholdとweeklyの双方で一定期間shadow readが継続一致している
- KOT社員同期後もCSVとSQLiteが一致する
- 社員の追加、更新、無効化後も一致する
- 部署コード、メールアドレス、個人別残業上限分、KOT Keyに変換差異がない
- SQLite障害時のCSVフォールバック方針が決まっている
- デプロイ手順とロールバック手順が整備されている
- dry-run、テスト、Raspberry Pi実機検証が成功している

一定期間一致したことだけを理由に自動的に切り替えない。切替時も既存通知を止めない設計と、CSVへ戻せるロールバック手順を必須とする。

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

DBとCSVは必ず同じバックアップ世代から復旧する。復旧中にWeb更新や通知処理がSQLite・CSVを参照しないよう、Webサービスと通知timerを停止し、oneshot serviceがすべて停止していることを確認してから作業する。

> [!WARNING]
> 復旧は障害対応時だけ実施する。`BACKUP_DIR`を実在するバックアップ世代へ変更し、整合性確認が`ok`であることを確認するまでは、現在のDBとCSVを置き換えない。

#### 1. 復旧元を選定して事前確認する

```bash
cd /home/pi/division-overtime
BACKUP_DIR="var/backups/kot-sync/<対象日時>"

[ -d "$BACKUP_DIR" ] || { echo "バックアップが見つかりません: $BACKUP_DIR" >&2; exit 1; }
[ -f "$BACKUP_DIR/division_overtime.sqlite3" ] || {
  echo "バックアップDBが見つかりません" >&2
  exit 1
}

find "$BACKUP_DIR" -maxdepth 1 -type f -printf '%M %m %p\n' | sort
sqlite3 "$BACKUP_DIR/division_overtime.sqlite3" 'PRAGMA integrity_check;'
```

期待値:

```text
ok
```

`employeeKey.csv`が存在する世代では、DBと同じディレクトリにあるCSVを必ず使用する。バックアップ世代にCSVがない場合は、その時点でCSVが存在しなかった状態へ戻すため、復旧時に現行CSVを削除する。

#### 2. Webと通知処理を停止する

先にtimerを停止し、新しい通知処理が起動しないようにする。その後Webサービスとoneshot serviceを停止する。

```bash
sudo systemctl stop \
  division-overtime-threshold.timer \
  division-overtime-weekly.timer \
  division-overtime-health.timer

sudo systemctl stop \
  division-overtime-web.service \
  division-overtime-threshold.service \
  division-overtime-weekly.service \
  division-overtime-health.service
```

すべて`inactive`であることを確認する。

```bash
systemctl is-active \
  division-overtime-web.service \
  division-overtime-threshold.service \
  division-overtime-weekly.service \
  division-overtime-health.service || true
```

`active`または`activating`が1つでも表示された場合は復旧を開始しない。

#### 3. 現在のDBとCSVを追加退避する

ライブDBの単純コピーは行わず、SQLite Backup APIを使用する。退避先は所有者だけが参照できる権限にする。

```bash
RESTORE_ID="$(date +%Y%m%d_%H%M%S)"
RESTORE_SAFETY_DIR="var/backups/manual-restore/$RESTORE_ID"

install -d -m 700 "$RESTORE_SAFETY_DIR"
sqlite3 var/division_overtime.sqlite3 \
  ".backup '$RESTORE_SAFETY_DIR/division_overtime.sqlite3'"
chmod 600 "$RESTORE_SAFETY_DIR/division_overtime.sqlite3"

if [ -f data/employeeKey.csv ]; then
  install -m 600 data/employeeKey.csv "$RESTORE_SAFETY_DIR/employeeKey.csv"
fi

sqlite3 "$RESTORE_SAFETY_DIR/division_overtime.sqlite3" 'PRAGMA integrity_check;'
printf '復旧前退避先: %s\n' "$RESTORE_SAFETY_DIR"
```

整合性確認が`ok`以外の場合は復旧を中止する。

#### 4. SQLiteとCSVを同一世代から復旧する

停止済みプロセスがないことを再確認してから、WAL・SHMを削除し、権限を限定した一時ファイル経由で置き換える。

```bash
systemctl is-active \
  division-overtime-web.service \
  division-overtime-threshold.service \
  division-overtime-weekly.service \
  division-overtime-health.service || true

rm -f var/division_overtime.sqlite3-wal var/division_overtime.sqlite3-shm

install -m 600 \
  "$BACKUP_DIR/division_overtime.sqlite3" \
  var/division_overtime.sqlite3.restore
mv -f var/division_overtime.sqlite3.restore var/division_overtime.sqlite3

if [ -f "$BACKUP_DIR/employeeKey.csv" ]; then
  install -m 600 "$BACKUP_DIR/employeeKey.csv" data/employeeKey.csv.restore
  mv -f data/employeeKey.csv.restore data/employeeKey.csv
else
  rm -f data/employeeKey.csv data/employeeKey.csv.restore
fi

chmod 600 var/division_overtime.sqlite3
[ ! -f data/employeeKey.csv ] || chmod 600 data/employeeKey.csv
sqlite3 var/division_overtime.sqlite3 'PRAGMA integrity_check;'
```

整合性確認が`ok`以外の場合はサービスを再開せず、後述のロールバックを行う。

#### 5. サービスを再開して確認する

```bash
sudo systemctl start division-overtime-web.service
sudo systemctl start \
  division-overtime-threshold.timer \
  division-overtime-weekly.timer \
  division-overtime-health.timer

curl -fsS http://127.0.0.1:8000/api/system/health
echo

systemctl is-active \
  division-overtime-threshold.timer \
  division-overtime-weekly.timer \
  division-overtime-health.timer \
  division-overtime-web.service

sqlite3 var/division_overtime.sqlite3 'PRAGMA integrity_check;'
ls -l var/division_overtime.sqlite3 data/employeeKey.csv 2>/dev/null || true
```

確認項目:

- SQLite整合性が`ok`
- Web API healthが`status: ok`
- 3つのtimerとWebサービスが`active`
- SQLiteとCSVの権限が`600`
- 社員一覧と`employeeKey.csv`の内容が対象バックアップ世代と一致
- threshold、weekly、healthのoneshot serviceに異常終了がない

#### ロールバック

復旧後の確認に失敗した場合は、手順3で作成した`RESTORE_SAFETY_DIR`から復旧前の状態へ戻す。Webサービスと通知timer/serviceを停止した状態で実行する。

```bash
RESTORE_SAFETY_DIR="var/backups/manual-restore/<復旧前退避日時>"

sudo systemctl stop \
  division-overtime-threshold.timer \
  division-overtime-weekly.timer \
  division-overtime-health.timer \
  division-overtime-web.service \
  division-overtime-threshold.service \
  division-overtime-weekly.service \
  division-overtime-health.service

sqlite3 "$RESTORE_SAFETY_DIR/division_overtime.sqlite3" 'PRAGMA integrity_check;'
rm -f var/division_overtime.sqlite3-wal var/division_overtime.sqlite3-shm

install -m 600 \
  "$RESTORE_SAFETY_DIR/division_overtime.sqlite3" \
  var/division_overtime.sqlite3.restore
mv -f var/division_overtime.sqlite3.restore var/division_overtime.sqlite3

if [ -f "$RESTORE_SAFETY_DIR/employeeKey.csv" ]; then
  install -m 600 \
    "$RESTORE_SAFETY_DIR/employeeKey.csv" \
    data/employeeKey.csv.restore
  mv -f data/employeeKey.csv.restore data/employeeKey.csv
else
  rm -f data/employeeKey.csv data/employeeKey.csv.restore
fi

sqlite3 var/division_overtime.sqlite3 'PRAGMA integrity_check;'
sudo systemctl start division-overtime-web.service
sudo systemctl start \
  division-overtime-threshold.timer \
  division-overtime-weekly.timer \
  division-overtime-health.timer
```

ロールバック後も、Web API health、SQLite整合性、timer状態、社員一覧、CSV内容を同じ手順で確認する。

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


## WebからのKOT社員同期

1. 社員管理画面へログインする
2. KOT社員同期欄で禁止時間帯でないことを確認する
3. 「KOTから取得」で差分をプレビューする
4. 対象を選択して反映する
5. SQLite / employeeKey.csv の整合性が「一致」であることを確認する
6. 最終実行日時と新規・更新・無効化件数を確認する

実行中の再実行はHTTP 409で拒否される。08:30〜10:00および17:30〜18:30はHTTP 423で拒否される。同期前バックアップとCSVの原子的再生成は既存のKOT同期サービスが行う。threshold、weekly、healthは引き続き`data/employeeKey.csv`を参照する。
