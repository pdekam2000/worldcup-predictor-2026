from __future__ import annotations

import sys
from typing import TextIO

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.domain.fixture import Fixture
from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.prediction import MatchPrediction, PredictionPlaceholder
from worldcup_predictor.domain.specialist import MatchSpecialistReport, SpecialistSignal
from worldcup_predictor.i18n.translator import Translator, get_translator
from worldcup_predictor.orchestration.inspect_pipeline import InspectPipeline
from worldcup_predictor.orchestration.pipeline import UpcomingPipeline
from worldcup_predictor.decision.audit_report import PredictionAuditReport
from worldcup_predictor.orchestration.audit_pipeline import AuditPipeline
from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline
from worldcup_predictor.orchestration.specialists_pipeline import SpecialistsPipeline
from worldcup_predictor.schedule.worldcup_schedule_service import WorldCupScheduleService
from worldcup_predictor.backtesting.backtest_runner import BacktestRunner
from worldcup_predictor.backtesting.report_writer import BacktestReportWriter
from worldcup_predictor.backtesting.historical_loader import HistoricalLoader
from worldcup_predictor.calibration.calibration_report import CalibrationReportWriter, CalibrationRunner
from worldcup_predictor.data_import.api_football_historical_importer import ApiFootballHistoricalImporter
from worldcup_predictor.data_import.csv_exporter import CsvExporter
from worldcup_predictor.data_import.import_report import ImportReportWriter
from worldcup_predictor.data_import.models import ExportResult, ImportResult
from worldcup_predictor.data_quality.diagnostics import run_csv_quality_preflight, validate_csv_file
from worldcup_predictor.competition.competition_service import CompetitionService
from worldcup_predictor.config.competitions import DEFAULT_COMPETITION_KEY
from worldcup_predictor.cli.competition_cli import (
    add_competition_argument,
    print_competition_banner,
    resolve_competition,
)
from worldcup_predictor.reasoning.openai_reasoning_service import OpenAIReasoningService
from worldcup_predictor.reasoning.report_models import ProfessionalMatchReport
from worldcup_predictor.schedule.competition_schedule import create_schedule_service
from worldcup_predictor.schedule.opening_match import (
    build_opening_snapshot,
    find_opening_fixture,
)


def _t_format(translator: Translator, key: str, params: dict[str, object] | None = None) -> str:
    template = translator.t(key)
    if params:
        try:
            return template.format(**params)
        except KeyError:
            return template
    return template


def run_schedule_command(
    *,
    limit: int = 5,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI handler: show next schedule fixtures for a competition."""
    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]

    comp_key = resolve_competition(competition)
    service = create_schedule_service(settings, competition_key=comp_key)
    matches = service.get_upcoming_matches(limit=limit)
    overview = service.get_tournament_overview()

    out.write("=" * 72 + "\n")
    out.write(f"  {translator.t('app.title')}\n")
    out.write(f"  {translator.t('cli.schedule.header')}\n")
    out.write("=" * 72 + "\n\n")
    print_competition_banner(out, translator, comp_key)
    out.write(f"  {translator.t('cli.schedule.next_matches')}\n\n")

    if overview.health.is_placeholder:
        out.write(f"  ⚠ {translator.t('cli.schedule.placeholder_warning')}\n\n")

    if not matches:
        out.write(f"  {translator.t('cli.schedule.no_fixtures')}\n")
        return 0

    for index, fixture in enumerate(matches, start=1):
        line = _t_format(
            translator,
            "cli.schedule.fixture_line",
            {
                "index": index,
                "home": fixture.home_team,
                "away": fixture.away_team,
                "kickoff": fixture.kickoff_time.strftime("%Y-%m-%d %H:%M"),
                "group": fixture.group,
                "venue": fixture.venue,
                "city": fixture.city,
            },
        )
        out.write(f"  {line}\n")
        if fixture.is_placeholder:
            out.write(f"    (placeholder fixture ID {fixture.fixture_id})\n")

    for warning in overview.health.warnings:
        out.write(f"\n  • {warning}\n")

    out.write("\n" + "=" * 72 + "\n")
    return 0


def run_list_competitions_command(
    *,
    locale: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI handler: list registered competitions and supported features."""
    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]
    service = CompetitionService()

    out.write("=" * 72 + "\n")
    out.write(f"  {translator.t('app.title')}\n")
    out.write(f"  {translator.t('cli.competition.list_header')}\n")
    out.write("=" * 72 + "\n\n")

    for comp in service.list_competitions():
        features = service.get_supported_features(comp.key)
        out.write(f"  • {comp.display_name} ({comp.key})\n")
        out.write(
            f"    {translator.t('cli.competition.type')}: {features['competition_type']} | "
            f"league_id={comp.api_football_league_id or 'setup required'}\n"
        )
        out.write(
            f"    {translator.t('cli.competition.features')}: "
            f"groups={features['supports_groups']}, "
            f"table={features['supports_table']}, "
            f"knockout={features['supports_knockout']}\n"
        )
        if comp.default_seasons:
            seasons = ", ".join(str(s) for s in comp.default_seasons)
            out.write(f"    {translator.t('cli.competition.seasons')}: {seasons}\n")
        if comp.notes:
            out.write(f"    {translator.t('cli.competition.notes')}: {comp.notes}\n")
        if service.requires_league_setup(comp.key):
            out.write(f"    ⚠ {service.setup_required_message(comp.key)}\n")
        out.write("\n")

    out.write(f"  {translator.t('cli.competition.default_key')}: {DEFAULT_COMPETITION_KEY}\n")
    out.write("=" * 72 + "\n")
    return 0


def run_groups_command(
    *,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI handler: show group or league tables for a competition."""
    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]

    comp_key = resolve_competition(competition)
    service = create_schedule_service(settings, competition_key=comp_key)
    overview = service.get_tournament_overview()

    out.write("=" * 72 + "\n")
    out.write(f"  {translator.t('app.title')}\n")
    out.write(f"  {translator.t('cli.groups.header')}\n")
    out.write("=" * 72 + "\n\n")
    print_competition_banner(out, translator, comp_key)

    if overview.health.is_placeholder:
        out.write(f"  ⚠ {translator.t('cli.groups.placeholder')}\n\n")
    else:
        out.write(f"  {translator.t('cli.groups.live')}\n\n")

    if not overview.groups:
        out.write(f"  {translator.t('cli.schedule.no_fixtures')}\n")
        return 0

    for group_name in sorted(overview.groups.keys()):
        group = overview.groups[group_name]
        out.write("-" * 72 + "\n")
        out.write(f"  {_t_format(translator, 'cli.groups.table_header', {'group': group_name})}\n")
        if group.is_placeholder:
            out.write(f"  ({translator.t('cli.groups.placeholder')})\n")
        out.write("-" * 72 + "\n")
        for row in sorted(group.standings, key=lambda r: r.rank or 99):
            status = translator.t(f"schedule.qualification.{row.qualification_status}")
            line = _t_format(
                translator,
                "cli.groups.row",
                {
                    "rank": row.rank or "-",
                    "team": row.team_name,
                    "played": row.played,
                    "won": row.won,
                    "drawn": row.drawn,
                    "lost": row.lost,
                    "gd": row.goal_difference,
                    "pts": row.points,
                    "status": status,
                },
            )
            out.write(f"    {line}\n")
        out.write("\n")

    out.write("=" * 72 + "\n")
    return 0


def run_team_schedule_command(
    *,
    team: str,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI handler: show all known matches for one team."""
    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]

    comp_key = resolve_competition(competition)
    service = create_schedule_service(settings, competition_key=comp_key)
    matches = service.get_team_schedule(team)
    overview = service.get_tournament_overview()

    out.write("=" * 72 + "\n")
    out.write(f"  {translator.t('app.title')}\n")
    out.write(f"  {translator.t('cli.team_schedule.header')}: {team}\n")
    print_competition_banner(out, translator, comp_key)
    out.write("=" * 72 + "\n\n")

    if overview.health.is_placeholder:
        out.write(f"  ⚠ {translator.t('cli.schedule.placeholder_warning')}\n\n")

    if not matches:
        out.write(f"  {_t_format(translator, 'cli.team_schedule.no_matches', {'team': team})}\n")
        return 0

    for fixture in matches:
        line = _t_format(
            translator,
            "cli.team_schedule.match_line",
            {
                "kickoff": fixture.kickoff_time.strftime("%Y-%m-%d %H:%M"),
                "home": fixture.home_team,
                "away": fixture.away_team,
                "group": fixture.group,
                "venue": fixture.venue,
            },
        )
        out.write(f"  {line}\n")
        if fixture.is_placeholder:
            out.write(f"    (placeholder)\n")

    out.write("\n" + "=" * 72 + "\n")
    return 0


def run_next_window_command(
    *,
    locale: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI handler: nearest analysis readiness window."""
    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]

    service = WorldCupScheduleService(settings)
    window = service.detect_next_betting_window()

    out.write("=" * 72 + "\n")
    out.write(f"  {translator.t('app.title')}\n")
    out.write(f"  {translator.t('cli.next_window.header')}\n")
    out.write("=" * 72 + "\n\n")
    out.write(f"  {translator.t('cli.next_window.note')}\n\n")
    out.write(
        f"  {translator.t('cli.next_window.readiness_score')}: "
        f"{window.analysis_readiness_score:.0f}/100\n"
    )
    ready_key = "cli.next_window.ready" if window.analysis_ready else "cli.next_window.not_ready"
    out.write(f"  {translator.t(ready_key)}\n\n")

    if window.is_placeholder:
        out.write(f"  ⚠ {translator.t('cli.schedule.placeholder_warning')}\n\n")

    out.write(f"  {translator.t('cli.schedule.next_matches')}:\n\n")
    for index, fixture in enumerate(window.fixtures, start=1):
        line = _t_format(
            translator,
            "cli.schedule.fixture_line",
            {
                "index": index,
                "home": fixture.home_team,
                "away": fixture.away_team,
                "kickoff": fixture.kickoff_time.strftime("%Y-%m-%d %H:%M"),
                "group": fixture.group,
                "venue": fixture.venue,
                "city": fixture.city,
            },
        )
        out.write(f"  {line}\n")

    if window.warnings:
        out.write(f"\n  {translator.t('cli.next_window.warnings')}:\n")
        for warning in window.warnings:
            out.write(f"    • {warning}\n")

    out.write("\n" + "=" * 72 + "\n")
    return 0


def run_live_opening_command(
    *,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI handler: live opening match (Mexico vs South Africa) readiness snapshot."""
    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]

    comp_key = resolve_competition(competition)
    service = create_schedule_service(settings, competition_key=comp_key)
    opening = find_opening_fixture(service)
    if opening is None:
        out.write(f"{translator.t('cli.live_opening.not_found')}\n")
        return 1

    inspect = InspectPipeline(settings, locale=active_locale, competition_key=comp_key)
    inspect_result = inspect.run(opening.fixture_id)
    intelligence = inspect_result.report if inspect_result.success else None
    snapshot = build_opening_snapshot(opening, intelligence, settings)

    out.write("=" * 72 + "\n")
    out.write(f"  {translator.t('app.title')}\n")
    out.write(f"  {translator.t('cli.live_opening.header')}\n")
    out.write("=" * 72 + "\n\n")
    print_competition_banner(out, translator, comp_key)

    out.write(f"  {opening.home_team} vs {opening.away_team}\n")
    out.write(f"  {translator.t('cli.inspect.fixture_id')}: {opening.fixture_id}\n")
    out.write(
        f"  {translator.t('cli.fixture.kickoff')}: "
        f"{opening.kickoff_time.strftime('%Y-%m-%d %H:%M')} UTC\n"
    )
    out.write(f"  {translator.t('cli.fixture.venue')}: {opening.venue}, {opening.city}\n")
    out.write(f"  {translator.t('cli.fixture.stage')}: {opening.group} / {opening.round}\n")
    out.write(f"  {translator.t('cli.live_opening.source')}: {opening.source}\n\n")

    readiness_key = {
        "Ready": "cli.live_opening.readiness_ready",
        "Partial": "cli.live_opening.readiness_partial",
        "Not Ready": "cli.live_opening.readiness_not_ready",
    }[snapshot.readiness]
    out.write(f"  {translator.t('cli.live_opening.readiness')}: {translator.t(readiness_key)}\n")
    if intelligence and intelligence.data_quality:
        out.write(
            f"  {translator.t('cli.inspect.quality_score')}: "
            f"{intelligence.data_quality.score:.0%} ({intelligence.data_quality.grade})\n"
        )
    out.write("\n")

    def _field(label_key: str, available: bool) -> None:
        status = translator.t("cli.live_opening.available") if available else translator.t(
            "cli.live_opening.unavailable"
        )
        out.write(f"    • {translator.t(label_key)}: {status}\n")

    out.write(f"  {translator.t('cli.live_opening.fields')}:\n")
    _field("cli.live_opening.field_lineups", snapshot.lineups_available)
    _field("cli.live_opening.field_injuries", snapshot.injuries_available)
    _field("cli.live_opening.field_odds", snapshot.odds_available)
    _field("cli.live_opening.field_weather", snapshot.weather_available)
    out.write("\n")

    if intelligence and intelligence.missing_data:
        out.write(f"  {translator.t('cli.inspect.missing')}:\n")
        for item in intelligence.missing_data:
            out.write(f"    • {item}\n")
        out.write("\n")

    if snapshot.prediction_allowed:
        out.write(f"  {translator.t('cli.live_opening.prediction_hint')}\n")
        out.write(
            f"  python main.py predict --fixture-id {opening.fixture_id} "
            f"--locale {active_locale}\n"
        )
    else:
        out.write(f"  ⚠ {translator.t('cli.live_opening.prediction_skipped')}\n")

    out.write("\n" + "=" * 72 + "\n")
    return 0


