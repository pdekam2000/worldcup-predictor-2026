# Phase 21A — Rule A Shadow Report

Generated: 2026-06-19T19:01:51.877423+00:00

## Mode

- **Shadow only** — production predictions unchanged
- **No deploy**, no user-facing changes
- Shadow store: `data\shadow\rule_a_shadow.jsonl`

## 1. Collection status

| Metric | Count | Target |
|--------|-------|--------|
| Shadow predictions (unique fixtures) | **207** | 100+ |
| Finished fixtures with results | **207** | 30+ |
| Ready for decision | **YES** | |

## 2. Accuracy (finished fixtures only)

| Strategy | Accuracy | n |
|----------|----------|---|
| Production | 30.0% | 207 |
| WDE only | 34.8% | 207 |
| Scoreline only | 30.0% | 207 |
| **Rule A shadow** | **36.7%** | 207 |

- Rule A vs Production: **+6.8%**
- Rule A vs WDE: **+1.9%**

## 3. Rule A source mix (finished)

- `wde`: 182 (87.9%)
- `scoreline`: 25 (12.1%)

## 4. Override rescue (Rule A fixed production-harmful cases)

- Cases where production wrong, WDE right, Rule A right: **62**

## 5. Phase 21B gate

**PROCEED to Phase 21B** — Rule A remains superior to production on finished shadow sample.

## Success criterion

- Rule A superior to production: **YES**

**Stop — shadow only unless Phase 21B approved.**
