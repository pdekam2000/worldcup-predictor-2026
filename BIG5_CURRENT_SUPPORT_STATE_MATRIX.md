# Big 5 — Current Support State Matrix

**Generated:** 2026-07-10 22:05 CEST

| League | Registry | GPT Tier | Owner scope | Production | Shadow | WDE | ECSE | Forward eval |
|--------|----------|----------|-------------|------------|--------|-----|------|--------------|
| Premier League | ✅ Tier A | **A TRUSTED** | ✅ | ✅ | ❌ | ALREADY_SUPPORTED | ALREADY_SUPPORTED | ✅ |
| Bundesliga | ✅ Tier A | **A TRUSTED** | ✅ | ✅ | ❌ | ALREADY_SUPPORTED | ALREADY_SUPPORTED | ✅ |
| Serie A | ✅ registry | **B TEST** (new) | ✅ | ❌ | ✅ | READY | READY | ✅ |
| La Liga | ✅ registry | **B TEST** (new) | ✅ | ❌ | ✅ | READY | READY | ✅ |
| Ligue 1 | ✅ registry | **B TEST** (new) | ✅ | ❌ | ✅ | READY | READY | ✅ |

**Key finding:** Premier League and Bundesliga were **already Tier A Trusted** in `DAILY_SUPPORTED_COMPETITIONS`. Duplicating them to Tier B would regress production policy — **not onboarded** to Tier B.

Serie A, La Liga, Ligue 1 were **registry-only / UNSUPPORTED in GPT Actions** before this phase — now Tier B Test Phase.
