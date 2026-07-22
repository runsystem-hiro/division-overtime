# division-overtime

King of Timeの月次残業データを部署単位で取得し、閾値通知と週次通知をSlack DMへ送るRaspberry Pi向け業務アプリです。

## 設計上の要点

- GUI非依存のCLIアプリ
- cronではなくsystemd oneshot service / timer
- SQLite（WAL・外部キー・busy timeout）で実行履歴、スナップショット、通知試行を一元管理
- 通知重複をDBの一意制約で防止
- Slack送信成功後のみ`sent`へ更新
- King of Time APIは社員単位ではなく「部署×月」単位で取得
- `.env`は秘密情報のみ、一般設定はTOML

## 初期セットアップ

```bash
cd /home/pi/division-overtime
cp .env.example .env
cp config/production.toml.example config/production.toml
cp data/employeeKey.sample.csv data/employeeKey.csv
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
```

## systemd

```bash
sudo systemctl enable --now division-overtime-threshold.timer
sudo systemctl enable --now division-overtime-weekly.timer
sudo systemctl enable --now division-overtime-health.timer
systemctl list-timers 'division-overtime-*'
```

ログ:

```bash
journalctl -u division-overtime-threshold.service -n 100 --no-pager
journalctl -u division-overtime-weekly.service -n 100 --no-pager
```

## 定期実行

- 平日10:30: 閾値通知
- 金曜21:30: 残業比率に関係なく週次通知

## 終了コード

- `0`: 正常
- `1`: 実行失敗
- `2`: 設定不備
- `4`: Slack送信失敗
