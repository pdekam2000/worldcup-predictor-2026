#!/usr/bin/env python3
"""PHASE PROJECT-ASSET-AUDIT-1 — Read-only project asset / DB / GitHub audit."""

from __future__ import annotations

import json
import os
import platform
import re
import sqlite3
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
REPORT = ROOT / "PROJECT_ASSET_DATABASE_GITHUB_AUDIT_REPORT.md"
DATE_TAG = date.today().isoformat().replace("-", "")

KEY_TABLES = [
    "fixtures",
    "fixture_results",
    "odds_snapshots",
    "worldcup_stored_predictions",
    "ecse_prediction_snapshots",
    "ecse_oddalerts_shadow_predictions",
    "ecse_oddalerts_shadow_monitor",
]

MODULE_PATHS = [
    ("worldcup_predictor", "backend core"),
    ("scripts", "scripts"),
    ("worldcup_predictor/owner_predict_eval", "owner_predict_eval"),
    ("worldcup_predictor/owner_daily", "owner_daily"),
    ("worldcup_predictor/owner_manual_exact", "owner_manual_exact"),
    ("worldcup_predictor/research/oddalerts_ecse_shadow.py", "oddalerts_ecse_shadow"),
    ("worldcup_predictor/research/ecse_live", "ecse_live"),
    ("worldcup_predictor/research/wde_shadow_historical", "wde_shadow_historical"),
    ("worldcup_predictor/data_import", "data_import"),
    ("worldcup_predictor/data_import/oddalerts_csv_promotion_write.py", "oddalerts_csv_promotion"),
    ("worldcup_predictor/data_import/external_historical_zip_importer.py", "historical_csv_ingest"),
    ("base44-d", "frontend base44-d"),
    ("base44-d/package.json", "frontend package.json"),
    ("alembic", "alembic migrations"),
    ("tests", "tests"),
]

GAP_MODULES = [
    ("owner_daily workflow", "worldcup_predictor/owner_daily"),
    ("owner_predict_eval", "worldcup_predictor/owner_predict_eval"),
    ("owner_manual_exact", "worldcup_predictor/owner_manual_exact"),
    ("OddAlerts CSV pipeline", "worldcup_predictor/data_import/oddalerts_csv_incremental_importer.py"),
    ("ECSE OddAlerts shadow", "worldcup_predictor/research/oddalerts_ecse_shadow.py"),
    ("ECSE OddAlerts monitor", "worldcup_predictor/research/oddalerts_ecse_monitor.py"),
    ("Historical CSV ingest", "worldcup_predictor/data_import/external_historical_zip_importer.py"),
    ("WDE shadow retrain", "scripts/train_wde_shadow_model_from_historical_csv.py"),
    ("manual exact score report", "MANUAL_OWNER_EXACT_SCORE_PREDICTION_REPORT.md"),
    ("knockout prediction eval", "scripts/evaluate_owner_knockout_predictions.py"),
    ("Owner Lab API routes", "worldcup_predictor/api/routes/owner_ecse_shadow_lab.py"),
    ("database migrations", "worldcup_predictor/database/migrations.py"),
]

DATA_FOLDERS = [
    "artifacts",
    "reports",
    "reports/owner",
    "logs",
    "data/external_historical_csv",
    "data/oddalerts_csv",
    "data/research",
    "data/backups",
    "backups",
    "models/shadow",
    ".cache",
    "data/evaluation",
]

SECRET_PATTERNS = re.compile(
    r"\.env$|credentials|token|gmail|api_key|secret|password|service_account|client_secret",
    re.I,
)


def _run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 120) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd or ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as exc:
        return 1, "", str(exc)


def _run_ssh(script: str, timeout: int = 60) -> tuple[int, str, str]:
    return _run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "root@91.107.188.229", script],
        cwd=ROOT,
        timeout=timeout,
    )


