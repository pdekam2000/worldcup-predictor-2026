"""Email delivery diagnostics — no secrets exposed."""

from __future__ import annotations

from worldcup_predictor.access.config import app_public_url
from worldcup_predictor.auth.verification_config import email_verification_required
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.notifications.email_delivery import admin_contact_email_configured, smtp_configured


def email_diagnostics(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    smtp_ok = smtp_configured(settings)
    admin_ok = admin_contact_email_configured(settings)
    public_url = app_public_url()
    return {
        "smtp_configured": smtp_ok,
        "admin_contact_email_configured": admin_ok,
        "email_operations_ready": smtp_ok and admin_ok,
        "smtp_host_set": bool((settings.smtp_host or "").strip()),
        "smtp_from_set": bool((settings.smtp_from or settings.smtp_user or "").strip()),
        "smtp_port": settings.smtp_port,
        "smtp_use_tls": settings.smtp_use_tls,
        "app_public_url": public_url,
        "verify_link_base": f"{public_url}/verify-email",
        "reset_link_base": f"{public_url}/reset-password",
        "channels": {
            "verification": smtp_ok,
            "password_reset": smtp_ok,
            "contact_admin": smtp_ok and admin_ok,
        },
        "email_verification_required": email_verification_required(settings),
    }
