# Changelog

## [1.0.0] - 2026-07-22

### Added

- PythonパッケージとCLI
- KING OF TIMEの部署・対象月単位取得
- 個人別、部署別、既定値の残業目安時間判定
- 60、70、80、90、100%の閾値通知
- 金曜21:30の週次通知
- SQLiteによる実行履歴、残業スナップショット、通知状態管理
- WAL、外部キー、busy timeout、トランザクション
- 通知重複防止と失敗時の再試行
- Slack送信成功後のみ`sent`へ確定
- dry-run、設定検証、DB整合性確認、ローカルhealth
- systemd oneshot service / timer
- 平日10:30のthreshold timer
- 金曜21:30のweekly timer
- 1時間ごとのhealth timer
- Ruffおよびpytest構成
- WindowsとRaspberry Piの両環境での検証手順
- 旧版を`legacy/pre-modernization`ブランチへ退避する移行方式

### Changed

- cron中心の旧構成からsystemd service / timerへ移行
- ファイルベースの通知フラグをSQLiteへ統合
- production側の部署別通知先を既定値へ追加せず、テーブル全体で置換
- KING OF TIME API利用禁止時間帯を避ける運用を明文化

### Security

- `.env`、`config/production.toml`、実社員CSV、SQLite DB、旧資産をGit管理対象外とした
- systemd serviceへ`NoNewPrivileges`、`ProtectSystem`、`ProtectHome`、書込先制限を設定
- healthは外部APIとSlackを呼び出さず、正常通知によるノイズを発生させない
