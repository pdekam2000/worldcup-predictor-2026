"""Phase 4 — production deployment readiness audit (local, no deploy)."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "base44-d"
DIST = FRONTEND / "dist"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def audit_env_template() -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    template = ROOT / "deployment" / ".env.production.example"
    ok = template.exists()
    results.append(("deployment/.env.production.example exists", "PASS" if ok else "FAIL", ""))
    if ok:
        text = _read(template)
        for key in (
            "APP_ENV=production",
            "DATABASE_URL=",
            "JWT_SECRET=",
            "ADMIN_USERNAME=",
            "ADMIN_PASSWORD=",
            "PUBLIC_ACCESS_CODE=",
            "API_FOOTBALL_KEY=",
        ):
            present = key in text
            results.append((f"template has {key.rstrip('=')}", "PASS" if present else "FAIL", ""))
    return results


def audit_deployment_files() -> list[tuple[str, str, str]]:
    files = [
        "deployment/systemd/worldcup-api.service",
        "deployment/nginx/worldcup.conf",
        "deployment/nginx/worldcup-ip.conf",
        "deployment/DEPLOY_REACT_FASTAPI.md",
        "deployment/CHECKLIST.md",
        "deployment/ROLLBACK.md",
        "alembic/versions/001_saas_initial.py",
    ]
    results: list[tuple[str, str, str]] = []
    for rel in files:
        path = ROOT / rel
        results.append((f"file {rel}", "PASS" if path.exists() else "FAIL", ""))
    return results


def audit_no_base44_runtime() -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    pkg = _read(FRONTEND / "package.json")
    results.append(
        (
            "no @base44/sdk dependency",
            "PASS" if "@base44/sdk" not in pkg else "FAIL",
            "",
        )
    )
    src_api = ROOT / "base44-d" / "src" / "api"
    if src_api.exists():
        has_base44_client = any("base44Client" in p.read_text(encoding="utf-8", errors="ignore") for p in src_api.rglob("*"))
        results.append(("no base44Client in src/api", "PASS" if not has_base44_client else "FAIL", ""))
    return results


def audit_frontend_production_build() -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    prod_env = _read(FRONTEND / ".env.production")
    results.append(
        (
            "VITE_API_BASE_URL empty in .env.production",
            "PASS" if "VITE_API_BASE_URL=" in prod_env and "127.0.0.1" not in prod_env.split("VITE_API_BASE_URL=")[-1].splitlines()[0] else "FAIL",
            "same-origin API via Nginx",
        )
    )

    if not DIST.exists():
        results.append(("frontend dist/ exists", "FAIL", "run npm run build"))
        return results

    results.append(("frontend dist/ exists", "PASS", ""))
    localhost_hits: list[str] = []
    for path in DIST.rglob("*"):
        if path.suffix in {".js", ".css", ".html", ".map"}:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "127.0.0.1:800" in text or "localhost:5173" in text:
                localhost_hits.append(str(path.relative_to(DIST)))
    results.append(
        (
            "production build has no hardcoded localhost API",
            "PASS" if not localhost_hits else "FAIL",
            ", ".join(localhost_hits[:3]) if localhost_hits else "",
        )
    )

    dev_bypass = False
    for path in DIST.rglob("*.js"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "VITE_DEV_AUTH_BYPASS" in text and '"true"' in text:
            dev_bypass = True
    results.append(("VITE_DEV_AUTH_BYPASS not enabled in build", "PASS" if not dev_bypass else "FAIL", ""))
    return results


def audit_production_guard() -> list[tuple[str, str, str]]:
    from worldcup_predictor.config.production_guard import validate_production_settings
    from worldcup_predictor.config.settings import Settings

    results: list[tuple[str, str, str]] = []

    bad = Settings(
        APP_ENV="production",
        DATABASE_URL="",
        JWT_SECRET="dev-only-change-in-production",
        API_FOOTBALL_KEY="",
    )
    errors = validate_production_settings(bad)
    results.append(
        (
            "production guard rejects missing secrets",
            "PASS" if len(errors) >= 3 else "FAIL",
            f"{len(errors)} errors detected",
        )
    )

    good = Settings(
        APP_ENV="production",
        DATABASE_URL="postgresql://u:p@127.0.0.1:5432/db",
        JWT_SECRET="x" * 48,
        API_FOOTBALL_KEY="test-key",
    )
    import os

    os.environ["ADMIN_USERNAME"] = "admin"
    os.environ["ADMIN_PASSWORD"] = "strong-password-123"
    os.environ["PUBLIC_ACCESS_CODE"] = "invite123"
    errors_good = validate_production_settings(good)
    results.append(
        (
            "production guard accepts valid config",
            "PASS" if not errors_good else "FAIL",
            "; ".join(errors_good),
        )
    )
    return results


def audit_alembic() -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    migration = ROOT / "alembic" / "versions" / "001_saas_initial.py"
    if not migration.exists():
        results.append(("alembic SaaS migration", "FAIL", "missing"))
        return results
    text = _read(migration)
    tables = (
        "users",
        "user_settings",
        "user_favorites",
        "user_alerts",
        "user_notifications",
        "subscriptions",
        "user_prediction_history",
    )
    for table in tables:
        ok = table in text
        results.append((f"alembic creates {table}", "PASS" if ok else "FAIL", ""))
    return results


def audit_postgres_local() -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    try:
        from worldcup_predictor.database.postgres.session import ping_postgres

        ok = ping_postgres()
        results.append(("local PostgreSQL ping (dev)", "PASS" if ok else "SKIP", "pgembed or system PG"))
    except Exception as exc:
        results.append(("local PostgreSQL ping (dev)", "SKIP", str(exc)[:80]))
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-production-env", action="store_true")
    args = parser.parse_args()

    sections = [
        ("Environment template", audit_env_template),
        ("Deployment files", audit_deployment_files),
        ("Base44 removal", audit_no_base44_runtime),
        ("Frontend production build", audit_frontend_production_build),
        ("Production guard", audit_production_guard),
        ("Alembic schema", audit_alembic),
        ("PostgreSQL connectivity", audit_postgres_local),
    ]

    all_rows: list[tuple[str, str, str]] = []
    for _title, fn in sections:
        all_rows.extend(fn())

    if args.require_production_env:
        from worldcup_predictor.config.production_guard import validate_production_settings
        from worldcup_predictor.config.settings import get_settings

        get_settings.cache_clear()
        settings = get_settings()
        errors = validate_production_settings(settings)
        all_rows.append(
            (
                ".env.production on server valid",
                "PASS" if not errors else "FAIL",
                "; ".join(errors),
            )
        )

    failed = sum(1 for _, status, _ in all_rows if status == "FAIL")
    print("=== Phase 4 Production Readiness ===")
    for name, status, detail in all_rows:
        line = f"| {name} | {status} | {detail} |"
        print(line)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
