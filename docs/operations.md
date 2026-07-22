# Operations

## Validate

```bash
.venv/bin/division-overtime --root /home/pi/division-overtime validate-config
.venv/bin/division-overtime --root /home/pi/division-overtime database status
```

## Dry run

```bash
.venv/bin/division-overtime --root /home/pi/division-overtime run threshold --dry-run
.venv/bin/division-overtime --root /home/pi/division-overtime run weekly --dry-run
```

Dry runs store execution and overtime snapshots for comparison but do not reserve notification dedupe keys and do not send Slack messages.

## Inspect timers

```bash
systemctl list-timers 'division-overtime-*'
systemctl status division-overtime-threshold.timer --no-pager
systemctl status division-overtime-weekly.timer --no-pager
```

## Inspect logs

```bash
journalctl -u division-overtime-threshold.service -n 100 --no-pager
journalctl -u division-overtime-weekly.service -n 100 --no-pager
```

## SQLite

```bash
sqlite3 var/division_overtime.sqlite3 'PRAGMA integrity_check;'
sqlite3 -header -column var/division_overtime.sqlite3 \
  'SELECT run_id, mode, started_at, status, dry_run FROM execution_runs ORDER BY id DESC LIMIT 10;'
sqlite3 -header -column var/division_overtime.sqlite3 \
  'SELECT recipient, notification_type, status, attempt_count, updated_at FROM notification_attempts ORDER BY id DESC LIMIT 20;'
```
