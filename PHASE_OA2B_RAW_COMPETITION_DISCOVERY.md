# PHASE OA-2B — Raw OddAlerts Competition Discovery

**Generated:** 2026-06-23T13:13:20.615080+00:00  
**Mode:** Raw discovery audit — no league assumptions  

---

## Primary Answer

Under the **current OddAlerts subscription**, historical finished fixtures are available only via the **`value/results` pool** (4215 rows scanned, 609 unique finished fixtures, 185 competitions).

The **competitions catalogue** lists **2415** competitions (2230 have **zero** fixtures in the results/upcoming pools).

**England Premier League (id 423), Champions League (id 51), and Germany Bundesliga (id 477) exist in the catalogue** but have **0 finished fixtures** in the `value/results` pool on this token. `fixtures/results` returns **0 rows** for their current `season_id` values.

There are **84** competitions named "Premier League" in the catalogue (different countries); only the England entry uses id **423**.

---

## API Usage

- API calls: **87**
- Value/results pages: **17**
- Value/upcoming pages: **7**

## Target Leagues (ID verification)

| Competition | Catalogue ID | In catalogue | Finished in results pool | fixtures/results rows |
|-------------|--------------|--------------|--------------------------|------------------------|
| england_premier_league | 423 | yes | 0 | 0 |
| champions_league | 51 | yes | 0 | 0 |
| germany_bundesliga | 477 | yes | 0 | 0 |

## Top 50 Competitions by Finished Fixtures (results pool)