def run_import_history_command(
    *,
    worldcup: bool = False,
    league_id: int | None = None,
    competition: str | None = None,
    seasons: list[int] | None = None,
    team_ids: list[int] | None = None,
    overwrite: bool = False,
    locale: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI handler: import historical matches from API-Football into CSV."""
    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]

    importer = ApiFootballHistoricalImporter(settings)
    exporter = CsvExporter()
    active_seasons = seasons or []

    if not importer.is_configured:
        out.write("=" * 72 + "\n")
        out.write(f"  {translator.t('app.title')}\n")
        out.write(f"  {translator.t('cli.import.header')}\n")
        out.write("=" * 72 + "\n\n")
        out.write(f"  {translator.t('cli.import.api_key_required')}\n\n")
        out.write(f"  {translator.t('cli.import.demo_separate')}\n\n")
        out.write("=" * 72 + "\n")
        return 1

    comp_key = resolve_competition(competition)
    comp_svc = CompetitionService()
    if not worldcup and league_id is None and comp_key != "world_cup_2026":
        league_id = comp_svc.resolve_league_id(comp_key)
        if league_id is None:
            out.write(f"{comp_svc.setup_required_message(comp_key)}\n")
            return 1
        if not active_seasons:
            active_seasons = [comp_svc.get_default_season(comp_key)]

    import_result: ImportResult | None = None
    export_result: ExportResult | None = None

    if worldcup:
        wc_seasons = active_seasons or [2014, 2018, 2022]
        import_result = importer.import_world_cup_history(wc_seasons)
        if import_result.imported_count > 0:
            export_result = exporter.export_worldcup(import_result, overwrite=overwrite)
    elif league_id is not None:
        if not active_seasons:
            out.write(f"{translator.t('cli.import.seasons_required')}\n")
            return 1
        from worldcup_predictor.data_import.api_football_historical_importer import (
            _dedupe_rows,
            _quality_notes,
        )

        combined = ImportResult(
            requested_competitions=[f"league_id={league_id}"],
            requested_seasons=active_seasons,
            source_label="api-football",
        )
        for season in active_seasons:
            partial = importer.import_fixtures(league_id=league_id, season=season)
            combined.rows.extend(partial.rows)
            combined.skipped_count += partial.skipped_count
            combined.api_errors.extend(partial.api_errors)
            for key, count in partial.missing_fields_summary.items():
                combined.missing_fields_summary[key] = (
                    combined.missing_fields_summary.get(key, 0) + count
                )
        combined.rows = _dedupe_rows(combined.rows)
        combined.imported_count = len(combined.rows)
        combined.success = combined.imported_count > 0
        combined.stats = importer._stats  # noqa: SLF001
        combined.message = f"League {league_id} import: {combined.imported_count} fixtures."
        combined.data_quality_notes = _quality_notes(combined)
        import_result = combined

        if import_result.imported_count > 0:
            if league_id == 1:
                export_result = exporter.export_worldcup(import_result, overwrite=overwrite)
            else:
                export_result = exporter.export_international(import_result, overwrite=overwrite)
    elif team_ids:
        import_result = importer.import_international_matches(team_ids=team_ids, seasons=active_seasons)
        if import_result.success:
            export_result = exporter.export_international(import_result, overwrite=overwrite)
    else:
        out.write(f"{translator.t('cli.import.mode_required')}\n")
        return 1

    if import_result is None:
        return 1

    writer = ImportReportWriter()
    json_path, md_path = writer.write(import_result, export_result)

    out.write("=" * 72 + "\n")
    out.write(f"  {translator.t('app.title')}\n")
    out.write(f"  {translator.t('cli.import.header')}\n")
    out.write("=" * 72 + "\n\n")
    out.write(f"  {translator.t('cli.import.source')}: API-Football\n")
    out.write(f"  {import_result.message}\n\n")

    out.write(f"  {translator.t('cli.import.imported')}: {import_result.imported_count}\n")
    out.write(f"  {translator.t('cli.import.skipped')}: {import_result.skipped_count}\n")
    out.write(f"  {translator.t('cli.import.cache_hits')}: {import_result.stats.cache_hits}\n")
    out.write(f"  {translator.t('cli.import.live_requests')}: {import_result.stats.live_requests}\n\n")

    if export_result:
        out.write(f"  {translator.t('cli.import.output')}: {export_result.output_path}\n")
        out.write(f"  {translator.t('cli.import.rows_written')}: {export_result.rows_written}\n")
        if export_result.rows_merged:
            out.write(f"  {translator.t('cli.import.merged')}: {export_result.rows_merged}\n")
        if overwrite:
            out.write(f"  {translator.t('cli.import.overwrite')}: yes\n")

    if import_result.missing_fields_summary:
        out.write(f"\n  {translator.t('cli.import.missing_fields')}:\n")
        for field_name, count in sorted(import_result.missing_fields_summary.items()):
            out.write(f"    • {field_name}: {count}\n")

    if import_result.api_errors:
        out.write(f"\n  {translator.t('cli.import.api_errors')}:\n")
        for error in import_result.api_errors:
            out.write(f"    • {error}\n")

    if import_result.data_quality_notes:
        out.write(f"\n  {translator.t('cli.import.quality_notes')}:\n")
        for note in import_result.data_quality_notes:
            out.write(f"    • {note}\n")

    out.write(f"\n  {translator.t('cli.import.reports')}:\n")
    out.write(f"    JSON: {json_path}\n")
    out.write(f"    MD:   {md_path}\n")

    out.write("\n" + "=" * 72 + "\n")
    out.write(f"  {translator.t('cli.import.disclaimer')}\n")
    out.write("=" * 72 + "\n")

    if not import_result.success:
        return 1
    if export_result and export_result.validation_errors:
        return 1
    return 0


def run_validate_csv_command(
    *,
    csv_path: str,
    locale: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI handler: validate historical CSV quality before backtest/calibration."""
    from pathlib import Path

    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]

    path = Path(csv_path)
    if not path.exists():
        HistoricalLoader.ensure_sample_csv(path)
        out.write(f"  ⚠ {translator.t('cli.validate.demo_created')}\n\n")

    report = validate_csv_file(path, write_report=True)
    json_path = Path("reports/data_quality/data_quality_summary.json")
    md_path = Path("reports/data_quality/data_quality_summary.md")

    out.write("=" * 72 + "\n")
    out.write(f"  {translator.t('app.title')}\n")
    out.write(f"  {translator.t('cli.validate.header')}\n")
    out.write("=" * 72 + "\n\n")
    out.write(f"  {translator.t('cli.validate.disclaimer')}\n\n")
    out.write(f"  {translator.t('cli.validate.csv')}: {path}\n")
    out.write(f"  {translator.t('cli.validate.source')}: {report.source_label}\n")
    out.write(f"  {translator.t('cli.validate.row_count')}: {report.row_count}\n")

    if report.health:
        out.write(
            f"  {translator.t('cli.validate.health_score')}: "
            f"{report.health.score:.0f}/100 ({report.health.label})\n"
        )
        out.write(f"    {report.health.summary}\n")

    out.write("\n" + "-" * 72 + "\n")
    out.write(f"  {translator.t('cli.validate.duplicates')}\n")
    out.write("-" * 72 + "\n")
    out.write(f"    fixture_id: {report.duplicate_fixture_id_count}\n")
    out.write(f"    match keys: {report.duplicate_match_count}\n")

    if report.missing_required_fields:
        out.write("\n" + "-" * 72 + "\n")
        out.write(f"  {translator.t('cli.validate.missing_required')}\n")
        out.write("-" * 72 + "\n")
        for col in report.missing_required_fields:
            out.write(f"    • {col}\n")

    out.write("\n" + "-" * 72 + "\n")
    out.write(f"  {translator.t('cli.validate.missing_optional')}\n")
    out.write("-" * 72 + "\n")
    for col, fill_pct in sorted(report.missing_optional_summary.items()):
        missing_pct = 100.0 - fill_pct
        if missing_pct > 0:
            out.write(f"    {col}: {missing_pct:.1f}% missing\n")

    if report.warnings:
        out.write("\n" + "-" * 72 + "\n")
        out.write(f"  {translator.t('cli.validate.warnings')}\n")
        out.write("-" * 72 + "\n")
        for warning in report.warnings:
            out.write(f"    • {warning}\n")

    if report.critical_errors or report.has_critical_errors:
        out.write("\n" + "-" * 72 + "\n")
        out.write(f"  {translator.t('cli.validate.critical_errors')}\n")
        out.write("-" * 72 + "\n")
        for err in report.critical_errors:
            out.write(f"    • {err}\n")
        critical_rows = [i for i in report.row_issues if i.severity == "critical"][:5]
        for issue in critical_rows:
            out.write(f"    • Row {issue.row_number}: {issue.message}\n")

    if report.repair_suggestions:
        out.write("\n" + "-" * 72 + "\n")
        out.write(f"  {translator.t('cli.validate.repair_suggestions')}\n")
        out.write("-" * 72 + "\n")
        for suggestion in report.repair_suggestions:
            out.write(f"    • {suggestion}\n")

    out.write("\n" + "-" * 72 + "\n")
    out.write(f"  {translator.t('cli.validate.safety')}\n")
    out.write("-" * 72 + "\n")
    out.write(
        f"    {translator.t('cli.validate.safe_backtest')}: "
        f"{'✓' if report.safe_for_backtest else '✗'}\n"
    )
    out.write(
        f"    {translator.t('cli.validate.safe_calibration')}: "
        f"{'✓' if report.safe_for_calibration else '✗'}\n"
    )

    out.write("\n" + "-" * 72 + "\n")
    out.write(f"  {translator.t('cli.validate.reports_written')}\n")
    out.write("-" * 72 + "\n")
    out.write(f"    JSON: {json_path}\n")
    out.write(f"    MD:   {md_path}\n")

    out.write("\n" + "=" * 72 + "\n")
    out.write(f"  {translator.t('cli.validate.footer')}\n")
    out.write("=" * 72 + "\n")

    if report.has_critical_errors:
        return 1
    return 0


def run_dashboard_command(*, stream: TextIO | None = None) -> int:
    """CLI handler: launch the Streamlit professional dashboard."""
    import subprocess
    from pathlib import Path

    out = stream or sys.stdout
    app_path = Path(__file__).resolve().parent.parent / "ui" / "streamlit_app.py"
    project_root = app_path.resolve().parents[2]

    if not app_path.exists():
        out.write(f"Dashboard app not found: {app_path}\n")
        return 1

    out.write("=" * 72 + "\n")
    out.write("  WorldCup Predictor Pro 2026 — Dashboard\n")
    out.write("=" * 72 + "\n\n")
    out.write(f"  Starting Streamlit at: {app_path.relative_to(project_root)}\n")
    out.write("  Press Ctrl+C in this terminal to stop the dashboard.\n\n")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "streamlit", "run", str(app_path)],
            cwd=str(project_root),
        )
        return int(result.returncode or 0)
    except FileNotFoundError:
        out.write(
            "Streamlit is not installed. Install dependencies:\n"
            "  pip install -r requirements.txt\n"
        )
        return 1


def run_gui_command(*, stream: TextIO | None = None) -> int:
    """CLI handler: launch the Phase 14 polished Streamlit GUI."""
    import subprocess
    from pathlib import Path

    out = stream or sys.stdout
    app_path = Path(__file__).resolve().parent.parent / "ui" / "gui_app.py"
    project_root = app_path.resolve().parents[2]

    if not app_path.exists():
        out.write(f"GUI app not found: {app_path}\n")
        return 1

    out.write("=" * 72 + "\n")
    out.write("  WorldCup Predictor Pro 2026 — Beautiful GUI\n")
    out.write("=" * 72 + "\n\n")
    out.write(f"  Starting Streamlit GUI at: {app_path.relative_to(project_root)}\n")
    out.write("  Open the URL shown below in your browser.\n")
    out.write("  Press Ctrl+C in this terminal to stop the GUI.\n\n")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "streamlit", "run", str(app_path)],
            cwd=str(project_root),
        )
        return int(result.returncode or 0)
    except FileNotFoundError:
        out.write(
            "Streamlit is not installed. Install dependencies:\n"
            "  pip install -r requirements.txt\n"
        )
        return 1


def run_test_apis_command(*, locale: str | None = None, stream: TextIO | None = None) -> int:
    """CLI handler: test API connectivity (primary + optional enrichment)."""
    from worldcup_predictor.ui.api_health import test_all_apis

    out = stream or sys.stdout
    settings = get_settings()
    translator = get_translator(locale or settings.default_locale)

    out.write("=" * 72 + "\n")
    out.write(f"  {translator.t('cli.api_test.title')}\n")
    out.write("=" * 72 + "\n\n")

    statuses = test_all_apis(settings)
    for status in statuses:
        if status.configured is False and status.connected is None:
            icon = "○"
            state = translator.t("cli.api_test.skipped")
        elif status.connected:
            icon = "✓"
            state = translator.t("cli.api_test.ok")
        else:
            icon = "✗"
            state = translator.t("cli.api_test.fail")

        latency = f" ({status.latency_ms:.0f} ms)" if status.latency_ms else ""
        out.write(f"  {icon} {status.service}: {state}{latency}\n")
        if status.message:
            out.write(f"      {status.message}\n")
        out.write("\n")

    primary_ok = any(s.service == "API-Football" and s.connected for s in statuses)
    out.write("-" * 72 + "\n")
    if primary_ok:
        out.write(f"  {translator.t('cli.api_test.primary_ok')}\n")
    else:
        out.write(f"  {translator.t('cli.api_test.primary_fail')}\n")
    out.write("\n")
    return 0 if primary_ok else 1


def run_sportmonks_test_command(*, stream: TextIO | None = None) -> int:
    """CLI handler: one cheap Sportmonks World Cup 2026 connectivity probe."""
    from worldcup_predictor.providers.sportmonks_provider import (
        SportmonksProvider,
        WORLD_CUP_2026_COMPETITION_KEY,
        WORLD_CUP_2026_LEAGUE_ID,
    )

    out = stream or sys.stdout
    settings = get_settings()
    provider = SportmonksProvider(settings)
    result = provider.run_world_cup_connectivity_test()

    out.write("=" * 72 + "\n")
    out.write("  Sportmonks World Cup 2026 — connectivity test\n")
    out.write("=" * 72 + "\n\n")
    out.write(f"  competition:     {WORLD_CUP_2026_COMPETITION_KEY}\n")
    out.write(f"  league_id:       {WORLD_CUP_2026_LEAGUE_ID}\n")
    out.write(f"  configured:      {result.configured}\n")
    out.write(f"  connected:       {result.connected}\n")
    if result.status_code is not None:
        out.write(f"  status_code:     {result.status_code}\n")
    out.write(f"  endpoint_path:   {result.endpoint_path}\n")
    if result.sample_count is not None:
        out.write(f"  sample_count:    {result.sample_count}\n")
    out.write(f"  message:         {result.message}\n")
    out.write("\n")
    return 0 if result.connected else 1


def run_sportmonks_fixture_test_command(
    *,
    fixture_id: int,
    force_refresh: bool = False,
    stream: TextIO | None = None,
) -> int:
    """CLI handler: fetch/cache one Sportmonks World Cup fixture enrichment payload."""
    from worldcup_predictor.providers.sportmonks_enrichment import (
        WORLD_CUP_FIXTURE_INCLUDES,
        fetch_worldcup_fixture_enrichment,
    )
    from worldcup_predictor.providers.sportmonks_provider import (
        WORLD_CUP_2026_LEAGUE_ID,
        WORLD_CUP_2026_SEASON_ID,
    )

    out = stream or sys.stdout
    result = fetch_worldcup_fixture_enrichment(
        fixture_id,
        force_refresh=force_refresh,
    )

    out.write("=" * 72 + "\n")
    out.write("  Sportmonks World Cup 2026 — fixture enrichment test\n")
    out.write("=" * 72 + "\n\n")
    out.write(f"  league_id:             {WORLD_CUP_2026_LEAGUE_ID}\n")
    out.write(f"  season_id:             {WORLD_CUP_2026_SEASON_ID}\n")
    out.write(f"  configured:            {result.configured}\n")
    out.write(f"  source:                {result.source}\n")
    out.write(f"  sportmonks_fixture_id: {result.sportmonks_fixture_id}\n")
    if result.status_code is not None:
        out.write(f"  status_code:           {result.status_code}\n")
    out.write(f"  endpoint_path:         {result.endpoint_path}\n")
    out.write(f"  includes:              {';'.join(WORLD_CUP_FIXTURE_INCLUDES)}\n")
    if result.keys_present:
        out.write(f"  keys_present:          {', '.join(result.keys_present)}\n")
    else:
        out.write("  keys_present:          (none)\n")
    out.write(f"  raw_json_size:         {result.raw_json_size}\n")
    out.write(f"  message:               {result.message}\n")
    out.write("\n")
    return 0 if result.success else 1


