# division-overtime

KING OF TIMEの月次残業データを部署単位で取得し、残業目安時間に対する到達状況をSlack DMへ通知するRaspberry Pi向け業務アプリです。

管理者・勤怠担当者向けの部署レポートと、条件に応じた社員本人向け通知を扱います。定期実行、実行履歴、通知重複防止、再試行、ローカルヘルスチェックはsystemdとSQLiteで管理します。

## 実行環境

- Raspberry Pi 4B
- Raspberry Pi OS Trixie 64-bit Desktop
- Python 3.13（対応範囲: `>=3.11,<3.14`）
- systemd service / timer
- SQLite 3（WALモード）

本アプリはGUIやデスクトップセッションに依存しません。

## 主な機能

- KING OF TIMEから部署・対象月単位で月次残業データを取得
- 個人別、部署別、既定値の優先順位で残業目安時間を決定
- 平日10:30の閾値通知
- 金曜21:30の週次通知
- 管理者・勤怠担当者には担当範囲のレポートを送信
- 指定社員には早期段階から本人通知
- 指定外社員には強制本人通知閾値以上で本人通知
- Slack通知文面を旧版互換の形式で生成
- SQLiteによる実行履歴、残業スナップショット、通知状態管理
- 通知重複防止と送信失敗時の再試行
- dry-run、設定検証、DB整合性確認、ローカルヘルスチェック

## 設計上の要点

- cronではなくsystemdのoneshot service / timerで実行
- SQLiteで実行履歴、残業スナップショット、通知試行を一元管理
- Web管理UI向けの社員情報をSQLiteで管理し、既存通知処理は引き続き`data/employeeKey.csv`を参照
- SQLiteはWAL、外部キー、busy timeoutを有効化
- 通知重複をDBの一意制約で防止
- Slack送信成功後だけ通知状態を`sent`へ更新
- 送信失敗は`failed`として保存し、次回実行で再試行可能
- dry-runはSlack送信も通知済み状態の消費も行わない
- KING OF TIME APIは社員単位ではなく「部署×対象月」単位で取得
- `.env`には秘密情報、TOMLには一般設定を保存
- health処理はローカル診断のみで、KING OF TIME APIとSlackを呼び出さない

## 通知仕様

### 残業目安時間の決定順

各社員の残業目安時間は、次の優先順位で決定します。

1. `data/employeeKey.csv`の個人別残業上限分
2. `config/production.toml`の部署別設定
3. `default_target_minutes`の既定値

個人別残業上限分が空欄で、所属部署も部署別設定に存在しない場合は、最終的に`default_target_minutes`が適用されます。

個人別残業上限分に`0`を明示した場合は未設定ではありません。「目安0分」として扱い、残業が発生した時点で100%超過相当になります。

設定例:

```toml
[overtime]
default_target_minutes = 600
force_self_threshold = 95

[overtime.division_targets]
"300" = 600
"156" = 1200
"158" = 1200
```

### ステータス表示

残業目安比率に応じて、Slackメッセージに次のステータスを表示します。

- 100%以上: `🚨 目安100%超過`
- 90%以上: `⚠️ 警告:90%超過`
- 80%以上: `⚠️ 注意:80%超過`
- 70%以上: `📙 注意: 70%超過`
- 60%以上: `📗 備考: 60%超過`
- 50%以上: `📘 備考: 50%超過`
- 50%未満: `✅ 問題なし`

50%の表示段階はレポート表示用です。通常の閾値通知は60%、70%、80%、90%、100%の到達段階を対象とします。

### 閾値通知

平日10:30に実行します。

- 土日はsystemd timerが起動しない
- 日本の祝日はアプリ側で処理をスキップ
- 60%、70%、80%、90%、100%の到達段階ごとに通知
- 同じ社員・同じ到達段階は週内で重複通知しない
- 新しい段階へ到達した場合は、その新しい段階として通知可能

管理者・勤怠担当者には、担当範囲内で通知対象となった社員のレポートを送信します。

本人通知を有効にした場合:

