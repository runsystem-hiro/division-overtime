# Release Checklist

## 変更範囲

- IssueとPRの目的が一致している
- 無関係な変更がない
- README、docs、CHANGELOG、テストが必要に応じて更新されている
- 本番影響がPRへ明記されている
- 秘密情報、実社員情報、実通知先、token、password、バックアップ、実KOT responseが含まれていない
- README、docs、sample、画面画像に本番固有のホスト名、IP、ユーザー名、部署コード、社員番号が含まれていない

## Windows側検証

```powershell
.\scripts\verify.ps1
git status
git diff --check
```

合格条件:

- version整合性成功
- Ruff成功
- pytest成功
- npm auditで既知の脆弱性なし
- Oxlint成功
- Vitest成功
- frontend build成功
- working treeが意図した変更だけ

## Pull Request

- PR本文に`Closes #Issue番号`
- 変更内容、検証、本番影響を記載
- CI結果を確認
- squash merge
- force pushは行わない
- merge後のmainをfast-forward更新

CIはmergeの必須条件ではなく、必須ステータスチェックには設定せず、補助確認として扱います。ローカル検証成功後にmergeできますが、CI失敗を認識した場合は原因を確認し、未解決のまま本番反映しません。

本番固有のホスト名、SSH接続先、インストールパス、ポート、systemd unit名は公開ドキュメントへ記載せず、リポジトリ外の運用手順を参照します。

## バージョンリリース

正式リリースの場合だけ、次の整合性を確認します。

- `VERSION`
- `pyproject.toml`
- `src/division_overtime/__init__.py`
- `frontend/package.json`
- `frontend/package-lock.json`
- `CHANGELOG.md`

```powershell
uv run python .\scripts\check_version.py --root .
```

## 本番環境への反映

```bash
cd <app-root>
git switch main
git status --short
./scripts/deploy.sh
```

## 本番環境での確認

```bash
curl -fsS <health-url>/api/system/health
.venv/bin/division-overtime --root . database status
.venv/bin/division-overtime --root . employees check-consistency
systemctl list-timers --all | grep <timer-name-pattern>
```

確認項目:

- `status=ok`
- version一致
- `frontendBuilt=true`
- SQLite integrity checkが`ok`
- SQLite/CSV整合性が一致
- timerが`active (waiting)`
- Web、通知、KOT同期に変更範囲外の異常がない

通知ロジックを変更していない場合、実通知serviceを手動実行しません。自然なtimer実行または既存履歴で確認します。

## バックアップ

DBや社員データを変更するリリースでは、[バックアップ・復旧](backup-restore.md)に従って復旧可能性を確認します。

## GitHub Release

正式リリース時のみtagとGitHub Releaseを作成します。既存形式に合わせて自動生成ノートを使用します。

```powershell
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin vX.Y.Z

gh release create vX.Y.Z `
  --repo runsystem-hiro/division-overtime `
  --title "vX.Y.Z" `
  --generate-notes `
  --notes-start-tag vPREVIOUS `
  --verify-tag `
  --latest
```
