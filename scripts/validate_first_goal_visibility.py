"""Validate first goal prediction data + UI render helpers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.ui.first_goal_display import (
        render_first_goal_sections,
        resolve_first_goal_v2,
    )

    fail = 0
    r = PredictPipeline(get_settings(), locale="en").run(1489374)
    if not r.success:
        print("FAIL pipeline")
        return 1
    p = r.prediction
    has_meta = bool((p.metadata or {}).get("first_goal_intelligence_v2"))
    fg = resolve_first_goal_v2(p, None)
    print(f"  metadata fg v2: {'PASS' if has_meta else 'FAIL'}")
    print(f"  resolve fg v2: {'PASS' if fg else 'FAIL'}")
    if not has_meta or not fg:
        fail += 1
    if fg:
        print(f"  team: {fg.first_goal_team_display}")
        print(f"  band: {fg.first_goal_minute_band}")
        print(f"  scorers: {len(fg.likely_first_goal_scorers)}")
        if fg.first_goal_team_display != "Germany":
            print("  FAIL expected Germany")
            fail += 1
        if fg.first_goal_minute_band != "16-30":
            print("  FAIL expected band 16-30")
            fail += 1
        if len(fg.likely_first_goal_scorers) < 2:
            print("  FAIL expected 2+ scorers")
            fail += 1

    class FakeSt:
        def markdown(self, *a, **k):
            pass

        def container(self, *a, **k):
            class C:
                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    pass

            return C()

        def progress(self, *a, **k):
            pass

        def caption(self, *a, **k):
            pass

        def info(self, *a, **k):
            pass

        def expander(self, *a, **k):
            class E:
                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    pass

            return E()

    import worldcup_predictor.ui.first_goal_display as fgd

    fgd.st = FakeSt()
    try:
        render_first_goal_sections(p, None, "en", key_suffix="test")
        print("  render_first_goal_sections: PASS")
    except Exception as exc:
        print(f"  render_first_goal_sections: FAIL ({exc})")
        fail += 1

    print(f"Result: {'PASS' if fail == 0 else 'FAIL'}")
    return fail


if __name__ == "__main__":
    raise SystemExit(main())
