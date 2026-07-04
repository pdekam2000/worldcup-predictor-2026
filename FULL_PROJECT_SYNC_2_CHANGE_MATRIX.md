# FULL-PROJECT-SYNC-2 — Change Matrix

| Change area | Local | GitHub (pre-sync) | Hetzner (pre-sync) | Action |
|-------------|-------|-------------------|--------------------|--------|
| Owner UI Top3 / EndResult panel | yes | no | no | commit → pull |
| odds freshness modules | yes | no | untracked | commit → pull |
| timestamp normalization | yes | no | untracked | commit → pull |
| fixture sync / wc_schedule_sync | yes | no | untracked | commit → pull |
| pipeline hotfix (predictions/cycle) | yes | no | tracked drift | commit → pull (local wins) |
| euro_c_odds_import timestamp write | yes | no | tracked drift | commit → pull |
| production_pipeline runner flags | yes | no | tracked drift | commit → pull |
| ECSE rerank research (shadow) | yes | no | untracked | commit → pull |
| top3/top10/eval_coverage research | yes | no | partial | commit → pull |
| match eval 1567310 tooling | yes | no | untracked | commit → pull |
| controlled knockout pred 2 | yes | no | untracked | commit → pull |
| validators (all phases) | yes | no | untracked | commit → pull |
| phase docs / reports | yes | no | partial untracked | commit → pull |
| production DB | Hetzner only | — | canonical | **no copy** |
| sportmonks dumps / JSONL | dirty both | no | runtime | **exclude** |
| stray root .py on Hetzner | no | no | yes | delete on server post-pull |
| validate_controlled_knockout_3 | **missing** | no | no | N/A (phase 3 not done) |

**Goal:** After sync, all approved source rows = **yes / yes / yes**.
