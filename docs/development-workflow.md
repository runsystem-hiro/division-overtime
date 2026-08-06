# 開発・GitHub運用

## 基本方針

- Issueを先に作成する
- `main` へ直接コミットしない
- 作業前に `main` を最新化する
- 現行ソースを確認してから変更する
- 無関係な変更を混ぜない
- コミットメッセージは英語で記述する
- Pull Request本文は日本語でよい
- Pull Requestは原則としてsquash mergeする
- Squash merge時のコミットタイトルは英語で記述する
- Squash mergeのコミット本文は原則として省略する
- GitHubのコミット履歴とファイル一覧では英語表記を維持する
- 本番影響をPull Requestへ記載する

## 標準フロー

```text
Issue
→ main更新
→ 作業ブランチ
→ 現行HEADの確認
→ 実装またはpatch適用
→ ローカル検証
→ commit
→ push
→ Pull Request
→ squash merge
→ main同期・ブランチ削除
→ 必要時のみリリース・デプロイ
→ 実機確認
```

## mainの更新と作業ブランチ

```powershell
git switch main
git fetch origin
git merge --ff-only origin/main
git status

git switch -c <type>/<description>
```

使用する接頭辞:

- `feat/`
- `fix/`
- `docs/`
- `refactor/`
- `chore/`

## 現行HEADのZIP提出

```powershell
git archive `
  --format=zip `
  --output="$env:USERPROFILE\Downloads\<repository-name>-issueXX.zip" `
  HEAD
```

`git archive` には未コミット変更、`.git`、Git管理外ファイルは含まれません。

## patch適用

```powershell
git apply --check "$env:USERPROFILE\Downloads\<repository-name>-issueXX.patch"
git apply "$env:USERPROFILE\Downloads\<repository-name>-issueXX.patch"
git status
git diff --stat
git diff
```

## 検証

標準検証は [開発環境と検証](development.md) を参照してください。

## コミットとpush

対象ファイルを確認してからstageします。

```powershell
git add <files>
git diff --cached --check
git diff --cached --stat
git commit -m "<type>: <description>"
git push -u origin <branch-name>
```

## Pull Request

Pull Request本文には、次を記載します。

- 概要
- 変更内容
- 背景または原因
- 検証結果
- 本番影響
- `Closes #<issue-number>`

## merge後

```powershell
git switch main
git fetch origin
git merge --ff-only origin/main
git branch -D <branch-name>
git push origin --delete <branch-name>
git fetch --prune
git status
```