- `self_notify_employee_codes`の指定社員には60%到達から本人通知
- 指定外社員には`force_self_threshold`以上で本人通知
- 本人通知先は`data/employeeKey.csv`のメールアドレスから解決

### 週次通知

金曜21:30に実行します。金曜日が祝日でも実行します。

管理者・勤怠担当者向け:

- 担当範囲の全社員分を通知
- 残業比率が低い社員も週次レポートへ含める

社員本人向け:

- `self_notify_employee_codes`の指定社員には本人レポートを通知
- 指定外社員には`force_self_threshold`以上の場合だけ本人通知
- 指定外かつ強制本人通知閾値未満の社員には通知しない

### 通知先の範囲

`notifications.department_recipients`で通知先ごとの担当範囲を設定します。

- `ALL`: 全社員を対象とする通知先
- 部署コード: その部署に所属する社員だけを対象とする通知先
- 同じ通知先を複数の部署へ設定可能

設定例:

```toml
[notifications]
enable_self_notify = true
self_notify_employee_codes = [
  "00711",
  "01115",
]

[notifications.department_recipients]
ALL = [
  "admin@example.com",
]

"156" = [
  "division-manager@example.com",
  "attendance-admin@example.com",
]

"158" = [
  "division-manager@example.com",
]
```

`config/production.toml`の`notifications.department_recipients`は、既定の部署別通知先へ追加するのではなく、テーブル全体を置換します。

## KING OF TIME API利用時間

サーバー負荷を考慮し、次の時間帯（JST）はAPI利用禁止です。

- 毎日08:30〜10:00
- 毎日17:30〜18:30

定期実行は利用禁止時間帯を避けています。

- 閾値通知: 平日10:30
- 週次通知: 金曜21:30

手動実行やdry-runも、利用禁止時間帯を避けてください。dry-runでもKING OF TIME APIからデータを取得します。

## 設定ファイル

### `.env`

秘密情報だけを保存します。

主な項目:

- KING OF TIME APIのベースURL
- KING OF TIME APIトークン
- Slack Bot Token

`.env`はGit管理対象外です。

### `config/production.toml`

秘密ではない本番設定を保存します。

主な項目:

- 既定の残業目安時間
- 部署別の残業目安時間
- 強制本人通知閾値
- 本人通知の有効・無効
- 早期本人通知の対象社員コード
- 管理者・勤怠担当者の通知先

`config/production.toml`はGit管理対象外です。

### `data/employeeKey.csv`

社員とKING OF TIME、部署、Slack通知先を対応付けます。

主な情報:

- 社員コード
- 社員名
- 部署コード
- 本人メールアドレス
- 個人別残業上限分

実社員を含む`data/employeeKey.csv`はGit管理対象外です。

### 社員SQLite管理基盤

Web管理UI向けに、社員情報を保存する`employees`テーブルを追加しています。
`data/employeeKey.csv`から初期取込できますが、現在のthreshold、weekly、health処理は引き続きCSVを参照します。

- CSV再取込時も、有効状態、無効理由、備考などの管理項目は保持
- KOT Keyは書込専用とし、Web APIレスポンス、一覧、編集時の既存値へ表示しない
- Web保存時はSQLiteと`employeeKey.csv`を一体更新し、失敗時は両方を元の状態へ戻す
- KOT社員同期の適用履歴には、反映前バックアップの保存先を記録し、管理画面の最終実行欄で確認可能
- 通知処理のSQLite直接参照は後続PRで実装

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

設定とDBを確認します。

```bash
.venv/bin/division-overtime --root . validate-config
.venv/bin/division-overtime --root . database init
.venv/bin/division-overtime --root . database status
```

通知内容を実送信せず確認します。

```bash
.venv/bin/division-overtime --root . run threshold --dry-run
.venv/bin/division-overtime --root . run weekly --dry-run
```

## 安全な本番切替

本番通知先を設定する前に、管理者1名だけへ限定して動作確認できます。

```toml
[notifications]
enable_self_notify = false
self_notify_employee_codes = []

[notifications.department_recipients]
ALL = [
  "admin@example.com",
]
```

確認手順:

