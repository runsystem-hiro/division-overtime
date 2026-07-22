# division-overtime

KING OF TIMEの月次残業データを部署単位で取得し、残業目安時間に対する到達状況をSlack DMへ通知するRaspberry Pi向け業務アプリです。

管理者・勤怠担当者向けの部署レポートと、条件に応じた社員本人向け通知を扱います。定期実行、実行履歴、通知重複防止、再試行、ローカルヘルスチェックはsystemdとSQLiteで管理します。

## 実行環境

- Raspberry Pi 4B
- Raspberry Pi OS Trixie 64-bit Desktop
- Python 3.13（対応範囲: `>=3.11,<3.14`）
- systemd service / timer
- SQLite 3（WALモード）

本アプリはGUIやデスクトップセッションに依存しません。

## 主な機能

- KING OF TIMEから部署・対象月単位で月次残業データを取得
- 個人別、部署別、既定値の優先順位で残業目安時間を決定
- 平日10:30の閾値通知
- 金曜21:30の週次通知
- 管理者・勤怠担当者には担当範囲のレポートを送信
- 指定社員には早期段階から本人通知
- 指定外社員には強制本人通知閾値以上で本人通知
- Slack通知文面を旧版互換の形式で生成
- SQLiteによる実行履歴、残業スナップショット、通知状態管理
- 通知重複防止と送信失敗時の再試行
- dry-run、設定検証、DB整合性確認、ローカルヘルスチェック

## 設計上の要点

- cronではなくsystemdのoneshot service / timerで実行
- SQLiteで実行履歴、残業スナップショット、通知試行を一元管理
- SQLiteはWAL、外部キー、busy timeoutを有効化
- 通知重複をDBの一意制約で防止
- Slack送信成功後だけ通知状態を`sent`へ更新
- 送信失敗は`failed`として保存し、次回実行で再試行可能
- dry-runはSlack送信も通知済み状態の消費も行わない
- KING OF TIME APIは社員単位ではなく「部署×対象月」単位で取得
- `.env`には秘密情報、TOMLには一般設定を保存
- health処理はローカル診断のみで、KING OF TIME APIとSlackを呼び出さない

## 通知仕様

### 残業目安時間の決定順

各社員の残業目安時間は、次の優先順位で決定します。

1. `data/employeeKey.csv`の個人別残業上限分
2. `config/production.toml`の部署別設定
3. `default_target_minutes`の既定値

個人別残業上限分が空欄で、所属部署も部署別設定に存在しない場合は、最終的に`default_target_minutes`が適用されます。

個人別残業上限分に`0`を明示した場合は未設定ではありません。「目安0分」として扱い、残業が発生した時点で100%超過相当になります。

設定例:

```toml
[overtime]
default_target_minutes = 600
force_self_threshold = 95

[overtime.division_targets]
"300" = 600
"156" = 1200
"158" = 1200
```

### ステータス表示

残業目安比率に応じて、Slackメッセージに次のステータスを表示します。

- 100%以上: `🚨 目安100%超過`
- 90%以上: `⚠️ 警告:90%超過`
- 80%以上: `⚠️ 注意:80%超過`
- 70%以上: `📙 注意: 70%超過`
- 60%以上: `📗 備考: 60%超過`
- 50%以上: `📘 備考: 50%超過`
- 50%未満: `✅ 問題なし`

50%の表示段階はレポート表示用です。通常の閾値通知は60%、70%、80%、90%、100%の到達段階を対象とします。

### 閾値通知

平日10:30に実行します。

- 土日はsystemd timerが起動しない
- 日本の祝日はアプリ側で処理をスキップ
- 60%、70%、80%、90%、100%の到達段階ごとに通知
- 同じ社員・同じ到達段階は週内で重複通知しない
- 新しい段階へ到達した場合は、その新しい段階として通知可能

管理者・勤怠担当者には、担当範囲内で通知対象となった社員のレポートを送信します。

本人通知を有効にした場合:

- `self_notify_employee_codes`の指定社員には60%到達から本人通知
- 指定外社員には`force_self_threshold`以上で本人通知
- 本人通知先は`data/employeeKey.csv`のメールアドレスから解決

### 週次通知

金曜21:30に実行します。金曜日が祝日でも実行します。

管理者・勤怠担当者向け:

- 担当範囲の全社員分を通知
- 残業比率が低い社員も週次レポートへ含める

社員本人向け:

- `self_notify_employee_codes`の指定社員には本人レポートを通知
- 指定外社員には`force_self_threshold`以上の場合だけ本人通知
- 指定外かつ強制本人通知閾値未満の社員には通知しない

### 通知先の範囲

`notifications.department_recipients`で通知先ごとの担当範囲を設定します。

- `ALL`: 全社員を対象とする通知先
- 部署コード: その部署に所属する社員だけを対象とする通知先
- 同じ通知先を複数の部署へ設定可能

設定例:

```toml
[notifications]
enable_self_notify = true
self_notify_employee_codes = [
  "00711",
  "01115",
]

[notifications.department_recipients]
ALL = [
  "admin@example.com",
]

"156" = [
  "division-manager@example.com",
  "attendance-admin@example.com",
]

"158" = [
  "division-manager@example.com",
]
```

`config/production.toml`の`notifications.department_recipients`は、既定の部署別通知先へ追加するのではなく、テーブル全体を置換します。

## KING OF TIME API利用時間

サーバー負荷を考慮し、次の時間帯（JST）はAPI利用禁止です。

- 毎日08:30〜10:00
- 毎日17:30〜18:30

定期実行は利用禁止時間帯を避けています。

