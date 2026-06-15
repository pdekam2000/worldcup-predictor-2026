"""Phase 49 validation — run: python scripts/validate_phase49.py"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ["PUBLIC_ACCESS_ENABLED"] = "true"
os.environ["FREE_DAILY_PREDICTION_LIMIT"] = "2"

from worldcup_predictor.access.config import access_db_path
from worldcup_predictor.access.prediction_gate import acquire_prediction_slot, preview_prediction_quota
from worldcup_predictor.access.repository import AccessRepository, get_access_repository


def main() -> int:
    db = Path(tempfile.gettempdir()) / f"phase49_test_{uuid.uuid4().hex}.db"
    os.environ["ACCESS_DB_PATH"] = str(db)
    import worldcup_predictor.access.repository as repo_mod

    repo_mod._repo_singleton = None
    repo = get_access_repository()
    user = repo.create_email_user("test@example.com")
    assert user is not None
    uid = user.user_id

    # Unpaid: 2 allowed, 3rd blocked
    for i in range(2):
        gate = acquire_prediction_slot(uid)
        assert gate.allowed, f"prediction {i+1} should be allowed"
    gate3 = acquire_prediction_slot(uid)
    assert not gate3.allowed, "3rd prediction should be blocked"
    assert gate3.show_upgrade

    preview = preview_prediction_quota(uid)
    assert preview.used_today >= 2

    # Paid unlock
    repo.mark_paid(uid, provider="test", payment_reference="test_ref")
    gate_paid = acquire_prediction_slot(uid)
    assert gate_paid.allowed and gate_paid.is_paid

    # Feedback
    assert repo.save_feedback(user_id=uid, rating=5, comment="Great", fixture_id=1489374)
    assert len(repo.list_feedback(limit=5)) >= 1
    assert "Great" in repo.export_feedback_csv()

    repo._conn.close() if repo._conn else None
    repo_mod._repo_singleton = None
    try:
        db.unlink()
    except OSError:
        pass
    print("Phase 49 validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
