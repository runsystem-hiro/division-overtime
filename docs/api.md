# Web API

Web APIはFastAPIで提供します。healthとversion、ログイン、認証状態確認を除き、管理APIは認証済みセッションを必要とします。

## System

### `GET /api/system/health`

Web serviceの稼働状態、version、時刻、timezone、frontend build、KOT同期設定を返します。外部サービスへ接続しません。リリース後は`status=ok`、`version=<VERSION>`、`frontendBuilt=true`を確認します。

### `GET /api/version`

`VERSION`の値を返します。

## Authentication

### `POST /api/auth/login`

管理者ログイン。成功時にHTTP only / SameSite strictのセッションcookieを設定します。失敗回数によるrate limitがあります。

### `POST /api/auth/logout`

セッションを削除します。

### `GET /api/auth/status`

未ログインでもHTTP 200です。

```json
{"authenticated":false,"user":null}
```

### `GET /api/auth/me`

認証必須です。未ログイン時はHTTP 401です。

## Employees

Base path: `/api/employees`

- `GET /api/employees`
- `GET /api/employees/consistency`
- `GET /api/employees/{code}`
- `POST /api/employees`
- `PUT /api/employees/{code}`
- `DELETE /api/employees/{code}`

社員保存ではSQLiteとCSVを一体更新します。KOT Keyは既存値をAPIレスポンスへ返しません。

## KING OF TIME sync

Base path: `/api/kot-sync`

- `POST /api/kot-sync/preview`
- `POST /api/kot-sync/apply`
- `GET /api/kot-sync/history`
- `GET /api/kot-sync/status`

previewだけでは本番データを変更しません。applyは選択されたcreate / update / reactivate / disableだけを反映し、適用前バックアップと履歴を作成します。

## Notification history

Base path: `/api/notification-runs`

- `GET /api/notification-runs`
- `GET /api/notification-runs/{run_id}`

一覧はmode、source、dry-run、status、対象数、attempt結果に加え、ページ情報と全履歴集計を返します。詳細は受信者別attempt、dedupe key、重複元run情報を含みます。

## API仕様の確認

開発環境ではFastAPIのOpenAPI UIを利用できます。公開範囲はネットワーク構成と認証方針に従って制限してください。

## 通知実行履歴ページネーション

`GET /api/notification-runs` は実行日時の降順で通知履歴を返します。Web UIは20件固定で取得します。

クエリパラメータ：

- `limit`: 1〜100。既定値は20
- `offset`: 0以上。既定値は0

レスポンス例：

```json
{
  "items": [],
  "total": 23,
  "limit": 20,
  "offset": 0,
  "summary": {
    "total": 23,
    "succeeded": 20,
    "attention": 3,
    "sent": 179
  }
}
```

`summary` は現在ページではなく全履歴を対象に集計します。同一実行日時の履歴は実行IDを第二キーとして安定した順序で返します。Web UIは常に20件固定ですが、APIは過大取得を防ぐため`limit`を最大100に制限します。

## Cloudflare Access viewerと権限昇格

`GET /api/auth/status` と `GET /api/auth/me` は `identitySource`、`elevatedUntil`、`logoutUrl` を返します。Access viewerは `POST /api/auth/elevate` に管理者パスワードを送って一時的にadminへ昇格し、`POST /api/auth/downgrade` でviewerへ戻ります。未認証時のstatusはHTTP 200、meはHTTP 401を維持します。
