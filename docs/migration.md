# Migration from the legacy cron version

1. Keep the legacy directory offline as a reference copy.
2. Do not copy legacy logs, cache files, flags, Slack user-ID cache, or the real employee CSV into Git.
3. Prepare `.env`, `config/production.toml`, and `data/employeeKey.csv` on the Raspberry Pi.
4. Run configuration validation and database initialization.
5. Run both modes with `--dry-run` and compare candidates with the legacy output.
6. Disable the two legacy cron entries.
7. Enable the new systemd timers.
8. Observe the first threshold and weekly executions with `journalctl` and SQLite status checks.

## Legacy schedules

- Every day 10:30: legacy script; internally skips weekends and Japanese holidays except force mode.
- Friday 21:30: legacy script; internally detects force mode.

## New schedules

- Monday-Friday 10:30: explicit `threshold` mode; Japanese public holidays are skipped.
- Friday 21:30: explicit `weekly` mode; runs regardless of overtime ratio.
