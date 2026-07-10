# 1 Lyga — Team Mapping Validation

**Generated:** 2026-07-10 20:35 CEST  
**Provider league ID:** 361  
**Canonical key:** `one_lyga`

---

## Summary

| Metric | Value |
|--------|------:|
| Fixtures sampled | 12 |
| Fully mapped | **12** |
| Partial | 0 |
| Unresolved | 0 |
| **Mapping success rate** | **100%** |

**Verdict:** Team mapping sufficient for Tier B pilot — **proceed**.

---

## Validation method

Read-only API-Football prematch fixtures for league 361 (2026-07-10 → +30d). Each fixture required:

- provider `fixture_id`
- `home_team_id` and `away_team_id` (API-Football)
- non-empty team names
- Unicode names preserved (e.g. Kauno Žalgiris II, FA Šiauliai II)

No silent alias creation performed.

---

## Representative samples

| fixture_id | Home | Away | home_id | away_id | Status |
|-----------:|------|------|--------:|--------:|--------|
| 1556381 | Minija | Jonava | 3864 | 3862 | fully_mapped |
| 1556382 | Tauras | FA Šiauliai II | 11885 | 18840 | fully_mapped |
| 1556383 | Kauno Žalgiris II | Babrungas | 13971 | 14382 | fully_mapped |
| 1556384 | Ekranas | BFA | 10696 | 3857 | fully_mapped |
| 1556385 | Transinvest 2 | Neptūną Klaipėda | 27557 | 14384 | fully_mapped |
| 1556386 | Hegelmann II | Žalgiris II | 23156 | 3871 | fully_mapped |

---

## Unresolved teams

None in sampled window.

---

## Notes

- Reserve/youth team suffixes (II) are provider-native names — no normalization override applied.
- Historical SQLite linkage thin for `one_lyga` pre-onboarding; forward sync will populate via broad discovery `sync_prediction_candidates`.
