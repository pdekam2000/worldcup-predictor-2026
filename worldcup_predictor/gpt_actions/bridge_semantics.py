"""GPT Actions bridge semantics — WDE decision parity and prediction report classification."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

from worldcup_predictor.config.env_loading import project_root
from worldcup_predictor.owner_daily.constants import REPORTS_DIR

ReportType = Literal[
    "PREDICTION_DAILY",
    "PREDICTION_MATCH",
    "PREDICTION_COMBO",
    "PREDICTION_OWNER",
    "FORENSIC",
    "VALIDATION",
    "GUIDE",
    "DEPLOYMENT",
    "RESEARCH",
    "UNKNOWN",
]

_PREDICTION_PREFIXES = (
    "TODAY_",
    "DAILY_",
    "TRI_COMBO_",
    "OWNER_DAILY_",
    "CONTROLLED_",
    "NEXT_",
    "WC_TODAY_",
)

_PREDICTION_MARKERS = (
    "_PREDICTION",
    "_PREDICTIONS_",
    "_ENDRESULT_",
    "_OWNER_PREDICTION",
    "_OWNER_LIST",
    "_OWNER_TRACKER",
)

_EXCLUDE_MARKERS = (
    "PHASE_",
    "_GUIDE",
    "_AUDIT",
    "_IMPLEMENTATION_REPORT",
    "_FORENSIC",
    "_VALIDATION",
    "CONNECTION_GUIDE",
    "DEPLOYMENT",
    "RUNBOOK",
    "DOMAIN_EXPANSION",
    "MASTER_DAILY_ENDRESULT_DOMAIN",
)

_VALID_1X2 = frozenset({"home_win", "draw", "away_win"})


def _normalize_1x2(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).lower().strip().replace(" ", "_")
    mapped = {"home": "home_win", "away": "away_win", "1": "home_win", "x": "draw", "2": "away_win"}.get(text)
    if mapped:
        return mapped
    return text if text in _VALID_1X2 else None


def _probability_argmax(h: Any, d: Any, a: Any) -> str | None:
    if h is None or d is None or a is None:
        return None
    try:
        sides = {"home_win": float(h), "draw": float(d), "away_win": float(a)}
    except (TypeError, ValueError):
        return None
    return max(sides, key=sides.get)


def extract_wde_semantics(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Canonical WDE decision layer vs probability argmax — never collapse them."""
    if not payload:
        return {
            "decision_pick": None,
            "effective_pick": None,
            "probability_argmax": None,
            "decision_source": None,
            "home_prob": None,
            "draw_prob": None,
            "away_prob": None,
            "confidence": None,
            "model_version": None,
            "btts": {},
            "ou25": {},
        }

    probs = payload.get("probabilities") or {}
    btts = probs.get("btts") or (payload.get("extended_markets") or {}).get("btts") or {}
    ou25 = probs.get("over_under_2_5") or (payload.get("detailed_markets") or {}).get("over_under_25") or {}
    h = probs.get("home_win") or probs.get("home")
    d = probs.get("draw")
    a = probs.get("away_win") or probs.get("away")

    effective = payload.get("effective_1x2") if isinstance(payload.get("effective_1x2"), dict) else {}
    one_x_two = payload.get("one_x_two") if isinstance(payload.get("one_x_two"), dict) else {}
    dm = payload.get("detailed_markets") if isinstance(payload.get("detailed_markets"), dict) else {}
    match_winner = dm.get("match_winner") if isinstance(dm.get("match_winner"), dict) else {}

    decision_pick = (
        _normalize_1x2(effective.get("pick"))
        or _normalize_1x2(one_x_two.get("selection"))
        or _normalize_1x2(payload.get("prediction") if isinstance(payload.get("prediction"), str) else None)
        or _normalize_1x2(match_winner.get("selection"))
        or _normalize_1x2(payload.get("predicted_1x2"))
    )
    effective_pick = _normalize_1x2(effective.get("pick")) or decision_pick
    probability_argmax = _probability_argmax(h, d, a)

    decision_source = payload.get("decision_source")
    if not decision_source and isinstance(effective, dict):
        decision_source = effective.get("decision_source") or effective.get("source")

    conf = payload.get("confidence_score") or payload.get("confidence")
    if conf is not None:
        try:
            cf = float(conf)
            confidence = round(cf, 2) if cf > 1 else round(cf * 100, 2)
        except (TypeError, ValueError):
            confidence = None
    else:
        confidence = None

    def _pct(value: Any) -> float | None:
        if value is None:
            return None
        try:
            v = float(value)
        except (TypeError, ValueError):
            return None
        return round(v * 100, 2) if v <= 1 else round(v, 2)

    return {
        "decision_pick": decision_pick,
        "effective_pick": effective_pick,
        "probability_argmax": probability_argmax,
        "decision_source": str(decision_source) if decision_source else None,
        "home_prob": _pct(h),
        "draw_prob": _pct(d),
        "away_prob": _pct(a),
        "confidence": confidence,
        "model_version": payload.get("model_version") or payload.get("wde_version"),
        "btts": btts if isinstance(btts, dict) else {},
        "ou25": ou25 if isinstance(ou25, dict) else {},
    }


