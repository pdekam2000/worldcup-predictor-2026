# OddAlerts Enrichment CSV Ingest Report

**Phase:** ODDALERTS-CSV-PLAYER-REF-1
**Final recommendation:** `ODDALERTS_ENRICHMENT_READY`
**Validation:** PASSED

## Files scanned

- `jfrehoXGyR.csv` → **REFEREE_CARDS_CSV** (15 rows, 44 cols, WC hint rows: 7)
- `oddalerts-upcoming-player-stats-2026-06-30.csv` → **PLAYER_STATS_CSV** (3063 rows, 60 cols, WC hint rows: 331)

## Import counts

- Player stats normalized rows: **3063**
- Referee/cards normalized rows: **15**
- High-confidence fixture links: **87**

## Crosswalk

- Status counts: `{'NO_MATCH': 80, 'MATCHED_LOW_CONFIDENCE': 12, 'MATCHED_HIGH_CONFIDENCE': 4}`

### Unmatched / low-confidence fixture names

- Adelaide Comets vs Croydon Kings
- Akademiya Ontustik vs Shakhter Karagandy
- Al Orouba FC vs Alsadd FC
- Astana II vs Kaspiy II
- Astana vs Zhenys
- Athletic Club Boise vs One Knoxville
- Atletico-PR U20 vs Vitoria U20
- Atlético JBG vs El Nacional
- Audax Italiano vs Palestino
- BATE vs Gomel
- Bahia U20 vs Cruzeiro U20
- Belgium vs Senegal
- Birmingham Legion vs Detroit City
- Botafogo PB vs Brusque
- Botafogo SP vs CRB
- Botafogo U20 vs Fluminense U20
- CODM Meknès vs FAR Rabat
- CR Khemis Zemamra vs FUS Rabat
- Caboolture vs SC Wanderers
- Caxias vs Anápolis

## Notes

- Enrichment only — **not** stored as odds snapshots.
- No ECSE/WDE generation. No public output changes.
- Owner WC report shows enrichment as informational only.

## Artifacts

- `artifacts\oddalerts_csv_schema_profile.json`
- `artifacts\oddalerts_enrichment_csv_import_summary.json`
- `artifacts\oddalerts_enrichment_fixture_crosswalk.json`
- `artifacts\oddalerts_enrichment_csv_validation.json`