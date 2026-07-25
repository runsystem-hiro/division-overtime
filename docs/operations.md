# Operations

## 運用原則

- 通知serviceを止めない
- 本番データ変更前にpreview、対象、件数を確認する
- KING OF TIME API利用禁止時間帯を避ける
- Web管理UIと通知処理は別プロセスとして扱う
- SQLiteと`employeeKey.csv`の整合性を維持する
- 本番確認でtoken、KOT Key、実社員情報をログやGitへ残さない

## KING OF TIME API利用禁止時間帯

JST:

- 08:30〜10:00
- 17:30〜18:30

thresholdは平日10:30、weeklyは金曜21:30に設定されています。手動実行とdry-runでも禁止時間帯を避けます。

## 日常確認

```bash
cd /home/pi/division-overtime

curl -fsS http://127.0.0.1:8000/api/system/health
.venv/bin/division-overtime --root . health
.venv/bin/division-overtime --root . database status
.venv/bin/division-overtime --root . employees check-consistency
systemctl list-timers --all | grep division-overtime
```

## systemd

### スケジュール

- threshold: 月曜〜金曜 10:30
- weekly: 金曜 21:30
- health: 起動10分後、その後1時間ごと
- employee consistency: 毎日 03:15

### 状態確認

```bash
systemctl status division-overtime-web.service --no-pager
systemctl status division-overtime-threshold.timer --no-pager
systemctl status division-overtime-weekly.timer --no-pager
systemctl status division-overtime-health.timer --no-pager
systemctl status division-overtime-employee-consistency.timer --no-pager
```

### ログ

```bash
journalctl -u division-overtime-threshold.service -n 100 --no-pager
journalctl -u division-overtime-weekly.service -n 100 --no-pager
journalctl -u division-overtime-health.service -n 100 --no-pager
journalctl -u division-overtime-web.service -n 100 --no-pager
```

## 手動実行

通知を伴うため、対象・時刻・重複キーへの影響を確認してから実行します。

```bash
.venv/bin/division-overtime --root . run threshold --dry-run --source test
.venv/bin/division-overtime --root . run weekly --dry-run --source test
```

本番送信を手動で行う場合は`--source manual`を使用します。検証履歴を明示したい場合は`--source test`を使用します。

## 重複通知

- threshold: ISO年・ISO週・社員・到達閾値・受信者
- weekly: ISO年・ISO週・社員・受信者
- 本人通知は部署通知と別の識別子

同じ識別条件は`skipped`として履歴に保存され、Web詳細画面から重複元runを確認できます。週が変わると新しい識別キーになります。

## 社員管理

当面の通知経路:

```text
SQLite -> employeeKey.csv -> notification service
```

- 一時停止、復帰予定あり: 無効化
- 退職、異動、恒久対象外: 削除
- KOT在籍中だが通知対象外: KOT同期のcreate候補を選択しない

Web保存はSQLiteとCSVを一体更新し、失敗時は元へ戻します。KOT Keyの既存値は画面やAPIへ返しません。

## KOT社員同期

1. API利用禁止時間帯外で「KOTから取得」を実行
2. create / update / reactivate / disable / unchangedを確認
3. 反映対象だけを選択
4. 適用
5. 件数、履歴、バックアップ先、SQLite/CSV整合性を確認

previewだけではSQLiteとCSVを変更しません。KOT退職済みかつSQLite未登録の社員は候補から除外されます。

## 通知履歴

Web管理UIで次を確認できます。

- 実行時刻、mode、source、dry-run、status
- 対象数、attempt数、sent / failed / skipped
- 受信者、通知種別、Slack timestamp、error
- dedupe key
- 重複元attempt / run / 実行時刻 / source

## 障害時の確認順

1. `/api/system/health`
2. Web service状態
3. timer状態
4. 直近service result / exit code
5. journal
6. `database status`
7. SQLite/CSV整合性
8. `.env`とTOML
9. 外部API利用時間帯と接続状況

復旧でDBやCSVを変更する場合は[バックアップ・復旧](backup-restore.md)を参照してください。
