# Migration from the legacy cron version

## 方針

旧版cron運用から、systemd、SQLite、Web管理UIを利用する現行版へ移行します。OSのDesktop/Liteには依存しませんが、64-bit Raspberry Pi OSとsystemdを前提とします。

## 手順

1. Windows側mainが最新でcleanであることを確認する。
2. Raspberry Piへリポジトリを配置する。
3. `.env`、`config/production.toml`、`data/employeeKey.csv`を実機上で作成する。
4. `scripts/install.sh`を実行する。
5. 設定検証とSQLite初期化を行う。
6. CSVをSQLiteへ初期取込する。
7. SQLite/CSV整合性を確認する。
8. thresholdとweeklyを`--dry-run --source test`で確認する。
9. Web認証、社員一覧、KOT同期preview、通知履歴を確認する。
10. 旧cronを無効化する。
11. systemd service / timerを有効化する。
12. 初回自動実行をjournal、Web通知履歴、SQLiteで確認する。

## 初期取込

```bash
.venv/bin/division-overtime --root . database init
.venv/bin/division-overtime --root . employees import-csv
.venv/bin/division-overtime --root . employees import-csv --apply
.venv/bin/division-overtime --root . employees check-consistency
```

## スケジュール

- threshold: 月曜〜金曜10:30
- weekly: 金曜21:30
- health: 起動10分後、その後1時間ごと
- employee consistency: 毎日03:15

## KING OF TIME API制約

- 08:30〜10:00
- 17:30〜18:30

JSTの利用禁止時間帯を避けます。healthは外部APIへ接続しません。

## 完了条件

- 設定検証成功
- SQLite integrity checkが`ok`
- SQLite/CSV整合性が一致
- dry-runの対象、宛先、残業値が妥当
- Web認証と主要画面が動作
- timerが`active (waiting)`
- 旧cronとの競合がない
- 初回timer実行が`source=timer`として履歴へ保存される
