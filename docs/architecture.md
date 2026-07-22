# Architecture

## Runtime flow

1. systemd timer starts a one-shot service with an explicit mode.
2. Configuration is loaded from `config/default.toml`, optional `config/production.toml`, and `.env` secrets.
3. Employee CSV is validated before API access.
4. King of Time data is fetched once for each division and month.
5. Employee snapshots and the execution record are stored in SQLite.
6. Notification candidates are reserved with a unique dedupe key.
7. Slack is called only for newly reserved candidates or previously failed candidates.
8. A successful send changes the notification state to `sent`; a failure remains retryable as `failed`.

## SQLite durability

- WAL journal mode
- Foreign keys enabled
- 5-second busy timeout
- Explicit transactions
- Unique `(dedupe_key, recipient)` constraint
- Dry runs do not consume notification dedupe keys

## Notification identity

Threshold notifications are unique by ISO week, employee, threshold, and recipient.
Weekly notifications are unique by ISO week, employee, and recipient.
