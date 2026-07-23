# Changelog

## [Unreleased]

### Added

- 認証済み社員一覧・詳細・追加・更新API
- 社員一覧、検索、状態絞り込み、追加・編集画面
- 社員保存時のSQLite更新と`employeeKey.csv`原子的再生成
- CSV生成失敗時のSQLiteロールバックと既存CSV保持
- KOT Keyの書込専用入力（APIレスポンス・一覧・編集値には非表示）
- 社員管理サービス、API、Repositoryのテスト

- Web管理UI向けの社員SQLite管理テーブル
- `employeeKey.csv`から社員情報を初期取込するRepository
- 社員の有効状態、無効理由、備考、KOT存在状態を保持する管理項目
- 社員SQLite管理基盤のテスト

- 管理者1名向けのユーザー名・パスワード認証
- Argon2によるパスワードハッシュ検証
- HttpOnly・SameSite=StrictのCookieセッション
- ログイン、ログアウト、認証状態取得API
- セッション期限とログイン試行制限
- 管理者ログイン画面
- パスワードハッシュ生成コマンド
- 認証・Cookie・期限・試行制限のテスト

### Security

- 認証失敗時の応答を統一し、ユーザー名の存在を判別できないようにした
- セッションIDは平文保存せず、秘密鍵によるHMACダイジェストで保持
- Web認証情報を`.env`からのみ読み込む

### Changed

- SQLiteスキーマバージョンを2へ更新

### Added

- FastAPIによるWeb管理UI基盤
- Web専用設定ローダー（KOT・Slackトークン不要）
- `/api/system/health`および`/api/version`
- React / Vite / TypeScriptの最小フロントエンド
- FastAPIからのビルド済みSPA配信
- `division-overtime-web.service`
- Web設定・API・静的配信のテスト5件

### Changed

- Web用Python依存関係を`web`オプションとして追加
- インストールスクリプトでWeb依存関係を導入
- READMEへWeb開発・ビルド・systemd手順を追加

## [1.0.2] - 2026-07-22

### Fixed

- 金曜weeklyの本人通知が全社員へ送られる旧版移行不全を修正
- weekly本人通知を、指定社員または強制本人通知閾値以上の社員に限定
- 指定外かつ強制本人通知閾値未満の社員本人には通知しない
- 管理者向けweekly通知は、担当範囲の全社員分を維持

### Changed

- 本人通知の目的を旧版運用に合わせて整理
  - 指定社員は60%到達から段階通知
  - 指定外社員は95%以上で本人通知
  - weeklyでも同じ本人通知条件を適用
- READMEへ管理者通知、本人通知、祝日、残業目安時間のフォールバック仕様を追記

### Tests

- 指定社員のweekly本人通知
- 指定外かつ95%未満の本人通知抑止
- 指定外かつ95%以上の本人通知
- 管理者向けweekly通知の継続
- WindowsおよびRaspberry Piで49件のテスト成功

## [1.0.1] - 2026-07-22

### Changed

- Slack通知文面を旧版互換のスタイルへ復元
- 50%、60%、70%、80%、90%、100%のステータス段階を復元
- 年月、前月比、目安まで、目安超過の表示を旧版へ統一
- 目安0分設定時の特別表示を復元
- 通知文生成を`message_formatter.py`へ分離

### Tests

- ステータス境界値
- 目安0分
- 目安未達・超過
- 本人通知
- 複数人通知

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

## Unreleased

### Added

- KING OF TIME従業員一覧を手動取得し、SQLite社員マスタとの差分をプレビューするAPIとWeb UIを追加。
- 新規・更新・無効化候補を選択して反映し、`employeeKey.csv`を安全に再生成する処理を追加。
- KOT同期履歴テーブルを追加し、成功時の反映件数を記録。

### Security

- KOT Keyは同期プレビュー、APIレスポンス、画面に含めず、サーバー内部の短時間プレビューだけで保持。
