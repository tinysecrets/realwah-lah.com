import html
import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class EmailService:
    """Server-side email delivery through the Resend HTTP API."""

    def __init__(self):
        self.api_key = os.environ.get("RESEND_API_KEY", "").strip()
        self.from_email = (
            os.environ.get("RESEND_FROM_EMAIL", "").strip()
            or os.environ.get("CUSTOM_EMAIL_FROM", "").strip()
            or os.environ.get("EMAIL_FROM", "").strip()
            or "WAH-LAH <onboarding@resend.dev>"
        )
        self.api_url = "https://api.resend.com/emails"

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
    ) -> tuple[bool, str]:
        """Send an email through Resend without exposing credentials or tokens in logs."""
        if not self.api_key:
            logger.warning("Resend API key not configured; email not sent")
            return False, "Email service not configured"

        payload = {
            "from": self.from_email,
            "to": [to_email],
            "subject": subject,
            "html": html_content,
        }
        if text_content:
            payload["text"] = text_content

        try:
            response = requests.post(
                self.api_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=10,
            )
        except requests.RequestException as exc:
            logger.error("Resend request failed: %s", exc)
            return False, "Email delivery failed"

        if 200 <= response.status_code < 300:
            logger.info("Email sent to %s", to_email)
            return True, "Email sent successfully"

        # Never log response bodies: providers can return diagnostic data that
        # should not become part of application logs.
        logger.error("Resend rejected email with HTTP %s", response.status_code)
        return False, "Email delivery failed"

    def send_welcome_email(self, to_email: str, name: str) -> tuple[bool, str]:
        safe_name = html.escape(name)
        frontend = os.environ.get("FRONTEND_URL", "https://realwah-lah.com").rstrip("/")
        body = f"""
        <html><body style="font-family:Arial,sans-serif;background:#12051a;color:#f7e9c9;padding:32px">
          <div style="max-width:600px;margin:auto;padding:28px;border-radius:16px;background:#260927">
            <h1>WAH-LAH</h1><h2>Welcome, {safe_name}!</h2>
            <p>Your account is ready. Start playing from the WAH-LAH dashboard.</p>
            <p><a href="{html.escape(frontend)}" style="display:inline-block;padding:12px 22px;background:#d4af37;color:#160b0b;text-decoration:none;border-radius:8px">Start Playing</a></p>
          </div>
        </body></html>
        """
        return self.send_email(to_email, "Welcome to WAH-LAH", body, f"Welcome to WAH-LAH, {name}! {frontend}")

    def send_deposit_confirmation(self, to_email: str, name: str, amount: float, credits: float, game_name: str) -> tuple[bool, str]:
        body = f"""
        <html><body style="font-family:Arial,sans-serif;background:#12051a;color:#f7e9c9;padding:32px">
          <div style="max-width:600px;margin:auto;padding:28px;border-radius:16px;background:#260927">
            <h2>Deposit Confirmed</h2><p>Hi {html.escape(name)}, your deposit was credited.</p>
            <p><strong>Amount:</strong> ${amount:.2f}</p><p><strong>Credits:</strong> {credits:.2f}</p><p><strong>Game:</strong> {html.escape(game_name)}</p>
          </div>
        </body></html>
        """
        return self.send_email(to_email, f"Deposit Confirmed - ${amount:.2f} - WAH-LAH", body)

    def send_withdrawal_notification(self, to_email: str, name: str, amount: float, status: str, btc_address: Optional[str] = None) -> tuple[bool, str]:
        body = f"""
        <html><body style="font-family:Arial,sans-serif;background:#12051a;color:#f7e9c9;padding:32px">
          <div style="max-width:600px;margin:auto;padding:28px;border-radius:16px;background:#260927">
            <h2>Withdrawal Update</h2><p>Hi {html.escape(name)}, your withdrawal status is <strong>{html.escape(status)}</strong>.</p>
            <p><strong>Amount:</strong> ${amount:.2f}</p>
          </div>
        </body></html>
        """
        return self.send_email(to_email, f"Withdrawal {status.title()} - WAH-LAH", body)

    def send_welcome_rich(self, to_email: str, name: str) -> tuple[bool, str]:
        frontend = os.environ.get("FRONTEND_URL", "https://realwah-lah.com").rstrip("/")
        safe_name = html.escape(name)
        safe_frontend = html.escape(frontend, quote=True)
        body = f"""
        <!doctype html><html><body style="margin:0;padding:40px 16px;background:#0f0410;font-family:Arial,sans-serif;color:#e9dfc2">
          <div style="max-width:600px;margin:auto;padding:30px;border-radius:16px;background:#1e0a23;border:1px solid #3b2141">
            <h1 style="color:#f7e9c9">WAH-LAH <span style="color:#d4af37">THE MAGIC REVEAL</span></h1>
            <p>Welcome, {safe_name}! Your WAH-LAH account is ready.</p>
            <p><a href="{safe_frontend}" style="display:inline-block;padding:14px 28px;border-radius:999px;background:#d4af37;color:#1a0a0a;text-decoration:none;font-weight:700">Begin the Reveal →</a></p>
            <p style="font-size:12px;color:#9d8b66">This message was sent from {html.escape(self.from_email)}</p>
          </div>
        </body></html>
        """
        return self.send_email(to_email, "Welcome to WAH-LAH — The Magic Reveal", body, f"Welcome to WAH-LAH, {name}! Visit {frontend} to get started.")

    def send_password_reset_email(self, to_email: str, name: str, token: str) -> tuple[bool, str]:
        """Send the one-time reset link. The token is never logged or returned."""
        frontend = os.environ.get("FRONTEND_URL", "https://realwah-lah.com").rstrip("/")
        reset_path = os.environ.get("PASSWORD_RESET_PATH", "/reset-password")
        reset_link = f"{frontend}{reset_path}?token={token}"
        safe_name = html.escape(name)
        safe_link = html.escape(reset_link, quote=True)
        body = f"""
        <!doctype html><html><body style="margin:0;padding:40px 16px;background:#0b0410;font-family:Arial,sans-serif;color:#e9dfc2">
          <div style="max-width:600px;margin:auto;padding:28px;border-radius:12px;background:#2b0b2f">
            <h2 style="color:#f7e9c9">Password Reset Requested</h2>
            <p>Hi {safe_name}, we received a request to reset your password.</p>
            <p>This link expires in 60 minutes and can only be used once.</p>
            <p style="text-align:center;margin:24px 0"><a href="{safe_link}" style="display:inline-block;padding:12px 26px;border-radius:8px;background:#d4af37;color:#0b0310;font-weight:700;text-decoration:none">Reset Password</a></p>
            <p style="font-size:12px;word-break:break-all;color:#bfae86">{safe_link}</p>
          </div>
        </body></html>
        """
        text = f"Reset your WAH-LAH password: {reset_link}\nThis link expires in 60 minutes."
        return self.send_email(to_email, "WAH-LAH Password Reset", body, text)


email_service = EmailService()