def run_calibrate_command(
    *,
    csv_path: str,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI handler: auto-tune weights and thresholds from historical CSV."""
    from pathlib import Path

    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]

    path = Path(csv_path)
    if not path.exists():
        HistoricalLoader.ensure_sample_csv(path)

    _, blocked = run_csv_quality_preflight(
        path, out=out, translator=translator, context="calibration"
    )
    if blocked:
        return 1

    comp_key = resolve_competition(competition)
    print_competition_banner(out, translator, comp_key)
    runner = CalibrationRunner(settings, locale=active_locale)
    result = runner.run(path, apply=True)
    writer = CalibrationReportWriter()
    json_path, md_path = writer.write(result)

    out.write("=" * 72 + "\n")
    out.write(f"  {translator.t('app.title')}\n")
    out.write(f"  {translator.t('cli.calibrate.header')}\n")
    out.write("=" * 72 + "\n\n")
    out.write(f"  {translator.t('cli.calibrate.disclaimer')}\n\n")

    if result.sample_size_warning:
        out.write(f"  ⚠ {result.sample_size_warning}\n\n")

    if result.is_demo_data:
        out.write(f"  ⚠ {translator.t('cli.calibrate.demo_data')}\n\n")

    out.write(f"  {translator.t('cli.calibrate.sample_size')}: {result.sample_size}\n")
    out.write(
        f"  {translator.t('cli.calibrate.weight_candidates')}: "
        f"{result.weight_tuning.candidates_evaluated}\n"
    )
    out.write(
        f"  {translator.t('cli.calibrate.threshold_candidates')}: "
        f"{result.threshold_tuning.candidates_evaluated}\n\n"
    )

    out.write("-" * 72 + "\n")
    out.write(f"  {translator.t('cli.calibrate.weights')}\n")
    out.write("-" * 72 + "\n")
    for key in sorted(result.current_weights):
        cur = result.current_weights[key]
        rec = result.recommended_weights.get(key, cur)
        out.write(f"    {key}: {cur:.2%} → {rec:.2%}\n")

    out.write("\n" + "-" * 72 + "\n")
    out.write(f"  {translator.t('cli.calibrate.performance')}\n")
    out.write("-" * 72 + "\n")
    wt = result.weight_tuning
    tt = result.threshold_tuning
    out.write(
        f"    1X2: {_format_pct(wt.performance_before.one_x_two_accuracy)} → "
        f"{_format_pct(wt.performance_after.one_x_two_accuracy)}\n"
    )
    out.write(
        f"    O/U 2.5: {_format_pct(wt.performance_before.over_under_accuracy)} → "
        f"{_format_pct(wt.performance_after.over_under_accuracy)}\n"
    )
    out.write(
        f"    {translator.t('cli.calibrate.no_bet_rate')}: "
        f"{_format_pct(tt.no_bet_rate_before)} → {_format_pct(tt.no_bet_rate_after)}\n"
    )
    out.write(
        f"    {translator.t('cli.calibrate.combined_accuracy')}: "
        f"{_format_pct(tt.accuracy_before)} → {_format_pct(tt.accuracy_after)}\n"
    )

    mc = result.market_comparison
    strongest = max(
        ("1x2", mc.get("1x2", {}).get("accuracy_after_weights") or 0),
        ("over_under_2_5", mc.get("over_under_2_5", {}).get("accuracy_after_weights") or 0),
        ("halftime", mc.get("halftime_bucket", {}).get("accuracy_after_weights") or 0),
        key=lambda item: item[1],
    )[0]
    out.write(f"\n  {translator.t('cli.calibrate.strongest')}: {strongest}\n")
    out.write(
        f"  {translator.t('cli.calibrate.best_market_weights')}: "
        f"1X2={_top_factors(result.weight_tuning.best_weights_1x2)}, "
        f"O/U={_top_factors(result.weight_tuning.best_weights_over_under)}\n"
    )

    if result.overfitting_warnings:
        out.write("\n" + "-" * 72 + "\n")
        out.write(f"  {translator.t('cli.calibrate.overfitting')}\n")
        out.write("-" * 72 + "\n")
        for warning in result.overfitting_warnings:
            out.write(f"    • {warning}\n")

    out.write("\n" + "-" * 72 + "\n")
    out.write(f"  {translator.t('cli.calibrate.reports_written')}\n")
    out.write("-" * 72 + "\n")
    out.write(f"    JSON: {json_path}\n")
    out.write(f"    MD:   {md_path}\n")

    out.write("\n" + "=" * 72 + "\n")
    out.write(f"  {translator.t('cli.calibrate.footer')}\n")
    out.write("=" * 72 + "\n")
    return 0


def _top_factors(weights: dict[str, float], n: int = 3) -> str:
    ordered = sorted(weights.items(), key=lambda item: item[1], reverse=True)
    return ", ".join(f"{name} {value:.0%}" for name, value in ordered[:n])


def run_backtest_command(
    *,
    csv_path: str,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI handler: historical backtest model evaluation."""
    from pathlib import Path

    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]

    path = Path(csv_path)
    created_demo = not path.exists()
    if created_demo:
        HistoricalLoader.ensure_sample_csv(path)

    _, blocked = run_csv_quality_preflight(
        path, out=out, translator=translator, context="backtest"
    )
    if blocked:
        return 1

    comp_key = resolve_competition(competition)
    print_competition_banner(out, translator, comp_key)
    runner = BacktestRunner(settings, locale=active_locale)
    result = runner.run(path)
    writer = BacktestReportWriter()
    json_path, md_path = writer.write(result)
    metrics = result.metrics

    out.write("=" * 72 + "\n")
    out.write(f"  {translator.t('app.title')}\n")
    out.write(f"  {translator.t('cli.backtest.header')}\n")
    out.write("=" * 72 + "\n\n")
    out.write(f"  {translator.t('cli.backtest.disclaimer')}\n\n")

    if created_demo or result.is_demo_data:
        out.write(f"  ⚠ {translator.t('cli.backtest.demo_created')}\n\n")

    out.write(f"  {translator.t('cli.backtest.csv')}: {path}\n")
    out.write(f"  {translator.t('cli.backtest.total_matches')}: {metrics.total_matches}\n\n")

    out.write("-" * 72 + "\n")
    out.write(f"  {translator.t('cli.backtest.market_accuracy')}\n")
    out.write("-" * 72 + "\n")
    out.write(f"    1X2: {_format_pct(metrics.one_x_two_accuracy)}\n")
    out.write(f"    O/U 2.5: {_format_pct(metrics.over_under_2_5_accuracy)}\n")
    out.write(f"    {translator.t('cli.backtest.halftime')}: {_format_pct(metrics.halftime_bucket_accuracy)} ")
    out.write(f"({metrics.halftime_evaluated_count})\n")
    out.write(f"    {translator.t('cli.backtest.avg_confidence')}: {metrics.average_confidence:.1f}\n")
    out.write(
        f"    {translator.t('cli.backtest.high_confidence')}: "
        f"{_format_pct(metrics.high_confidence_accuracy)} ({metrics.high_confidence_count})\n"
    )
    out.write(
        f"    {translator.t('cli.backtest.no_bet')}: {metrics.no_bet_count} "
        f"({_format_pct(metrics.no_bet_rate)})\n\n"
    )

    out.write(f"  {translator.t('cli.backtest.strongest')}: {metrics.strongest_market or 'n/a'}\n")
    out.write(f"  {translator.t('cli.backtest.weakest')}: {metrics.weakest_market or 'n/a'}\n\n")

    out.write("-" * 72 + "\n")
    out.write(f"  {translator.t('cli.backtest.calibration')}\n")
    out.write("-" * 72 + "\n")
    for bucket in metrics.confidence_buckets:
        if bucket.count == 0:
            continue
        out.write(
            f"    {bucket.label}: n={bucket.count} "
            f"1X2={_format_pct(bucket.one_x_two_accuracy)} "
            f"O/U={_format_pct(bucket.over_under_accuracy)} "
            f"avg_conf={bucket.average_confidence:.0f}\n"
        )

    if metrics.data_limitations:
        out.write("\n" + "-" * 72 + "\n")
        out.write(f"  {translator.t('cli.backtest.limitations')}\n")
        out.write("-" * 72 + "\n")
        for item in metrics.data_limitations:
            out.write(f"    • {item}\n")

    if metrics.weight_recommendations:
        out.write("\n" + "-" * 72 + "\n")
        out.write(f"  {translator.t('cli.backtest.recommendations')}\n")
        out.write("-" * 72 + "\n")
        for item in metrics.weight_recommendations:
            out.write(f"    • {item}\n")

    out.write("\n" + "-" * 72 + "\n")
    out.write(f"  {translator.t('cli.backtest.reports_written')}\n")
    out.write("-" * 72 + "\n")
    out.write(f"    JSON: {json_path}\n")
    out.write(f"    MD:   {md_path}\n")

    out.write("\n" + "=" * 72 + "\n")
    out.write(f"  {translator.t('cli.backtest.footer')}\n")
    out.write("=" * 72 + "\n")
    return 0


def _format_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def run_accuracy_command(
    *,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI handler: evaluate stored predictions against finished fixtures."""
    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]

    from worldcup_predictor.accuracy.service import AccuracyTrackerService
    from worldcup_predictor.schedule.competition_schedule import create_schedule_service
    from worldcup_predictor.schedule.match_center import build_match_center

    comp_key = resolve_competition(competition)
    print_competition_banner(out, translator, comp_key)

    schedule = create_schedule_service(settings, competition_key=comp_key)
    center = build_match_center(schedule, settings, enrich_live=False, enrich_finished_limit=50)
    fixtures = center.finished + center.live + center.upcoming

    service = AccuracyTrackerService(settings, competition_key=comp_key)
    snapshot = service.refresh(fixtures)
    metrics = snapshot.metrics

    out.write("=" * 72 + "\n")
    out.write(f"  {translator.t('app.title')}\n")
    out.write("  Model Evaluation Accuracy\n")
    out.write("=" * 72 + "\n\n")
    out.write("  Historical model evaluation does not guarantee future results.\n")
    out.write("  Learning memory and calibration only — not profit or betting advice.\n\n")

    out.write(f"  Evaluated predictions: {metrics.total_evaluated}\n")
    out.write(f"  Pending (not finished): {metrics.pending_predictions}\n")
    out.write(f"  1X2 accuracy: {_format_pct(metrics.one_x_two_accuracy)}\n")
    out.write(f"  O/U 2.5 accuracy: {_format_pct(metrics.over_under_2_5_accuracy)}\n")
    out.write(f"  Halftime bucket: {_format_pct(metrics.halftime_bucket_accuracy)} ")
    out.write(f"({metrics.halftime_evaluated_count})\n\n")

    out.write(f"  Best confidence range: {metrics.best_confidence_range or 'n/a'}\n")
    out.write(f"  Weakest confidence range: {metrics.worst_confidence_range or 'n/a'}\n\n")

    out.write("  Reports written:\n")
    out.write("    reports/accuracy/accuracy_summary.json\n")
    out.write("    reports/accuracy/accuracy_summary.md\n")
    out.write("\n" + "=" * 72 + "\n")
    return 0


def run_verify_predictions_command(
    *,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI handler: auto-verify stored predictions against finished results."""
    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]

    from worldcup_predictor.schedule.competition_schedule import create_schedule_service
    from worldcup_predictor.schedule.match_center import build_match_center
    from worldcup_predictor.results.match_results_store import save_finished_fixtures
    from worldcup_predictor.verification.auto_verification_agent import AutoVerificationAgent

    comp_key = resolve_competition(competition)
    print_competition_banner(out, translator, comp_key)

    schedule = create_schedule_service(settings, competition_key=comp_key)
    center = build_match_center(schedule, settings, enrich_live=False, enrich_finished_limit=50)
    save_finished_fixtures(center.finished)
    fixtures = center.finished + center.live + center.upcoming

    agent = AutoVerificationAgent()
    result = agent.run(fixtures, all_predictions=True)
    metrics = result.metrics

    out.write("=" * 72 + "\n")
    out.write(f"  {translator.t('app.title')}\n")
    out.write("  Auto Prediction Verification\n")
    out.write("=" * 72 + "\n\n")
    out.write("  Automated model verification — not profit or betting advice.\n\n")
    out.write(f"  Predictions checked: {metrics.total_predictions_checked}\n")
    out.write(f"  Evaluated matches: {metrics.evaluated_matches}\n")
    out.write(f"  Pending matches: {metrics.pending_matches}\n")
    out.write(f"  New market rows saved: {result.saved_rows}\n")
    out.write(f"  Model grade (1X2): {metrics.model_grade}\n\n")
    out.write(f"  1X2 winrate: {_format_pct(metrics.one_x_two_winrate)}\n")
    out.write(f"  O/U 2.5 winrate: {_format_pct(metrics.over_under_winrate)}\n")
    out.write(f"  Halftime bucket: {_format_pct(metrics.halftime_bucket_winrate)}\n")
    out.write(f"  Exact scoreline: {_format_pct(metrics.scoreline_winrate)}\n")
    out.write(f"  First goal team: {_format_pct(metrics.first_goal_team_winrate)}\n\n")
    out.write(f"  Strongest market: {metrics.strongest_market or 'n/a'}\n")
    out.write(f"  Weakest market: {metrics.weakest_market or 'n/a'}\n\n")

    for summary in result.summaries[:10]:
        out.write(f"  {summary.match_name} ({summary.final_score})\n")
        for market in summary.markets:
            icon = "OK" if market.result == "correct" else "X" if market.result == "wrong" else "-"
            out.write(
                f"    [{icon}] {market.market}: predicted {market.predicted} · actual {market.actual}\n"
            )
        out.write("\n")

    out.write("  Reports written:\n")
    out.write("    data/verification/prediction_verification.jsonl\n")
    out.write("    reports/verification/verification_summary.json\n")
    out.write("    reports/verification/verification_summary.md\n")
    out.write("\n" + "=" * 72 + "\n")
    return 0


