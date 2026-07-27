# Deployment

## 原則

- Windows側Gitリポジトリを正本とする
- mainへ直接commitしない
- Issue、作業ブランチ、PR、squash mergeで進める
- Raspberry Piは本番実行環境とする
- 自動デプロイは使用しない
- 本番反映はSSH後に`deploy.sh`を手動実行する

## 事前条件

Windows側:

```powershell
.\scripts\verify.ps1
git status
```

Raspberry Pi側:

- mainブランチ
- working treeがclean
- `.venv`作成済み
- `.env`、`config/production.toml`、`data/employeeKey.csv`設定済み
- npm、curl、sudo利用可能

## 正式デプロイ

```bash
cd /home/pi/division-overtime
./scripts/deploy.sh
```

`deploy.sh`は次を実行します。

1. 必須コマンドとworking treeのpreflight
2. `git pull --ff-only`
3. `VERSION`読込
4. Python依存更新
5. `npm ci`
6. frontend build
7. `scripts/verify.sh`
8. リポジトリ内の全systemd unitを`/etc/systemd/system/`へ反映
9. 反映後のunitがリポジトリ内定義と一致することを検証
10. threshold / weekly / health / employee consistency timerを有効化
11. Web再起動
12. `/api/system/health`再試行
13. 稼働versionと`VERSION`の一致確認

health待機中の一時的な接続失敗は表示せず、最終的に成功すれば異常ではありません。

## デプロイ後確認

```bash
curl -fsS http://127.0.0.1:8000/api/system/health
systemctl status division-overtime-web.service --no-pager
systemctl list-timers --all | grep division-overtime
systemctl cat division-overtime-threshold.service
systemctl cat division-overtime-weekly.service
```

期待する主要項目:

- `status=ok`
- `version`が`VERSION`と一致
- `frontendBuilt=true`
- Web serviceが`active (running)`
- threshold / weekly / health / employee-consistency timerが`active (waiting)`
- threshold / weekly serviceの`ExecStart`に`--source timer`が含まれる

## 通知処理との独立性

Webサービス停止中も通知timerとCLI healthは独立して動作します。通常のリリース確認では通知serviceを手動実行せず、直近のsystemd結果とjournalを確認します。

```bash
systemctl show division-overtime-threshold.service -p Result -p ExecMainStatus
systemctl show division-overtime-weekly.service -p Result -p ExecMainStatus
systemctl show division-overtime-health.service -p Result -p ExecMainStatus
```

## ロールバック

コードだけ戻す緊急確認では、直前の正常commitへdetachしてdeployできます。恒久対応はWindows側でrevert PRを作成します。

DBやCSVを戻す場合は、先に現状をバックアップし、[バックアップ・復旧](backup-restore.md)の手順を使用してください。