1. `validate-config`を実行
2. `run threshold --dry-run`を実行
3. `run weekly --dry-run`を実行
4. 対象社員、通知先、残業目安時間を確認
5. 管理者・勤怠担当者の本番通知先を設定
6. 本人通知を有効化
7. 再度dry-runで最終確認

## CLI

### 設定検証

```bash
.venv/bin/division-overtime --root . validate-config
```

### DB初期化・状態確認

```bash
.venv/bin/division-overtime --root . database init
.venv/bin/division-overtime --root . database status
```

### 閾値通知

```bash
# dry-run
.venv/bin/division-overtime --root . run threshold --dry-run

# 実送信
.venv/bin/division-overtime --root . run threshold
```

### 週次通知

```bash
# dry-run
.venv/bin/division-overtime --root . run weekly --dry-run

# 実送信
.venv/bin/division-overtime --root . run weekly
```

### ローカルヘルスチェック

```bash
.venv/bin/division-overtime --root . health
```

ヘルスチェックはKING OF TIME APIとSlackを呼び出しません。

## systemd

serviceとtimerを配置して有効化します。

```bash
sudo cp systemd/*.service /etc/systemd/system/
sudo cp systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now \
  division-overtime-threshold.timer \
  division-overtime-weekly.timer \
  division-overtime-health.timer \
  division-overtime-employee-consistency.timer
```

確認:

```bash
systemctl list-timers --all | grep division-overtime
```

個別確認:

```bash
systemctl status division-overtime-threshold.timer --no-pager
systemctl status division-overtime-weekly.timer --no-pager
systemctl status division-overtime-health.timer --no-pager
systemctl status division-overtime-employee-consistency.timer --no-pager
```

ログ:

```bash
journalctl -u division-overtime-threshold.service -n 100 --no-pager
journalctl -u division-overtime-weekly.service -n 100 --no-pager
journalctl -u division-overtime-health.service -n 100 --no-pager
journalctl -u division-overtime-employee-consistency.service -n 100 --no-pager
```

## 定期実行

- 平日10:30: 閾値通知
- 金曜21:30: 週次通知
- 起動10分後、その後1時間ごと: ローカルヘルスチェック

ヘルスチェックは正常時もSlackへ通知しません。結果は終了コードとjournalで確認します。

## 検証

WindowsまたはRaspberry Piで次を実行します。

```bash
ruff check .
ruff format --check .
pytest -q
```

Raspberry Piでは、プロジェクト全体の検証スクリプトも実行できます。

```bash
./scripts/verify.sh
```

検証内容:

- Ruff lint
- Ruff format
- pytest
- production設定の読み込み
- 社員CSVの存在確認
- SQLite integrity check
- ローカルヘルスチェック

### GitHub Actions CI

Pull Request作成時に、`.github/workflows/ci.yml`で次を自動実行します。必要な場合はGitHub Actions画面から手動実行もできます。

- バージョン整合性確認
- Ruff lint・format確認
- pytest
- frontendの`npm ci`と`npm run build`

CIは検証専用です。Raspberry Piへのデプロイ、KOT APIへの接続、Slack通知、タグ作成、GitHub Release作成は行いません。同じPull Requestへ追加pushした場合は古い実行を自動キャンセルし、mainへのmerge後は重複実行しません。ローカルでの事前検証を主とし、CIはクリーン環境での補助確認として使用します。

### GitHub Flowとmain保護

`main`はGitHub Rulesetで保護し、軽微な文書修正を含むすべての変更を原則として作業ブランチとPull Request経由で反映します。

- Issueを作成してから`feat/*`、`fix/*`、`docs/*`、`refactor/*`、`ci/*`等の作業ブランチを作成する
- ローカル検証後にpushし、Pull Request本文へ`Closes #Issue番号`を記載する
- CI結果を確認し、ローカル検証済みであればCI完了を必須条件とせずsquash mergeできる
- `main`へのforce pushとブランチ削除は禁止する
- merge commitとrebase mergeは使用せず、squash mergeのみ使用する

