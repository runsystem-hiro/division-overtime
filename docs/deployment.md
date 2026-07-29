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
- Python仮想環境作成済み
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
4. Python依存更新
5. frontend依存インストールとbuild
6. ローカル検証
7. リポジトリ内の全systemd unitを反映
8. 反映後のunitがリポジトリ内定義と一致することを検証
9. 定期実行timerの有効化
10. Web再起動
11. `/api/system/health`再試行
12. 稼働versionと`VERSION`の一致確認

health待機中の一時的な接続失敗は、最終的に成功すれば異常ではありません。

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