def run_coach_model_command(
    *,
    locale: str | None = None,
    competition: str | None = None,
    all_competitions: bool = False,
    stream: TextIO | None = None,
) -> int:
    """CLI handler: run model coach learning agent."""
    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]

    from worldcup_predictor.learning.model_coach_agent import ModelCoachAgent

    agent = ModelCoachAgent()
    if all_competitions:
        reports = agent.run_all()
        report = reports[0]
    else:
        comp_key = resolve_competition(competition)
        print_competition_banner(out, translator, comp_key)
        report = agent.run(competition_key=comp_key)

    out.write("=" * 72 + "\n")
    out.write(f"  {translator.t('app.title')}\n")
    out.write("  Model Coach — Learning Agent\n")
    out.write("=" * 72 + "\n\n")
    out.write("  Recommendations only — weights are not changed automatically.\n")
    out.write("  Model improvement analysis — not profit or betting advice.\n\n")
    out.write(f"  Evaluated matches: {report.evaluated_matches}\n")
    out.write(f"  Market rows analyzed: {report.total_market_rows}\n")
    out.write(f"  Strongest market: {report.strongest_market or 'n/a'}\n")
    out.write(f"  Weakest market: {report.weakest_market or 'n/a'}\n")
    out.write(f"  Suggested focus: {report.suggested_focus_area or 'n/a'}\n\n")

    if report.warnings_about_small_sample_size:
        out.write("  Sample size warnings:\n")
        for warning in report.warnings_about_small_sample_size:
            out.write(f"    ! {warning}\n")
        out.write("\n")

    out.write("  Market winrates:\n")
    for market, rate in report.market_winrates.items():
        out.write(f"    {market}: {_format_pct(rate)}\n")
    out.write("\n")

    if report.recommended_weight_adjustments:
        out.write("  Recommended weight adjustments:\n")
        for factor, note in report.recommended_weight_adjustments.items():
            out.write(f"    · {factor}: {note}\n")
        out.write("\n")

    if report.recommended_market_rules:
        out.write("  Recommended market rules:\n")
        for rule in report.recommended_market_rules:
            out.write(f"    · {rule}\n")
        out.write("\n")

    if report.decision_agent_advice:
        out.write("  Decision agent advice:\n")
        for advice in report.decision_agent_advice:
            out.write(f"    · {advice}\n")
        out.write("\n")

    if report.sample_size_warning:
        out.write(f"  {report.sample_size_warning}\n\n")

    if report.recommended_selection_rules:
        out.write("  Recommended selection rules:\n")
        for rule in report.recommended_selection_rules:
            out.write(f"    · {rule}\n")
        out.write("\n")

    out.write("  Reports written:\n")
    out.write("    reports/learning/model_coach_report.json\n")
    out.write("    reports/learning/model_coach_report.md\n")
    out.write("    data/football_intelligence.db (model_coach_reports)\n")
    out.write("\n" + "=" * 72 + "\n")
    return 0


def run_discover_patterns_command(
    *,
    locale: str | None = None,
    competition: str | None = None,
    all_competitions: bool = False,
    stream: TextIO | None = None,
) -> int:
    """CLI handler: pattern discovery from SQLite history."""
    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]

    from worldcup_predictor.learning.patterns import PatternDiscoveryEngine

    engine = PatternDiscoveryEngine()
    if all_competitions:
        report = engine.run_all(write_reports=True)
    else:
        comp_key = resolve_competition(competition)
        print_competition_banner(out, translator, comp_key)
        report = engine.run(competition_key=comp_key, write_reports=True)

    out.write("=" * 72 + "\n")
    out.write(f"  {translator.t('app.title')}\n")
    out.write("  Pattern Discovery — Learning Agent V2\n")
    out.write("=" * 72 + "\n\n")
    out.write("  Advisory only — weights, thresholds, and ML models are not changed.\n\n")
    out.write(f"  Verified rows analyzed: {report.total_rows}\n")
    out.write(f"  Baseline winrate: {_format_pct(report.baseline_winrate)}\n")
    out.write(f"  Patterns discovered: "
              f"{len(report.strongest_patterns) + len(report.failure_causes) + len(report.success_causes)}\n\n")

    if not report.total_rows:
        out.write("  No verified prediction rows in SQLite yet.\n")
        out.write("  Run sync-data and verify-predictions first.\n\n")
    else:
        if report.strongest_patterns:
            out.write("  Strongest patterns:\n")
            for p in report.strongest_patterns[:5]:
                out.write(
                    f"    + {p.label}: {_format_pct(p.winrate)} "
                    f"(n={p.sample_size}, confidence={p.confidence_level})\n"
                )
            out.write("\n")

        if report.weakest_patterns:
            out.write("  Weakest patterns:\n")
            for p in report.weakest_patterns[:5]:
                out.write(
                    f"    - {p.label}: {_format_pct(p.winrate)} "
                    f"(n={p.sample_size}, confidence={p.confidence_level})\n"
                )
            out.write("\n")

        if report.failure_causes:
            out.write("  Failure causes:\n")
            for p in report.failure_causes[:5]:
                out.write(
                    f"    ! {p.label}: {_format_pct(p.winrate)} "
                    f"(baseline {_format_pct(p.baseline_winrate)}, n={p.sample_size})\n"
                )
            out.write("\n")

        if report.success_causes:
            out.write("  Success causes:\n")
            for p in report.success_causes[:5]:
                out.write(
                    f"    ✓ {p.label}: {_format_pct(p.winrate)} "
                    f"(baseline {_format_pct(p.baseline_winrate)}, n={p.sample_size})\n"
                )
            out.write("\n")

        if report.decision_agent_advice:
            out.write("  Decision agent advice:\n")
            for advice in report.decision_agent_advice:
                out.write(f"    · [{advice.priority.upper()}] {advice.message}\n")
            out.write("\n")

        if report.competition_patterns:
            out.write("  Competition-specific highlights:\n")
            for comp, patterns in sorted(report.competition_patterns.items()):
                if patterns:
                    top = patterns[0]
                    out.write(
                        f"    · {comp}: {top.label} ({_format_pct(top.winrate)}, n={top.sample_size})\n"
                    )
            out.write("\n")

    out.write("  Reports written:\n")
    out.write("    reports/learning/pattern_discovery.json\n")
    out.write("    reports/learning/pattern_discovery.md\n")
    out.write("\n" + "=" * 72 + "\n")
    return 0


def run_sync_data_command(
    *,
    competition: str | None = None,
    all_active: bool = False,
    locale: str | None = None,
    stream: TextIO | None = None,
) -> int:
    out = stream or sys.stdout
    settings = get_settings()
    translator = get_translator(locale or settings.default_locale)  # type: ignore[arg-type]

    from worldcup_predictor.ingestion.sync_service import DataSyncService

    service = DataSyncService(settings)
    if all_active:
        results = service.sync_all_active()
        out.write("=" * 72 + "\n")
        out.write("  Data Sync — All Active Competitions\n")
        out.write("=" * 72 + "\n\n")
        for result in results:
            out.write(f"  {result.competition_key}: fixtures={result.fixtures_synced}, results={result.results_synced}\n")
            for warning in result.warnings:
                out.write(f"    ! {warning}\n")
    else:
        comp_key = resolve_competition(competition)
        print_competition_banner(out, translator, comp_key)
        result = service.sync_competition(comp_key)
        out.write(f"  Fixtures synced: {result.fixtures_synced}\n")
        out.write(f"  Results synced: {result.results_synced}\n")
        out.write(f"  Odds snapshots: {result.odds_snapshots}\n")
        out.write(f"  xG snapshots: {result.xg_snapshots}\n")
        out.write(f"  Skipped placeholders: {result.skipped_placeholder}\n")
        for warning in result.warnings:
            out.write(f"  ! {warning}\n")
    out.write("\n  Database: data/football_intelligence.db\n")
    out.write("=" * 72 + "\n")
    return 0


def run_migrate_jsonl_command(
    *,
    competition: str | None = None,
    locale: str | None = None,
    stream: TextIO | None = None,
) -> int:
    out = stream or sys.stdout
    settings = get_settings()
    translator = get_translator(locale or settings.default_locale)  # type: ignore[arg-type]
    comp_key = resolve_competition(competition)
    print_competition_banner(out, translator, comp_key)

    from worldcup_predictor.database.migrate_jsonl import migrate_jsonl_to_db

    result = migrate_jsonl_to_db(competition_key=comp_key)
    out.write("=" * 72 + "\n")
    out.write("  JSONL → SQLite Migration\n")
    out.write("=" * 72 + "\n\n")
    out.write(f"  Predictions imported: {result.predictions_imported}\n")
    out.write(f"  Results imported: {result.results_imported}\n")
    out.write(f"  Verifications imported: {result.verifications_imported}\n")
    if result.errors:
        out.write(f"  Errors: {len(result.errors)}\n")
        for err in result.errors[:5]:
            out.write(f"    · {err}\n")
    out.write("\n  Database: data/football_intelligence.db\n")
    out.write("=" * 72 + "\n")
    return 0


def run_shortlist_command(
    *,
    competition: str | None = None,
    days: int = 3,
    locale: str | None = None,
    stream: TextIO | None = None,
) -> int:
    out = stream or sys.stdout
    settings = get_settings()
    translator = get_translator(locale or settings.default_locale)  # type: ignore[arg-type]
    comp_key = resolve_competition(competition)
    print_competition_banner(out, translator, comp_key)

    from worldcup_predictor.schedule.competition_schedule import create_schedule_service
    from worldcup_predictor.selection.match_selection_engine import MatchSelectionEngine

    schedule = create_schedule_service(settings, competition_key=comp_key)
    fixtures = schedule.get_all_worldcup_fixtures()
    engine = MatchSelectionEngine()
    shortlist = engine.build_shortlist(fixtures, competition_key=comp_key, days=days)

    out.write("=" * 72 + "\n")
    out.write("  Daily Match Shortlist\n")
    out.write("=" * 72 + "\n\n")
    out.write("  Model selection only — not profit or betting advice.\n\n")

    def _print_group(title: str, items: list) -> None:
        out.write(f"  {title} ({len(items)})\n")
        for item in items[:10]:
            out.write(
                f"    · {item.match_name} — score {item.scores.total:.1f} — {item.reason}\n"
            )
        out.write("\n")

    _print_group("AUTO_PREDICT", shortlist.auto_predict)
    _print_group("WATCHLIST", shortlist.watchlist)
    _print_group("WAIT_FOR_LINEUPS", shortlist.wait_for_lineups)
    _print_group("SKIPPED", shortlist.skipped)
    out.write("=" * 72 + "\n")
    return 0


def run_auto_prematch_command(
    *,
    window_hours: float | None = None,
    lineup_final: bool = False,
    selected_only: bool = False,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI handler: automated pre-match prediction scan."""
    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]

    from worldcup_predictor.automation.prematch_scheduler import PreMatchScheduler

    comp_key = resolve_competition(competition)
    print_competition_banner(out, translator, comp_key)

    scheduler = PreMatchScheduler(settings, competition_key=comp_key, locale=active_locale)
    if lineup_final:
        result = scheduler.run_lineup_final_scan()
        mode_label = "Final lineup refresh"
    else:
        hours = window_hours if window_hours is not None else 24.0
        result = scheduler.run_window_scan(window_hours=hours, selected_only=selected_only)
        mode_label = f"Pre-match window ({hours}h)"
        if selected_only:
            mode_label += " — selected only"

    out.write("=" * 72 + "\n")
    out.write(f"  {translator.t('app.title')}\n")
    out.write(f"  Pre-Match Automation — {mode_label}\n")
    out.write("=" * 72 + "\n\n")
    out.write("  Analytical automation only — not betting instruction.\n")
    out.write("  Preliminary versions are labeled when official lineups are missing.\n\n")

    out.write(f"  Matches scanned: {result.matches_scanned}\n")
    out.write(f"  Predictions created: {result.predictions_created}\n")
    out.write(f"  Predictions skipped: {result.predictions_skipped}\n")
    out.write(f"  Predictions refreshed: {result.predictions_refreshed}\n")
    out.write(f"  Errors: {result.errors}\n\n")

    out.write("  Upcoming window counts:\n")
    out.write(f"    Within 24h: {result.window_counts.within_24h}\n")
    out.write(f"    Within 6h: {result.window_counts.within_6h}\n")
    out.write(f"    Within 90m: {result.window_counts.within_90m}\n\n")

    if result.log:
        out.write("-" * 72 + "\n")
        out.write("  Automation log (sample)\n")
        out.write("-" * 72 + "\n")
        for entry in result.log[:20]:
            out.write(
                f"    [{entry.action.upper()}] {entry.match_name} "
                f"({entry.prediction_version or '—'}): {entry.message}\n"
            )
        if len(result.log) > 20:
            out.write(f"    … and {len(result.log) - 20} more entries\n")

    out.write("\n  Reports written:\n")
    out.write("    reports/automation/prematch_automation_summary.json\n")
    out.write("    reports/automation/prematch_automation_summary.md\n")
    out.write("\n" + "=" * 72 + "\n")
    return 0


def run_upcoming_command(
    *,
    limit: int | None = None,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI handler: fetch and display upcoming World Cup 2026 matches."""
    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]

    comp_key = resolve_competition(competition)
    pipeline = UpcomingPipeline(settings, locale=active_locale, competition_key=comp_key)
    result = pipeline.run(limit=limit)

    if not result.success:
        out.write("Pipeline failed.\n")
        for agent_result in result.agent_results:
            if not agent_result.success:
                out.write(f"  [{agent_result.agent_name}] {agent_result.message}\n")
        return 1

    print_competition_banner(out, translator, comp_key)
    _render_header(out, translator, result.fixtures.is_placeholder)
    out.write("\n")

    prediction_by_fixture = {p.fixture_id: p for p in result.predictions}

    for index, fixture in enumerate(result.fixtures.fixtures, start=1):
        prediction = prediction_by_fixture.get(fixture.id)
        _render_fixture_block(out, translator, index, fixture, prediction, active_locale)

    out.write("\n")
    _render_multilingual_disclaimer(out, result.predictions[0] if result.predictions else None)
    return 0


def run_inspect_command(
    *,
    fixture_id: int,
    locale: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI handler: inspect match intelligence for a single fixture."""
    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]

    pipeline = InspectPipeline(settings, locale=active_locale)
    result = pipeline.run(fixture_id=fixture_id)

    if not result.success:
        out.write(f"{translator.t('cli.inspect.header')}: failed\n")
        for agent_result in result.agent_results:
            if not agent_result.success:
                out.write(f"  [{agent_result.agent_name}] {agent_result.message}\n")
        return 1

    _render_inspect_report(out, translator, result.report, active_locale)
    return 0


def run_predict_command(
    *,
    fixture_id: int,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI handler: generate analytical prediction for a single fixture."""
    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]

    comp_key = resolve_competition(competition)
    pipeline = PredictPipeline(settings, locale=active_locale, competition_key=comp_key)
    result = pipeline.run(fixture_id=fixture_id)

    if not result.success:
        out.write(f"{translator.t('cli.predict.header')}: failed\n")
        for agent_result in result.agent_results:
            if not agent_result.success:
                out.write(f"  [{agent_result.agent_name}] {agent_result.message}\n")
        return 1

    _render_predict_report(out, translator, result.prediction, active_locale, comp_key)
    out.write("\n  Stored in data/predictions/prediction_history.jsonl (learning memory).\n")
    return 0


