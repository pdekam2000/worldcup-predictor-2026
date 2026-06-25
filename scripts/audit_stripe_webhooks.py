#!/usr/bin/env python3
"""List Stripe webhook endpoints — no secrets."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stripe
from worldcup_predictor.config.settings import get_settings

s = get_settings()
stripe.api_key = s.stripe_secret_key.strip()
eps = stripe.WebhookEndpoint.list(limit=10)
print(f"webhook_count: {len(eps.data)}")
for ep in eps.data:
    print(f"webhook_url: {ep.url}")
    print(f"webhook_status: {getattr(ep, 'status', 'enabled')}")
    events = list(getattr(ep, 'enabled_events', []) or [])
    print(f"events: {','.join(events[:8])}")
