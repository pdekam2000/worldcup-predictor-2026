# Phase 44D — Storage Contract Report

**Date:** 2026-06-21  
**Status:** PHASE_44D_STATUS = **DOCUMENTED**

## Problem

PostgreSQL, SQLite, and JSONL were used across the platform without a single authoritative ownership contract.

## Deliverable

**Authoritative document:** `STORAGE_CONTRACT.md` (v1.0)

## Summary

### PostgreSQL — SaaS primary

**Owns:** users, auth, subscriptions, billing, per-user prediction history, admin audit  
**Write:** via `saas_uow()` only; billing via Stripe webhooks  
**Read:** authenticated SaaS API routes  
**Sync:** no automatic SQLite → PG mirroring

### SQLite — prediction intelligence

**Path:** `data/football_intelligence.db`  
**Owns:** fixtures, stored predictions, evaluations, performance summaries, provider caches  
**Write:** `FootballIntelligenceRepository`; eval job writes evaluations only  
**Read:** global archive, performance center, best tips, predict cache  
**Sync:** file cache mirror on stored prediction upsert

### JSONL — legacy / research

**Owns:** shadow replays, training exports, debugging traces  
**Write:** validation scripts, shadow runners (never production SaaS path)  
**Read:** offline analysis only  
**Sync:** none to PG/SQLite without explicit migration job

## Validation

Included in `scripts/validate_phase44_hardening_sprint.py` as `storage_contract_doc` check — **PASS**

## Impact

Documentation-only phase — no runtime or prediction logic changes.
