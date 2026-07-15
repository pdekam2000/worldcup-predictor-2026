"""Daily owner report generation — prematch, postmatch, compact FA summary."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from worldcup_predictor.config.env_loading import project_root
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.forward_evaluation.db import connect_eval_db
from worldcup_predictor.gpt_actions.bridge_semantics import extract_wde_semantics
from worldcup_predictor.owner_daily.pipeline.constants import DAILY_REPORTS_DIR
from worldcup_predictor.owner_daily.report import _load_ecse, _load_wde, build_daily_report
from worldcup_predictor.owner_daily.data_completeness import FixtureCompletenessReport
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture


@dataclass
class DailyPipelineReports:
    prematch_md: Path
    prematch_fa_md: Path
    evaluation_md: Path | None = None
    evaluation_fa_md: Path | None = None
    owner_summary_fa_md: Path | None = None
    json_summary: Path | None = None
    legacy_md: Path | None = None


def _score_topn(scores: list[Any], n: int) -> list[str]:
    out: list[str] = []
    for item in (scores or [])[:n]:
        if isinstance(item, dict):
            out.append(str(item.get("scoreline") or item.get("label") or ""))
        else:
            out.append(str(item))
    while len(out) < n:
        out.append("—")
    return out[:n]


def build_prematch_reports(
    *,
    report_date: str,
    timezone_name: str,
    fixtures: list[DailyFixture],
    eligibility: list[dict[str, Any]],
    completeness: list[FixtureCompletenessReport],
    settings: Settings | None = None,
) -> DailyPipelineReports:
    settings = settings or get_settings()
    conn = connect(settings.sqlite_path)
    DAILY_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    tag = report_date
    md_path = DAILY_REPORTS_DIR / f"{tag}_DAILY_PREDICTIONS.md"
    fa_path = DAILY_REPORTS_DIR / f"{tag}_DAILY_PREDICTIONS_FA.md"

    elig_by_id = {int(r["fixture_id"]): r for r in eligibility}
    lines = [
        f"# Daily Prematch Predictions — {tag}",
        "",
        f"Timezone: **{timezone_name}**",
        "",
        "## Coverage summary",
        "",
        f"- Discovered: **{len(fixtures)}**",
        f"- Eligible / frozen / blocked: see table below",
        "",
        "## All fixtures",
        "",
        "| Kickoff (Vienna) | League | Match | Status | WDE | H/D/A | BTTS | O/U | Top1–Top5 | Quality |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    fa_lines = [
        f"# گزارش پیش‌بینی روزانه — {tag}",
        "",
        "## پیش‌بینی‌های روز",
        "",
        "| ساعت | لیگ | بازی | WDE | BTTS | O/U | Top1 | Top2 | Top3 | Top4 | Top5 | کیفیت |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    blocked_fa: list[str] = ["", "## بازی‌های مسدود یا NO_BET", "", "| ساعت | بازی | وضعیت | دلیل |", "|---|---|---|---|"]

    for fx in fixtures:
        fid = int(fx.provider_fixture_id)
        el = elig_by_id.get(fid, {})
        wde = _load_wde(fid, settings, fx.competition_key)
        ecse = _load_ecse(conn, fid)
        kick = el.get("kickoff_europe_vienna") or fx.kickoff_utc
        status = el.get("lifecycle_status") or "UNKNOWN"
        if not el.get("eligible"):
            blocked_fa.append(
                f"| {kick} | {fx.home_team} vs {fx.away_team} | {status} | {el.get('eligibility_reason', '')} |"
            )
            lines.append(
                f"| {kick} | {fx.competition_key} | {fx.home_team} vs {fx.away_team} | **{status}** | — | — | — | — | — | blocked |"
            )
            continue
        wde_pick = (wde or {}).get("predicted_1x2") or "—"
        probs = "—"
        if wde:
            probs = f"{wde.get('predicted_1x2', '—')}"
        btts = (wde or {}).get("btts_pick") or "—"
        ou = (wde or {}).get("predicted_over_under_2_5") or "—"
        tops = _score_topn((ecse or {}).get("top_5_scores") or [], 5)
        qual = el.get("prediction_completeness") or "—"
        lines.append(
            f"| {kick} | {fx.competition_key} | {fx.home_team} vs {fx.away_team} | {status} | "
            f"{wde_pick} | {probs} | {btts} | {ou} | {' / '.join(tops)} | {qual} |"
        )
        fa_lines.append(
            f"| {kick} | {fx.competition_key} | {fx.home_team} vs {fx.away_team} | {wde_pick} | {btts} | {ou} | "
            f"{tops[0]} | {tops[1]} | {tops[2]} | {tops[3]} | {tops[4]} | {qual} |"
        )

    lines.extend(["", "## Blocked fixtures", ""])
    for row in eligibility:
        if row.get("eligible"):
            continue
        lines.append(
            f"- **{row.get('match')}** — `{row.get('lifecycle_status')}`: {row.get('eligibility_reason')}"
        )

    md_path.write_text("\n".join(lines), encoding="utf-8")
    fa_path.write_text("\n".join(fa_lines + blocked_fa), encoding="utf-8")

    legacy = build_daily_report(
        fixtures,
        completeness,
        target_date=tag,
        timezone_name=timezone_name,
        provider_calls={},
        settings=settings,
    )
    conn.close()
    return DailyPipelineReports(
        prematch_md=md_path,
        prematch_fa_md=fa_path,
        legacy_md=legacy.md_path,
    )


def build_evaluation_reports(
    *,
    report_date: str,
    timezone_name: str,
    settings: Settings | None = None,
) -> DailyPipelineReports | None:
    """Build postmatch evaluation for fixtures on report_date with frozen predictions."""
    settings = settings or get_settings()
    ev = connect_eval_db(project_root())
    prod = connect(settings.sqlite_path)
    DAILY_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    md_path = DAILY_REPORTS_DIR / f"{report_date}_DAILY_EVALUATION.md"
    fa_path = DAILY_REPORTS_DIR / f"{report_date}_DAILY_EVALUATION_FA.md"

    rows = ev.execute(
        """
        SELECT fp.*, me.*
        FROM frozen_predictions fp
        LEFT JOIN market_evaluations me ON me.prediction_id = fp.prediction_id
        WHERE date(fp.kickoff) = date(?)
        ORDER BY fp.kickoff
        """,
        (report_date,),
    ).fetchall()
    if not rows:
        ev.close()
        prod.close()
        return None

    lines = [
        f"# Daily Evaluation — {report_date}",
        "",
        f"Timezone: **{timezone_name}**",
        "",
        "| Match | Result | WDE | FT | BTTS | O/U | Top1 | Top3 | Top5 | ECSE rank |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    stats = {"wde": [0, 0], "btts": [0, 0], "ou": [0, 0], "t1": [0, 0], "t3": [0, 0], "t5": [0, 0]}

    for r in rows:
        row = dict(r)
        fid = int(row["fixture_id"])
        res = prod.execute(
            "SELECT home_goals, away_goals, regulation_home_goals, regulation_away_goals, final_score FROM fixture_results WHERE fixture_id=?",
            (fid,),
        ).fetchone()
        if not res:
            continue
        res = dict(res)
        rh = res.get("regulation_home_goals") if res.get("regulation_home_goals") is not None else res.get("home_goals")
        ra = res.get("regulation_away_goals") if res.get("regulation_away_goals") is not None else res.get("away_goals")
        if rh is None or ra is None:
            continue
        final = f"{int(rh)}-{int(ra)}"
        match = f"{row.get('home_team_name') or '?'} vs {row.get('away_team_name') or '?'}"

        wde_hit = row.get("wde_hit")
        if wde_hit in ("hit", "miss"):
            stats["wde"][1] += 1
            stats["wde"][0] += int(wde_hit == "hit")
        btts_hit = row.get("btts_hit")
        if btts_hit in ("hit", "miss"):
            stats["btts"][1] += 1
            stats["btts"][0] += int(btts_hit == "hit")
        ou_hit = row.get("ou25_hit")
        if ou_hit in ("hit", "miss"):
            stats["ou"][1] += 1
            stats["ou"][0] += int(ou_hit == "hit")
        for key, col in (
            ("t1", "ecse_top1_hit"),
            ("t3", "ecse_top3_hit"),
            ("t5", "ecse_top5_hit"),
        ):
            v = row.get(col)
            if v in ("hit", "miss"):
                stats[key][1] += 1
                stats[key][0] += int(v == "hit")

        lines.append(
            f"| {match} | {final} | {row.get('wde_hit')} | {row.get('ft_marginal_hit')} | "
            f"{row.get('btts_hit')} | {row.get('ou25_hit')} | {row.get('ecse_top1_hit')} | "
            f"{row.get('ecse_top3_hit')} | {row.get('ecse_top5_hit')} | {row.get('actual_score_rank')} |"
        )

    lines.extend(
        [
            "",
            "## Accuracy (evaluated fixtures only; blocked excluded)",
            "",
            f"- WDE: {stats['wde'][0]}/{stats['wde'][1]}",
            f"- BTTS: {stats['btts'][0]}/{stats['btts'][1]}",
            f"- O/U: {stats['ou'][0]}/{stats['ou'][1]}",
            f"- Top1: {stats['t1'][0]}/{stats['t1'][1]}",
            f"- Top3: {stats['t3'][0]}/{stats['t3'][1]}",
            f"- Top5: {stats['t5'][0]}/{stats['t5'][1]}",
        ]
    )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    fa_path.write_text(
        "\n".join(
            [
                f"# ارزیابی روزانه — {report_date}",
                "",
                "\n".join(lines[4:]),
            ]
        ),
        encoding="utf-8",
    )
    ev.close()
    prod.close()
    return DailyPipelineReports(prematch_md=md_path, prematch_fa_md=fa_path, evaluation_md=md_path, evaluation_fa_md=fa_path)


def build_owner_summary_fa(
    *,
    report_date: str,
    eligibility: list[dict[str, Any]],
    stats: dict[str, Any],
) -> Path:
    DAILY_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = DAILY_REPORTS_DIR / f"{report_date}_OWNER_SUMMARY_FA.md"
    blocked = [r for r in eligibility if not r.get("eligible")]
    predicted = [r for r in eligibility if r.get("eligible")]
    lines = [
        f"# خلاصه مالک — {report_date}",
        "",
        "### آمار",
        "",
        f"- کشف‌شده: {stats.get('discovered', len(eligibility))}",
        f"- واجد شرایط: {stats.get('eligible', len(predicted))}",
        f"- Freeze: {stats.get('frozen', 0)}",
        f"- Blocked: {stats.get('blocked', len(blocked))}",
        f"- WDE accuracy: {stats.get('wde_accuracy')}",
        f"- Top5 accuracy: {stats.get('top5_accuracy')}",
        "",
        f"*(جزئیات در {report_date}_DAILY_PREDICTIONS_FA.md)*",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
