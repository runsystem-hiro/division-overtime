# Architecture

## Runtime flow

1. systemd timer starts a one-shot service with an explicit mode.
2. Configuration is loaded from `config/default.toml`, optional `config/production.toml`, and `.env` secrets.
3. Employee CSV is validated before API access.
4. KING OF TIME data is fetched once for each division and month.
5. Employee snapshots and the execution record are stored in SQLite.
6. Notification candidates are reserved with a unique dedupe key.
7. Slack is called only for newly reserved candidates or previously failed candidates.
8. A successful send changes the notification state to `sent`; a failure remains retryable as `failed`.

## Execution modes

- `threshold`: weekday threshold evaluation and notification
- `weekly`: Friday report regardless of overtime ratio
- `health`: local-only integrity and file-existence checks

`health` does not call KING OF TIME and does not send Slack notifications.

## KING OF TIME API restrictions

The API must not be used during these JST windows:

- 08:30-10:00
- 17:30-18:30

The scheduled threshold and weekly runs are outside these windows. Manual and dry-run executions must also avoid them.

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

## Configuration override policy

`config/production.toml` overrides general defaults. The following notification recipient table is replaced as a whole rather than deep-merged:

```toml
[notifications.department_recipients]
```

This prevents default or sample recipients from remaining active when production recipients are specified.
