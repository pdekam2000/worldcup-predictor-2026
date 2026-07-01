#!/usr/bin/env python3
"""PHASE CODEBASE-CONSOLIDATION-1 — Local → GitHub safe source batches."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_RE = re.compile(
    r"(^|/)(credentials/|\.env$|\.env\.|data/|artifacts/|reports/|models/|\.cache/|backups/)|"
    r"\.(db|sqlite|sqlite3|csv|jsonl|parquet|pkl|joblib|gz|zip)$|"
    r"gmail_token|gmail_oauth_client|\.gmail_token",
    re.I,
)

CODE_EXT = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".css", ".scss", ".html", ".sh",
    ".service", ".timer", ".md", ".txt", ".toml", ".yaml", ".yml", ".sql",
}
CODE_NAMES = {
    "Dockerfile", "requirements.txt", "requirements-oddalerts-gmail.txt",
    "requirements-dev.txt", "package.json", "package-lock.json", "alembic.ini",
    "CODEBASE_CONSOLIDATION_PLAN.md", "PROJECT_ASSET_DATABASE_GITHUB_AUDIT_REPORT.md",
}


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True, check=check,
    )


def is_safe_code(path: str) -> bool:
    p = path.replace("\\", "/")
    if FORBIDDEN_RE.search(p):
        return False
    if p.startswith(("deploy_staging_phase40a/", "_pack_", "dist_")):
        return False
    if p.startswith("scripts/_audit") or p.startswith("scripts/_codebase_consolidation"):
        return False
    name = Path(p).name
    if name in CODE_NAMES:
        return True
    ext = Path(p).suffix.lower()
    if ext in CODE_EXT:
        if ext == ".json" and "package" not in name:
            return False
        if name == "^":
            return False
        return True
    return False


def classify_files() -> dict:
    r = run(["git", "status", "--porcelain", "-uall"], check=False)
    entries: list[dict] = []
    for line in r.stdout.splitlines():
        if not line.strip():
            continue
        status, path = line[:2].strip(), line[3:].strip().strip('"')
        if " -> " in path:
            path = path.split(" -> ")[-1]
        safe = is_safe_code(path)
        entries.append({"status": status, "path": path, "safe_code": safe})
    safe = [e for e in entries if e["safe_code"]]
    unsafe = [e for e in entries if not e["safe_code"]]
    return {
        "total": len(entries),
        "safe_code": len(safe),
        "excluded": len(unsafe),
        "safe_files": [e["path"] for e in safe],
        "excluded_sample": [e["path"] for e in unsafe[:50]],
    }


@dataclass
class Batch:
    name: str
    message: str
    paths: list[str]


BATCHES: list[Batch] = [
    Batch(
        "batch0_hygiene",
        "chore(consolidation): expand gitignore and remove tracked secrets from index",
        [".gitignore"],
    ),
    Batch(
        "batch1_db_config",
        "feat(db): migrations repository and settings for owner/ECSE",
        [
            "worldcup_predictor/database/",
            "worldcup_predictor/config/",
        ],
    ),
    Batch(
        "batch2_data_import",
        "feat(data-import): historical CSV OddAlerts and European import pipelines",
        [
            "worldcup_predictor/data_import/",
            "requirements-oddalerts-gmail.txt",
        ],
    ),
    Batch(
        "batch3_research",
        "feat(research): ECSE live/X2/X3/WC OddAlerts shadow and WDE historical",
        [
            "worldcup_predictor/research/",
        ],
    ),
    Batch(
        "batch4_owner",
        "feat(owner): daily predict eval manual exact and euro pipelines",
        [
            "worldcup_predictor/owner_daily/",
            "worldcup_predictor/owner_predict_eval/",
            "worldcup_predictor/owner_manual_exact/",
            "worldcup_predictor/owner/",
        ],
    ),
    Batch(
        "batch5_api_automation",
        "feat(api): owner ECSE routes result refresh and core client updates",
        [
            "worldcup_predictor/api/",
            "worldcup_predictor/automation/",
            "worldcup_predictor/autonomous/",
            "worldcup_predictor/clients/",
            "worldcup_predictor/providers/",
            "worldcup_predictor/quota/",
        ],
    ),
    Batch(
        "batch6_frontend",
        "feat(frontend): Owner Lab ECSE panels and navigation",
        ["base44-d/src/"],
    ),
    Batch(
        "batch7_scripts",
        "feat(scripts): owner ECSE WDE and data pipeline CLI entrypoints",
        ["scripts/"],
    ),
    Batch(
        "batch8_docs",
        "docs: phase reports and consolidation audit artifacts",
        [],  # filled dynamically
    ),
    Batch(
        "batch9_tooling",
        "chore(tooling): project asset audit and consolidation runners",
        [
            "scripts/run_project_asset_audit.py",
            "scripts/validate_project_asset_audit.py",
            "scripts/run_codebase_consolidation_1.py",
            "CODEBASE_CONSOLIDATION_PLAN.md",
            "PROJECT_ASSET_DATABASE_GITHUB_AUDIT_REPORT.md",
        ],
    ),
]


GITIGNORE_ADDITION = """
# CODEBASE-CONSOLIDATION-1 — runtime/generated (code-first)
data/
!data/.gitkeep
artifacts/
logs/
models/
credentials/
*.db
*.sqlite
*.sqlite3
*.csv
*.jsonl
**/.gmail_token.json
**/gmail_oauth_client*.json
backups/
deploy_staging_phase40a/
_pack_*/
dist_*/
scripts/_audit_*.py
scripts/_codebase_consolidation_analyze.py
^
"""


def update_gitignore() -> None:
    path = ROOT / ".gitignore"
    text = path.read_text(encoding="utf-8")
    marker = "# CODEBASE-CONSOLIDATION-1"
    if marker not in text:
        path.write_text(text.rstrip() + "\n" + GITIGNORE_ADDITION, encoding="utf-8")


def reset_to_origin() -> None:
    run(["git", "fetch", "origin", "main"])
    run(["git", "reset", "--mixed", "origin/main"])


def remove_cached_secrets() -> list[str]:
    removed: list[str] = []
    for pattern in ["credentials", "data/backups", "data/imports"]:
        p = ROOT / pattern
        if not p.exists():
            continue
        r = run(["git", "ls-files", pattern], check=False)
        for f in r.stdout.splitlines():
            if f.strip():
                run(["git", "rm", "-r", "--cached", f.strip()], check=False)
                removed.append(f.strip())
    return removed


def expand_batch_paths(batch: Batch, all_safe: set[str]) -> list[str]:
    if batch.name == "batch0_hygiene":
        return [".gitignore"]
    if batch.name == "batch8_docs":
        return sorted(
            p for p in all_safe
            if p.endswith("_REPORT.md") or p.endswith("_TABLES.md")
            or p in ("CODEBASE_CONSOLIDATION_1_REPORT.md",)
        )
    out: list[str] = []
    for prefix in batch.paths:
        prefix = prefix.replace("\\", "/")
        if prefix.endswith("/"):
            out.extend(sorted(p for p in all_safe if p.startswith(prefix)))
        else:
            if prefix in all_safe:
                out.append(prefix)
    return out


def commit_batch(batch: Batch, files: list[str]) -> dict:
    if not files:
        return {"batch": batch.name, "skipped": True, "files": 0}
    for f in files:
        if not is_safe_code(f):
            raise RuntimeError(f"Forbidden file in batch {batch.name}: {f}")
    run(["git", "add", "--"] + files)
    # verify staged
    staged = run(["git", "diff", "--cached", "--name-only"]).stdout.splitlines()
    bad = [f for f in staged if not is_safe_code(f)]
    if bad:
        run(["git", "reset", "HEAD", "--"] + bad, check=False)
        staged = [f for f in staged if f not in bad]
    if not staged:
        return {"batch": batch.name, "skipped": True, "files": 0, "reason": "nothing staged"}
    run(["git", "commit", "-m", batch.message])
    sha = run(["git", "rev-parse", "--short", "HEAD"]).stdout.strip()
    return {"batch": batch.name, "commit": sha, "files": len(staged), "message": batch.message}


def main() -> int:
    dry = "--dry-run" in sys.argv
    report: dict = {
        "phase": "CODEBASE-CONSOLIDATION-1",
        "started_at": datetime.now().isoformat(),
        "dry_run": dry,
    }

    classification = classify_files()
    report["classification"] = classification
    all_safe = set(classification["safe_files"])

    if dry:
        for b in BATCHES:
            files = expand_batch_paths(b, all_safe)
            print(f"{b.name}: {len(files)} files")
        print(json.dumps(report, indent=2))
        return 0

    update_gitignore()
    reset_to_origin()
    removed = remove_cached_secrets()
    report["removed_from_index"] = removed

    # refresh classification after reset
    classification = classify_files()
    all_safe = set(classification["safe_files"])
    report["classification_after_reset"] = classification

    all_safe.add(".gitignore")

    commits: list[dict] = []
    for batch in BATCHES:
        files = expand_batch_paths(batch, all_safe)
        # skip already committed paths
        files = [f for f in files if (ROOT / f).exists() or run(["git", "ls-files", "--error-unmatch", f], check=False).returncode == 0]
        try:
            result = commit_batch(batch, files)
            commits.append(result)
            if result.get("commit"):
                print(f"OK {batch.name} {result['commit']} ({result['files']} files)")
        except Exception as exc:
            commits.append({"batch": batch.name, "error": str(exc)})
            print(f"FAIL {batch.name}: {exc}", file=sys.stderr)

    report["commits"] = commits

    # validators
    validators: list[dict] = []
    compile_r = run(["python", "-m", "compileall", "-q", "worldcup_predictor"], check=False)
    validators.append({"check": "compileall", "passed": compile_r.returncode == 0})
    for script in [
        "scripts/validate_project_asset_audit.py",
    ]:
        if (ROOT / script).exists():
            vr = run(["python", script, "--date", "today"], check=False)
            validators.append({"check": script, "passed": vr.returncode == 0})
    report["validators"] = validators

    # push
    push_r = run(["git", "push", "-u", "origin", "main"], check=False)
    report["push"] = {
        "success": push_r.returncode == 0,
        "stdout": push_r.stdout[-500:] if push_r.stdout else "",
        "stderr": push_r.stderr[-500:] if push_r.stderr else "",
    }
    report["final_commit"] = run(["git", "rev-parse", "HEAD"], check=False).stdout.strip()
    push_r2 = run(["git", "fetch", "origin", "main"], check=False)
    report["origin_main_after"] = run(["git", "rev-parse", "origin/main"], check=False).stdout.strip()

    out = ROOT / "artifacts" / "codebase_consolidation_1_result.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"commits": len(commits), "push": report["push"]["success"]}, indent=2))
    return 0 if report["push"]["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
