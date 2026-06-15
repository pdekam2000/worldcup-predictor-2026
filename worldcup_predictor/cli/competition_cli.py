from __future__ import annotations

import argparse

from worldcup_predictor.competition.competition_service import CompetitionService
from worldcup_predictor.config.competitions import DEFAULT_COMPETITION_KEY, get_competition


def add_competition_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--competition",
        type=str,
        default=DEFAULT_COMPETITION_KEY,
        help=f"Competition registry key (default: {DEFAULT_COMPETITION_KEY})",
    )


def resolve_competition(competition: str | None) -> str:
    """Normalize and validate competition key; raises KeyError when unknown."""
    comp = get_competition(competition)
    return comp.key


def print_competition_banner(out, translator, competition_key: str) -> None:
    service = CompetitionService()
    comp = service.get_competition(competition_key)
    features = service.get_supported_features(competition_key)
    out.write(f"  {translator.t('cli.competition.active')}: {comp.display_name} ({comp.key})\n")
    out.write(
        f"  {translator.t('cli.competition.type')}: {features['competition_type']} | "
        f"  {translator.t('cli.competition.features')}: "
        f"groups={features['supports_groups']}, "
        f"table={features['supports_table']}, "
        f"knockout={features['supports_knockout']}\n"
    )
    if service.requires_league_setup(competition_key):
        out.write(f"  ⚠ {service.setup_required_message(competition_key)}\n")
    if comp.notes:
        out.write(f"  {translator.t('cli.competition.notes')}: {comp.notes}\n")
    out.write("\n")
