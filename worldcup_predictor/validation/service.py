"""Phase 26 — real-world validation orchestration."""

from __future__ import annotations

from worldcup_predictor.results.match_results_store import MatchResultsStore
from worldcup_predictor.validation.contribution import update_contribution_stats
from worldcup_predictor.validation.outcome_evaluator import settle_records_from_results
from worldcup_predictor.validation.readiness import compute_readiness_score
from worldcup_predictor.validation.reports import generate_monthly_impact_report, generate_weekly_summary
from worldcup_predictor.validation.store import PromotionContributionStore, RealWorldValidationStore


class RealWorldValidationService:
    def __init__(
        self,
        store: RealWorldValidationStore | None = None,
        stats_store: PromotionContributionStore | None = None,
    ) -> None:
        self._store = store or RealWorldValidationStore()
        self._stats = stats_store or PromotionContributionStore()

    def settle_from_match_results(self) -> int:
        records = self._store.load_all()
        if not records:
            return 0
        results = MatchResultsStore().by_fixture_id()
        settled = settle_records_from_results(records, results)
        changed = sum(1 for a, b in zip(records, settled) if a.settled != b.settled or a.actual_1x2 != b.actual_1x2)
        self._store.rewrite_all(settled)
        stats = update_contribution_stats(None, settled)
        self._stats.save(stats)
        return changed

    def readiness(self):
        return compute_readiness_score(self._store.load_all())

    def generate_reports(self) -> tuple[str, str]:
        weekly = str(generate_weekly_summary(store=self._store))
        monthly = str(generate_monthly_impact_report(store=self._store, stats_store=self._stats))
        return weekly, monthly

    def backfill_from_phase25_replay(self, replay_path: str | None = None) -> int:
        """Bootstrap validation store from Phase 25 replay JSONL (offline)."""
        from pathlib import Path
        import json
        from datetime import datetime, timezone

        from worldcup_predictor.validation.models import IntelligenceSnapshots, PromotionTrackSnapshot, RealWorldValidationRecord

        path = Path(replay_path or "data/shadow/phase25_promotion_replay.jsonl")
        if not path.exists():
            return 0
        existing = {r.fixture_id for r in self._store.load_all()}
        added = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("stack") != "gated_simulation":
                continue
            fid = int(row.get("fixture_id") or 0)
            if fid in existing:
                continue
            record = RealWorldValidationRecord(
                fixture_id=fid,
                match_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                prediction_timestamp=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                match_name=str(row.get("match_name") or f"fixture_{fid}"),
                predicted_1x2=str(row.get("predicted_1x2") or ""),
                confidence=float(row.get("confidence") or 0),
                actual_1x2=row.get("actual_1x2"),
                one_x_two_correct=row.get("correct"),
                settled=bool(row.get("actual_1x2")),
                promotions=[
                    PromotionTrackSnapshot(
                        promotion_key="24a_lineup",
                        signal_available=abs(float(row.get("lineup_delta") or 0)) > 0,
                        delta=float(row.get("lineup_delta") or 0),
                        mode="shadow",
                    ),
                    PromotionTrackSnapshot(
                        promotion_key="24b_context",
                        signal_available=abs(float(row.get("context_delta") or 0)) > 0,
                        delta=float(row.get("context_delta") or 0),
                        mode="shadow",
                    ),
                    PromotionTrackSnapshot(
                        promotion_key="24c_xg",
                        signal_available=abs(float(row.get("xg_delta") or 0)) > 0,
                        delta=float(row.get("xg_delta") or 0),
                        mode="shadow",
                    ),
                    PromotionTrackSnapshot(
                        promotion_key="24c_sportmonks",
                        signal_available=bool(row.get("disagreement_signal")),
                        delta=float(row.get("sportmonks_conf_delta") or 0),
                        disagreement=float(str(row.get("disagreement_signal") or "").split(":")[-1])
                        if ":" in str(row.get("disagreement_signal") or "")
                        else None,
                        mode="shadow",
                    ),
                ],
                snapshots=IntelligenceSnapshots(),
                shadow_signals={"source": "phase25_b bootstrap"},
            )
            if record.settled and record.one_x_two_correct is not None:
                record.confidence_calibration_ok = record.one_x_two_correct == (record.confidence >= 50)
            self._store.append(record)
            existing.add(fid)
            added += 1
        if added:
            self.settle_from_match_results()
        return added
