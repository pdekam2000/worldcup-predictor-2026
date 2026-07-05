# NEXT-3-FRESH-ODDS-CONTROLLED-REGENERATION-1 — Report

**Phase:** NEXT-3-FRESH-ODDS-CONTROLLED-REGENERATION-1
**Recommendation:** `NEXT_3_MIXED_KEEP_AND_PROMOTE`
**Commit:** `282ef700f7bc31090f775f752f168d30e701ba24`
**Provider calls:** 1

## Task A — Forensic input audit

### Brazil vs Norway (1568100)
- Code path: `missing_odds_path`
- WDE pick: home conf=52.1 odds_status=ODDS_MISSING
- ECSE top1: 2-0 λ=(2.022103,0.892685)

### Mexico vs England (1570714)
- Code path: `missing_odds_path`
- WDE pick: home conf=27.6 odds_status=ODDS_MISSING
- ECSE top1: 1-1 λ=(1.013158,1.268576)

### Portugal vs Spain (1576756)
- Code path: `missing_odds_path`
- WDE pick: away conf=49.1 odds_status=ODDS_MISSING
- ECSE top1: 0-1 λ=(0.910577,1.845117)

## Promotion decisions

- **Brazil vs Norway**: PROMOTE_FRESH_INPUT_REGENERATION
  - promoted: {'promoted': True, 'ecse_snapshot_id': 8, 'ecse_reason': 'inserted', 'wde_hash': 'ea138a56bde02fa9', 'ecse_top1': '2-0', 'backup_ref': {'wde_hash': 'f08d0b93637b8f2a', 'ecse_top1': '2-0'}}
- **Mexico vs England**: KEEP_EXISTING_FROZEN
- **Portugal vs Spain**: KEEP_EXISTING_FROZEN