def run_report_command(
    *,
    fixture_id: int,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI handler: professional narrative match report (OpenAI or local rules)."""
    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]

    comp_key = resolve_competition(competition)
    service = OpenAIReasoningService(settings)
    report, success = service.generate_for_fixture(
        fixture_id, locale=active_locale, competition=comp_key
    )  # type: ignore[arg-type]

    if not success:
        out.write(f"{translator.t('cli.report.header')}: {translator.t('cli.report.pipeline_failed')}\n")
        return 1

    _render_professional_report(out, translator, report, active_locale, comp_key)
    return 0


def _render_professional_report(
    out: TextIO,
    translator: Translator,
    report: ProfessionalMatchReport,
    locale: str,
    competition_key: str | None = None,
) -> None:
    out.write("=" * 72 + "\n")
    out.write(f"  {translator.t('app.title')}\n")
    out.write(f"  {translator.t('cli.report.header')}\n")
    out.write("=" * 72 + "\n\n")
    if competition_key:
        print_competition_banner(out, translator, competition_key)
    out.write(f"  {translator.t('cli.report.disclaimer_short')}\n\n")
    out.write(f"  {report.match_name}\n")
    out.write(f"  {translator.t('cli.inspect.fixture_id')}: {report.fixture_id}\n")
    out.write(f"  {translator.t('cli.report.source')}: {report.source}\n")
    if report.watch_only:
        out.write(f"  ⚠ {translator.t('cli.audit.watch_only')}: {translator.t('audit.watch_only_message')}\n")
    out.write("\n")

    out.write("-" * 72 + "\n")
    out.write(f"  {translator.t('cli.report.executive_summary')}\n")
    out.write("-" * 72 + "\n")
    out.write(f"  {report.executive_summary}\n\n")

    out.write("-" * 72 + "\n")
    out.write(f"  {translator.t('cli.report.prediction_summary')}\n")
    out.write("-" * 72 + "\n")
    for key, value in report.prediction_summary.items():
        out.write(f"    {key}: {value}\n")
    out.write("\n")

    if report.audit_highlights:
        out.write("-" * 72 + "\n")
        out.write(f"  {translator.t('cli.report.audit_highlights')}\n")
        out.write("-" * 72 + "\n")
        for item in report.audit_highlights:
            out.write(f"    • {item}\n")
        out.write("\n")

    if report.key_factors:
        out.write("-" * 72 + "\n")
        out.write(f"  {translator.t('cli.report.key_factors')}\n")
        out.write("-" * 72 + "\n")
        for item in report.key_factors:
            out.write(f"    • {item}\n")
        out.write("\n")

    if report.tactical_context:
        out.write("-" * 72 + "\n")
        out.write(f"  {translator.t('cli.report.tactical_context')}\n")
        out.write("-" * 72 + "\n")
        out.write(f"  {report.tactical_context}\n\n")

    if report.risk_notes:
        out.write("-" * 72 + "\n")
        out.write(f"  {translator.t('cli.report.risk_notes')}\n")
        out.write("-" * 72 + "\n")
        for item in report.risk_notes:
            out.write(f"    • {item}\n")
        out.write("\n")

    if report.data_limitations:
        out.write("-" * 72 + "\n")
        out.write(f"  {translator.t('cli.report.data_limitations')}\n")
        out.write("-" * 72 + "\n")
        for item in report.data_limitations:
            out.write(f"    • {item}\n")
        out.write("\n")

    if report.market_analysis_information_only:
        out.write("-" * 72 + "\n")
        out.write(f"  {translator.t('cli.report.market_analysis')}\n")
        out.write("-" * 72 + "\n")
        out.write(f"  {report.market_analysis_information_only}\n\n")

    out.write("-" * 72 + "\n")
    out.write(f"  {translator.t('cli.report.final_view')}\n")
    out.write("-" * 72 + "\n")
    out.write(f"  {report.final_analytical_view}\n\n")

    if report.safety_warnings:
        out.write("-" * 72 + "\n")
        out.write(f"  {translator.t('cli.report.safety_warnings')}\n")
        out.write("-" * 72 + "\n")
        for item in report.safety_warnings:
            out.write(f"    • {item}\n")
        out.write("\n")

    out.write("=" * 72 + "\n")
    out.write(f"  {report.disclaimer}\n")
    out.write("=" * 72 + "\n")


def run_specialists_command(
    *,
    fixture_id: int,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI handler: run specialist agents for a fixture."""
    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]

    comp_key = resolve_competition(competition)
    pipeline = SpecialistsPipeline(settings, locale=active_locale, competition_key=comp_key)
    result = pipeline.run(fixture_id=fixture_id)

    if not result.success:
        out.write(f"{translator.t('cli.specialists.header')}: failed\n")
        for agent_result in result.agent_results:
            if not agent_result.success:
                out.write(f"  [{agent_result.agent_name}] {agent_result.message}\n")
        return 1

    _render_specialists_report(out, translator, result.report, active_locale, comp_key)
    return 0


def _render_specialists_report(
    out: TextIO,
    translator: Translator,
    report: MatchSpecialistReport,
    locale: str,
    competition_key: str | None = None,
) -> None:
    out.write("=" * 72 + "\n")
    out.write(f"  {translator.t('app.title')}\n")
    out.write(f"  {translator.t('cli.specialists.header')}\n")
    out.write("=" * 72 + "\n")
    if competition_key:
        print_competition_banner(out, translator, competition_key)
    out.write(f"\n  {translator.t('cli.inspect.fixture_id')}: {report.fixture_id}\n")
    if report.aggregated_signal_score is not None:
        out.write(
            f"  {translator.t('cli.specialists.aggregated_score')}: "
            f"{report.aggregated_signal_score:.1f}\n"
        )

    order = (
        "weather_agent",
        "referee_agent",
        "lineup_agent",
        "injury_suspension_agent",
        "team_form_agent",
        "tactics_agent",
        "player_quality_agent",
        "odds_market_agent",
        "motivation_psychology_agent",
    )

    for agent_name in order:
        signal = report.signals.get(agent_name)
        if signal:
            _render_specialist_section(out, translator, signal)

    if report.master:
        out.write("\n" + "=" * 72 + "\n")
        out.write(f"  {translator.t('cli.specialists.master')}\n")
        out.write("=" * 72 + "\n")
        _render_signal_body(out, translator, report.master, indent="  ")

        conflicts = report.master.signals.get("conflicts_between_agents") or []
        if conflicts:
            out.write(f"\n  {translator.t('cli.specialists.conflicts')}:\n")
            for item in conflicts:
                out.write(f"    • {item}\n")

        adjustments = report.master.signals.get("recommended_prediction_adjustments") or []
        if adjustments:
            out.write(f"\n  {translator.t('cli.specialists.adjustments')}:\n")
            for item in adjustments:
                out.write(f"    • {item}\n")

        summary = report.master.signals.get("final_context_summary")
        if summary:
            out.write(f"\n  {summary}\n")

    out.write("\n" + "=" * 72 + "\n")
    out.write(f"  {translator.t('cli.specialists.no_prediction')}\n")
    out.write("=" * 72 + "\n")


def _render_specialist_section(out: TextIO, translator: Translator, signal: SpecialistSignal) -> None:
    title_key = f"specialists.{signal.agent_name}"
    title = translator.t(title_key) if title_key else signal.agent_name
    out.write("\n" + "-" * 72 + "\n")
    out.write(f"  {title}\n")
    out.write("-" * 72 + "\n")
    out.write(f"  {translator.t('cli.specialists.status')}: {signal.status}\n")
    _render_signal_body(out, translator, signal, indent="  ")


def _render_signal_body(
    out: TextIO,
    translator: Translator,
    signal: SpecialistSignal,
    indent: str = "  ",
) -> None:
    if signal.impact_score is not None:
        out.write(f"{indent}{translator.t('cli.predict.confidence_score')}: {signal.impact_score}\n")

    if signal.signals:
        out.write(f"{indent}{translator.t('cli.specialists.key_signals')}:\n")
        for key, value in signal.signals.items():
            if key == "informational_disclaimer":
                out.write(f"{indent}  • {value}\n")
            elif isinstance(value, (list, dict)):
                out.write(f"{indent}  • {key}: {_format_signal_value(value)}\n")
            else:
                out.write(f"{indent}  • {key}: {value}\n")

    if signal.warnings:
        out.write(f"{indent}{translator.t('cli.specialists.warnings')}:\n")
        for warning in signal.warnings:
            out.write(f"{indent}  • {warning}\n")

    if signal.missing_data:
        out.write(f"{indent}{translator.t('cli.inspect.missing')}: {', '.join(signal.missing_data)}\n")

    if signal.notes:
        out.write(f"{indent}Note: {signal.notes}\n")


def _format_signal_value(value: object) -> str:
    if isinstance(value, list):
        if not value:
            return "[]"
        if isinstance(value[0], dict):
            return f"[{len(value)} items]"
        return ", ".join(str(v) for v in value[:5])
    if isinstance(value, dict):
        return ", ".join(f"{k}={v}" for k, v in list(value.items())[:5])
    return str(value)


def _render_predict_report(
    out: TextIO,
    translator: Translator,
    prediction: MatchPrediction,
    locale: str,
    competition_key: str | None = None,
) -> None:
    out.write("=" * 72 + "\n")
    out.write(f"  {translator.t('app.title')}\n")
    out.write(f"  {translator.t('cli.predict.header')}\n")
    out.write("=" * 72 + "\n\n")
    if competition_key:
        print_competition_banner(out, translator, competition_key)

    out.write(f"  {prediction.match_name}\n")
    if prediction.kickoff_utc:
        out.write(f"  {translator.t('cli.fixture.kickoff')}: {prediction.kickoff_utc:%Y-%m-%d %H:%M}\n")
    if prediction.stage:
        out.write(f"  {translator.t('cli.predict.competition')}: {prediction.stage}\n")
    out.write(f"  {translator.t('cli.inspect.fixture_id')}: {prediction.fixture_id}\n")

    out.write("\n" + "-" * 72 + "\n")
    out.write(f"  {translator.t('cli.predict.one_x_two')}\n")
    out.write("-" * 72 + "\n")
    label = prediction.one_x_two.label.get(locale) if prediction.one_x_two.label else prediction.one_x_two.selection  # type: ignore[arg-type]
    out.write(f"    {label}\n")
    if prediction.one_x_two.probability is not None:
        out.write(
            f"    {translator.t('cli.predict.probability')}: "
            f"{prediction.one_x_two.probability:.0%}\n"
        )

    out.write("\n" + "-" * 72 + "\n")
    out.write(f"  {translator.t('cli.predict.over_under')}\n")
    out.write("-" * 72 + "\n")
    ou_label = prediction.over_under.label.get(locale) if prediction.over_under.label else prediction.over_under.selection  # type: ignore[arg-type]
    out.write(f"    {ou_label}\n")
    if prediction.over_under.probability is not None:
        out.write(
            f"    {translator.t('cli.predict.probability')}: "
            f"{prediction.over_under.probability:.0%}\n"
        )

    out.write("\n" + "-" * 72 + "\n")
    out.write(f"  {translator.t('cli.predict.halftime')}\n")
    out.write("-" * 72 + "\n")
    out.write(f"    {prediction.halftime.estimated_total_goals}\n")
    if prediction.halftime.note:
        out.write(f"    {prediction.halftime.note.get(locale)}\n")  # type: ignore[arg-type]

    out.write("\n" + "-" * 72 + "\n")
    out.write(f"  {translator.t('cli.predict.first_goal')}\n")
    out.write("-" * 72 + "\n")
    out.write(f"    {translator.t('cli.predict.first_goal_team')}: {prediction.first_goal.team}\n")
    out.write(
        f"    {translator.t('cli.predict.first_goal_player')}: "
        f"{prediction.first_goal.player or translator.t('cli.inspect.none')}\n"
    )
    out.write(
        f"    {translator.t('cli.predict.first_goal_minute')}: "
        f"{prediction.first_goal.minute_range or translator.t('cli.inspect.none')}\n"
    )

    if prediction.scoreline:
        out.write(
            f"\n  {translator.t('cli.predict.scoreline')}: {prediction.scoreline.label}\n"
        )

    out.write("\n" + "-" * 72 + "\n")
    out.write(f"  {translator.t('cli.predict.confidence')}\n")
    out.write("-" * 72 + "\n")
    out.write(f"    {translator.t('cli.predict.confidence_score')}: {prediction.confidence_score:.0f}/100\n")
    out.write(f"    {translator.t('cli.prediction.confidence')}: {prediction.confidence_level.value}\n")
    out.write(f"    {translator.t('cli.predict.risk_level')}: {prediction.risk_level}\n")

    no_bet_text = (
        translator.t("cli.predict.no_bet_true")
        if prediction.no_bet_flag
        else translator.t("cli.predict.no_bet_false")
    )
    out.write(f"    {translator.t('cli.predict.no_bet_flag')}: {no_bet_text}\n")

    if prediction.missing_data_warnings:
        out.write(f"\n  {translator.t('cli.predict.missing_data')}:\n")
        out.write(f"    {prediction.missing_data_warnings.get(locale)}\n")  # type: ignore[arg-type]

    if prediction.lineup_warning:
        out.write(f"\n  {translator.t('cli.predict.lineup_warning')}:\n")
        out.write(f"    {prediction.lineup_warning.get(locale)}\n")  # type: ignore[arg-type]

    if prediction.explanation:
        out.write("\n" + "-" * 72 + "\n")
        out.write(f"  {translator.t('cli.predict.explanation')}\n")
        out.write("-" * 72 + "\n")
        out.write(f"    {prediction.explanation.get(locale)}\n")  # type: ignore[arg-type]

    out.write("\n" + "=" * 72 + "\n")
    out.write(f"  {translator.t('cli.predict.disclaimer')}\n")
    out.write("=" * 72 + "\n")
    if prediction.disclaimer:
        out.write(f"  {prediction.disclaimer.get(locale)}\n")  # type: ignore[arg-type]

    if prediction.audit_report:
        _render_audit_brief(out, translator, prediction.audit_report, locale)


