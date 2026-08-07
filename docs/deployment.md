# Deployment

## 原則

- Windows側Gitリポジトリを正本とする
- mainへ直接commitしない
- Issue、作業ブランチ、PR、squash mergeで進める
- Linuxの本番実行環境へ手動で反映する
- 自動デプロイは使用しない
- 本番固有のホスト名、接続先、インストールパス、ポート、systemd unit名はリポジトリ外の運用手順で管理する

## 事前条件

Windows側:

```powershell
.\scripts\verify.ps1
git status
```

本番側:

- mainブランチ
- working treeがclean
- uvがインストール済みで`uv --version`が成功する
- Python仮想環境（`.venv`）作成済み
- `.env`、環境別TOML、社員CSV設定済み
- frontend buildに必要なNode.js / npmが利用可能
- `curl`とsystemd管理権限が利用可能

## 正式デプロイ

```bash
cd <app-root>
./scripts/deploy.sh
```

`deploy.sh`は概ね次を実行します。

1. 必須コマンドとworking treeのpreflight
2. `git pull --ff-only`
3. `VERSION`読込
4. `uv sync --frozen --extra web --extra dev`で`uv.lock`からPython依存を同期
5. frontend依存インストールとbuild
6. 本番DBの存在と既存スキーマを確認
7. SQLite Backup APIでマイグレーション前バックアップを作成・検証
8. 既存DBを最新スキーマへマイグレーション
9. 更新後schema versionとintegrityを確認
10. ローカル検証
11. リポジトリ内の全systemd unitを反映
12. 反映後のunitがリポジトリ内定義と一致することを検証
13. 定期実行timerの有効化
14. Web再起動
15. `/api/system/health`再試行
16. 稼働versionと`VERSION`の一致確認

### Raspberry Piへのuv導入

本番Raspberry Piでは、正式deployの前に`pi`ユーザーでuvを導入します。公式スタンドアロンインストーラーを使用する場合は、内容を確認してから実行します。

```bash
curl -LsSf https://astral.sh/uv/install.sh | less
curl -LsSf https://astral.sh/uv/install.sh | sh
exec "$SHELL" -l
uv --version
```

`deploy.sh`はuv自体を自動インストールしません。`uv sync --frozen --extra web --extra dev`を使用し、`pyproject.toml`と`uv.lock`からプロジェクト直下の`.venv`を同期します。`--frozen`を付けるため、本番deployで`uv.lock`は更新しません。systemdの実行パスは従来どおり`.venv/bin/...`を維持します。

health待機中の一時的な接続失敗は、最終的に成功すれば異常ではありません。待機ループ内の`curl` stderrだけを抑制し、全試行失敗時は最後のhealth確認、systemd status、journalを表示して原因調査に必要な情報を残します。再試行回数・間隔・成功条件は変更しません。

## DBマイグレーションの安全性

`deploy.sh`は`verify.sh`より前に次を実行します。

```bash
.venv/bin/python -m division_overtime.cli --root . database migrate
```

`database migrate`は既存DB専用です。DBファイル、`schema_meta`、`employees`テーブル、schema versionを読み取り専用で確認し、DBが存在しない場合や既存DBとして認識できない場合は空DBを作らず停止します。

マイグレーション前にはSQLite Backup APIで次へバックアップします。

```text
var/backups/deploy-database/<timestamp>/division_overtime.sqlite3
```

バックアップのintegrity確認に失敗した場合はマイグレーションを開始しません。成功時はdeployログにバックアップ先、`schema_version_before`、`schema_version_after`、`integrity_check=ok`を出力します。マイグレーションまたは検証に失敗した場合、systemd unit反映とWeb再起動へ進みません。最新schemaへの再実行も安全です。

マイグレーションと更新後integrity確認の成功後、`deploy-database`の正常なバックアップ世代を最新30世代へ整理します。想定外ディレクトリ、symlink、不完全な世代は削除しません。古い世代の削除に失敗した場合は警告に留め、deploy本体は継続します。

## デプロイ後確認

環境固有値はリポジトリ外の運用手順から設定します。

```bash
APP_ROOT=<app-root>
HEALTH_URL=<health-url>
WEB_SERVICE=<web-service>
TIMER_PATTERN=<timer-name-pattern>

cd "$APP_ROOT"
curl -fsS "$HEALTH_URL/api/system/health"
systemctl status "$WEB_SERVICE" --no-pager
systemctl list-timers --all | grep "$TIMER_PATTERN"
```

期待する主要項目:

- `status=ok`
- `version`が`VERSION`と一致
- `frontendBuilt=true`
- Web serviceが稼働中
- 必要なtimerが待機中

## systemd定義の確認

unit名そのものは公開情報として扱い、接続先・配置先・実行時刻・通知先などの環境固有値だけをリポジトリ外で管理します。正式デプロイ後は、少なくとも通知serviceの定義がリポジトリ内定義と一致し、timer起動では`--source timer`が付与されていることを確認します。

```bash
systemctl cat division-overtime-threshold.service
systemctl cat division-overtime-weekly.service
```

確認点:

- 全systemd unitが反映対象になっている
- 反映後のunitがリポジトリ内定義と一致する
- threshold / weekly serviceの`ExecStart`に`--source timer`が含まれる

## 通知処理との独立性

Webサービス停止中も通知timerとCLI healthは独立して動作します。通常のリリース確認では通知serviceを手動実行せず、直近のsystemd結果とjournalを確認します。

具体的なservice名、timer名、journal確認コマンド、通知時刻は本番運用手順で管理してください。

## ロールバック

コードだけ戻す緊急確認では、直前の正常commitへdetachしてdeployできます。恒久対応はWindows側でrevert PRを作成します。

DBやCSVを戻す場合は、先に現状をバックアップし、[バックアップ・復旧](backup-restore.md)の手順を使用してください。

### uv移行時のロールバック

uv同期後に問題が発生した場合は、まずWindows側で原因修正またはrevert PRを作成し、正常commitへ戻すことを原則とします。緊急時にpip運用へ戻す必要がある場合は、本番データに触れず`.venv`だけを再作成します。

```bash
cd <app-root>
rm -rf .venv
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[web,dev]'
./scripts/verify.sh
```

この操作はPython仮想環境を再作成します。SQLite DB、`employeeKey.csv`、`.env`、backupは削除しません。実施前に対象が`<app-root>/.venv`であることを必ず確認してください。
