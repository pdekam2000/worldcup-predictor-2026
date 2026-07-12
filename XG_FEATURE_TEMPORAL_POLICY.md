# xG Feature Temporal Policy

1. **Historical realized match xG** — POST_MATCH_ONLY, never in prematch store
2. **Rolling team xG prior** — SAFE if source fixture kickoff < target kickoff
3. **Provider prematch xG** — SAFE only with valid availability timestamp (WC SportMonks live)
4. **Target match realized xG** — EXCLUDED always

Do not use CSV `expectedGoalsHome` as prematch feature.