def run_audit_command(
    *,
    fixture_id: int,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI handler: weighted decision audit for a single fixture."""
    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]

    comp_key = resolve_competition(competition)
    pipeline = AuditPipeline(settings, locale=active_locale, competition_key=comp_key)
    result = pipeline.run(fixture_id=fixture_id)

    if not result.success:
        out.write(f"{translator.t('cli.audit.header')}: failed\n")
        for agent_result in result.agent_results:
            if not agent_result.success:
                out.write(f"  [{agent_result.agent_name}] {agent_result.message}\n")
        return 1

    _render_audit_report(out, translator, result.prediction, active_locale, comp_key)
    return 0


def _factor_label(translator: Translator, factor_name: str) -> str:
    key = f"audit.factor.{factor_name}"
    label = translator.t(key)
    return label if label != key else factor_name.replace("_", " ").title()


def _render_audit_brief(
    out: TextIO,
    translator: Translator,
    audit: PredictionAuditReport,
    locale: str,
) -> None:
    out.write("\n" + "-" * 72 + "\n")
    out.write(f"  {translator.t('cli.audit.brief_summary')}\n")
    out.write("-" * 72 + "\n")
    if audit.supported_factors:
        top = audit.supported_factors[:3]
        out.write(f"  {translator.t('cli.audit.supported')}: ")
        out.write(", ".join(_factor_label(translator, f.factor_name) for f in top) + "\n")
    if audit.trace and audit.trace.watch_only:
        out.write(f"  {translator.t('cli.audit.watch_only')}: {translator.t('audit.watch_only_message')}\n")


def _render_audit_report(
    out: TextIO,
    translator: Translator,
    prediction: MatchPrediction,
    locale: str,
    competition_key: str | None = None,
) -> None:
    _render_predict_report(out, translator, prediction, locale, competition_key)

    audit = prediction.audit_report
    if audit is None:
        out.write("\n  (No audit report available)\n")
        return

    out.write("\n" + "=" * 72 + "\n")
    out.write(f"  {translator.t('cli.audit.header')}\n")
    out.write("=" * 72 + "\n")

    out.write(f"\n  {translator.t('cli.audit.final_prediction')}\n")
    out.write(f"    1X2: {prediction.one_x_two.selection}\n")
    out.write(f"    O/U 2.5: {prediction.over_under.selection}\n")
    out.write(f"    {translator.t('cli.predict.halftime')}: {prediction.halftime.estimated_total_goals}\n")
    out.write(f"    {translator.t('cli.predict.first_goal_team')}: {prediction.first_goal.team}\n")
    out.write(
        f"    {translator.t('cli.predict.first_goal_player')}: "
        f"{prediction.first_goal.player or translator.t('cli.inspect.none')}\n"
    )

    if audit.factor_weights:
        out.write("\n" + "-" * 72 + "\n")
        out.write(f"  {translator.t('cli.audit.factor_weights')}\n")
        out.write("-" * 72 + "\n")
        for name, weight in audit.factor_weights.items():
            out.write(f"    • {_factor_label(translator, name)}: {weight:.0f}%\n")

    def _render_contribs(title_key: str, contribs: list) -> None:
        if not contribs:
            return
        out.write("\n" + "-" * 72 + "\n")
        out.write(f"  {translator.t(title_key)}\n")
        out.write("-" * 72 + "\n")
        for c in contribs:
            out.write(
                f"    • {_factor_label(translator, c.factor_name)} "
                f"(weight {c.weight_pct:.0f}%, score {c.score:.0f}, "
                f"contrib {c.contribution:+.1f})\n"
            )

    _render_contribs("cli.audit.supported", audit.supported_factors)
    _render_contribs("cli.audit.opposed", audit.opposed_factors)
    _render_contribs("cli.audit.neutral", audit.neutral_factors)

    if audit.conflicts:
        out.write("\n" + "-" * 72 + "\n")
        out.write(f"  {translator.t('cli.audit.conflicts')}\n")
        out.write("-" * 72 + "\n")
        for conflict in audit.conflicts:
            out.write(f"    • [{conflict.severity}] {conflict.description}\n")

    if audit.limitations:
        out.write("\n" + "-" * 72 + "\n")
        out.write(f"  {translator.t('cli.audit.limitations')}\n")
        out.write("-" * 72 + "\n")
        for lim in audit.limitations:
            out.write(f"    • {lim.field}: {lim.impact}\n")

    if audit.market_disagreement_warnings:
        out.write("\n" + "-" * 72 + "\n")
        out.write(f"  {translator.t('cli.audit.market_disagreement')}\n")
        out.write("-" * 72 + "\n")
        for warning in audit.market_disagreement_warnings:
            out.write(f"    • {warning}\n")

    if audit.trace:
        trace = audit.trace
        out.write("\n" + "-" * 72 + "\n")
        out.write(f"  {translator.t('cli.audit.confidence_caps')}\n")
        out.write("-" * 72 + "\n")
        if trace.confidence_caps_applied:
            for cap in trace.confidence_caps_applied:
                out.write(f"    • {cap}\n")
        else:
            out.write(f"    {translator.t('cli.inspect.none')}\n")

        out.write("\n" + "-" * 72 + "\n")
        out.write(f"  {translator.t('cli.audit.confidence_reductions')}\n")
        out.write("-" * 72 + "\n")
        if trace.confidence_reductions:
            for item in trace.confidence_reductions:
                out.write(f"    • {item}\n")
        else:
            out.write(f"    {translator.t('cli.inspect.none')}\n")

        out.write("\n" + "-" * 72 + "\n")
        out.write(f"  {translator.t('cli.audit.no_bet_reasons')}\n")
        out.write("-" * 72 + "\n")
        for reason in trace.no_bet_reasons:
            out.write(f"    • {reason}\n")

        out.write(
            f"\n  Baseline confidence: {trace.baseline_confidence:.0f} → "
            f"Final: {trace.final_confidence:.0f}\n"
        )
        if audit.first_goal_player_confidence is not None:
            out.write(
                f"  {translator.t('cli.audit.first_goal_player_confidence')}: "
                f"{audit.first_goal_player_confidence:.0f}/100\n"
            )
        if trace.watch_only:
            out.write(f"\n  {translator.t('cli.audit.watch_only')}:\n")
            out.write(f"    {translator.t('audit.watch_only_message')}\n")
        out.write(f"\n  {translator.t('cli.audit.analytical_edge')}: {trace.analytical_edge_note}\n")

    out.write("\n" + "=" * 72 + "\n")
    out.write(f"  {translator.t('cli.audit.disclaimer')}\n")
    out.write("=" * 72 + "\n")
    out.write(f"  {translator.t('audit.disclaimer')}\n")


def _source_label(translator: Translator, source: str) -> str:
    mapping = {
        "placeholder": "cli.inspect.placeholder",
        "live": "cli.inspect.live",
        "cache": "cli.inspect.cached",
    }
    return translator.t(mapping.get(source, "cli.inspect.placeholder"))


def _render_inspect_report(
    out: TextIO,
    translator: Translator,
    report: MatchIntelligenceReport,
    locale: str,
) -> None:
    out.write("=" * 72 + "\n")
    out.write(f"  {translator.t('app.title')}\n")
    out.write(f"  {translator.t('cli.inspect.header')}\n")
    out.write("=" * 72 + "\n\n")

    fixture = report.fixture
    if fixture:
        out.write(f"  {fixture.display_match}\n")
        out.write(f"  {translator.t('cli.fixture.kickoff')}: {fixture.kickoff_utc:%Y-%m-%d %H:%M}\n")
        out.write(f"  {translator.t('cli.fixture.venue')}: {fixture.venue}\n")
        out.write(f"  {translator.t('cli.fixture.stage')}: {fixture.stage}\n")

    out.write(f"  {translator.t('cli.inspect.fixture_id')}: {report.fixture_id}\n")
    out.write(f"  {translator.t('cli.inspect.data_source')}: {_source_label(translator, report.source)}\n")

    if report.data_quality:
        out.write(
            f"  {translator.t('cli.inspect.quality_score')}: "
            f"{report.data_quality.score:.0%}\n"
        )
        out.write(
            f"  {translator.t('cli.inspect.quality_grade')}: "
            f"{report.data_quality.grade}\n"
        )

    out.write("\n" + "-" * 72 + "\n")
    out.write(f"  {translator.t('cli.inspect.available')}\n")
    out.write("-" * 72 + "\n")
    available = report.data_quality.available_fields if report.data_quality else []
    if available:
        for field in available:
            out.write(f"    • {field}\n")
    else:
        out.write(f"    {translator.t('cli.inspect.none')}\n")

    out.write("\n" + "-" * 72 + "\n")
    out.write(f"  {translator.t('cli.inspect.missing')}\n")
    out.write("-" * 72 + "\n")
    if report.missing_data:
        for field in report.missing_data:
            out.write(f"    • {field}\n")
    else:
        out.write(f"    {translator.t('cli.inspect.none')}\n")

    if report.data_quality and report.data_quality.errors:
        out.write("\n" + "-" * 72 + "\n")
        out.write(f"  {translator.t('cli.inspect.errors')}\n")
        out.write("-" * 72 + "\n")
        for error in report.data_quality.errors:
            out.write(f"    • {error}\n")

    out.write("\n" + "-" * 72 + "\n")
    out.write(f"  {translator.t('cli.inspect.detail')}\n")
    out.write("-" * 72 + "\n")

    _render_team_section(out, translator, report.home_team, side="home")
    _render_team_section(out, translator, report.away_team, side="away")

    h2h_count = (report.head_to_head or {}).get("count", 0)
    out.write(f"\n  {translator.t('cli.inspect.h2h')}: ")
    out.write(f"{h2h_count} {translator.t('cli.inspect.meetings')}\n" if h2h_count else f"{translator.t('cli.inspect.no')}\n")

    lineups_available = bool(report.lineups and report.lineups.get("available"))
    out.write(f"  {translator.t('cli.inspect.lineups')}: ")
    out.write(f"{translator.t('cli.inspect.yes')}\n" if lineups_available else f"{translator.t('cli.inspect.no')}\n")

    stats_available = bool(report.fixture_statistics and report.fixture_statistics.get("items"))
    out.write(f"  {translator.t('cli.inspect.fixture_stats')}: ")
    out.write(f"{translator.t('cli.inspect.yes')}\n" if stats_available else f"{translator.t('cli.inspect.no')}\n")

    events_count = len(report.fixture_events or [])
    out.write(f"  {translator.t('cli.inspect.events')}: {events_count}\n")

    odds_available = bool(report.odds and report.odds.available)
    out.write(f"  {translator.t('cli.inspect.odds')}: ")
    out.write(f"{translator.t('cli.inspect.yes')}\n" if odds_available else f"{translator.t('cli.inspect.no')}\n")
    if report.odds and report.odds.available:
        out.write(f"    ({report.odds.note})\n")

    out.write("\n" + "=" * 72 + "\n")
    out.write(f"  {translator.t('cli.inspect.no_prediction')}\n")
    out.write(f"  {translator.t('cli.inspect.no_betting')}\n")
    out.write("=" * 72 + "\n")


def _render_team_section(out: TextIO, translator: Translator, team, side: str) -> None:
    out.write(f"\n  [{side.upper()}] {team.team_name}\n")
    form_display = "".join(team.form) if team.form else translator.t("cli.inspect.none")
    out.write(f"    {translator.t('cli.inspect.team_form')}: {form_display}\n")
    has_stats = translator.t("cli.inspect.yes") if team.statistics else translator.t("cli.inspect.no")
    out.write(f"    {translator.t('cli.inspect.team_stats')}: {has_stats}\n")
    injury_count = len(team.injuries.players) if team.injuries else 0
    out.write(f"    {translator.t('cli.inspect.injuries')}: {injury_count}\n")


def _render_header(out: TextIO, translator: Translator, is_placeholder: bool) -> None:
    out.write("=" * 72 + "\n")
    out.write(f"  {translator.t('app.title')}\n")
    out.write(f"  {translator.t('app.subtitle')}\n")
    out.write("=" * 72 + "\n")
    out.write(f"\n{translator.t('cli.upcoming.header')}\n")
    source_key = (
        "cli.upcoming.source_placeholder"
        if is_placeholder
        else "cli.upcoming.source_live"
    )
    out.write(f"{translator.t(source_key)}\n")


def _render_fixture_block(
    out: TextIO,
    translator: Translator,
    index: int,
    fixture: Fixture,
    prediction: PredictionPlaceholder | None,
    locale: str,
) -> None:
    out.write("\n" + "-" * 72 + "\n")
    out.write(f"  #{index}  {fixture.display_match}\n")
    out.write("-" * 72 + "\n")
    out.write(f"  {translator.t('cli.fixture.kickoff')}: {fixture.kickoff_utc:%Y-%m-%d %H:%M}\n")
    out.write(f"  {translator.t('cli.fixture.venue')}: {fixture.venue}\n")
    out.write(f"  {translator.t('cli.fixture.stage')}: {fixture.stage}\n")
    out.write(f"  {translator.t('cli.fixture.status')}: {fixture.status}\n")
    out.write(f"  Fixture ID: {fixture.id}  |  Source: {fixture.source}\n")

    if prediction is None:
        return

    phase = prediction.metadata.get("phase", "1")
    if phase == "5":
        envelope_label = "Prediction summary (Phase 5 weighted + audit)"
    elif phase == "3":
        envelope_label = "Prediction summary (Phase 3 analytical)"
    else:
        envelope_label = "Prediction envelope (Phase 1 placeholder)"
    out.write(f"\n  --- {envelope_label} ---\n")
    out.write(f"  {translator.t('cli.prediction.confidence')}: {prediction.confidence_level.value}\n")

    score_label = translator.t("cli.prediction.confidence_score")
    score_value = (
        f"{prediction.confidence_score:.0f}/100"
        if prediction.confidence_score is not None
        else translator.t("cli.prediction.not_available")
    )
    out.write(f"  {score_label}: {score_value}\n")

    if phase == "3" and prediction.metadata.get("one_x_two"):
        out.write(f"  {translator.t('cli.predict.one_x_two')}: {prediction.metadata['one_x_two']}\n")
        no_bet = prediction.metadata.get("no_bet_flag", "True")
        out.write(f"  {translator.t('cli.predict.no_bet_flag')}: {no_bet}\n")

    if prediction.confidence_note:
        out.write(f"  Note ({locale}): {prediction.confidence_note.get(locale)}\n")  # type: ignore[arg-type]

    if prediction.summary:
        out.write(
            f"  {translator.t('cli.prediction.summary')} ({locale}): {prediction.summary.get(locale)}\n"  # type: ignore[arg-type]
        )

    if prediction.risk:
        out.write(
            f"  {translator.t('cli.prediction.risk')} ({locale}): {prediction.risk.warnings.get(locale)}\n"  # type: ignore[arg-type]
        )


def _render_multilingual_disclaimer(
    out: TextIO,
    prediction: PredictionPlaceholder | None,
) -> None:
    if prediction is None or prediction.risk is None:
        return

    out.write("=" * 72 + "\n")
    out.write("  Risk disclaimers (EN / DE / FA)\n")
    out.write("=" * 72 + "\n")
    out.write(f"  [EN] {prediction.risk.disclaimer.en}\n")
    out.write(f"  [DE] {prediction.risk.disclaimer.de}\n")
    out.write(f"  [FA] {prediction.risk.disclaimer.fa}\n")


def run_odds_consensus_command(
    *,
    fixture_id: int,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI: market consensus for a fixture."""
    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]
    comp_key = resolve_competition(competition)

    from worldcup_predictor.agents.match_intelligence_builder import MatchIntelligenceBuilder
    from worldcup_predictor.clients.api_football import ApiFootballClient
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    from worldcup_predictor.odds.market_consensus_agent import build_market_consensus

    print_competition_banner(out, translator, comp_key)
    report = MatchIntelligenceBuilder(ApiFootballClient(settings)).build_by_fixture_id(fixture_id)
    snapshots: list[dict] = []
    try:
        repo = FootballIntelligenceRepository()
        snapshots = repo.fetch_odds_snapshots(fixture_id)
        repo.close()
    except Exception:
        pass

    signal = build_market_consensus(
        report,
        supplemental=getattr(report, "supplemental_sources", None) or {},
        stored_snapshots=snapshots,
    )

    out.write("=" * 72 + "\n")
    out.write("  Market Consensus — analysis only, not betting advice\n")
    out.write("=" * 72 + "\n\n")
    out.write(f"  Fixture: {fixture_id}\n")
    out.write(f"  Market favorite: {signal.market_favorite}\n")
    out.write(f"  Consensus strength: {signal.consensus_strength}/100\n")
    out.write(f"  Bookmakers used (1X2): {signal.bookmaker_count_1x2}\n")
    out.write(f"  Bookmakers used (O/U 2.5): {signal.bookmaker_count_ou25}\n")
    out.write(f"  Aggregation: {signal.aggregation_method}\n")
    out.write(f"  Bookmaker disagreement (1X2): {signal.bookmaker_disagreement_level}\n")
    out.write(f"  Bookmaker disagreement (O/U): {signal.bookmaker_disagreement_level_ou25}\n")
    out.write(f"  Bookmaker disagreement score: {signal.bookmaker_disagreement_score:.1%}\n")
    out.write(f"  Model/market agreement: {signal.model_market_agreement}\n")
    out.write(f"  Market supports model: {signal.market_supports_model}\n\n")
    out.write("  Implied probabilities:\n")
    out.write(f"    Home: {_format_pct(signal.home_implied_probability)}\n")
    out.write(f"    Draw: {_format_pct(signal.draw_implied_probability)}\n")
    out.write(f"    Away: {_format_pct(signal.away_implied_probability)}\n")
    out.write(f"    Over 2.5: {_format_pct(signal.over_2_5_probability)}\n")
    out.write(f"    Under 2.5: {_format_pct(signal.under_2_5_probability)}\n\n")
    if signal.notes:
        out.write("  Notes:\n")
        for note in signal.notes:
            out.write(f"    • {note}\n")
    out.write(f"\n  {signal.informational_disclaimer}\n")
    out.write("=" * 72 + "\n")
    return 0


