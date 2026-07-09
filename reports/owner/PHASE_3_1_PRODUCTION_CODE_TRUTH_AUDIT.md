# Phase 3.1 — Production Code Truth Audit

**Date:** 2026-07-09  
**Server:** `ubuntu-8gb-fsn1-1` (`root@91.107.188.229`)  
**App path:** `/opt/worldcup-predictor`

## Git identity

| Field | Value |
|-------|--------|
| whoami | `root` |
| hostname | `ubuntu-8gb-fsn1-1` |
| branch | `main` (tracking `origin/main`) |
| **HEAD** | `df93d421bdd03da78b86c5575431699ed7762659` |
| Phase 3 branch HEAD (GitHub) | `1e7d638` (`infra/phase3-mcp-prediction-server`) |

## Services

| Service | Status |
|---------|--------|
| worldcup-api | **active** |
| worldcup-mcp | **active** |

## Answers

| # | Question | Answer |
|---|----------|--------|
| 1 | Is production HEAD the Phase 3 branch commit? | **NO** — production at `df93d42`, Phase 3 at `1e7d638` |
| 2 | Is production detached HEAD? | **NO** — on branch `main` |
| 3 | Is MCP code different from GitHub branch? | **PARTIALLY** — MCP files checked out/staged but **not committed** on production |
| 4 | Were files copied manually? | **YES** — `git checkout origin/infra/phase3-mcp-prediction-server -- <paths>` during Phase 3 install |
| 5 | Is production source tree dirty? | **YES** — staged MCP additions + modified runtime/shadow files |
| 6 | Is `strict_live_refresh.py` tracked or manually copied? | **Staged (A)** via checkout from Phase 3 branch; not in production `df93d42` HEAD |
| 7 | Does `requirements.txt` match branch? | **YES** — contains `mcp>=1.27,<2` (staged) |
| 8 | Is `mcp` installed in venv? | **YES** — `mcp==1.28.1` |
| 9 | Is systemd unit identical to committed unit? | **YES** — `diff` empty vs `deployment/systemd/worldcup-mcp.service` |

## Production git status summary

- **Staged MCP additions:** `worldcup_predictor/mcp_server/**`, tests, scripts, docs, systemd unit, `requirements.txt`, `strict_live_refresh.py`
- **Modified (unstaged runtime):** shadow JSONL files, pipeline last-run markdown
- **Untracked:** various local artifacts (`?? =1.27,`, research scripts)

## Lineage note

- `origin/main` (GitHub) = `71f4169` (includes `strict_live_refresh`)
- Production `main` = `df93d42` (ahead of older history, **behind** `origin/main` by 2 commits including strict live refresh merge)
- Phase 3 branch is based on `71f4169` + MCP commits

## Risk

Production MCP runtime is **operating from uncommitted staged files** on a `main` checkout that does not match `origin/main` or the Phase 3 branch HEAD. This is **not** a safe long-term state.

## Recommended reconciliation

See `PHASE_3_1_MCP_END_TO_END_REPORT.md` Part J — merge Phase 3 PR → deploy from `origin/main` → remove manual checkout drift.

**PRODUCTION_MAIN_ALIGNED = NO**
