#!/usr/bin/env python3
"""WorldCup Predictor Pro 2026 — CLI entry point."""

from __future__ import annotations

import argparse
import sys


def _configure_stdio() -> None:
    """Use UTF-8 on Windows so Persian/German output renders correctly."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                pass


def _competition_arg(args: argparse.Namespace) -> str | None:
    return getattr(args, "competition", None)


def build_parser() -> argparse.ArgumentParser:
    from worldcup_predictor.cli.competition_cli import add_competition_argument

    parser = argparse.ArgumentParser(
        prog="worldcup-predictor",
        description="WorldCup Predictor Pro 2026 — multi-agent football analysis",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    upcoming = subparsers.add_parser(
        "upcoming",
        help="Show the next World Cup 2026 matches with prediction placeholders",
    )
    upcoming.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Number of fixtures to show (default: 5)",
    )
    upcoming.add_argument(
        "--locale",
        choices=["en", "de", "fa", "sr", "bs", "hr"],
        default=None,
        help="Output locale (default: from DEFAULT_LOCALE env or en)",
    )
    add_competition_argument(upcoming)

    list_competitions = subparsers.add_parser(
        "list-competitions",
        help="List registered competitions and supported features",
    )
    list_competitions.add_argument(
        "--locale",
        choices=["en", "de", "fa", "sr", "bs", "hr"],
        default=None,
        help="Output locale (default: from DEFAULT_LOCALE env or en)",
    )

    inspect = subparsers.add_parser(
        "inspect",
        help="Inspect match intelligence for a single fixture",
    )
    inspect.add_argument(
        "--fixture-id",
        type=int,
        required=True,
        help="Fixture ID to inspect",
    )
    inspect.add_argument(
        "--locale",
        choices=["en", "de", "fa", "sr", "bs", "hr"],
        default=None,
        help="Output locale (default: from DEFAULT_LOCALE env or en)",
    )

    predict = subparsers.add_parser(
        "predict",
        help="Generate analytical prediction for a single fixture",
    )
    predict.add_argument(
        "--fixture-id",
        type=int,
        required=True,
        help="Fixture ID to predict",
    )
    predict.add_argument(
        "--locale",
        choices=["en", "de", "fa", "sr", "bs", "hr"],
        default=None,
        help="Output locale (default: from DEFAULT_LOCALE env or en)",
    )
    add_competition_argument(predict)

    specialists = subparsers.add_parser(
        "specialists",
        help="Run specialist agent analysis for a single fixture",
    )
    specialists.add_argument(
        "--fixture-id",
        type=int,
        required=True,
        help="Fixture ID to analyze",
    )
    specialists.add_argument(
        "--locale",
        choices=["en", "de", "fa", "sr", "bs", "hr"],
        default=None,
        help="Output locale (default: from DEFAULT_LOCALE env or en)",
    )
    add_competition_argument(specialists)

    audit = subparsers.add_parser(
        "audit",
        help="Weighted decision audit with factor trace for a fixture",
    )
    audit.add_argument(
        "--fixture-id",
        type=int,
        required=True,
        help="Fixture ID to audit",
    )
    audit.add_argument(
        "--locale",
        choices=["en", "de", "fa", "sr", "bs", "hr"],
        default=None,
        help="Output locale (default: from DEFAULT_LOCALE env or en)",
    )
    add_competition_argument(audit)

    schedule = subparsers.add_parser(
        "schedule",
        help="Show next World Cup 2026 schedule fixtures",
    )
    schedule.add_argument(
        "--locale",
        choices=["en", "de", "fa", "sr", "bs", "hr"],
        default=None,
        help="Output locale (default: from DEFAULT_LOCALE env or en)",
    )
    add_competition_argument(schedule)

    groups = subparsers.add_parser(
        "groups",
        help="Show World Cup 2026 group tables",
    )
    groups.add_argument(
        "--locale",
        choices=["en", "de", "fa", "sr", "bs", "hr"],
        default=None,
        help="Output locale (default: from DEFAULT_LOCALE env or en)",
    )
    add_competition_argument(groups)

    team_schedule = subparsers.add_parser(
        "team-schedule",
        help="Show all known matches for one team",
    )
    team_schedule.add_argument(
        "--team",
        type=str,
        required=True,
        help="Team name (e.g. Germany, USA)",
    )
    team_schedule.add_argument(
        "--locale",
        choices=["en", "de", "fa", "sr", "bs", "hr"],
        default=None,
        help="Output locale (default: from DEFAULT_LOCALE env or en)",
    )
    add_competition_argument(team_schedule)

    next_window = subparsers.add_parser(
        "next-window",
        help="Show nearest analysis readiness window",
    )
    next_window.add_argument(
        "--locale",
        choices=["en", "de", "fa", "sr", "bs", "hr"],
        default=None,
        help="Output locale (default: from DEFAULT_LOCALE env or en)",
    )

    live_opening = subparsers.add_parser(
        "live-opening",
        help="Show live opening match readiness (Mexico vs South Africa)",
    )
    live_opening.add_argument(
        "--locale",
        choices=["en", "de", "fa", "sr", "bs", "hr"],
        default=None,
        help="Output locale (default: from DEFAULT_LOCALE env or en)",
    )
    add_competition_argument(live_opening)

    backtest = subparsers.add_parser(
        "backtest",
        help="Run historical backtest model evaluation from CSV",
    )
    backtest.add_argument(
        "--csv",
        type=str,
        default="data/historical/worldcup_sample.csv",
        help="Path to historical matches CSV",
    )
    backtest.add_argument(
        "--locale",
        choices=["en", "de", "fa", "sr", "bs", "hr"],
        default=None,
        help="Output locale (default: from DEFAULT_LOCALE env or en)",
    )
    add_competition_argument(backtest)

    calibrate = subparsers.add_parser(
        "calibrate",
        help="Auto-tune factor weights and confidence thresholds from historical CSV",
    )
    calibrate.add_argument(
        "--csv",
        type=str,
        default="data/historical/worldcup_sample.csv",
        help="Path to historical matches CSV",
    )
    calibrate.add_argument(
        "--locale",
        choices=["en", "de", "fa", "sr", "bs", "hr"],
        default=None,
        help="Output locale (default: from DEFAULT_LOCALE env or en)",
    )
    add_competition_argument(calibrate)

    import_history = subparsers.add_parser(
        "import-history",
        help="Import historical matches from API-Football into backtest CSV",
    )
    import_history.add_argument(
        "--worldcup",
        action="store_true",
        help="Import FIFA World Cup history",
    )
    import_history.add_argument(
        "--league-id",
        type=int,
        default=None,
        help="API-Football league ID (e.g. 1 for World Cup)",
    )
    import_history.add_argument(
        "--seasons",
        type=int,
        nargs="+",
        default=None,
        help="Season years to import (e.g. 2018 2022)",
    )
    import_history.add_argument(
        "--team-ids",
        type=int,
        nargs="+",
        default=None,
        help="Team IDs for international match import",
    )
    import_history.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing CSV instead of merging",
    )
    import_history.add_argument(
        "--locale",
        choices=["en", "de", "fa", "sr", "bs", "hr"],
        default=None,
        help="Output locale (default: from DEFAULT_LOCALE env or en)",
    )
    add_competition_argument(import_history)

    validate_csv = subparsers.add_parser(
        "validate-csv",
        help="Validate historical CSV quality before backtest or calibration",
    )
    validate_csv.add_argument(
        "--csv",
        type=str,
        default="data/historical/worldcup_sample.csv",
        help="Path to historical matches CSV",
    )
    validate_csv.add_argument(
        "--locale",
        choices=["en", "de", "fa", "sr", "bs", "hr"],
        default=None,
        help="Output locale (default: from DEFAULT_LOCALE env or en)",
    )

    dashboard = subparsers.add_parser(
        "dashboard",
        help="Launch the Streamlit professional analysis dashboard",
    )

    gui = subparsers.add_parser(
        "gui",
        help="Launch the beautiful Streamlit GUI (Phase 14 — recommended)",
    )

    test_apis = subparsers.add_parser(
        "test-apis",
        help="Test API connectivity (API-Football primary + optional enrichment)",
    )
    test_apis.add_argument(
        "--locale",
        choices=["en", "de", "fa", "sr", "bs", "hr"],
        default=None,
        help="Output locale (default: from DEFAULT_LOCALE env or en)",
    )

    report = subparsers.add_parser(
        "report",
        help="Generate professional narrative match report (OpenAI or local rules)",
    )
    report.add_argument(
        "--fixture-id",
        type=int,
        required=True,
        help="Fixture ID to report on",
    )
    report.add_argument(
        "--locale",
        choices=["en", "de", "fa", "sr", "bs", "hr"],
        default=None,
        help="Output locale (default: from DEFAULT_LOCALE env or en)",
    )
    add_competition_argument(report)

    accuracy = subparsers.add_parser(
        "accuracy",
        help="Evaluate stored predictions against finished matches (model evaluation)",
    )
    accuracy.add_argument(
        "--locale",
        choices=["en", "de", "fa", "sr", "bs", "hr"],
        default=None,
        help="Output locale (default: from DEFAULT_LOCALE env or en)",
    )
    add_competition_argument(accuracy)

    verify_predictions = subparsers.add_parser(
        "verify-predictions",
        help="Auto-verify stored predictions against finished results (model evaluation)",
    )
    verify_predictions.add_argument(
        "--locale",
        choices=["en", "de", "fa", "sr", "bs", "hr"],
        default=None,
        help="Output locale (default: from DEFAULT_LOCALE env or en)",
    )
    add_competition_argument(verify_predictions)

    coach_model = subparsers.add_parser(
        "coach-model",
        help="Run learning agent and produce model improvement recommendations",
    )
    coach_model.add_argument(
        "--locale",
        choices=["en", "de", "fa", "sr", "bs", "hr"],
        default=None,
        help="Output locale (default: from DEFAULT_LOCALE env or en)",
    )
    add_competition_argument(coach_model)
    coach_model.add_argument(
        "--all",
        dest="all_competitions",
        action="store_true",
        help="Run coach for all registered competitions",
    )

    discover_patterns = subparsers.add_parser(
        "discover-patterns",
        help="Discover success/failure patterns from SQLite prediction history",
    )
    discover_patterns.add_argument(
        "--locale",
        choices=["en", "de", "fa", "sr", "bs", "hr"],
        default=None,
        help="Output locale (default: from DEFAULT_LOCALE env or en)",
    )
    add_competition_argument(discover_patterns)
    discover_patterns.add_argument(
        "--all",
        dest="all_competitions",
        action="store_true",
        help="Include competition-specific pattern breakdown",
    )

    sync_data = subparsers.add_parser(
        "sync-data",
        help="Sync real API fixtures/results into SQLite intelligence database",
    )
    sync_data.add_argument("--locale", choices=["en", "de", "fa", "sr", "bs", "hr"], default=None)
    add_competition_argument(sync_data)
    sync_data.add_argument(
        "--all-active",
        dest="all_active",
        action="store_true",
        help="Sync all competitions with configured league IDs",
    )

    migrate_jsonl = subparsers.add_parser(
        "migrate-jsonl-to-db",
        help="Import JSONL backup stores into SQLite primary database",
    )
    migrate_jsonl.add_argument("--locale", choices=["en", "de", "fa", "sr", "bs", "hr"], default=None)
    add_competition_argument(migrate_jsonl)

    shortlist = subparsers.add_parser(
        "shortlist",
        help="Build daily match shortlist using smart selection engine",
    )
    shortlist.add_argument("--locale", choices=["en", "de", "fa", "sr", "bs", "hr"], default=None)
    shortlist.add_argument("--days", type=int, default=3, help="Lookahead window in days")
    add_competition_argument(shortlist)

    auto_prematch = subparsers.add_parser(
        "auto-prematch",
        help="Automated pre-match prediction scan (24h / 6h / lineup final)",
    )
    auto_prematch.add_argument(
        "--window-hours",
        type=float,
        default=None,
        help="Scan matches starting within this many hours (default: 24 when not using --lineup-final)",
    )
    auto_prematch.add_argument(
        "--lineup-final",
        action="store_true",
        help="Create final pre-match versions when official lineups are available",
    )
    auto_prematch.add_argument(
        "--selected-only",
        action="store_true",
        help="League mode: only auto-predict selection-engine approved matches",
    )
    auto_prematch.add_argument(
        "--locale",
        choices=["en", "de", "fa", "sr", "bs", "hr"],
        default=None,
        help="Output locale (default: from DEFAULT_LOCALE env or en)",
    )
    add_competition_argument(auto_prematch)

    odds_consensus = subparsers.add_parser(
        "odds-consensus",
        help="Show market consensus for a fixture (analysis only)",
    )
    odds_consensus.add_argument("--fixture-id", type=int, required=True)
    odds_consensus.add_argument("--locale", choices=["en", "de", "fa", "sr", "bs", "hr"], default=None)
    add_competition_argument(odds_consensus)

    odds_movement = subparsers.add_parser(
        "odds-movement",
        help="Show odds movement for a fixture (analysis only)",
    )
    odds_movement.add_argument("--fixture-id", type=int, required=True)
    odds_movement.add_argument("--locale", choices=["en", "de", "fa", "sr", "bs", "hr"], default=None)
    add_competition_argument(odds_movement)

    league_learning = subparsers.add_parser(
        "league-learning",
        help="Show league-specific learning profile (analysis only)",
    )
    league_learning.add_argument("--locale", choices=["en", "de", "fa", "sr", "bs", "hr"], default=None)
    add_competition_argument(league_learning)

    lineup_intel = subparsers.add_parser(
        "lineup-intelligence",
        help="Show Lineup Intelligence V2 for a fixture (analysis only)",
    )
    lineup_intel.add_argument("--fixture-id", type=int, required=True)
    lineup_intel.add_argument("--locale", choices=["en", "de", "fa", "sr", "bs", "hr"], default=None)
    add_competition_argument(lineup_intel)

    injury_intel = subparsers.add_parser(
        "injury-intelligence",
        help="Show Injury & Suspension Intelligence V2 for a fixture (analysis only)",
    )
    injury_intel.add_argument("--fixture-id", type=int, required=True)
    injury_intel.add_argument("--locale", choices=["en", "de", "fa", "sr", "bs", "hr"], default=None)
    add_competition_argument(injury_intel)

    market_intel = subparsers.add_parser(
        "market-intelligence",
        help="Show Sharp Money & Market Intelligence V2 for a fixture (analysis only)",
    )
    market_intel.add_argument("--fixture-id", type=int, required=True)
    market_intel.add_argument("--locale", choices=["en", "de", "fa", "sr", "bs", "hr"], default=None)
    add_competition_argument(market_intel)

    explain_pred = subparsers.add_parser(
        "explain-prediction",
        help="Show Prediction Explainability & Final Report V2 (analysis only)",
    )
    explain_pred.add_argument("--fixture-id", type=int, required=True)
    explain_pred.add_argument("--locale", choices=["en", "de", "fa", "sr", "bs", "hr"], default=None)
    add_competition_argument(explain_pred)

    learning_report = subparsers.add_parser(
        "learning-report",
        help="Self-Learning Accuracy Engine V2 full report (human review only)",
    )
    learning_report.add_argument("--locale", choices=["en", "de", "fa", "sr", "bs", "hr"], default=None)
    add_competition_argument(learning_report)

    hall_of_fame = subparsers.add_parser(
        "hall-of-fame",
        help="Prediction Accuracy Hall of Fame — read-only trust metrics",
    )
    hall_of_fame.add_argument("--locale", choices=["en", "de", "fa", "sr", "bs", "hr"], default=None)
    add_competition_argument(hall_of_fame)

    agent_perf = subparsers.add_parser(
        "agent-performance",
        help="Specialist agent performance rankings (analysis only)",
    )
    agent_perf.add_argument("--locale", choices=["en", "de", "fa", "sr", "bs", "hr"], default=None)
    add_competition_argument(agent_perf)

    calibration_report = subparsers.add_parser(
        "calibration-report",
        help="Confidence calibration report (analysis only)",
    )
    calibration_report.add_argument("--locale", choices=["en", "de", "fa", "sr", "bs", "hr"], default=None)
    add_competition_argument(calibration_report)

    recent_audit = subparsers.add_parser(
        "recent-accuracy-audit",
        help="Audit recent verified prediction errors (analysis only)",
    )
    recent_audit.add_argument("--locale", choices=["en", "de", "fa", "sr", "bs", "hr"], default=None)
    add_competition_argument(recent_audit)

    recalibration = subparsers.add_parser(
        "recalibration-report",
        help="Build conservative recalibration recommendations from recent errors",
    )
    recalibration.add_argument("--locale", choices=["en", "de", "fa", "sr", "bs", "hr"], default=None)
    add_competition_argument(recalibration)

    replay_recent = subparsers.add_parser(
        "replay-recent-predictions",
        help="Diagnostic replay of stored predictions vs finished results (read-only)",
    )
    replay_recent.add_argument("--limit", type=int, default=50)
    replay_recent.add_argument("--locale", choices=["en", "de", "fa", "sr", "bs", "hr"], default=None)
    add_competition_argument(replay_recent)

    tournament_intel = subparsers.add_parser(
        "tournament-intelligence",
        help="Show Tournament Intelligence V2 for a fixture (analysis only)",
    )
    tournament_intel.add_argument("--fixture-id", type=int, required=True)
    tournament_intel.add_argument("--locale", choices=["en", "de", "fa", "sr", "bs", "hr"], default=None)
    add_competition_argument(tournament_intel)

    elo_intel = subparsers.add_parser(
        "elo-intelligence",
        help="Show ELO & Team Strength Intelligence V2 for a fixture (analysis only)",
    )
    elo_intel.add_argument("--fixture-id", type=int, required=True)
    elo_intel.add_argument("--locale", choices=["en", "de", "fa", "sr", "bs", "hr"], default=None)
    add_competition_argument(elo_intel)

    xg_intel = subparsers.add_parser(
        "xg-intelligence",
        help="Show xG & Chance Quality Intelligence V2 for a fixture (analysis only)",
    )
    xg_intel.add_argument("--fixture-id", type=int, required=True)
    xg_intel.add_argument("--locale", choices=["en", "de", "fa", "sr", "bs", "hr"], default=None)
    add_competition_argument(xg_intel)

    first_goal = subparsers.add_parser(
        "first-goal",
        help="Show First Goal Intelligence V2 for a fixture (informational JSON)",
    )
    first_goal.add_argument("--fixture-id", type=int, required=True)
    first_goal.add_argument("--locale", choices=["en", "de", "fa", "sr", "bs", "hr"], default=None)
    add_competition_argument(first_goal)

    odds_api_usage = subparsers.add_parser(
        "odds-api-usage",
        help="Show The Odds API daily/monthly credit usage",
    )

    odds_api_reset = subparsers.add_parser(
        "odds-api-reset-test-usage",
        help="Remove validation/test Odds API usage rows (dev only)",
    )
    odds_api_reset.add_argument("--date", dest="usage_date", default=None, help="YYYY-MM-DD (default: today)")
    odds_api_reset.add_argument(
        "--include-unmarked-local",
        action="store_true",
        help="Also clear all usage rows for date on local dev DB only",
    )

    odds_api_diag = subparsers.add_parser(
        "odds-api-diagnostics",
        help="Odds API guard and event-match diagnostics for a fixture",
    )
    odds_api_diag.add_argument("--fixture-id", type=int, required=True)
    odds_api_diag.add_argument(
        "--force",
        action="store_true",
        help="Force live Odds API enrichment (respects hard daily limit)",
    )

    fusion_report = subparsers.add_parser(
        "fusion-report",
        help="Show Final Decision Fusion V2 report for a fixture (analysis only)",
    )
    fusion_report.add_argument("--fixture-id", type=int, required=True)
    fusion_report.add_argument("--locale", choices=["en", "de", "fa", "sr", "bs", "hr"], default=None)
    add_competition_argument(fusion_report)

    export_report = subparsers.add_parser(
        "export-report",
        help="Export professional match report (Markdown, JSON, summary)",
    )
    export_report.add_argument("--fixture-id", type=int, required=True)
    export_report.add_argument("--locale", choices=["en", "de", "fa"], default=None)
    add_competition_argument(export_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()

    from worldcup_predictor.cli.commands import (
        run_audit_command,
        run_accuracy_command,
        run_auto_prematch_command,
        run_backtest_command,
        run_calibrate_command,
        run_dashboard_command,
        run_gui_command,
        run_test_apis_command,
        run_groups_command,
        run_import_history_command,
        run_inspect_command,
        run_list_competitions_command,
        run_live_opening_command,
        run_next_window_command,
        run_predict_command,
        run_report_command,
        run_schedule_command,
        run_specialists_command,
        run_team_schedule_command,
        run_upcoming_command,
        run_validate_csv_command,
        run_verify_predictions_command,
        run_coach_model_command,
        run_discover_patterns_command,
        run_sync_data_command,
        run_migrate_jsonl_command,
        run_shortlist_command,
        run_odds_consensus_command,
        run_odds_movement_command,
        run_league_learning_command,
        run_lineup_intelligence_command,
        run_injury_intelligence_command,
        run_market_intelligence_command,
        run_explain_prediction_command,
        run_learning_report_command,
        run_hall_of_fame_command,
        run_agent_performance_command,
        run_calibration_report_command,
        run_recent_accuracy_audit_command,
        run_recalibration_report_command,
        run_replay_recent_predictions_command,
        run_tournament_intelligence_command,
        run_elo_intelligence_command,
        run_xg_intelligence_command,
        run_first_goal_command,
        run_odds_api_usage_command,
        run_odds_api_reset_test_usage_command,
        run_odds_api_diagnostics_command,
        run_fusion_report_command,
        run_export_report_command,
    )

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "upcoming":
        return run_upcoming_command(
            limit=args.limit,
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "list-competitions":
        return run_list_competitions_command(locale=args.locale)

    if args.command == "inspect":
        return run_inspect_command(fixture_id=args.fixture_id, locale=args.locale)

    if args.command == "predict":
        return run_predict_command(
            fixture_id=args.fixture_id,
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "specialists":
        return run_specialists_command(
            fixture_id=args.fixture_id,
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "audit":
        return run_audit_command(
            fixture_id=args.fixture_id,
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "report":
        return run_report_command(
            fixture_id=args.fixture_id,
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "accuracy":
        return run_accuracy_command(
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "verify-predictions":
        return run_verify_predictions_command(
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "coach-model":
        return run_coach_model_command(
            locale=args.locale,
            competition=_competition_arg(args),
            all_competitions=getattr(args, "all_competitions", False),
        )

    if args.command == "discover-patterns":
        return run_discover_patterns_command(
            locale=args.locale,
            competition=_competition_arg(args),
            all_competitions=getattr(args, "all_competitions", False),
        )

    if args.command == "sync-data":
        return run_sync_data_command(
            locale=args.locale,
            competition=_competition_arg(args),
            all_active=getattr(args, "all_active", False),
        )

    if args.command == "migrate-jsonl-to-db":
        return run_migrate_jsonl_command(
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "shortlist":
        return run_shortlist_command(
            locale=args.locale,
            competition=_competition_arg(args),
            days=getattr(args, "days", 3),
        )

    if args.command == "auto-prematch":
        return run_auto_prematch_command(
            window_hours=args.window_hours,
            lineup_final=args.lineup_final,
            selected_only=getattr(args, "selected_only", False),
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "odds-consensus":
        return run_odds_consensus_command(
            fixture_id=args.fixture_id,
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "odds-movement":
        return run_odds_movement_command(
            fixture_id=args.fixture_id,
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "league-learning":
        return run_league_learning_command(
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "lineup-intelligence":
        return run_lineup_intelligence_command(
            fixture_id=args.fixture_id,
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "injury-intelligence":
        return run_injury_intelligence_command(
            fixture_id=args.fixture_id,
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "market-intelligence":
        return run_market_intelligence_command(
            fixture_id=args.fixture_id,
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "explain-prediction":
        return run_explain_prediction_command(
            fixture_id=args.fixture_id,
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "learning-report":
        return run_learning_report_command(
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "hall-of-fame":
        return run_hall_of_fame_command(
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "agent-performance":
        return run_agent_performance_command(
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "calibration-report":
        return run_calibration_report_command(
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "recent-accuracy-audit":
        return run_recent_accuracy_audit_command(
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "recalibration-report":
        return run_recalibration_report_command(
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "replay-recent-predictions":
        return run_replay_recent_predictions_command(
            limit=getattr(args, "limit", 50),
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "tournament-intelligence":
        return run_tournament_intelligence_command(
            fixture_id=args.fixture_id,
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "elo-intelligence":
        return run_elo_intelligence_command(
            fixture_id=args.fixture_id,
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "xg-intelligence":
        return run_xg_intelligence_command(
            fixture_id=args.fixture_id,
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "first-goal":
        return run_first_goal_command(
            fixture_id=args.fixture_id,
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "odds-api-usage":
        return run_odds_api_usage_command()

    if args.command == "odds-api-reset-test-usage":
        return run_odds_api_reset_test_usage_command(
            usage_date=getattr(args, "usage_date", None),
            include_unmarked_local=getattr(args, "include_unmarked_local", False),
        )

    if args.command == "odds-api-diagnostics":
        return run_odds_api_diagnostics_command(
            fixture_id=args.fixture_id,
            force=getattr(args, "force", False),
        )

    if args.command == "fusion-report":
        return run_fusion_report_command(
            fixture_id=args.fixture_id,
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "export-report":
        return run_export_report_command(
            fixture_id=args.fixture_id,
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "schedule":
        return run_schedule_command(
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "groups":
        return run_groups_command(
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "team-schedule":
        return run_team_schedule_command(
            team=args.team,
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "next-window":
        return run_next_window_command(locale=args.locale)

    if args.command == "live-opening":
        return run_live_opening_command(
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "backtest":
        return run_backtest_command(
            csv_path=args.csv,
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "calibrate":
        return run_calibrate_command(
            csv_path=args.csv,
            locale=args.locale,
            competition=_competition_arg(args),
        )

    if args.command == "import-history":
        return run_import_history_command(
            worldcup=args.worldcup,
            league_id=args.league_id,
            competition=_competition_arg(args),
            seasons=args.seasons,
            team_ids=args.team_ids,
            overwrite=args.overwrite,
            locale=args.locale,
        )

    if args.command == "validate-csv":
        return run_validate_csv_command(csv_path=args.csv, locale=args.locale)

    if args.command == "dashboard":
        return run_dashboard_command()

    if args.command == "gui":
        return run_gui_command()

    if args.command == "test-apis":
        return run_test_apis_command(locale=args.locale)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
