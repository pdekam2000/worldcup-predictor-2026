"""Professional Match Report Exporter V2 — Phase 47."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.export.match_report_collector import (
    collect_match_report_bundle,
    collect_match_report_bundle_for_fixture,
)
from worldcup_predictor.export.models import ExportFormat, ExportLocale, ExportResult, MatchReportBundle
from worldcup_predictor.export.report_i18n import report_t

DEFAULT_REPORTS_DIR = Path("reports/match_reports")


class ProfessionalMatchReportExporterV2:
    """Generate and save professional match reports — export only, no scoring changes."""

    def __init__(self, output_dir: Path | str | None = None) -> None:
        self._output_dir = Path(output_dir or DEFAULT_REPORTS_DIR)

    def export(
        self,
        bundle: MatchReportBundle,
        *,
        formats: tuple[ExportFormat, ...] = ("markdown", "json", "summary"),
    ) -> ExportResult:
        """Write report files — never raises."""
        result = ExportResult(fixture_id=bundle.fixture_id, locale=bundle.locale)
        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            result.errors.append(f"Could not create output directory: {exc}")
            return result

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        fid = bundle.fixture_id or 0
        base = f"fixture_{fid}_{ts}"

        if "markdown" in formats:
            path = self._output_dir / f"{base}.md"
            try:
                path.write_text(self.render_markdown(bundle), encoding="utf-8")
                result.markdown_path = str(path.resolve())
            except OSError as exc:
                result.errors.append(f"Markdown write failed: {exc}")

        if "json" in formats:
            path = self._output_dir / f"{base}.json"
            try:
                path.write_text(
                    json.dumps(bundle.to_dict(), indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                result.json_path = str(path.resolve())
            except OSError as exc:
                result.errors.append(f"JSON write failed: {exc}")

        if "summary" in formats:
            path = self._output_dir / f"{base}_summary.txt"
            try:
                path.write_text(self.render_summary(bundle), encoding="utf-8")
                result.summary_path = str(path.resolve())
            except OSError as exc:
                result.errors.append(f"Summary write failed: {exc}")

        return result

    def export_fixture(
        self,
        settings: Any,
        fixture_id: int,
        *,
        locale: ExportLocale = "en",
        competition_key: str = "world_cup_2026",
        formats: tuple[ExportFormat, ...] = ("markdown", "json", "summary"),
    ) -> tuple[MatchReportBundle, ExportResult]:
        bundle = collect_match_report_bundle_for_fixture(
            settings,
            fixture_id,
            competition_key=competition_key,
            locale=locale,
        )
        return bundle, self.export(bundle, formats=formats)

    @staticmethod
    def render_markdown(bundle: MatchReportBundle) -> str:
        loc = bundle.locale
        lines: list[str] = [
            f"# {report_t('report.title', loc)}",
            "",
            f"**{report_t('report.match', loc)}:** {bundle.match_name}  ",
            f"**{report_t('report.fixture_id', loc)}:** {bundle.fixture_id}  ",
        ]
        if bundle.kickoff_utc:
            lines.append(f"**{report_t('report.kickoff', loc)}:** {bundle.kickoff_utc}  ")
        if bundle.stage:
            lines.append(f"**{report_t('report.stage', loc)}:** {bundle.stage}  ")
        lines.append(f"**Generated:** {bundle.generated_at}  ")
        lines.append("")

        pred = bundle.prediction or {}
        lines.extend(
            [
                f"## {report_t('report.prediction', loc)}",
                "",
                f"- **{report_t('report.one_x_two', loc)}:** {pred.get('one_x_two', '—')} "
                f"({pred.get('one_x_two_probability', '—')})",
                f"- **{report_t('report.over_under', loc)}:** {pred.get('over_under', '—')} "
                f"({pred.get('over_under_probability', '—')})",
                f"- **{report_t('report.confidence', loc)}:** {pred.get('confidence_score', '—')}/100 "
                f"({pred.get('confidence_level', '—')})",
                f"- **{report_t('report.scoreline', loc)}:** {pred.get('scoreline', '—')}",
                f"- **{report_t('report.no_bet', loc)}:** {pred.get('no_bet_flag', '—')}",
                "",
            ]
        )
        fg_team = pred.get("first_goal_team")
        fg_band = pred.get("first_goal_minute_band")
        if fg_team or fg_band:
            lines.extend(
                [
                    f"## {report_t('report.first_goal', loc)}",
                    "",
                    f"- **{report_t('report.first_goal_team', loc)}:** {fg_team or '—'}",
                    f"- **{report_t('report.first_goal_band', loc)}:** {fg_band or '—'}",
                    f"- **{report_t('report.first_goal_confidence', loc)}:** {pred.get('first_goal_confidence', '—')}/100",
                    "",
                ]
            )
            for row in pred.get("first_goal_scorer_candidates") or []:
                if isinstance(row, dict):
                    name = row.get("player_name") or row.get("player")
                    if name:
                        pos = row.get("position") or ""
                        conf = row.get("confidence") or row.get("score")
                        pos_txt = f", {pos}" if pos else ""
                        conf_txt = f" — {conf}/100" if conf is not None else ""
                        lines.append(f"- Scorer candidate: {name} ({row.get('team', '—')}{pos_txt}){conf_txt}")
            if pred.get("first_goal_data_limitations"):
                lines.append(f"_{pred['first_goal_data_limitations']}_")
            if pred.get("first_goal_disclaimer"):
                lines.append(f"_{pred['first_goal_disclaimer']}_")
            lines.append("")

        fusion = bundle.fusion or {}
        if fusion:
            lines.extend(
                [
                    f"## {report_t('report.fusion', loc)}",
                    "",
                    fusion.get("final_summary") or report_t("report.unavailable", loc),
                    "",
                    f"- Consensus: {fusion.get('consensus_strength', '—')}/100",
                    f"- Quality: {fusion.get('decision_quality_band', '—')} "
                    f"({fusion.get('decision_quality_score', '—')}/100)",
                    f"- Confidence adj.: {fusion.get('confidence_adjustment', 0):+.2f}",
                    "",
                ]
            )
            if fusion.get("conflict_resolution_summary"):
                lines.append(f"_{fusion['conflict_resolution_summary']}_")
                lines.append("")

        expl = bundle.explainability or {}
        api_ctx = expl.get("api_sports_context") or {}
        if api_ctx.get("api_football_prediction", {}).get("available"):
            ref = api_ctx["api_football_prediction"]
            lines.extend(
                [
                    "## API-Football prediction reference",
                    "",
                    f"- **Model 1X2:** {ref.get('model_one_x_two', '—')}",
                    f"- **API-Football lean:** {ref.get('api_one_x_two_lean', '—')}",
                    f"- **Agreement:** {ref.get('agreement_pct', '—')}%",
                    "_External reference only — does not override model prediction._",
                    "",
                ]
            )
        if api_ctx.get("top_scorers_sample"):
            lines.append("## Tournament top scorers (API-Sports)")
            lines.append("")
            for row in api_ctx["top_scorers_sample"][:5]:
                if isinstance(row, dict):
                    lines.append(
                        f"- {row.get('player', '—')} ({row.get('team', '—')}) — "
                        f"{row.get('goals', 0)} goals"
                    )
            lines.append("")

        if api_ctx.get("player_ratings_sample"):
            lines.append("## Player ratings & chance creation (API-Sports)")
            lines.append("")
            for row in api_ctx["player_ratings_sample"][:5]:
                if isinstance(row, dict):
                    parts = [f"- {row.get('player', '—')} ({row.get('team', '—')})"]
                    if row.get("rating") is not None:
                        parts.append(f"rating {row.get('rating')}")
                    if row.get("assists") is not None:
                        parts.append(f"{row.get('assists')} ast")
                    if row.get("key_passes") is not None:
                        parts.append(f"{row.get('key_passes')} kp")
                    lines.append(" — ".join(parts))
            lines.append("")

        squad_intel = api_ctx.get("squad_intelligence") or {}
        if squad_intel.get("available"):
            lines.append("## Squad depth & experience (Phase 55)")
            lines.append("")
            for side in ("home", "away"):
                block = squad_intel.get(side) or {}
                depth = block.get("bench_depth") or {}
                age = block.get("squad_age_profile") or {}
                if depth.get("available") or age.get("available"):
                    label = side.title()
                    depth_score = depth.get("effective_depth_score", "—")
                    avg_age = age.get("average_age", "—")
                    lines.append(f"- **{label}:** bench depth {depth_score}/100 · avg age {avg_age}")
            lines.append("")

        if expl.get("executive_summary"):
            lines.extend(
                [
                    f"## {report_t('report.executive', loc)}",
                    "",
                    str(expl["executive_summary"]),
                    "",
                ]
            )

        contributions = expl.get("agent_contributions") or []
        if contributions:
            lines.extend([f"## {report_t('report.agents', loc)}", "", "| Agent | Influence | Verdict |", "| --- | ---: | --- |"])
            for row in contributions[:12]:
                if isinstance(row, dict):
                    lines.append(
                        f"| {row.get('label', '—')} | {row.get('influence_pct', 0):.1f}% | {row.get('verdict', '—')} |"
                    )
            lines.append("")

        risk = expl.get("risk_analysis") or {}
        if risk:
            lines.extend([f"## {report_t('report.risk', loc)}", "", f"**Level:** {risk.get('risk_level', '—')}"])
            for item in (risk.get("top_risks") or [])[:8]:
                lines.append(f"- {item}")
            lines.append("")

        conflicts = expl.get("conflicts") or {}
        conflict_list = conflicts.get("conflicts") or []
        fusion_conflicts = fusion.get("conflicts") or []
        if conflict_list or fusion_conflicts:
            lines.extend([f"## {report_t('report.conflicts', loc)}", ""])
            for c in conflict_list[:6]:
                lines.append(f"- {c}")
            for c in fusion_conflicts[:4]:
                if isinstance(c, dict):
                    lines.append(f"- [{c.get('severity', 'medium')}] {c.get('description', '')}")
            lines.append("")

        v2_sections = (
            ("lineup_intelligence_v2", "report.lineup"),
            ("injury_intelligence_v2", "report.injury"),
            ("sharp_money_v2", "report.sharp"),
            ("tournament_v2", "report.tournament"),
            ("elo_strength_v2", "report.elo"),
            ("xg_chance_quality_v2", "report.xg"),
        )
        intel = bundle.intelligence_v2 or {}
        for key, label_key in v2_sections:
            block = intel.get(key) or {}
            summary = block.get("summary") or report_t("report.unavailable", loc)
            status = block.get("status", "unavailable")
            lines.extend(
                [
                    f"## {report_t(label_key, loc)}",
                    "",
                    f"**Status:** {status}",
                    "",
                    summary,
                    "",
                ]
            )

        lines.extend([f"## {report_t('report.disclaimer', loc)}", "", bundle.disclaimer or report_t("report.disclaimer", loc), ""])
        return "\n".join(lines)

    @staticmethod
    def render_summary(bundle: MatchReportBundle) -> str:
        loc = bundle.locale
        pred = bundle.prediction or {}
        fusion = bundle.fusion or {}
        expl = bundle.explainability or {}

        lines = [
            report_t("summary.intro", loc),
            "",
            f"{report_t('report.match', loc)}: {bundle.match_name}",
            f"{report_t('report.fixture_id', loc)}: {bundle.fixture_id}",
        ]
        if bundle.kickoff_utc:
            lines.append(f"{report_t('report.kickoff', loc)}: {bundle.kickoff_utc}")

        lines.extend(
            [
                "",
                f"{report_t('report.one_x_two', loc)}: {pred.get('one_x_two', '—')}",
                f"{report_t('report.over_under', loc)}: {pred.get('over_under', '—')}",
                f"{report_t('report.confidence', loc)}: {pred.get('confidence_score', '—')}/100",
                "",
            ]
        )

        if fusion.get("final_summary"):
            lines.extend([report_t("report.fusion", loc) + ":", fusion["final_summary"], ""])

        if expl.get("executive_summary"):
            lines.extend([report_t("report.executive", loc) + ":", str(expl["executive_summary"]), ""])

        lines.append(report_t("report.disclaimer", loc))
        return "\n".join(lines)


def export_match_report(
    settings: Any,
    fixture_id: int,
    *,
    locale: ExportLocale = "en",
    competition_key: str = "world_cup_2026",
    output_dir: Path | str | None = None,
    formats: tuple[ExportFormat, ...] = ("markdown", "json", "summary"),
) -> ExportResult:
    """Convenience wrapper — never raises."""
    try:
        exporter = ProfessionalMatchReportExporterV2(output_dir=output_dir)
        _, result = exporter.export_fixture(
            settings,
            fixture_id,
            locale=locale,
            competition_key=competition_key,
            formats=formats,
        )
        return result
    except Exception as exc:
        return ExportResult(fixture_id=fixture_id, locale=locale, errors=[str(exc)])