def classify_report_type(path: Path) -> ReportType | None:
    """Return report type or None if file must be excluded from GPT prediction report endpoints."""
    name = path.name.upper()
    if not name.endswith(".MD"):
        return None
    if any(marker in name for marker in _EXCLUDE_MARKERS):
        if "PREDICTION" in name and name.startswith("CONTROLLED_") and "_REPORT" in name:
            pass
        elif "TODAY_" in name and "ENDRESULT" in name:
            pass
        else:
            if name.startswith("PHASE_"):
                return None
            if any(x in name for x in ("_GUIDE", "CONNECTION_GUIDE", "_AUDIT", "_FORENSIC", "_VALIDATION", "DEPLOYMENT", "RUNBOOK")):
                return None

    if name.startswith("TODAY_") and ("PREDICTION" in name or "ENDRESULT" in name):
        return "PREDICTION_DAILY"
    if name.startswith("DAILY_") and "PREDICTION" in name:
        return "PREDICTION_DAILY"
    if name.startswith("WC_TODAY_") or name.startswith("OWNER_DAILY_"):
        return "PREDICTION_OWNER"
    if name.startswith("TRI_COMBO_"):
        return "PREDICTION_COMBO"
    if name.startswith("CONTROLLED_") and ("PREDICTION" in name or "OWNER_LIST" in name or "OWNER_TRACKER" in name):
        return "PREDICTION_MATCH"
    if name.startswith("NEXT_") and "PREDICTION" in name:
        return "PREDICTION_DAILY"
    if any(name.startswith(p) for p in _PREDICTION_PREFIXES) and any(m in name for m in _PREDICTION_MARKERS):
        if name.startswith("TRI_COMBO_"):
            return "PREDICTION_COMBO"
        if name.startswith("CONTROLLED_"):
            return "PREDICTION_MATCH"
        return "PREDICTION_DAILY"

    return None


def _report_search_roots() -> list[Path]:
    roots = [REPORTS_DIR.resolve(), project_root().resolve()]
    seen: set[Path] = set()
    out: list[Path] = []
    for root in roots:
        if root.is_dir() and root not in seen:
            seen.add(root)
            out.append(root)
    return out


def iter_prediction_reports() -> list[Path]:
    """All legitimate prediction markdown reports, newest mtime first."""
    candidates: list[Path] = []
    for root in _report_search_roots():
        for path in root.glob("*.md"):
            if classify_report_type(path) is not None:
                candidates.append(path)
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)


def _date_tags(target: date) -> set[str]:
    return {
        target.isoformat(),
        target.strftime("%Y_%m_%d"),
        target.strftime("%Y%m%d"),
    }


def _extract_report_date(path: Path) -> date | None:
    name = path.stem
    for pattern in (
        r"(\d{4})-(\d{2})-(\d{2})",
        r"(\d{4})_(\d{2})_(\d{2})",
        r"(\d{4})(\d{2})(\d{2})",
    ):
        m = re.search(pattern, name)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
    return None


def build_report_response(path: Path, *, max_bytes: int, report_date: str | None = None) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8", errors="replace")
    if len(content.encode("utf-8")) > max_bytes:
        content = content.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore") + "\n...[truncated]"
    rtype = classify_report_type(path)
    extracted = _extract_report_date(path)
    return {
        "found": True,
        "report_name": path.name,
        "report_date": report_date or (extracted.isoformat() if extracted else path.stem),
        "content": content,
        "generated_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
        "report_type": rtype,
        "source": "prediction_report",
    }


def latest_prediction_report_payload(*, max_bytes: int) -> dict[str, Any]:
    files = iter_prediction_reports()
    if not files:
        return {
            "found": False,
            "report_name": None,
            "report_date": None,
            "content": "",
            "generated_at": None,
            "report_type": None,
            "source": None,
        }
    return build_report_response(files[0], max_bytes=max_bytes)


def prediction_report_by_date_payload(target: date, *, max_bytes: int) -> dict[str, Any]:
    tags = _date_tags(target)
    matches: list[tuple[date, Path]] = []
    for path in iter_prediction_reports():
        extracted = _extract_report_date(path)
        if extracted == target or any(tag in path.name for tag in tags):
            matches.append((datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).date(), path))
    if not matches:
        return {
            "found": False,
            "report_date": target.isoformat(),
            "report_name": None,
            "content": "",
            "generated_at": None,
            "report_type": None,
            "source": None,
        }
    matches.sort(key=lambda x: (x[0], x[1].stat().st_mtime), reverse=True)
    best = matches[0][1]
    return build_report_response(best, max_bytes=max_bytes, report_date=target.isoformat())
