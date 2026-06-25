"""Outbound notifications (email)."""

from worldcup_predictor.notifications.diagnostics import email_diagnostics
from worldcup_predictor.notifications.email_delivery import EmailSendResult, send_email, smtp_configured

__all__ = ["EmailSendResult", "email_diagnostics", "send_email", "smtp_configured"]