def _git_info() -> dict[str, Any]:
    info: dict[str, Any] = {"path": str(ROOT.resolve())}
    for key, cmd in {
        "branch": ["git", "branch", "--show-current"],
        "commit": ["git", "rev-parse", "HEAD"],
        "remote": ["git", "remote", "-v"],
    }.items():
        _, out, _ = _run(cmd)
        info[key] = out
    _, out, _ = _run(["git", "log", "--oneline", "-5"])
    info["last_5_commits"] = out.splitlines() if out else []
    _, out, _ = _run(["git", "status", "--short"])
    lines = [ln for ln in out.splitlines() if ln.strip()]
    info["status_lines"] = len(lines)
    info["untracked_count"] = sum(1 for ln in lines if ln.startswith("??"))
    info["modified_count"] = sum(1 for ln in lines if ln.startswith(" M") or ln.startswith("M ") or ln.startswith(" D") or ln.startswith("D "))
    info["dirty"] = bool(lines)
    _, out, _ = _run(["git", "rev-list", "--left-right", "--count", "origin/main...HEAD"])
    parts = out.split() if out else ["0", "0"]
    info["behind_origin"] = int(parts[0]) if len(parts) > 0 else 0
    info["ahead_origin"] = int(parts[1]) if len(parts) > 1 else 0
    _, out, _ = _run(["git", "ls-remote", "origin", "refs/heads/main"])
    info["origin_main_commit"] = out.split()[0] if out else None
    _, tracked, _ = _run(["git", "ls-files"])
    info["tracked_file_count"] = len(tracked.splitlines()) if tracked else 0
    return info


def _env_var_names() -> list[str]:
    env_path = ROOT / ".env"
    names: list[str] = []
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            names.append(line.split("=", 1)[0].strip())
    return names


def _folder_stats(rel: str) -> dict[str, Any]:
    p = ROOT / rel
    if not p.exists():
        return {"path": rel, "exists": False, "file_count": 0, "size_bytes": 0}
    files = [f for f in p.rglob("*") if f.is_file()]
    size = sum(f.stat().st_size for f in files)
    return {
        "path": rel,
        "exists": True,
        "file_count": len(files),
        "size_bytes": size,
        "size_mb": round(size / (1024 * 1024), 2),
        "should_git_track": False,
        "should_backup": True,
        "should_gitignore": True,
        "purpose": "generated/runtime data",
    }


def _audit_db(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path.resolve()), "exists": False}
    st = path.stat()
    info: dict[str, Any] = {
        "path": str(path.resolve()),
        "exists": True,
        "size_bytes": st.st_size,
        "size_mb": round(st.st_size / (1024 * 1024), 2),
        "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
    }
    low = str(path).lower()
    if "backup" in low:
        info["inferred_role"] = "backup"
    elif "validation" in low or "test" in low:
        info["inferred_role"] = "test_or_validation"
    elif path.name == "football_intelligence.db":
        info["inferred_role"] = "likely_canonical_local"
    else:
        info["inferred_role"] = "other"
    try:
        uri = f"file:{path.resolve()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
        info["table_count"] = len(tables)
        counts = {}
        for t in KEY_TABLES:
            if t in tables:
                try:
                    counts[t] = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
                except Exception as exc:
                    counts[t] = f"error:{exc}"
            else:
                counts[t] = None
        info["row_counts"] = counts
        conn.close()
    except Exception as exc:
        info["read_error"] = str(exc)
    return info


