# Internship Radar poller

Checks company job boards directly every ~15 minutes (hourly overnight) plus the
Simplify and vanshb03 trackers. Every new matching Summer 2027 role gets a fit score.
New **Tier S** roles send an instant phone push and their own email.

- `companies.toml`: tiers and sources. Edit this to add or move companies.
- `poller.py`: the poller (Python standard library only).
- `data/new_roles.jsonl`: every new role found, with tier, fit score, category,
  opened time and detection lag. The Claude Internship Radar reads this.
- `data/health.json`: which sources work. Check this if alerts go quiet.
- `data/snapshot.json`: current Tier S/A matches (written on manual runs and pushes).

## Secrets (Settings > Secrets and variables > Actions)

| Secret | What |
| --- | --- |
| `NTFY_TOPIC` | Your private ntfy topic name (phone push) |
| `ALERT_EMAIL` | Where Tier S emails go |
| `SMTP_USER`, `SMTP_PASS` | Optional. Gmail address + app password to send the email yourself instead of through ntfy |

## Run it now

Actions tab > Internship Radar poller > Run workflow.

The first run of each source only learns what is already posted, so you
don't get flooded with old roles. Alerts start from the second run.
