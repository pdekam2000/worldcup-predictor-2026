# Controlled infra deployment plan

1. Local validation + tests green
2. Commit to GitHub source-of-truth branch
3. Migration dry-run on staging DB copy
4. Backup production DB
5. Apply additive CREATE TABLE migrations
6. Deploy code with shadow flag ON, canonical unchanged
7. Restart shadow/worker only (not required for canonical)
8. Health: canonical prediction sample + shadow row inserts
9. GPT Actions: confirm public schema unchanged
10. Rollback plan ready

Do **not** set Lambda V2 / Exact V2 as canonical.