def run_lineup_intelligence_command(
    *,
    fixture_id: int,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI: Lineup Intelligence V2 debug output for a fixture."""
    import json

    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]
    comp_key = resolve_competition(competition)

    from worldcup_predictor.agents.match_intelligence_builder import MatchIntelligenceBuilder
    from worldcup_predictor.clients.api_football import ApiFootballClient
    from worldcup_predictor.lineups.lineup_intelligence_engine import build_lineup_intelligence

    print_competition_banner(out, translator, comp_key)
    api = ApiFootballClient(settings)
    report = MatchIntelligenceBuilder(api).build_by_fixture_id(fixture_id)
    result = build_lineup_intelligence(report, api_client=api)

    out.write("=" * 72 + "\n")
    out.write("  Lineup Intelligence V2 — analysis only, not betting advice\n")
    out.write("=" * 72 + "\n\n")
    out.write(f"  Fixture: {fixture_id}\n")
    out.write(f"  Summary: {result.summary}\n\n")
    out.write(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    out.write("\n\n")
    out.write("=" * 72 + "\n")
    return 0


def run_injury_intelligence_command(
    *,
    fixture_id: int,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI: Injury & Suspension Intelligence V2 debug output for a fixture."""
    import json

    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]
    comp_key = resolve_competition(competition)

    from worldcup_predictor.agents.match_intelligence_builder import MatchIntelligenceBuilder
    from worldcup_predictor.clients.api_football import ApiFootballClient
    from worldcup_predictor.injuries.injury_intelligence_engine import build_injury_intelligence

    print_competition_banner(out, translator, comp_key)
    api = ApiFootballClient(settings)
    report = MatchIntelligenceBuilder(api).build_by_fixture_id(fixture_id)
    result = build_injury_intelligence(report)

    out.write("=" * 72 + "\n")
    out.write("  Injury & Suspension Intelligence V2 — analysis only, not betting advice\n")
    out.write("=" * 72 + "\n\n")
    out.write(f"  Fixture: {fixture_id}\n")
    out.write(f"  Summary: {result.summary}\n\n")
    out.write(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    out.write("\n\n")
    out.write("=" * 72 + "\n")
    return 0


def run_explain_prediction_command(
    *,
    fixture_id: int,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI: Prediction Explainability & Final Report V2 for a fixture."""
    import json

    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]
    comp_key = resolve_competition(competition)

    from worldcup_predictor.agents.base import AgentContext
    from worldcup_predictor.agents.data_collector_agent import DataCollectorAgent
    from worldcup_predictor.agents.prediction_agent import PredictionAgent
    from worldcup_predictor.agents.specialists.orchestrator import SpecialistOrchestrator
    from worldcup_predictor.domain.prediction import MatchPrediction
    from worldcup_predictor.explainability.prediction_explainability_engine import build_prediction_explainability
    from worldcup_predictor.schedule.context_loader import load_tournament_context

    print_competition_banner(out, translator, comp_key)
    ctx = AgentContext(settings=settings, competition_key=comp_key, locale=active_locale)
    load_tournament_context(ctx)

    collector = DataCollectorAgent(ctx)
    if not collector.run(fixture_id=fixture_id).success:
        final = build_prediction_explainability(None, None)
    else:
        SpecialistOrchestrator(ctx).run(fixture_id=fixture_id)
        pred_result = PredictionAgent(ctx).run(fixture_id=fixture_id)
        report = (ctx.shared.get("intelligence_reports") or {}).get(fixture_id)
        prediction = pred_result.data if pred_result.success and isinstance(pred_result.data, MatchPrediction) else None
        specialist = (ctx.shared.get("specialist_reports") or {}).get(fixture_id)
        if report and specialist and not getattr(report, "specialist_report", None):
            report.specialist_report = specialist
        final = build_prediction_explainability(prediction, report, specialist_report=specialist)

    out.write("=" * 72 + "\n")
    out.write("  Prediction Explainability & Final Report V2 — analysis only, not betting advice\n")
    out.write("=" * 72 + "\n\n")
    out.write(f"  Fixture: {fixture_id}\n")
    out.write(f"  Executive summary: {final.executive_summary}\n\n")
    out.write(json.dumps(final.to_dict(), indent=2, ensure_ascii=False))
    out.write("\n\n")
    out.write("=" * 72 + "\n")
    return 0


def run_market_intelligence_command(
    *,
    fixture_id: int,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI: Sharp Money & Market Intelligence V2 for a fixture."""
    import json

    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]
    comp_key = resolve_competition(competition)

    from worldcup_predictor.agents.match_intelligence_builder import MatchIntelligenceBuilder
    from worldcup_predictor.clients.api_football import ApiFootballClient
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    from worldcup_predictor.odds.sharp_money_intelligence_engine import build_sharp_money_intelligence
    from worldcup_predictor.odds.snapshot_service import OddsSnapshotService

    print_competition_banner(out, translator, comp_key)
    api = ApiFootballClient(settings)
    report = MatchIntelligenceBuilder(api).build_by_fixture_id(fixture_id)
    snapshots: list[dict] = []
    try:
        repo = FootballIntelligenceRepository()
        OddsSnapshotService(repo).persist_from_report(report)
        snapshots = repo.fetch_odds_snapshots(fixture_id)
        repo.close()
    except Exception:
        pass

    result = build_sharp_money_intelligence(report, stored_snapshots=snapshots)

    out.write("=" * 72 + "\n")
    out.write("  Sharp Money & Market Intelligence V2 — analysis only, not betting advice\n")
    out.write("=" * 72 + "\n\n")
    out.write(f"  Fixture: {fixture_id}\n")
    out.write(f"  Summary: {result.summary}\n\n")
    out.write(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    out.write("\n\n")
    out.write("=" * 72 + "\n")
    return 0


def run_odds_movement_command(
    *,
    fixture_id: int,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI: odds movement for a fixture."""
    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]
    comp_key = resolve_competition(competition)

    from worldcup_predictor.agents.match_intelligence_builder import MatchIntelligenceBuilder
    from worldcup_predictor.clients.api_football import ApiFootballClient
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    from worldcup_predictor.odds.odds_movement_agent import build_odds_movement

    print_competition_banner(out, translator, comp_key)
    report = MatchIntelligenceBuilder(ApiFootballClient(settings)).build_by_fixture_id(fixture_id)
    supplemental = getattr(report, "supplemental_sources", None) or {}
    snapshots: list[dict] = []
    try:
        repo = FootballIntelligenceRepository()
        snapshots = repo.fetch_odds_snapshots(fixture_id)
        repo.close()
    except Exception:
        pass

    signal = build_odds_movement(
        fixture_id=fixture_id,
        supplemental=supplemental,
        stored_snapshots=snapshots,
    )

    out.write("=" * 72 + "\n")
    out.write("  Odds Movement — analysis only, not betting advice\n")
    out.write("=" * 72 + "\n\n")
    out.write(f"  Fixture: {fixture_id}\n")
    out.write(f"  Snapshots: {signal.snapshot_count}\n")
    if signal.warning:
        out.write(f"  Warning: {signal.warning}\n")
    out.write(f"  Strongest move: {signal.strongest_move or 'n/a'}\n")
    out.write(f"  Movement confidence: {signal.movement_confidence}/100\n\n")
    out.write(f"  Home movement: {_format_move(signal.home_movement)}\n")
    out.write(f"  Draw movement: {_format_move(signal.draw_movement)}\n")
    out.write(f"  Away movement: {_format_move(signal.away_movement)}\n")
    out.write(f"  Over movement: {_format_move(signal.over_movement)}\n")
    out.write(f"  Under movement: {_format_move(signal.under_movement)}\n")
    if signal.market_drift:
        out.write(f"\n  Market drift: {signal.market_drift}\n")
    out.write(f"\n  {signal.informational_disclaimer}\n")
    out.write("=" * 72 + "\n")
    return 0


def run_league_learning_command(
    *,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI: league-specific learning profile."""
    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]
    comp_key = resolve_competition(competition)

    from worldcup_predictor.odds.league_learning import LeagueLearningEngine

    print_competition_banner(out, translator, comp_key)
    engine = LeagueLearningEngine()
    profile = engine.build_profile(comp_key)

    out.write("=" * 72 + "\n")
    out.write("  League-specific Learning — analysis only\n")
    out.write("=" * 72 + "\n\n")
    out.write(f"  Competition: {profile.competition_name} ({profile.competition_key})\n")
    out.write(f"  Evaluated matches: {profile.evaluated_matches}\n")
    out.write(f"  Strongest market: {profile.strongest_market or 'n/a'}\n")
    out.write(f"  Weakest market: {profile.weakest_market or 'n/a'}\n")
    if profile.sample_size_warning:
        out.write(f"  Warning: {profile.sample_size_warning}\n")
    out.write("\n  Market winrates:\n")
    for market, rate in profile.market_winrates.items():
        out.write(f"    {market}: {_format_pct(rate)}\n")
    out.write("\n  Confidence reliability:\n")
    for bucket, rate in profile.confidence_reliability.items():
        out.write(f"    {bucket}: {_format_pct(rate)}\n")
    out.write("\n  Data quality reliability:\n")
    for bucket, rate in profile.data_quality_reliability.items():
        out.write(f"    {bucket}: {_format_pct(rate)}\n")
    if profile.recommended_rules:
        out.write("\n  Recommended rules:\n")
        for rule in profile.recommended_rules:
            out.write(f"    • {rule}\n")
    out.write("\n  Model improvement analysis — not profit or betting advice.\n")
    out.write("=" * 72 + "\n")
    return 0


def run_tournament_intelligence_command(
    *,
    fixture_id: int,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI: Tournament Intelligence V2 for a fixture."""
    import json

    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]
    comp_key = resolve_competition(competition)

    from worldcup_predictor.agents.base import AgentContext
    from worldcup_predictor.agents.match_intelligence_builder import MatchIntelligenceBuilder
    from worldcup_predictor.clients.api_football import ApiFootballClient
    from worldcup_predictor.schedule.context_loader import fixture_tournament_context, load_tournament_context
    from worldcup_predictor.tournament.tournament_intelligence_engine import build_tournament_intelligence

    print_competition_banner(out, translator, comp_key)
    ctx = AgentContext(settings=settings, competition_key=comp_key, locale=active_locale)
    load_tournament_context(ctx)
    report = MatchIntelligenceBuilder(ApiFootballClient(settings)).build_by_fixture_id(fixture_id)
    tctx = fixture_tournament_context(ctx, fixture_id)
    result = build_tournament_intelligence(report, tournament_context=tctx)

    out.write("=" * 72 + "\n")
    out.write("  Tournament Intelligence V2 — analysis only, not betting advice\n")
    out.write("=" * 72 + "\n\n")
    out.write(f"  Fixture: {fixture_id}\n")
    out.write(f"  Summary: {result.summary}\n\n")
    out.write(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    out.write("\n\n")
    out.write("=" * 72 + "\n")
    return 0


def run_elo_intelligence_command(
    *,
    fixture_id: int,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI: ELO & Team Strength Intelligence V2 for a fixture."""
    import json

    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]
    comp_key = resolve_competition(competition)

    from worldcup_predictor.agents.match_intelligence_builder import MatchIntelligenceBuilder
    from worldcup_predictor.clients.api_football import ApiFootballClient
    from worldcup_predictor.strength.team_strength_intelligence_engine import build_elo_team_strength_intelligence

    print_competition_banner(out, translator, comp_key)
    report = MatchIntelligenceBuilder(ApiFootballClient(settings)).build_by_fixture_id(fixture_id)
    result = build_elo_team_strength_intelligence(report)

    out.write("=" * 72 + "\n")
    out.write("  ELO & Team Strength Intelligence V2 — analysis only, not betting advice\n")
    out.write("=" * 72 + "\n\n")
    out.write(f"  Fixture: {fixture_id}\n")
    out.write(f"  Summary: {result.summary}\n\n")
    out.write(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    out.write("\n\n")
    out.write("=" * 72 + "\n")
    return 0


def run_xg_intelligence_command(
    *,
    fixture_id: int,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI: xG & Chance Quality Intelligence V2 for a fixture."""
    import json

    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]
    comp_key = resolve_competition(competition)

    from worldcup_predictor.agents.match_intelligence_builder import MatchIntelligenceBuilder
    from worldcup_predictor.clients.api_football import ApiFootballClient
    from worldcup_predictor.chance_quality.xg_chance_quality_intelligence_engine import (
        build_xg_chance_quality_intelligence,
    )

    print_competition_banner(out, translator, comp_key)
    report = MatchIntelligenceBuilder(ApiFootballClient(settings)).build_by_fixture_id(fixture_id)
    result = build_xg_chance_quality_intelligence(report)

    out.write("=" * 72 + "\n")
    out.write("  xG & Chance Quality Intelligence V2 — analysis only, not betting advice\n")
    out.write("=" * 72 + "\n\n")
    out.write(f"  Fixture: {fixture_id}\n")
    out.write(f"  Summary: {result.summary}\n\n")
    out.write(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    out.write("\n\n")
    out.write("=" * 72 + "\n")
    return 0


def run_first_goal_command(
    *,
    fixture_id: int,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI: First Goal Intelligence V2 for a fixture (informational JSON)."""
    import json

    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]
    comp_key = resolve_competition(competition)

    from worldcup_predictor.agents.match_intelligence_builder import MatchIntelligenceBuilder
    from worldcup_predictor.clients.api_football import ApiFootballClient
    from worldcup_predictor.intelligence.first_goal_intelligence_v2 import build_first_goal_intelligence_v2
    from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline

    print_competition_banner(out, translator, comp_key)
    report = MatchIntelligenceBuilder(ApiFootballClient(settings)).build_by_fixture_id(fixture_id)
    pipeline = PredictPipeline(settings, competition_key=comp_key, locale=active_locale)
    pred_result = pipeline.run(fixture_id, record_history=False)
    prediction = pred_result.prediction if pred_result.success else None
    result = build_first_goal_intelligence_v2(
        report,
        prediction=prediction,
        specialist_report=getattr(report, "specialist_report", None),
    )

    out.write("=" * 72 + "\n")
    out.write("  First Goal Intelligence V2 — analysis only, not betting advice\n")
    out.write("=" * 72 + "\n\n")
    out.write(f"  Fixture: {fixture_id}\n")
    out.write(f"  Summary: {result.summary}\n\n")
    out.write(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    out.write("\n\n")
    out.write("=" * 72 + "\n")
    return 0


def run_fusion_report_command(
    *,
    fixture_id: int,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI: Final Decision Fusion V2 report for a fixture."""
    import json

    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]
    comp_key = resolve_competition(competition)

    from worldcup_predictor.fusion.final_decision_fusion_engine_v2 import (
        build_final_decision_fusion,
        load_fusion_from_prediction,
    )
    from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline

    print_competition_banner(out, translator, comp_key)
    pipeline = PredictPipeline(settings, competition_key=comp_key, locale=active_locale)
    result = pipeline.run(fixture_id, record_history=False)
    prediction = result.prediction

    fusion = load_fusion_from_prediction(prediction)
    if not fusion:
        fusion = build_final_decision_fusion(prediction)
    report_data = fusion.to_dict()

    out.write("=" * 72 + "\n")
    out.write("  Final Decision Fusion V2 — analysis only, not betting advice\n")
    out.write("=" * 72 + "\n\n")
    out.write(f"  Fixture: {fixture_id}\n")
    out.write(f"  Summary: {report_data.get('final_summary', '')}\n\n")
    out.write(json.dumps(report_data, indent=2, ensure_ascii=False))
    out.write("\n\n")
    out.write("=" * 72 + "\n")
    return 0


def run_export_report_command(
    *,
    fixture_id: int,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI: Export professional match report (Markdown, JSON, summary)."""
    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    if active_locale not in {"en", "de", "fa"}:
        active_locale = "en"
    translator = get_translator(active_locale)  # type: ignore[arg-type]
    comp_key = resolve_competition(competition)

    from worldcup_predictor.export.professional_match_report_exporter_v2 import (
        ProfessionalMatchReportExporterV2,
    )

    print_competition_banner(out, translator, comp_key)
    exporter = ProfessionalMatchReportExporterV2()
    _, result = exporter.export_fixture(
        settings,
        fixture_id,
        locale=active_locale,  # type: ignore[arg-type]
        competition_key=comp_key,
    )

    out.write("=" * 72 + "\n")
    out.write("  Professional Match Report Export V2 — analysis only, not betting advice\n")
    out.write("=" * 72 + "\n\n")
    out.write(f"  Fixture: {fixture_id}\n")
    out.write(f"  Locale: {active_locale}\n\n")
    if result.markdown_path:
        out.write(f"  Markdown: {result.markdown_path}\n")
    if result.json_path:
        out.write(f"  JSON: {result.json_path}\n")
    if result.summary_path:
        out.write(f"  Summary: {result.summary_path}\n")
    for err in result.errors:
        out.write(f"  Warning: {err}\n")
    if not result.paths:
        out.write("  Export failed — no files written.\n")
    out.write("\n")
    out.write("=" * 72 + "\n")
    return 0 if result.paths else 1


def run_learning_report_command(
    *,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI: Self-Learning Accuracy Engine V2 full report."""
    import json

    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]
    comp_key = resolve_competition(competition)

    from worldcup_predictor.learning.self_learning_engine_v2 import build_self_learning_report

    print_competition_banner(out, translator, comp_key)
    report = build_self_learning_report(competition_key=comp_key)

    out.write("=" * 72 + "\n")
    out.write("  Self-Learning Accuracy Report V2 — human review required\n")
    out.write("=" * 72 + "\n\n")
    out.write(f"  Records: {report.total_records} total, {report.verified_records} verified\n\n")
    for insight in report.insights:
        out.write(f"  • {insight}\n")
    out.write("\n")
    out.write(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    out.write("\n\n")
    out.write(f"  {report.disclaimer}\n")
    out.write("=" * 72 + "\n")
    return 0


def run_hall_of_fame_command(
    *,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI: Prediction Accuracy Hall of Fame (read-only trust metrics)."""
    import json

    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]
    comp_key = resolve_competition(competition)

    from worldcup_predictor.performance.hall_of_fame import build_hall_of_fame_report

    print_competition_banner(out, translator, comp_key)
    report = build_hall_of_fame_report(settings=settings, competition_key=comp_key)

    out.write("=" * 72 + "\n")
    out.write("  Prediction Accuracy Hall of Fame — verified history only\n")
    out.write("=" * 72 + "\n\n")
    out.write(
        f"  Total predictions: {report.total_predictions} · "
        f"Verified: {report.verified_predictions} · "
        f"Pending: {report.pending_predictions}\n\n"
    )
    out.write(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    out.write("\n\n")
    out.write(f"  {report.disclaimer}\n")
    out.write("=" * 72 + "\n")
    return 0


def run_agent_performance_command(
    *,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI: specialist agent performance rankings."""
    import json

    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]
    comp_key = resolve_competition(competition)

    from worldcup_predictor.learning.self_learning_engine_v2 import build_agent_performance_report

    print_competition_banner(out, translator, comp_key)
    payload = build_agent_performance_report(competition_key=comp_key)

    out.write("=" * 72 + "\n")
    out.write("  Agent Performance Report V2\n")
    out.write("=" * 72 + "\n\n")
    out.write(json.dumps(payload, indent=2, ensure_ascii=False))
    out.write("\n\n")
    out.write("=" * 72 + "\n")
    return 0


def run_calibration_report_command(
    *,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI: confidence calibration report."""
    import json

    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]
    comp_key = resolve_competition(competition)

    from worldcup_predictor.learning.self_learning_engine_v2 import build_calibration_report

    print_competition_banner(out, translator, comp_key)
    payload = build_calibration_report(competition_key=comp_key)

    out.write("=" * 72 + "\n")
    out.write("  Confidence Calibration Report V2\n")
    out.write("=" * 72 + "\n\n")
    out.write(json.dumps(payload, indent=2, ensure_ascii=False))
    out.write("\n\n")
    out.write("=" * 72 + "\n")
    return 0


def run_recent_accuracy_audit_command(
    *,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI: audit recent verified prediction errors and write markdown report."""
    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]
    comp_key = resolve_competition(competition)

    from worldcup_predictor.accuracy.recent_error_audit import (
        build_recent_error_audit,
        fetch_fixtures_for_audit,
        write_recent_error_audit_markdown,
    )

    print_competition_banner(out, translator, comp_key)
    fixtures = fetch_fixtures_for_audit(settings=settings, competition_key=comp_key)
    audit = build_recent_error_audit(fixtures, competition_key=comp_key, settings=settings)
    path = write_recent_error_audit_markdown(audit)

    out.write("=" * 72 + "\n")
    out.write("  Recent Prediction Error Audit\n")
    out.write("=" * 72 + "\n\n")
    out.write(f"  Verified predictions: {audit.total_verified}\n")
    out.write(f"  Sample adequate: {audit.sample_adequate}\n\n")
    for w in audit.warnings:
        out.write(f"  WARNING: {w}\n")
    if audit.windows:
        w0 = audit.windows[0]
        out.write(f"\n  Latest window 1X2: {_format_pct(w0.one_x_two)} · O/U: {_format_pct(w0.over_under)}\n")
    out.write("\n  Root causes:\n")
    for cause in audit.root_causes:
        out.write(f"    - {cause}\n")
    out.write(f"\n  Report: {path}\n")
    out.write("\n" + "=" * 72 + "\n")
    return 0


def run_recalibration_report_command(
    *,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI: build recalibration recommendations from recent error audit."""
    import json

    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]
    comp_key = resolve_competition(competition)

    from worldcup_predictor.accuracy.recalibration_engine import run_full_recalibration_pipeline

    print_competition_banner(out, translator, comp_key)
    audit, rec = run_full_recalibration_pipeline(competition_key=comp_key, write_audit=True)

    out.write("=" * 72 + "\n")
    out.write("  Recent Recalibration Report\n")
    out.write("=" * 72 + "\n\n")
    out.write(f"  Verified sample: {rec.verified_sample}\n")
    out.write(f"  Confidence correction factor: {rec.confidence_correction_factor}\n")
    out.write(f"  Scoreline cap: {rec.scoreline_probability_cap}\n\n")
    out.write("  Fixes (live calibration config only — not factor weights):\n")
    for fix in rec.fixes_applied:
        out.write(f"    - {fix}\n")
    for w in rec.warnings:
        out.write(f"  WARNING: {w}\n")
    out.write("\n  reports/calibration/recent_recalibration_report.json\n")
    out.write("  reports/calibration/recent_live_calibration.json\n")
    out.write("\n  Distribution:\n")
    out.write(json.dumps({"before": rec.before_distribution, "after": rec.after_distribution}, indent=2))
    out.write("\n\n" + "=" * 72 + "\n")
    return 0


def run_replay_recent_predictions_command(
    *,
    limit: int = 50,
    locale: str | None = None,
    competition: str | None = None,
    stream: TextIO | None = None,
) -> int:
    """CLI: diagnostic replay — does not rewrite stored predictions."""
    import json

    out = stream or sys.stdout
    settings = get_settings()
    active_locale = locale or settings.default_locale
    translator = get_translator(active_locale)  # type: ignore[arg-type]
    comp_key = resolve_competition(competition)

    from worldcup_predictor.accuracy.recent_error_audit import (
        fetch_fixtures_for_audit,
        replay_recent_predictions,
    )

    print_competition_banner(out, translator, comp_key)
    fixtures = fetch_fixtures_for_audit(settings=settings, competition_key=comp_key)
    rows = replay_recent_predictions(fixtures, limit=limit, competition_key=comp_key)

    out.write("=" * 72 + "\n")
    out.write("  Replay Recent Predictions (diagnostic)\n")
    out.write("=" * 72 + "\n\n")
    out.write(json.dumps(rows, indent=2, ensure_ascii=False))
    out.write("\n\n" + "=" * 72 + "\n")
    return 0


def _format_move(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.2f}%"


def run_odds_api_usage_command(*, stream: TextIO | None = None) -> int:
    """CLI: show The Odds API credit usage summary."""
    import json

    out = stream or sys.stdout
    settings = get_settings()
    from worldcup_predictor.providers.odds_api_credit import usage_summary
    from worldcup_predictor.providers.odds_api_credit.repository import get_odds_api_repository

    summary = usage_summary(settings)
    rows = get_odds_api_repository().usage_rows_for_date()
    out.write("=" * 72 + "\n")
    out.write("  The Odds API — usage summary\n")
    out.write("=" * 72 + "\n\n")
    out.write(f"  Key configured: {settings.the_odds_api_configured}\n")
    out.write(f"  Daily used: {summary['daily_used']} / {summary['daily_hard_limit']}\n")
    out.write(f"  Monthly used: {summary['monthly_used']} / {summary['monthly_limit']}\n\n")
    if rows:
        out.write("  Today's rows:\n")
        for row in rows[:30]:
            out.write(
                f"    fixture={row.get('fixture_id')} credits={row.get('credits_used')} "
                f"source={row.get('source', 'live')} endpoint={row.get('endpoint')}\n"
            )
    else:
        out.write("  No usage rows today.\n")
    out.write("\n" + json.dumps(summary, indent=2) + "\n")
    out.write("=" * 72 + "\n")
    return 0


def run_odds_api_reset_test_usage_command(
    *,
    usage_date: str | None = None,
    include_unmarked_local: bool = False,
    stream: TextIO | None = None,
) -> int:
    """CLI: reset validation/test Odds API usage rows (dev only)."""
    out = stream or sys.stdout
    from datetime import date

    from worldcup_predictor.providers.odds_api_credit.repository import (
        get_odds_api_repository,
        is_local_dev_db,
        utc_today,
    )

    day = usage_date or utc_today()
    repo = get_odds_api_repository()
    deleted = repo.delete_validation_usage(day)
    out.write(f"Removed {deleted} validation row(s) for {day}.\n")

    if include_unmarked_local:
        if not is_local_dev_db():
            out.write(
                "ERROR: --include-unmarked-local only allowed on local dev DB "
                f"({repo.path}). No unmarked rows deleted.\n"
            )
            return 1
        remaining = repo.sum_credits_for_date(day)
        if remaining > 0:
            extra = repo.delete_unmarked_test_day(day)
            out.write(
                f"Local dev cleanup: removed {extra} unmarked row(s) for {day}. "
                "Use only for test pollution cleanup.\n"
            )
        else:
            out.write("No unmarked rows remaining after validation cleanup.\n")
    return 0


def run_odds_api_diagnostics_command(
    *,
    fixture_id: int,
    force: bool = False,
    stream: TextIO | None = None,
) -> int:
    """CLI: Odds API guard + match diagnostics for a fixture."""
    import json

    out = stream or sys.stdout
    from worldcup_predictor.providers.odds_api_diagnostics import run_odds_api_diagnostics

    payload = run_odds_api_diagnostics(fixture_id, force=force, dry_run=not force)
    out.write("=" * 72 + "\n")
    out.write("  The Odds API Diagnostics — analysis only\n")
    out.write("=" * 72 + "\n\n")
    out.write(json.dumps(payload, indent=2, ensure_ascii=False))
    out.write("\n\n")
    out.write("=" * 72 + "\n")
    return 0


def run_import_league_history_command(
    *,
    league: int | None = None,
    season: int | None = None,
    all_enabled: bool = False,
    from_season: int | None = None,
    to_season: int | None = None,
    enrich: bool = True,
    stream: TextIO | None = None,
) -> int:
    """CLI: import European league history into SQLite (Phase 39B)."""
    out = stream or sys.stdout
    from worldcup_predictor.ingestion.league_history_importer import LeagueHistoryImporter

    importer = LeagueHistoryImporter(enrich=enrich)
    out.write("=" * 72 + "\n")
    out.write("  Phase 39 — League History Import (SQLite)\n")
    out.write("=" * 72 + "\n\n")

    if not importer.is_configured:
        out.write("  API_FOOTBALL_KEY not configured.\n\n")
        out.write("=" * 72 + "\n")
        return 1

    results = []
    if all_enabled and from_season is not None and to_season is not None:
        results = importer.import_all_enabled_range(from_season=from_season, to_season=to_season)
    elif all_enabled:
        if season is None:
            out.write("  --season required with --all-enabled (unless using --from-season/--to-season).\n")
            return 1
        results = importer.import_all_enabled(season=season)
    elif league is not None:
        if season is None:
            out.write("  --season required with --league.\n")
            return 1
        results = [importer.import_league_season(league_id=league, season=season)]
    else:
        out.write("  Specify --league ID, or --all-enabled with --season or season range.\n")
        return 1

    exit_code = 0
    for result in results:
        out.write(
            f"  {result.competition_key} (league {result.league_id}, {result.season}): "
            f"{result.message}\n"
        )
        if not result.success:
            exit_code = 1
        for err in result.errors:
            out.write(f"    ! {err}\n")

    out.write("\n" + "=" * 72 + "\n")
    return exit_code