- 閾値通知: 平日10:30
- 週次通知: 金曜21:30

手動実行やdry-runも、利用禁止時間帯を避けてください。dry-runでもKING OF TIME APIからデータを取得します。

## 設定ファイル

### `.env`

秘密情報だけを保存します。

主な項目:

- KING OF TIME APIのベースURL
- KING OF TIME APIトークン
- Slack Bot Token

`.env`はGit管理対象外です。

### `config/production.toml`

秘密ではない本番設定を保存します。

主な項目:

- 既定の残業目安時間
- 部署別の残業目安時間
- 強制本人通知閾値
- 本人通知の有効・無効
- 早期本人通知の対象社員コード
- 管理者・勤怠担当者の通知先

`config/production.toml`はGit管理対象外です。

### `data/employeeKey.csv`

社員とKING OF TIME、部署、Slack通知先を対応付けます。

主な情報:

- 社員コード
- 社員名
- 部署コード
- 本人メールアドレス
- 個人別残業上限分

実社員を含む`data/employeeKey.csv`はGit管理対象外です。

## 初期セットアップ

```bash
cd /home/pi/division-overtime
cp .env.example .env
cp config/production.toml.example config/production.toml
cp data/employeeKey.sample.csv data/employeeKey.csv
chmod 600 .env config/production.toml data/employeeKey.csv
vim .env
vim config/production.toml
vim data/employeeKey.csv
./scripts/install.sh
```

設定とDBを確認します。

```bash
.venv/bin/division-overtime --root . validate-config
.venv/bin/division-overtime --root . database init
.venv/bin/division-overtime --root . database status
```

通知内容を実送信せず確認します。

```bash
.venv/bin/division-overtime --root . run threshold --dry-run
.venv/bin/division-overtime --root . run weekly --dry-run
```

## 安全な本番切替

本番通知先を設定する前に、管理者1名だけへ限定して動作確認できます。

```toml
[notifications]
enable_self_notify = false
self_notify_employee_codes = []

[notifications.department_recipients]
ALL = [
  "admin@example.com",
]
```

確認手順:

1. `validate-config`を実行
2. `run threshold --dry-run`を実行
3. `run weekly --dry-run`を実行
4. 対象社員、通知先、残業目安時間を確認
5. 管理者・勤怠担当者の本番通知先を設定
6. 本人通知を有効化
7. 再度dry-runで最終確認

## CLI

### 設定検証

```bash
.venv/bin/division-overtime --root . validate-config
```

### DB初期化・状態確認

```bash
.venv/bin/division-overtime --root . database init
.venv/bin/division-overtime --root . database status
```

### 閾値通知

```bash
# dry-run
.venv/bin/division-overtime --root . run threshold --dry-run

# 実送信
.venv/bin/division-overtime --root . run threshold
```

### 週次通知

```bash
# dry-run
.venv/bin/division-overtime --root . run weekly --dry-run

# 実送信
.venv/bin/division-overtime --root . run weekly
```

### ローカルヘルスチェック

```bash
.venv/bin/division-overtime --root . health
```

ヘルスチェックはKING OF TIME APIとSlackを呼び出しません。

## systemd

serviceとtimerを配置して有効化します。

```bash
sudo cp systemd/*.service /etc/systemd/system/
sudo cp systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now \
  division-overtime-threshold.timer \
  division-overtime-weekly.timer \
  division-overtime-health.timer
```

確認:

```bash
systemctl list-timers --all | grep division-overtime
```

個別確認:

```bash
systemctl status division-overtime-threshold.timer --no-pager
systemctl status division-overtime-weekly.timer --no-pager
systemctl status division-overtime-health.timer --no-pager
```

ログ:

```bash
journalctl -u division-overtime-threshold.service -n 100 --no-pager
journalctl -u division-overtime-weekly.service -n 100 --no-pager
journalctl -u division-overtime-health.service -n 100 --no-pager
```

## 定期実行

- 平日10:30: 閾値通知
- 金曜21:30: 週次通知
- 起動10分後、その後1時間ごと: ローカルヘルスチェック

ヘルスチェックは正常時もSlackへ通知しません。結果は終了コードとjournalで確認します。

## 検証

WindowsまたはRaspberry Piで次を実行します。

```bash
ruff check .
ruff format --check .
pytest -q
```

Raspberry Piでは、プロジェクト全体の検証スクリプトも実行できます。

```bash
./scripts/verify.sh
```

検証内容:

- Ruff lint
- Ruff format
- pytest
- production設定の読み込み
- 社員CSVの存在確認
- SQLite integrity check
- ローカルヘルスチェック

## 更新手順

Windows側で変更、テスト、PR、マージを行い、Raspberry Piは実行環境として更新します。

Raspberry Pi側:

```bash
cd /home/pi/division-overtime
git switch main
git pull
./scripts/verify.sh
```

通知仕様や設定を変更した場合は、更新後に次も確認します。

```bash
.venv/bin/division-overtime --root . validate-config
.venv/bin/division-overtime --root . run threshold --dry-run
.venv/bin/division-overtime --root . run weekly --dry-run
```

## 終了コード

- `0`: 正常
- `1`: 実行失敗
- `2`: 設定不備
- `4`: Slack送信失敗

## セキュリティ

次のファイルはGitへ登録しません。

- `.env`
- `config/production.toml`
- `data/employeeKey.csv`
- SQLite DBとWAL関連ファイル
- 旧版の秘密情報を含む資産

秘密情報や実社員情報を、README、Issue、Pull Request、ログ共有へ貼り付けないでください。
