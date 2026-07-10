# Systemd Forward Automation Readiness Report

Date: 2026-07-10

## Installed units

| Unit | Path | Enabled | Active |
|------|------|---------|--------|
| `worldcup-forward-evaluation-daily.service` | `/etc/systemd/system/` | via timer | oneshot |
| `worldcup-forward-evaluation-daily.timer` | `/etc/systemd/system/` | **enabled** | **active** |
| `worldcup-forward-evaluation-weekly.service` | `/etc/systemd/system/` | via timer | oneshot |
| `worldcup-forward-evaluation-weekly.timer` | `/etc/systemd/system/` | **enabled** | **active** |

**Not installed:** legacy sync timer (orchestrator includes result sync).

## Configuration review

- WorkingDirectory: `/opt/worldcup-predictor` ✓
- Python: `.venv/bin/python` ✓
- User: root (evaluation DB under `data/`) ✓
- TimeoutStartSec: 600 daily / 300 weekly ✓
- No secrets in unit files ✓
- Journal logging ✓

## Cadence (Europe/Vienna)

| Timer | Schedule (local) | UTC hint (CEST) |
|-------|------------------|-----------------|
| Daily orchestrator | 07:00, 17:00 | ~05:00, ~15:00 |
| Weekly report | Mon 08:00 | Mon ~06:00 |

Next scheduled: daily `2026-07-11 07:00 UTC` (systemd display), weekly `2026-07-13 08:00 UTC`

**Status:** `SYSTEMD_TEMPLATE_VALID`
