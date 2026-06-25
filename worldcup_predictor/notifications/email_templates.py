"""HTML + plain-text email templates for transactional mail."""

from __future__ import annotations

from html import escape


def _layout(*, title: str, body_html: str, cta_url: str | None = None, cta_label: str | None = None) -> tuple[str, str]:
    cta_block = ""
    if cta_url and cta_label:
        cta_block = (
            f'<p style="margin:24px 0;">'
            f'<a href="{escape(cta_url)}" style="background:#2563eb;color:#fff;padding:12px 20px;'
            f'text-decoration:none;border-radius:6px;display:inline-block;">{escape(cta_label)}</a>'
            f"</p>"
            f'<p style="font-size:13px;color:#64748b;">Or copy this link:<br>{escape(cta_url)}</p>'
        )
    html = f"""<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;line-height:1.5;color:#0f172a;max-width:560px;margin:0 auto;padding:24px;">
  <h2 style="color:#0f172a;margin-top:0;">{escape(title)}</h2>
  {body_html}
  {cta_block}
  <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0;">
  <p style="font-size:12px;color:#94a3b8;">WorldCup Predictor Pro — for entertainment purposes only.</p>
</body></html>"""
    return html, title


def verification_email(*, verify_url: str, ttl_hours: int) -> tuple[str, str, str]:
    subject = "Verify your WorldCup Predictor account"
    text = (
        "Please verify your email address to activate prediction access.\n\n"
        f"Verification link (expires in {ttl_hours} hours):\n{verify_url}\n\n"
        "If you did not create this account, you can ignore this email."
    )
    body = (
        f"<p>Please verify your email address to activate prediction access.</p>"
        f"<p>This link expires in <strong>{ttl_hours} hours</strong>.</p>"
        f"<p>If you did not create this account, you can ignore this email.</p>"
    )
    html, _ = _layout(title="Verify your email", body_html=body, cta_url=verify_url, cta_label="Verify email")
    return subject, text, html


def password_reset_email(*, reset_url: str, ttl_hours: int) -> tuple[str, str, str]:
    subject = "Reset your WorldCup Predictor password"
    text = (
        "We received a request to reset your password.\n\n"
        f"Reset link (expires in {ttl_hours} hours):\n{reset_url}\n\n"
        "If you did not request this, you can ignore this email."
    )
    body = (
        "<p>We received a request to reset your password.</p>"
        f"<p>This link expires in <strong>{ttl_hours} hours</strong>.</p>"
        "<p>If you did not request this, you can ignore this email.</p>"
    )
    html, _ = _layout(title="Reset your password", body_html=body, cta_url=reset_url, cta_label="Reset password")
    return subject, text, html


def contact_admin_notification(
    *,
    user_email: str,
    subject: str,
    message: str,
    category: str,
) -> tuple[str, str, str]:
    mail_subject = f"[WCP Contact] {subject}"
    text = (
        f"User email: {user_email}\n"
        f"Category: {category}\n"
        f"Subject: {subject}\n\n"
        f"{message}\n"
    )
    body = (
        f"<p><strong>From:</strong> {escape(user_email)}</p>"
        f"<p><strong>Category:</strong> {escape(category)}</p>"
        f"<p><strong>Subject:</strong> {escape(subject)}</p>"
        f'<pre style="white-space:pre-wrap;background:#f8fafc;padding:12px;border-radius:6px;">{escape(message)}</pre>'
    )
    html, _ = _layout(title="New contact message", body_html=body)
    return mail_subject, text, html
