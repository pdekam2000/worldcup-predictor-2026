# PHASE A19B — AI Assistant Alert Scan Timer

**Date:** 2026-06-25  
**Environment:** Production `https://footballpredictor.it.com`

---

## Final Status

**`ASSISTANT_ALERT_TIMER_ACTIVE`**

---

## Summary

Automated AI Assistant alert scanning via systemd timer. Runs `run_alert_scan()` every 15 minutes with overlap protection, structured logging, and preserved dedup/quiet-hours/preferences behavior. No changes to WDE, EGIE, models, scoring, calibration, or billing.

---

## Files Changed / Added

| Path | Role |
|------|------|
| `deployment/systemd/worldcup-assistant-alert-scan.service` | Oneshot service (www-data) |
| `deployment/systemd/worldcup-assistant-alert-scan.timer` | 15-minute calendar timer |
| `worldcup_predictor/ai_assistant/scan_job.py` | Lock, logging, CLI entry |
| `main.py` | `assistant-alert-scan` CLI command |
| `worldcup_predictor/api/routes/ai_assistant.py` | Admin scan uses `run_alert_scan_job()` |
| `scripts/install_phase_a19b_assistant_alert_timer.sh` | Install + enable timer |
| `scripts/deploy_phase_a19b_production.sh` | Deploy + validate |
| `scripts/validate_phase_a19b_assistant_alert_timer.py` | 20-check validation |

---

## Timer Cadence

```
OnCalendar=*-*-* *:00/15:00   # :00, :15, :30, :45 each hour
Persistent=true
RandomizedDelaySec=30
```

**Service:** `worldcup-assistant-alert-scan.service`  
**Timer:** `worldcup-assistant-alert-scan.timer` (enabled)

---

## Safety

| Mechanism | Implementation |
|-----------|----------------|
| Overlap prevention | Python `fcntl` flock on `/run/worldcup/assistant-alert-scan.lock` |
| Logging | `journalctl -u worldcup-assistant-alert-scan.service` |
| Quiet hours | Existing `should_notify_user()` in detectors |
| 6-hour dedup | Existing `dedup_key` in `AssistantStore` |
| User preferences | `min_bet_quality`, `alert_frequency`, etc. per user |
| Legacy notifications | SaaS `/api/notifications` unchanged |

**Note:** Initial deploy used double flock (systemd + Python on same file), causing false overlap skips. Fixed by using Python lock only.

---

## CLI

```bash
python main.py assistant-alert-scan
python main.py assistant-alert-scan --user-id <id>
```

---

## Validation Result

| Environment | Result |
|-------------|--------|
| Local | **20/20 PASS** |
| Production | **20/20 PASS** |

Checks: service/timer files, CLI, scan execution, overlap handling, dedup, preferences, quiet hours, legacy notifications preserved, WDE unchanged.

---

## Deploy Result

```
● worldcup-assistant-alert-scan.timer - active (waiting)
   Trigger: every 15 minutes

Manual service run (post-fix):
  Status: ok
  Users scanned: 3
  Notifications created: 0
```

Commands used:
```bash
systemctl enable --now worldcup-assistant-alert-scan.timer
systemctl list-timers | grep assistant
journalctl -u worldcup-assistant-alert-scan.service -n 15
```

---

## Rollback Plan

```bash
sudo systemctl disable --now worldcup-assistant-alert-scan.timer
sudo rm /etc/systemd/system/worldcup-assistant-alert-scan.service
sudo rm /etc/systemd/system/worldcup-assistant-alert-scan.timer
sudo systemctl daemon-reload
```

Manual admin scan remains available: `POST /api/admin/assistant/scan-alerts`

---

## Operations

| Action | Command |
|--------|---------|
| Timer status | `systemctl status worldcup-assistant-alert-scan.timer` |
| Manual run | `systemctl start worldcup-assistant-alert-scan.service` |
| Logs | `journalctl -u worldcup-assistant-alert-scan.service -f` |
| Next runs | `systemctl list-timers \| grep assistant` |