ローカル検証を主たる品質確認とし、CIはクリーンなGitHub Actions環境で同じ主要検証を再確認する補助手段として使用します。CIは必須ステータスチェックには設定せず、待ち時間より開発体験を優先します。失敗しているCIを把握したまま本番反映しない運用は維持します。

## バージョン管理とリリース

公開バージョンはルートの`VERSION`を基準とし、Pythonパッケージ、モジュール、フロントエンドの各定義を同じ値へそろえます。

```bash
.venv/bin/python scripts/check_version.py --root .
```

`./scripts/verify.sh`と`./scripts/deploy.sh`もバージョン整合性を確認します。デプロイ後は`/api/system/health`の稼働バージョンが`VERSION`と一致しなければ失敗します。

v2.0.3のWindows検証、Raspberry Pi実機確認、Web停止時の通知独立性確認、ロールバック、タグ・GitHub Release作成は[リリースチェックリスト](docs/release-checklist.md)を使用します。

## 更新手順

Windows側で変更、テスト、PR、マージを行い、Raspberry Piは実行環境として更新します。

Raspberry Pi側:

```bash
cd /home/pi/division-overtime
git switch main
git pull
./scripts/verify.sh
```

通知仕様や設定を変更した場合は、更新後に次も確認します。

```bash
.venv/bin/division-overtime --root . validate-config
.venv/bin/division-overtime --root . run threshold --dry-run
.venv/bin/division-overtime --root . run weekly --dry-run
```

## 社員管理画面の整合性表示

社員管理画面では、SQLiteの有効社員と`data/employeeKey.csv`の整合性を読み取り専用で確認し、「一致」「不一致」「確認失敗」を表示します。不一致時に表示するのは社員コードと差分項目名だけで、KOT Keyの値はAPI・画面のどちらにも表示しません。

## KOT社員同期のWeb実行

社員管理画面からKOT社員差分を取得・確認し、選択した差分をSQLiteと`employeeKey.csv`へ反映できます。同期処理は二重起動を拒否し、API利用禁止時間帯（08:30〜10:00、17:30〜18:30）は開始できません。同期前にはSQLiteとCSVのバックアップを作成し、CSVは原子的に再生成します。画面には最終実行日時と新規・更新・無効化件数を表示します。反映成功時は、作成した反映前バックアップディレクトリも成功メッセージへ表示します。KOT KeyやAPIトークンは表示しません。

## 通知処理の社員データ参照

threshold・weeklyの通知処理は、`CsvEmployeeSource`を通じて引き続き`data/employeeKey.csv`を参照します。health処理は社員データを読み込みません。今回の分離は将来の段階的移行に備えた内部構造の整理であり、通知対象・通知条件・送信内容・実行時刻は変更しません。

`SqliteEmployeeSource`も実装済みで、SQLiteの有効社員を社員コード順に通知用`Employee`へ変換できます。threshold・weekly実行時にはSQLiteをshadow readし、CSVとの一致件数または社員コード単位の差分種別をログへ記録します。通知対象・本文・送信先の判定にはCSVだけを使用し、shadow readが失敗しても通知処理は継続します。KOT Keyやメールアドレスの値は比較ログへ出しません。

