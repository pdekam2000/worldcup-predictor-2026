# OpenAPI Scope Default Review

## Finding

Owner GPT instructions use `scope=owner`. OpenAPI/API defaults omitted `scope` to `production` (Tier A only).

## Decision

**PUBLIC_DEFAULT_BEHAVIOR_UNCHANGED = YES**

Global API default remains `scope=production` for backward compatibility with public SaaS clients.

**OWNER_DEFAULT_DAILY_GPT_FLOW_INCLUDES_A_PLUS_B = YES**

Achieved via:

1. **Owner GPT instructions** — explicitly require `scope=owner` for daily discovery, filtering, and prediction jobs.
2. **Worker default** — when `scope=owner` and `prediction_scope` omitted, resolves to `prediction_scope=owner` (unified A+B).
3. **Per-fixture internal routing** — Tier A uses `production`, Tier B uses `owner_shadow` inside worker; owner sees one unified list.
4. **New `listTodayMatches` endpoint** — broad listing without prediction eligibility gate; separate from `discoverTodayMatches`.

## Not changed

- Global OpenAPI default for `scope` on public endpoints (still `production`).
- Public production prediction behavior.

## Owner-visible labels

| Tier | display_status | display_label |
|------|----------------|---------------|
| A | TRUSTED | TRUSTED |
| B | TEST_PHASE | TEST PHASE — UNDER FORWARD EVALUATION |

## Scope aliases (owner convenience)

- `scope=trusted` → production discovery (Tier A only)
- `scope=test_phase` → shadow discovery (Tier B only)
- `scope=owner` → Tier A + Tier B
