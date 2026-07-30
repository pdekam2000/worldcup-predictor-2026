# Phase 6 — Proposed systemd timers (NOT ENABLED)

**Status:** Documented only. Do **not** enable until dry-run + cap-20 + cap-50 validation pass.

No promotion. No routing activation. Challengers remain `SHADOW_RESEARCH_ONLY`.

## Proposed units (draft)

### Early discovery + freeze pass

- **Timer:** `phase6-hv-tf-morning.timer`
- **OnCalendar:** `*-*-* 07:15:00` Europe/Vienna
- **Service ExecStart:**
  `/opt/worldcup-predictor/.venv/bin/python /opt/worldcup-predictor/scripts/run_phase6_true_forward_day.py --date today --cap 20`
- **Notes:** Start at cap 20; raise to 50/100 only after promotion_gate_for_next_stage (operational cap, not model promotion).

### Controlled refresh pass (prematch only)

- **Timer:** `phase6-hv-tf-refresh.timer`
- **OnCalendar:** `*-*-* 15:30:00` Europe/Vienna
- **Service ExecStart:** same script with `--resume-checkpoint <id>` or idempotent re-run (reuse immutable freezes; skip post-KO).
- **Guards:** executor blocks `already_started`; odds gates unchanged; no freeze overwrite.

### Result follow-up

- **Timer:** `phase6-hv-tf-followup.timer`
- **OnCalendar:** `*-*-* 00:40:00,06:40:00,12:40:00,18:40:00` Europe/Vienna
- **Service ExecStart:**
  `/opt/worldcup-predictor/.venv/bin/python /opt/worldcup-predictor/scripts/report_phase6_true_forward.py --followup --followup-batch-size 50 --out /opt/worldcup-predictor/artifacts/phase6_hv_tf/cumulative_latest.json`

### Daily report after follow-up

- Fold into follow-up service or a separate `phase6-hv-tf-report.timer` at `01:10` Vienna writing `daily_report.json` + cumulative.

## Prevent

| Risk | Mitigation |
|---|---|
| Duplicate freezes from multiple passes | Immutable freeze reuse; first ACTIVE freeze wins |
| Post-kickoff refresh | Executor `post_kickoff` / status gates |
| Relabel historical as true_forward | `resolve_cohort_type(backfill=True)` never returns true_forward |
| Overwrite snapshots | Freeze bridge + content_hash check after shadow |
| Disk exhaustion | Stop batch if free < 8G; alert < 10G |

## Enable checklist (owner)

1. Stage 1 dry-run OK
2. Stage 2 cap 20: canonical/shadow rates + no freeze mutation
3. Stage 3 cap 50: provider/latency/locks/disk OK
4. Stage 4 cap 100: only then
5. Explicit owner approval to `systemctl enable --now` any timer
6. Confirm: **No promotion and no routing activation occurred.**