| Rank | ID | Name | Country | Finished | Seasons in pool | Embedded odds | odds/history sample |
|------|-----|------|---------|----------|-----------------|---------------|---------------------|
| 1 | 378 | Serie D | Brazil | 32 | 2026(1036049), current_season_id(1036049) | 919 | 234 |
| 2 | 927 | USL League Two | United States | 19 | 2026(1036569), current_season_id(1036569) | 460 | 52 |
| 3 | 750 | Primera B Nacional | Argentina | 17 | 2026(1035687), current_season_id(1035687) | 665 | 249 |
| 4 | 764 | Torneo Federal A | Argentina | 17 | 2026(1035839), current_season_id(1035839) | 387 | 230 |
| 5 | 966 | Chilean Cup | Chile | 14 | 2026(1036085), current_season_id(1036085) | 734 | 248 |
| 6 | 1690 | World Cup | World | 12 | 2026(1035503), current_season_id(1035503) | 1881 | 313 |
| 7 | 297385 | Copa de La Liga | Peru | 12 | 2026(2254073), current_season_id(2254073) | 327 | 81 |
| 8 | 656 | Paulista Série B | Brazil | 11 | 2026(1036026), current_season_id(1036026) | 68 | 29 |
| 9 | 207 | Serie C | Brazil | 10 | 2026(1036065), current_season_id(1036065) | 528 | 222 |
| 10 | 759 | Primera B Metropolitana | Argentina | 10 | 2026(1035691), current_season_id(1035691) | 439 | 259 |
| 11 | 71 | USL Championship | United States | 9 | 2026(1035643), current_season_id(1035643) | 533 | 281 |
| 12 | 540 | Brasileiro U20 | Brazil | 9 | 2026(1700767), current_season_id(1700767) | 337 | 180 |
| 13 | 56 | Botola Pro | Morocco | 8 | 2025/2026(910989), current_season_id(910989) | 419 | 245 |
| 14 | 102 | Botola 2 | Morocco | 8 | 2025/2026(1034777), current_season_id(1034777) | 163 | 166 |
| 15 | 206 | Serie B | Brazil | 8 | 2026(1036064), current_season_id(1036064) | 575 | 301 |
| 16 | 242 | Superettan | Sweden | 8 | 2026(1035685), current_season_id(1035685) | 558 | 309 |
| 17 | 928 | Tercera  - Playoffs | Spain | 8 | 2025/2026(1035237), current_season_id(1035237) | 92 | 3 |
| 18 | 977 | WPSL | United States | 8 | 2026(1036568), current_season_id(1036568) | 63 | 28 |
| 19 | 1215 | MLS Next Pro | United States | 8 | 2026(1036436), current_season_id(1036436) | 386 | 134 |
| 20 | 1314 | USL W League | United States | 8 | 2026(1036566), current_season_id(1036566) | 77 | 31 |
| 21 | 116 | USL League One | United States | 7 | 2026(1035647), current_season_id(1035647) | 304 | 220 |
| 22 | 125 | 1. Division | Norway | 7 | 2026(1035677), current_season_id(1035677) | 591 | 299 |
| 23 | 186 | Division 2: Sodra Svealand | Sweden | 7 | 2026(1036539), current_season_id(1036539) | 275 | 187 |
| 24 | 362 | Liga 3 | Georgia | 7 | 2026(1036204), current_season_id(1036204) | 43 | 26 |
| 25 | 747 | Azadegan League | Iran | 7 | 2025/2026(1034733), current_season_id(1034733) | 87 | 149 |
| 26 | 1130 | Club Friendlies 3 | World | 7 | 2026(1035622), current_season_id(1035622) | 273 | 3 |
| 27 | 1306 | Tercera A | Chile | 7 | 2026(1036074), current_season_id(1036074) | 59 | 41 |
| 28 | 12 | Premier League | Kazakhstan | 6 | 2026(1036304), current_season_id(1036304) | 333 | 208 |
| 29 | 59 | Besta deild | Iceland | 6 | 2026(1036240), current_season_id(1036240) | 415 | 256 |
| 30 | 76 | FNL 2 - Group 1 | Russia | 6 | 2026(1036459), current_season_id(1036459) | 15 | 9 |
| 31 | 243 | Vysshaya Liga | Belarus | 6 | 2026(1035958), current_season_id(1035958) | 126 | 139 |
| 32 | 400 | Women's National League | Republic of Ireland | 6 | 2026(1035657), current_season_id(1035657) | 49 | 40 |
| 33 | 463 | Segunda División | Chile | 6 | 2026(1036087), current_season_id(1036087) | 260 | 222 |
| 34 | 810 | GFF First Division | Gambia | 6 | 2025/2026(1035626), current_season_id(1035626) | 65 | 31 |
| 35 | 1213 | 3. Division - Group 4 | Norway | 6 | 2026(1035786), current_season_id(1035786) | 187 | 165 |
| 36 | 1370 | Primera División Amateur | Uruguay | 6 | 2026(1991776), current_season_id(1991776) | 51 | 50 |
| 37 | 21 | Segunda Division | Uruguay | 5 | 2026(1036581), current_season_id(1036581) | 223 | 220 |
| 38 | 25 | Zain Premier League | Kuwait | 5 | 2025/2026(1034769), current_season_id(1034769) | 192 | 188 |
| 39 | 124 | Esiliiga A | Estonia | 5 | 2026(1036142), current_season_id(1036142) | 230 | 184 |
| 40 | 148 | Erovnuli Liga 2 | Georgia | 5 | 2026(1035775), current_season_id(1035775) | 149 | 148 |
| 41 | 190 | Inkasso-Deildin | Iceland | 5 | 2026(1036233), current_season_id(1036233) | 273 | 270 |
| 42 | 254 | Esiliiga B | Estonia | 5 | 2026(1036143), current_season_id(1036143) | 172 | 157 |
| 43 | 630 | 1. Division Women | Norway | 5 | 2026(1035679), current_season_id(1035679) | 47 | 41 |
| 44 | 726 | Elite One | Cameroon | 5 | 2025/2026(1035756), current_season_id(1035756) | 6 | 3 |
| 45 | 761 | Premier League | Ethiopia | 5 | 2025/2026(1035486), current_season_id(1035486) | 126 | 152 |
| 46 | 798 | NPSL | United States | 5 | 2026(1036634), current_season_id(1036634) | 70 | 51 |
| 47 | 1285 | New South Wales NPL Women | Australia | 5 | 2026(1035762), current_season_id(1035762) | 58 | 61 |
| 48 | 1331 | Carioca A2 | Brazil | 5 | 2026(1035995), current_season_id(1035995) | 110 | 61 |
| 49 | 1422 | Primera Division Women | Argentina | 5 | 2026(1035833), current_season_id(1035833) | 118 | 90 |
| 50 | 3 | Premier League | Mongolia | 4 | 2025/2026(1035445), current_season_id(1035445) | 52 | 91 |

## Seasons

Unique competition+season pairs observed in pools: **2451**
(Full list in `artifacts/oddalerts_raw_competition_inventory.json` → `seasons_available`.)

## Catalogue vs Pool Gap

The token can **list** 2,415 competitions but only **~185** appear in `value/results` + `value/upcoming`. Major European leagues are catalogue-only on this subscription tier.

---

**Artifact:** `artifacts/oddalerts_raw_competition_inventory.json`
