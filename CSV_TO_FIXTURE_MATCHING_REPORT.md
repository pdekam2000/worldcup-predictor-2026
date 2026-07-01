# CSV to Fixture Matching Report (DATA-1B)

**Matched rows:** 4061
**Unmatched rows:** 2059273

## Matching strategy

1. `kickoff[:10] + normalized home_team + normalized away_team` → `fixtures` table
2. OddAlerts `ID` column stored as `oddalerts_row_id` (selection id, not API fixture id)

## Unmatched sample (first 50)

| Source file | Kickoff | Home | Away | Market | Selection |
|-------------|---------|------|------|--------|-----------|
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Santos Laguna | DC United | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Charlotte | Cruz Azul | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Atletico Mitre | Temperley | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Atlético GO | Vasco da Gama | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Corinthians | Grêmio | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Milan | Real Madrid | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Carlos Manucci | ADT | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | New Mexico United | Las Vegas Lights | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Nashville SC | Mazatlán | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Dallas | Juárez | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Tigres UANL | Puebla | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Manchester United | Real Betis | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | SJ Earthquakes | LA Galaxy | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Astana | Milsami | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Al Mokawloon | Ceramica Cleopatra | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Bravo | Zrinjski | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Urartu | Baník Ostrava | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Ordabasy | Differdange 03 | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Pafos FC | Žalgiris | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | P-Iirot | Ilves II | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Levadia | Osijek | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Polissya Zhytomyr | Olimpija | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Tobol | St. Gallen | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | TransINVEST Vilnius | Mladá Boleslav | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | AEK Larnaca | Paksi SE | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Sabah | Maccabi Haifa | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Inter Club d'Escalde | AEK Athens | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Paide | Stjarnan | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Elfsborg | Sheriff | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Brann | Go Ahead Eagles | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Torpedo Kutaisi | Omonia Nicosia | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Tromsø | KuPS | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Universitatea Craiov | Maribor | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Progrès Niedercorn | Djurgården | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Ironi Kiryat Shmona | Ironi Tiberias | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Caernarfon Town | Legia Warszawa | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | IFK Trelleborg | Karlskrona | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Maccabi Petah Tikva | Sporting Braga | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Vaduz | St Patrick's | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Cherno More | Hapoel Be'er Sheva | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Botev Plovdiv | Panathinaikos | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Víkingur | Gent | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Neman Grodno | CFR Cluj | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Partizani Tirana | FC Iberia 1999 | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Smouha | Al Masry | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Egnatia Rrogozhinë | Víkingur Reykjavík | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Śląsk Wrocław | Riga | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Dunajská Streda | Zira | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | St. Mirren | Valur | team_over_under | over_05 |
| `away_over_under_0_5__over_05__unknown_to_unknown.csv` | 2024-08-01 | Shelbourne | Zürich | team_over_under | over_05 |

*…and 2059223 more unmatched rows.*
