# Development

## 推奨環境

- Windows 11 / PowerShell 7
- Python 3.13
- uv
- Node.js 22
- npm

Frontendの主要構成:

- React 19.2系
- Vite 8.1系
- TypeScript 6.0系
- Vitest 4系
- Oxlint

Pythonの許容範囲は`pyproject.toml`、Node.jsとnpmの許容範囲は`frontend/package.json`を正とします。

## 初回セットアップ

```powershell
uv sync --frozen --extra web --extra dev

Set-Location .\frontend
npm ci
Set-Location ..
```

## 開発環境データ

`.env`でdevelopmentを選択します。

```dotenv
DIVISION_OVERTIME_ENV=development
```

開発用ダミーデータ生成:

```powershell
uv run python .\scripts\seed_development_data.py
```

開発環境は`var/development/`と`data/development/`を利用し、KING OF TIME本番APIを無効化してmock previewを利用します。

## Backend / Web API

```powershell
uv run division-overtime-web
```

## Frontend

別ターミナルで起動します。

```powershell
Set-Location .\frontend
npm run dev
```

Vite開発サーバーはbackend APIへproxyします。

## 標準検証

```powershell
.\scripts\verify.ps1
```

実行内容:

- `uv sync --frozen --extra web --extra dev`
- version整合性
- Ruff lint / format check
- pytest
- `npm ci`
- Oxlint
- Vitest
- TypeScript / Vite build
- `git diff --check`

`verify.ps1`は自動修正、commit、push、PR、merge、deploy、本番接続を行いません。

## 個別コマンド

```powershell
uv run python .\scripts\check_version.py --root .
uv run ruff check .
uv run ruff format --check .
uv run pytest -q

Set-Location .\frontend
npm run lint
npm run test
npm run build
```

整形が必要な場合だけ実行します。

```powershell
uv run ruff format .
```

## CI

GitHub Actionsはpull requestとworkflow_dispatchで実行します。

- Python 3.13
- uv 0.11.32
- Node.js 22
- lock file準拠
- Python jobとFrontend jobを分離

CIはクリーン環境での補助確認です。ローカル`verify.ps1`を主たる検証とします。CIから本番、Raspberry Pi、KOT API、Slackへ接続しません。

## Frontendだけの実機確認

正式デプロイ前の開発確認に限り、Windowsでbuildした`frontend/dist`を`.\scripts\deploy-frontend.ps1`でPiへ反映できます。正式リリースは必ずPi上の`./scripts/deploy.sh`を使用します。
