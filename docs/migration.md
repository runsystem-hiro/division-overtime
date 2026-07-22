# Migration from the legacy cron version

## 移行方針

旧版は参照用として`legacy/pre-modernization`ブランチおよびローカルバックアップへ退避し、新設計版を`main`として運用する。

## 移行手順

1. Raspberry Pi OS Trixie 64-bit Desktopをクリーンインストールする。
2. 旧ログ、キャッシュ、通知フラグ、SlackユーザーIDキャッシュを新Gitリポジトリへ含めない。
3. `.env`、`config/production.toml`、`data/employeeKey.csv`を実機上で作成する。
4. 設定検証とSQLite初期化を実行する。
5. thresholdとweeklyを`--dry-run`で実行し、残業値・通知候補・宛先を確認する。
6. 通知先を一時的に管理者1名へ限定してweeklyを実送信する。
7. SQLiteの`sent`記録とSlack受信を確認する。
8. 同一コマンドを再実行し、重複送信がスキップされることを確認する。
9. systemd serviceを手動実行し、終了コードとjournalを確認する。
10. 旧cronが存在しないことを確認する。
11. systemd timerを有効化する。
12. 初回自動実行をjournalとSQLiteで確認する。

## 旧スケジュール

- 毎日10:30: 旧スクリプトを起動し、内部で曜日・祝日・閾値を判定
- 金曜21:30: 旧スクリプトを起動し、内部で強制通知モードを判定

## 新スケジュール

- 月曜〜金曜10:30: 明示的な`threshold`モード
- 金曜21:30: 明示的な`weekly`モード
- 起動10分後、その後1時間ごと: ローカルhealth

## KING OF TIME API制約

API利用禁止時間帯（JST）:

- 08:30〜10:00
- 17:30〜18:30

新スケジュールはこの時間帯を避けている。
healthではAPIへアクセスしない。

## 移行完了条件

- WindowsとPiの両方でRuff成功
- WindowsとPiの両方でpytest成功
- SQLite整合性`ok`
- SQLite journal mode `wal`
- dry-runで想定通知先だけが表示される
- Slack実送信成功
- 同一週の重複送信防止成功
- systemd service手動実行成功
- 3つのtimerが`active (waiting)`
- cron競合なし