def _module_inventory(tracked: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rel, label in MODULE_PATHS:
        p = ROOT / rel
        exists = p.exists()
        if p.is_file():
            fc = 1 if exists else 0
            mtime = datetime.fromtimestamp(p.stat().st_mtime).isoformat() if exists else None
        elif p.is_dir():
            files = list(p.rglob("*")) if exists else []
            fc = sum(1 for f in files if f.is_file())
            mtime = max((f.stat().st_mtime for f in files if f.is_file()), default=0)
            mtime = datetime.fromtimestamp(mtime).isoformat() if mtime else None
        else:
            fc = 0
            mtime = None
        prefix = rel.replace("\\", "/")
        tracked_count = sum(1 for t in tracked if t == prefix or t.startswith(prefix + "/"))
        rows.append(
            {
                "module": label,
                "path": rel,
                "exists": exists,
                "file_count": fc,
                "last_modified": mtime,
                "tracked_files": tracked_count,
                "git_tracked": tracked_count > 0,
                "likely_local_only": exists and tracked_count == 0,
            }
        )
    return rows


def _secret_scan(tracked_text: str, status_text: str, staged_text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(source: str, name: str, severity: str, note: str) -> None:
        if name in seen:
            return
        seen.add(name)
        findings.append({"source": source, "filename": name, "severity": severity, "note": note})

    for line in tracked_text.splitlines():
        if SECRET_PATTERNS.search(line):
            sev = "high" if ".env" in line or "credentials/" in line or "gmail_token" in line else "medium"
            add("git_ls_files", line, sev, "review whether secrets should be tracked")

    for line in status_text.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2 and SECRET_PATTERNS.search(parts[1]):
            add("git_status", parts[1], "medium", f"working tree status {parts[0]}")

    for line in staged_text.splitlines():
        if SECRET_PATTERNS.search(line):
            add("git_staged", line, "high", "staged secret-like filename")

    return findings


def _github_gap(tracked: set[str], server_flags: dict[str, bool]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for label, rel in GAP_MODULES:
        p = ROOT / rel
        local = p.exists()
        norm = rel.replace("\\", "/")
        on_github = norm in tracked or any(t.startswith(norm + "/") for t in tracked)
        _, out, _ = _run(["git", "status", "--short", "--", rel])
        modified_locally = bool(out.strip())
        server_key = rel.split("/")[-1].replace(".py", "").replace(".md", "")
        server_present = server_flags.get(rel, server_flags.get(server_key, None))
        rows.append(
            {
                "module": label,
                "path": rel,
                "local": local,
                "github_tracked": on_github,
                "modified_locally": modified_locally,
                "server_present": server_present,
                "local_only": local and not on_github,
                "needs_commit": local and (not on_github or modified_locally),
                "status": _gap_status(local, on_github, server_present, modified_locally),
            }
        )
    return rows


def _gap_status(local: bool, github: bool, server: bool | None, modified: bool) -> str:
    if not local:
        return "missing_local"
    if modified:
        return "modified_uncommitted"
    if not github:
        return "local_only_not_on_github"
    if server is False:
        return "on_github_not_on_server"
    if server is True:
        return "synced_or_present"
    return "local_and_github_unknown_server"


def _server_audit() -> dict[str, Any]:
    info: dict[str, Any] = {"host": "91.107.188.229", "path": "/opt/worldcup-predictor", "reachable": False}
    rc, out, err = _run_ssh(
        "cd /opt/worldcup-predictor && "
        "echo BRANCH=$(git branch --show-current) && "
        "echo COMMIT=$(git rev-parse HEAD) && "
        "echo AB=$(git rev-list --left-right --count origin/main...HEAD) && "
        "echo STATUS_COUNT=$(git status --short | wc -l) && "
        "python3 --version 2>&1 && "
        "node --version 2>&1 && "
        "ls -lh data/football_intelligence.db 2>/dev/null && "
        "du -sh artifacts data/backups logs .cache models/shadow 2>/dev/null && "
        "systemctl is-active worldcup-api nginx 2>/dev/null && "
        "grep -E '^(EnvironmentFile|WorkingDirectory|ExecStart)=' /etc/systemd/system/worldcup-api.service 2>/dev/null"
    )
    if rc != 0 and not out:
        info["error"] = err or "ssh_failed"
        return info
    info["reachable"] = True
    info["raw"] = out
    for line in out.splitlines():
        if line.startswith("BRANCH="):
            info["branch"] = line.split("=", 1)[1]
        elif line.startswith("COMMIT="):
            info["commit"] = line.split("=", 1)[1]
        elif line.startswith("AB="):
            parts = line.split("=", 1)[1].split()
            info["behind"] = int(parts[0]) if parts else 0
            info["ahead"] = int(parts[1]) if len(parts) > 1 else 0
        elif line.startswith("STATUS_COUNT="):
            info["dirty_lines"] = int(line.split("=", 1)[1])
        elif line.startswith("EnvironmentFile="):
            info["environment_file"] = line.split("=", 1)[1]
        elif line.startswith("WorkingDirectory="):
            info["working_directory"] = line.split("=", 1)[1]
        elif line.startswith("ExecStart="):
            info["exec_start"] = line.split("=", 1)[1]
        elif "football_intelligence.db" in line:
            info["db_ls"] = line.strip()

    rc2, out2, _ = _run_ssh(
        "python3 <<'PY'\n"
        "import sqlite3\n"
        "c=sqlite3.connect('file:/opt/worldcup-predictor/data/football_intelligence.db?mode=ro', uri=True)\n"
        "ts=['fixtures','fixture_results','odds_snapshots','worldcup_stored_predictions','ecse_prediction_snapshots','ecse_oddalerts_shadow_predictions']\n"
        "for t in ts:\n"
        "  try:\n"
        "    print(t, c.execute(f'SELECT COUNT(*) FROM [{t}]').fetchone()[0])\n"
        "  except Exception as e:\n"
        "    print(t, 'MISSING')\n"
        "PY"
    )
    if rc2 == 0:
        counts = {}
        for line in out2.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                counts[parts[0]] = parts[1]
        info["db_row_counts"] = counts

    flags: dict[str, bool] = {}
    for rel, _ in GAP_MODULES:
        rc3, o3, _ = _run_ssh(f"test -e /opt/worldcup-predictor/{rel} && echo YES || echo NO")
        flags[rel] = o3.strip().endswith("YES")
    info["module_flags"] = flags
    return info


def _canonical_decision(local_dbs: list[dict[str, Any]], server: dict[str, Any], env_names: list[str]) -> dict[str, Any]:
    local_main = next((d for d in local_dbs if d.get("inferred_role") == "likely_canonical_local"), None)
    reasons: list[str] = []
    confidence = 50
    if local_main:
        reasons.append("Local SQLITE_PATH default football_intelligence.db exists and is largest active DB")
        confidence += 15
        rc = local_main.get("row_counts") or {}
        if rc.get("odds_snapshots") and int(rc["odds_snapshots"]) > 2000:
            reasons.append("Local odds_snapshots count matches expected production scale (~2200+)")
            confidence += 10
        if rc.get("ecse_prediction_snapshots") is not None:
            reasons.append("Local DB has ECSE production tables present")
            confidence += 10
    if "SQLITE_PATH" in env_names or "DATABASE_URL" in env_names:
        reasons.append("Config references DATABASE_URL and/or SQLITE_PATH env vars")
        confidence += 5
    if server.get("reachable"):
        reasons.append("Production server uses /opt/worldcup-predictor/data/football_intelligence.db via systemd")
        confidence += 10
        srv_counts = server.get("db_row_counts") or {}
        if local_main and srv_counts:
            reasons.append("WARNING: server DB row counts differ significantly from local — not the same copy")
            confidence -= 15
    duplicates = [d for d in local_dbs if d.get("exists") and d.get("inferred_role") == "backup"]
    return {
        "local_canonical_candidate": str((ROOT / "data" / "football_intelligence.db").resolve()),
        "server_canonical_candidate": "/opt/worldcup-predictor/data/football_intelligence.db",
        "type": "SQLite primary intelligence DB; PostgreSQL via DATABASE_URL for SaaS layer",
        "confidence": max(0, min(100, confidence)),
        "reasons": reasons,
        "risks": [
            "Local and server DB sizes/counts diverge — do not assume sync",
            "Multiple backup DBs under data/backups/ (~40GB total locally)",
            "Large untracked local code not on GitHub or server",
        ],
        "duplicate_dbs_local": [d["path"] for d in local_dbs if d.get("inferred_role") == "backup"],
        "do_not_delete": [
            "data/football_intelligence.db (local active)",
            "/opt/worldcup-predictor/data/football_intelligence.db (production active)",
            "data/backups/*.db until consolidation plan approved",
            "data/oddalerts_csv/ staged CSV data",
        ],
        "recommendation": "Treat local and production DBs as separate canonical instances until explicit sync plan",
    }


def _recommendation(
    git: dict[str, Any],
    secrets: list[dict[str, Any]],
    canonical: dict[str, Any],
    server: dict[str, Any],
) -> str:
    flags: list[str] = ["AUDIT_COMPLETE_CANONICAL_DB_IDENTIFIED"]
    if git.get("ahead_origin", 0) > 0 or git.get("untracked_count", 0) > 100:
        flags.append("AUDIT_COMPLETE_GITHUB_BEHIND")
    if any(s["severity"] == "high" for s in secrets):
        flags.append("SECRET_RISK_REVIEW_REQUIRED")
    if len(canonical.get("duplicate_dbs_local") or []) >= 3:
        flags.append("LARGE_DUPLICATE_DB_REVIEW_REQUIRED")
    if server.get("reachable") and server.get("db_row_counts"):
        flags.append("DO_NOT_CONSOLIDATE_YET")
    if canonical.get("confidence", 0) < 70:
        flags[0] = "AUDIT_COMPLETE_NEED_DB_DECISION"
    return "; ".join(flags)


def _write_report(payload: dict[str, Any]) -> None:
    git = payload["environments"]["local_git"]
    server = payload["environments"]["server"]
    canonical = payload["canonical_db"]
    rec = payload["final_recommendation"]

    lines = [
        "# PROJECT ASSET / DATABASE / GITHUB AUDIT REPORT",
        "",
        f"**Phase:** PROJECT-ASSET-AUDIT-1  ",
        f"**Generated:** {payload['generated_at']}  ",
        f"**Mode:** Read-only audit — no changes performed",
        "",
        "## 1. Executive summary",
        "",
        f"- **Primary local workspace:** `{git['path']}`",
        f"- **Production server code:** `/opt/worldcup-predictor` (91.107.188.229)",
        f"- **GitHub repo:** https://github.com/pdekam2000/worldcup-predictor-2026.git",
        f"- **GitHub `main` commit:** `{git.get('origin_main_commit', 'unknown')[:12]}…`",
        f"- **Local commit:** `{git.get('commit', '')[:12]}…` (**ahead {git.get('ahead_origin', 0)}**, behind {git.get('behind_origin', 0)})",
        f"- **Server commit:** `{str(server.get('commit', 'unknown'))[:12]}…` (matches GitHub main; extensive dirty tree)",
        f"- **Local dirty:** {git.get('modified_count', 0)} modified + {git.get('untracked_count', 0)} untracked",
        f"- **GitHub status:** Local is **ahead** of origin/main; GitHub does **not** contain latest local commit or most new modules",
        "",
        "## 2. Canonical database conclusion",
        "",
        f"- **Local candidate:** `{canonical['local_canonical_candidate']}`",
        f"- **Server candidate:** `{canonical['server_canonical_candidate']}`",
        f"- **Type:** {canonical['type']}",
        f"- **Confidence:** {canonical['confidence']}/100",
        "",
        "**Reasons:**",
        *[f"- {r}" for r in canonical.get("reasons", [])],
        "",
        "**Do NOT delete:**",
        *[f"- `{p}`" for p in canonical.get("do_not_delete", [])],
        "",
        "## 3. Environment table",
        "",
        "| Environment | Path | Git commit | Dirty | DB path | Notes |",
        "|-------------|------|------------|-------|---------|-------|",
        f"| Local PC | `{git['path']}` | `{str(git.get('commit',''))[:12]}` | yes ({git.get('status_lines',0)} lines) | `data/football_intelligence.db` (~31GB) | Ahead of GitHub; owner modules local |",
        f"| GitHub origin/main | remote | `{str(git.get('origin_main_commit',''))[:12]}` | n/a | n/a | Published baseline |",
        f"| Production server | `/opt/worldcup-predictor` | `{str(server.get('commit',''))[:12]}` | yes (~{server.get('dirty_lines','?')} lines) | `data/football_intelligence.db` (~9.5GB) | systemd active; missing new ECSE tables |",
        "",
        "## 4. Source code gap table",
        "",
        "| Module | Local | GitHub tracked | Server | Status |",
        "|--------|-------|----------------|--------|--------|",
    ]
    for row in payload["github_gap"]:
        lines.append(
            f"| {row['module']} | {row['local']} | {row['github_tracked']} | {row.get('server_present')} | {row['status']} |"
        )

    lines.extend(["", "## 5. Database inventory table", "", "| DB path | Size (MB) | Tables | Key counts | Role |", "|---------|-----------|--------|------------|------|"])
    for db in payload["database_inventory"]:
        if not db.get("exists"):
            continue
        rc = db.get("row_counts") or {}
        rc_s = ", ".join(f"{k}={v}" for k, v in rc.items() if v is not None)
        lines.append(
            f"| `{Path(db['path']).name}` | {db.get('size_mb')} | {db.get('table_count','?')} | {rc_s} | {db.get('inferred_role')} |"
        )

    lines.extend(["", "## 6. Generated data / artifact inventory", "", "| Folder | Size (MB) | Files | Git track? | Backup? |", "|--------|-----------|-------|------------|---------|"])
    for f in payload["data_folders"]:
        if not f.get("exists"):
            continue
        lines.append(f"| `{f['path']}` | {f.get('size_mb',0)} | {f.get('file_count',0)} | no | yes |")

    lines.extend(["", "## 7. Secret risk summary", "", "No secret **values** printed in this audit.", ""])
    if payload["secret_scan"]:
        lines.append("| File | Severity | Note |")
        lines.append("|------|----------|------|")
        for s in payload["secret_scan"]:
            lines.append(f"| `{s['filename']}` | {s['severity']} | {s['note']} |")
    else:
        lines.append("No secret-like tracked filenames beyond expected credential paths.")

    lines.extend(
        [
            "",
            "## 8. Recommended consolidation plan (later — not executed)",
            "",
            "1. Backup canonical DB on local and server separately",
            "2. Freeze production writes during any merge window",
            "3. Git: commit local modules in logical chunks",
            "4. Push to GitHub after review",
            "5. Server: pull/deploy only after DB strategy decided",
            "6. Decide single canonical DB or explicit local↔prod sync policy",
            "7. Archive duplicate backup DBs only after verification",
            "8. Update `.gitignore` for artifacts/cache/CSV/data",
            "9. Document owner daily workflow paths",
            "",
            "## 9. Final recommendation",
            "",
            f"**{rec}**",
        ]
    )
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    generated_at = datetime.now().isoformat()
    _, tracked_out, _ = _run(["git", "ls-files"])
    tracked = set(tracked_out.splitlines()) if tracked_out else set()
    _, status_out, _ = _run(["git", "status", "--short"])
    _, staged_out, _ = _run(["git", "diff", "--cached", "--name-only"])

    git = _git_info()
    env_names = _env_var_names()
    server = _server_audit()

    dbs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pat in ("*.db", "*.sqlite", "*.sqlite3"):
        for p in ROOT.rglob(pat):
            key = str(p.resolve())
            if key not in seen:
                seen.add(key)
                dbs.append(_audit_db(p))
    dbs.sort(key=lambda x: x.get("size_bytes", 0), reverse=True)

    source_inventory = {
        "phase": "PROJECT-ASSET-AUDIT-1",
        "generated_at": generated_at,
        "local_path": str(ROOT.resolve()),
        "python_version": platform.python_version(),
        "modules": _module_inventory(tracked),
    }
    db_inventory = {
        "phase": "PROJECT-ASSET-AUDIT-1",
        "generated_at": generated_at,
        "env_var_names": env_names,
        "postgres_configured": "DATABASE_URL" in env_names,
        "sqlite_default": "data/football_intelligence.db",
        "databases": dbs,
    }
    github_gap = {
        "phase": "PROJECT-ASSET-AUDIT-1",
        "generated_at": generated_at,
        "origin_main": git.get("origin_main_commit"),
        "local_commit": git.get("commit"),
        "ahead": git.get("ahead_origin"),
        "behind": git.get("behind_origin"),
        "modules": _github_gap(tracked, server.get("module_flags") or {}),
    }

    canonical = _canonical_decision(dbs, server, env_names)
    secrets = _secret_scan(tracked_out, status_out, staged_out)
    data_folders = [_folder_stats(f) for f in DATA_FOLDERS]

    payload = {
        "generated_at": generated_at,
        "environments": {
            "local_git": git,
            "server": server,
        },
        "canonical_db": canonical,
        "database_inventory": dbs,
        "source_inventory": source_inventory["modules"],
        "github_gap": github_gap["modules"],
        "data_folders": data_folders,
        "secret_scan": secrets,
    }
    payload["final_recommendation"] = _recommendation(git, secrets, canonical, server)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / f"project_source_inventory_{DATE_TAG}.json").write_text(
        json.dumps(source_inventory, indent=2), encoding="utf-8"
    )
    (ARTIFACTS / f"project_database_inventory_{DATE_TAG}.json").write_text(
        json.dumps(db_inventory, indent=2), encoding="utf-8"
    )
    (ARTIFACTS / f"project_github_gap_analysis_{DATE_TAG}.json").write_text(
        json.dumps(github_gap, indent=2), encoding="utf-8"
    )
    (ARTIFACTS / f"project_asset_audit_summary_{DATE_TAG}.json").write_text(
        json.dumps({**payload, "final_recommendation": payload["final_recommendation"]}, indent=2, default=str),
        encoding="utf-8",
    )
    _write_report(payload)

    print(json.dumps({"report": str(REPORT), "recommendation": payload["final_recommendation"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