shadow readログの確認方法、不一致時の一次対応、SQLite切替前の最低条件は、[運用手順](docs/operations.md#shadow-readの運用確認)を参照してください。

## 社員データ整合性確認

SQLiteの有効社員データと、既存通知処理が参照する`data/employeeKey.csv`を読み取り専用で比較します。通知処理の参照先はCSVのままです。

```bash
.venv/bin/division-overtime --root . employees check-consistency
```

一致時は件数と`employee_data_consistency=ok`を表示し、終了コード`0`を返します。不一致時はSQLite側のみ、CSV側のみ、または項目差分の社員コードと差分項目名を表示し、終了コード`1`を返します。KOT Keyは差分の有無だけを判定し、値は表示しません。

監視や運用スクリプトから利用する場合はJSON形式で出力できます。

```bash
.venv/bin/division-overtime --root . employees check-consistency --json
```

JSONには件数、SQLite側のみ・CSV側のみの社員コード、内容不一致の社員コードと差分項目名を含めます。KOT Key、メールアドレス、氏名などの値は出力しません。

整合性結果を履歴へ追記する場合:

```bash
.venv/bin/division-overtime --root . employees record-consistency
```

結果は`data/employee-consistency-history.jsonl`へ1実行1行で追記されます。履歴には社員コードと差分項目名だけを保存し、KOT Key、氏名、メールアドレスなどの実値は保存しません。`division-overtime-employee-consistency.timer`が毎日03:15に自動実行し、停止中に時刻を過ぎた場合は`Persistent=true`により次回起動後に補完実行します。

## 終了コード

- `0`: 正常
- `1`: 社員データ不一致、または実行失敗
- `2`: 設定不備
- `4`: Slack送信失敗

## セキュリティ

次のファイルはGitへ登録しません。

- `.env`
- `config/production.toml`
- `data/employeeKey.csv`
- SQLite DBとWAL関連ファイル
- 旧版の秘密情報を含む資産

秘密情報や実社員情報を、README、Issue、Pull Request、ログ共有へ貼り付けないでください。

## Web管理UI基盤（Issue #5）

Web管理UIは既存のthreshold、weekly、health処理から独立したFastAPIサービスとして起動します。認証後に社員一覧・検索・追加・編集・有効無効切替・削除を行えます。保存時はSQLiteを更新し、有効社員から既存通知用の`employeeKey.csv`を安全に再生成します。KOT社員同期は後続PRで追加します。

### 構成

```text
src/division_overtime/web/
├── __init__.py
├── __main__.py
├── app.py
├── auth.py
├── config.py
├── dependencies.py
├── password_hash.py
└── routes/
    ├── __init__.py
    ├── auth.py
    ├── employees.py
    └── system.py

frontend/
├── index.html
├── package.json
├── tsconfig.json
├── tsconfig.app.json
├── tsconfig.node.json
├── vite.config.ts
└── src/
    ├── App.tsx
    ├── main.tsx
    └── styles.css
```

Web設定の読み込みでは、KING OF TIMEとSlackのトークンを要求しません。外部サービスの認証情報は、既存通知コマンドが必要になった時点でのみ読み込みます。

### 管理者認証の初期設定

Argon2ハッシュを生成します。入力したパスワード自体は表示・保存されません。

```powershell
division-overtime-web-hash-password
```

出力されたハッシュとランダムなセッション秘密鍵を`.env`へ設定します。

```env
WEB_ADMIN_USERNAME=hiro
WEB_ADMIN_PASSWORD_HASH=<Argon2ハッシュ>
WEB_SESSION_SECRET=<32文字以上のランダム文字列>
WEB_SESSION_COOKIE_NAME=division_overtime_session
WEB_SESSION_COOKIE_SECURE=false
WEB_SESSION_MAX_AGE_SECONDS=28800
WEB_LOGIN_MAX_ATTEMPTS=5
WEB_LOGIN_WINDOW_SECONDS=900
WEB_LOGIN_LOCKOUT_SECONDS=900
```

LAN内HTTP運用中は`WEB_SESSION_COOKIE_SECURE=false`とします。HTTPS化した場合は`true`へ変更します。セッションはWebプロセスのメモリ上に保存され、サービス再起動時には全セッションが失効します。

### Python依存関係

Windowsのローカル開発環境では`uv`を標準とします。`.python-version`でPython 3.13を指定し、`uv.lock`からWeb用・開発用依存関係を再現します。

```powershell
uv sync --frozen --extra web --extra dev
```

初回導入時や依存関係を変更した場合は、ロックファイルを更新してから同期します。

```powershell
uv lock
uv sync --extra web --extra dev
```

既存のvenv / pip手順も当面利用できます。

```powershell
python -m pip install -e ".[web,dev]"
```

Raspberry Piでは従来どおり次のようにインストールします。

```bash
./.venv/bin/python -m pip install -e '.[web]'
```

### フロントエンドの開発

```powershell
cd frontend
npm install
npm run dev
```

Vite開発サーバーは`/api`を`http://127.0.0.1:8000`へ転送します。別ターミナルでFastAPIを起動してください。

```powershell
cd D:\_dev\division-overtime
$env:WEB_HOST = "127.0.0.1"
$env:WEB_PORT = "8000"
division-overtime-web
```

### Node.js運用方針

- Windows開発環境とGitHub ActionsはNode.js 22を推奨
- Raspberry Pi本番は既存のNode.js 20.19.2 / npm 9.2.0を継続利用
- frontendの対応範囲はNode.js 20.19以上24系まで
- 正式リリースはRaspberry Pi上の`scripts/deploy.sh`で`npm ci`と`npm run build`を実行
- Windowsでbuildしたdistの配信は、開発中のfrontend実機確認に限定

Node.js更新と正式リリース方式の変更は同時に行わず、Raspberry Piでの動作確認後に別Issueで判断します。

### 本番用ビルドと同一オリジン配信

```powershell
cd frontend
npm ci
npm run lint
npm run test
npm run build
cd ..
division-overtime-web
```

frontendの品質確認にはOxlintとVitest / Testing Libraryを使用します。`npm run test:watch`は開発中の監視実行専用で、PR前の標準検証では単発実行の`npm run test`を使用します。

frontendはReact 19.2系を使用します。React Compiler、Server Components、Actionsなどの新機能はこの段階では導入せず、既存のSPA構成と認証フローを維持します。

`frontend/dist/index.html`が存在する場合、FastAPIがSPAと`/assets`を配信します。未ビルドの場合もAPIは起動し、`/`はHTTP 503と`frontend_not_built`を返します。

### 開発中のfrontend実機確認

APIやPython処理を変更せず、frontendだけをRaspberry Piで確認する場合は、cleanな作業ツリーから次を実行します。`<SSH接続先>`にはSSH configのHost名または`pi@ホスト名`を指定します。

```powershell
.\scripts\deploy-frontend.ps1 -Target <SSH接続先>
```

このスクリプトは次を行います。

1. ローカルとRaspberry Piの`VERSION`一致を確認
2. `npm ci`と`npm run build`を実行
3. `frontend/dist`だけをRaspberry Piへ転送
4. 既存distを`var/backups/frontend-dist/`へ退避
5. 一時ディレクトリからdistを原子的に切り替え
6. Webサービスを再起動し、`/api/system/health`のversionと`frontendBuilt=true`を確認
7. 失敗時は直前のdistへ自動復旧

バックアップは最新5世代を保持します。`.env`、SQLite、実社員CSV、KOT設定、通知service / timerには触れません。正式リリースではこのスクリプトを使用せず、従来どおりRaspberry Piで`./scripts/deploy.sh`を実行します。

主要エンドポイント:

- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/status`
- `GET /api/auth/me`
- `GET /api/system/health`
- `GET /api/version`
- `GET /api/employees`
- `GET /api/employees/{code}`
- `POST /api/employees`
- `PUT /api/employees/{code}`
- `GET /api/docs`

Web用環境変数:

```env
WEB_HOST=0.0.0.0
WEB_PORT=8000
WEB_LOG_LEVEL=INFO
WEB_ADMIN_USERNAME=hiro
WEB_ADMIN_PASSWORD_HASH=<Argon2ハッシュ>
WEB_SESSION_SECRET=<32文字以上のランダム文字列>
```

### 社員管理の保存動作

社員追加・編集時は次の順序で処理します。保存APIは、保存された社員情報に加えて、`employeeKey.csv`の生成成否・生成日時・出力件数・出力先・更新前バックアップ先を返します。CLIの`employees export-csv --apply`も同じ生成結果を標準出力へ記録します。成功・失敗はアプリケーションログにも記録しますが、KOT Keyは応答・標準出力・ログに含めません。

1. 入力値を検証
2. SQLiteトランザクション内で社員情報を更新
3. 未コミット状態から有効社員を取得
4. 一時CSVへ出力し、既存CSVローダーで再検証
5. 既存CSVがある場合は`data/backups/employee-csv/`へ所有者限定権限で複製
6. `Path.replace()`で`data/employeeKey.csv`を原子的に置換
7. 更新成功後に`employeeKey_*.csv`の最新30世代を残して古いバックアップを整理
8. SQLiteをコミット

バックアップ作成に失敗した場合はCSV置換を開始しません。途中で失敗した場合はSQLiteをロールバックし、CSVを置換済みの場合は更新前の内容へ復元します。有効社員を0件にする更新は拒否します。バックアップは最新30世代を保持します。整理対象は命名規則に一致する`employeeKey_*.csv`だけで、想定外のファイルやディレクトリは削除しません。整理に失敗した場合は警告ログを記録し、生成済みCSVと新規バックアップは維持します。

KOT Keyは新規追加時のみ必須です。編集時は空欄のまま保存すると既存値を維持し、新しい値を入力した場合だけ更新します。KOT KeyはAPIレスポンス、一覧、既存値の編集表示、アプリケーションログへ出力しません。

### 社員削除

退職、対象部署からの異動、部内判断による恒久的な残業管理対象外など、今後通知対象へ戻す予定がない社員は編集画面から削除できます。削除前にSQLiteと`employeeKey.csv`を`var/backups/employee-delete/<timestamp>/`へ保存し、SQLiteから社員を削除した後、有効社員でCSVを再生成します。CSV生成に失敗した場合はSQLite削除をロールバックし、既存CSVを維持します。有効社員が0件になる削除は拒否します。

一時的に通知を止める場合や復帰可能性が高い場合は「無効」、退職・異動・恒久的な管理対象外は「削除」を使用します。KOTに在籍中の削除社員は次回同期で新規候補へ再表示されますが、選択して反映しない限り通知対象には戻りません。

通知処理は引き続き`data/employeeKey.csv`を参照します。Webサービスが停止してもthreshold、weekly、healthのserviceおよびtimerは独立して動作します。

### systemd

```bash
sudo cp systemd/division-overtime-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now division-overtime-web.service
systemctl status division-overtime-web.service --no-pager
```

初期アクセスURL:

```text
http://<Raspberry-Piのホスト名>:8000/
```

Webサービスを停止しても、既存のthreshold、weekly、healthサービスおよびtimerには影響しません。

## KOT社員同期

管理画面の「KOT社員同期」から、KING OF TIMEの従業員一覧を手動取得できます。

1. 「KOTから取得」を押す
2. 新規・更新・無効化候補を確認する
3. 反映対象を選択する
4. 「選択した差分を反映」を押す

取得とプレビューだけではSQLiteおよび`data/employeeKey.csv`は変更されません。明示的な反映操作時のみ、反映前バックアップを作成してからSQLiteを更新し、有効社員のCSVを一時ファイルへ生成・検証して原子的に置換します。反映成功時はAPIレスポンスと管理画面にバックアップ先を表示します。処理に失敗した場合はSQLiteとCSVを元へ戻します。

### KOT同期反映前バックアップ

「選択した差分を反映」を実行すると、SQLite更新を開始する前に次のディレクトリへバックアップを作成します。

```text
var/backups/kot-sync/YYYYMMDD_HHMMSS_ffffff/
├── division_overtime.sqlite3
└── employeeKey.csv  # 反映前に存在する場合のみ
```

- SQLiteはファイルコピーではなくSQLite Backup APIで整合性を保って保存
- バックアップDBに対して`PRAGMA integrity_check`を実行
- CSVが存在する場合は同じバックアップ世代へ保存
- バックアップ作成または整合性確認に失敗した場合は、SQLite更新とCSV再生成を開始しない
- バックアップにはKOT Keyや社員名を含む識別情報をファイル名・ディレクトリ名として使用しない

復旧手順は`docs/operations.md`を参照してください。

KOT Keyは画面およびAPIレスポンスには表示されません。Webサービスで同期機能を利用するには、既存通知処理と同じ`.env`の`KINGOFTIME_TOKEN`が必要です。

KOT側に存在しない有効社員や退職日が設定された有効社員は削除せず、無効化候補として表示します。KOT側に存在しない場合と退職日が設定されている場合のどちらでも、すでに無効な社員は無効化候補へ再表示しません。SQLiteに未登録でKOT退職済みの社員は新規候補へ表示しません。KOT在籍中でSQLite未登録の社員は従来どおり新規候補へ表示します。従業員グループの「勤怠管理なし」「休職中」「業務委託」「セカンドからの出向者」は注意情報として表示し、自動除外はしません。

### KOT同期対象部署

KOT社員同期は全社社員を取得した後、`KOT_SYNC_DIVISION_CODES` に指定した部署だけを差分判定対象にします。初期値は `156,158,300` です。空設定では全社同期へフォールバックせず、Web起動時に設定エラーとなります。取得件数と同期対象件数はプレビュー画面で分けて表示され、差分は初期状態では未選択です。

- KOT同期プレビューは差分種別、勤怠管理なし、休職中で表示を絞り込み、変更項目を確認してから選択できます。

### KOT同期の再有効化

KOTで在籍中かつSQLiteで無効の社員は `reactivate` 候補として表示し、管理者が選択した場合だけ通知対象へ戻します。既存のメールアドレス・個人上限分・メモは保持し、KOT同期バックアップは最新30世代を維持します。

## Windowsローカル開発環境

新しいWindows端末では、リポジトリ取得後に次を実行します。デスクトップPCとノートPCで同じ`uv.lock`を使用するため、同一のPython依存関係を再現できます。

```powershell
git clone https://github.com/runsystem-hiro/division-overtime.git
cd division-overtime

.\scripts\verify.ps1
```

`.\scripts\verify.ps1`は、uv同期、バージョン整合性、Ruff、pytest、frontend lint・test・build、`git diff --check`を順番に実行します。失敗した工程で停止し、実行後は呼び出し元ディレクトリへ戻ります。

個別の確認や問題の切り分けでは、従来どおり`uv sync`、`uv run`、`npm`を直接実行できます。`uv sync`はプロジェクト直下の`.venv`を作成・更新します。通常は仮想環境を手動で有効化せず、`uv run`でコマンドを実行します。

個別実行する場合は次のコマンドを使用します。

```powershell
uv sync --frozen --extra web --extra dev
uv run python .\scripts\check_version.py --root .
uv run ruff check .
uv run ruff format --check .
uv run pytest -q

cd frontend
npm ci
npm run build
cd ..

git diff --check
```

Web管理画面の開発では、本番データと分離した`config/development.toml`を使用します。
既定環境は従来どおり`production`です。ローカル起動時だけ`.env`で次を指定します。

```dotenv
DIVISION_OVERTIME_ENV=development
```

認証は本番と同じログイン画面・API・セッション処理を使用します。`WEB_ADMIN_USERNAME`と
`WEB_ADMIN_PASSWORD_HASH`はローカルの`.env`へ設定し、秘密情報はGit管理しません。

初回またはダミーデータを初期化するときは、次を実行します。

```powershell
$env:DIVISION_OVERTIME_ENV = "development"
python .\scripts\seed_development_data.py --root .

cd frontend
npm ci
npm run build
cd ..

python -m division_overtime.web
```

生成先は次のとおりです。

- SQLite: `var/development/division_overtime.sqlite3`
- CSV: `data/development/employeeKey.csv`

開発用通知先は全部署共通の`ALL`を`h-tanaka@runsystem.co.jp`だけに固定し、
個人宛て通知を無効化しています。開発環境でも通知コマンドを実行する前に、
`DIVISION_OVERTIME_ENV=development`であることを確認してください。

開発環境のKOT同期画面では、KOT本番APIへ接続せず固定のダミーKOT社員データを使用します。
`KOTから取得`の代わりに`ダミーKOTから取得`と表示され、`create`、`update`、
`reactivate`、`disable`、`unchanged`を各1件ずつ確認できます。選択した差分の反映先は、
開発用SQLiteと`data/development/employeeKey.csv`だけです。再現状態へ戻す場合は、
`python .\scripts\seed_development_data.py --root .`を再実行してください。
