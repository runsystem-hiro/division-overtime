# division-overtime

KING OF TIMEの月次残業データを部署単位で取得し、閾値通知と週次通知をSlack DMへ送るRaspberry Pi向け業務アプリです。

## 実行環境

- Raspberry Pi 4B
- Raspberry Pi OS Trixie 64-bit Desktop
- Python 3.13（対応範囲: `>=3.11,<3.14`）
- systemd service / timer
- SQLite 3（WALモード）

本アプリはGUIやデスクトップセッションに依存しません。

## 設計上の要点

- cronではなくsystemdのoneshot service / timerで実行
- SQLiteで実行履歴、残業スナップショット、通知試行を一元管理
- 通知重複をDBの一意制約で防止
- Slack送信成功後だけ通知状態を`sent`へ更新
- 送信失敗は`failed`として保存し、次回実行で再試行可能
- dry-runはSlack送信も通知済み状態の消費も行わない
- KING OF TIME APIは社員単位ではなく「部署×対象月」単位で取得
- `.env`には秘密情報、TOMLには一般設定を保存
- health処理はローカル診断のみで、KING OF TIME APIとSlackを呼び出さない

## KING OF TIME API利用時間

サーバー負荷を考慮し、次の時間帯（JST）はAPI利用禁止です。

- 毎日 08:30〜10:00
- 毎日 17:30〜18:30

定期実行は利用禁止時間帯を避けています。

- 閾値通知: 平日10:30
- 週次通知: 金曜21:30

手動実行やdry-runも、利用禁止時間帯を避けてください。

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

確認:

```bash
.venv/bin/division-overtime --root . validate-config
.venv/bin/division-overtime --root . database init
.venv/bin/division-overtime --root . database status
.venv/bin/division-overtime --root . run threshold --dry-run
.venv/bin/division-overtime --root . run weekly --dry-run
```

## 安全なテスト通知先

本番切替前に通知先を1名へ限定する場合:

```toml
[notifications]
enable_self_notify = false
self_notify_employee_codes = []

[notifications.department_recipients]
ALL = ["h-tanaka@runsystem.co.jp"]
```

`production.toml`の`notifications.department_recipients`は、既定の部署別通知先を完全置換します。

## systemd

配置と有効化:

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

ログ:

```bash
journalctl -u division-overtime-threshold.service -n 100 --no-pager
journalctl -u division-overtime-weekly.service -n 100 --no-pager
journalctl -u division-overtime-health.service -n 100 --no-pager
```

## 定期実行

- 平日10:30: 閾値通知
- 金曜21:30: 残業比率に関係なく週次通知
- 起動10分後、その後1時間ごと: ローカルヘルスチェック

ヘルスチェックは正常時もSlackへ通知しません。結果は終了コードとjournalで確認します。

## 終了コード

- `0`: 正常
- `1`: 実行失敗
- `2`: 設定不備
- `4`: Slack送信失敗
