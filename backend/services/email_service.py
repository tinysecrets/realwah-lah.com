import os
import logging
from typing import Optional
import requests

logger = logging.getLogger(__name__)

class EmailService:
    """
    Email service using Resend API
    """
    
    def __init__(self):
        self.api_key = os.environ.get("RESEND_API_KEY", "")
        # Auto-upgrade sender: if CUSTOM_EMAIL_FROM is set AND not empty, use it.
        # Otherwise fall back to Resend's always-works sandbox sender so launch
        # isn't blocked by DNS verification.
        custom = (os.environ.get("CUSTOM_EMAIL_FROM") or "").strip()
        default_sandbox = "WAH-LAH <onboarding@resend.dev>"
        self.from_email = custom or os.environ.get("EMAIL_FROM") or default_sandbox
        self.api_url = "https://api.resend.com/emails"
    
    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None
    ) -> tuple[bool, str]:
        """Send an email via Resend"""
        try:
            if not self.api_key:
                logger.warning("Resend API key not configured, skipping email")
                return False, "Email service not configured"
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            # Ensure the Authorization header uses the configured API key
            headers['Authorization'] = f"Bearer {self.api_key}"
            
            payload = {
                "from": self.from_email,
                "to": [to_email],
                "subject": subject,
                "html": html_content
            }
            
            if text_content:
                payload["text"] = text_content
            
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"Email sent to {to_email}: {subject}")
                return True, "Email sent successfully"
            else:
                error_msg = f"Email failed: {response.status_code} - {response.text}"
                logger.error(error_msg)
                return False, error_msg
        
        except Exception as e:
            logger.error(f"Email error: {str(e)}")
            return False, f"Email error: {str(e)}"
    
    def send_welcome_email(self, to_email: str, name: str) -> tuple[bool, str]:
        """Send welcome email to new users"""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; background: linear-gradient(135deg, #1a0a2e 0%, #2d1b3d 100%); color: #ffffff; padding: 40px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: rgba(45, 27, 61, 0.9); border-radius: 20px; padding: 40px; border: 2px solid #ff1493; }}
                .logo {{ text-align: center; margin-bottom: 30px; }}
                .logo h1 {{ color: #ff1493; font-size: 36px; margin: 0; text-shadow: 0 0 20px rgba(255, 20, 147, 0.5); }}
                .logo span {{ color: #ffd700; }}
                .content {{ line-height: 1.8; }}
                .button {{ display: inline-block; background: linear-gradient(135deg, #ff1493, #9b59b6); color: white; padding: 15px 40px; text-decoration: none; border-radius: 30px; margin: 20px 0; font-weight: bold; }}
                .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ff1493; font-size: 12px; color: #aaa; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="logo">
                    <h1>WAH-LAH <span>SWEEPS</span></h1>
                </div>
                <div class="content">
                    <h2>Welcome, {name}! 🎉</h2>
                    <p>Your WAH-LAH account is ready to roll! Get started with these sweet features:</p>
                    <ul>
                        <li>🎮 Play Fire Kirin, Panda Master, Orion Stars & Game Vault</li>
                        <li>💰 Deposit with Bitcoin or Card</li>
                        <li>⚡ Instant credit allocation</li>
                        <li>🏆 Fast BTC withdrawals</li>
                    </ul>
                    <p style="text-align: center;">
                        <a href="{os.environ.get('FRONTEND_URL', 'https://wahlah-deploy.preview.emergentagent.com')}" class="button">Start Playing</a>
                    </p>
                    <p><strong>Need help?</strong> Contact our support team anytime.</p>
                </div>
                <div class="footer">
                    <p>WAH-LAH - Play Responsibly | Must be 18+</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(
            to_email=to_email,
            subject="🎉 Welcome to WAH-LAH!",
            html_content=html
        )
    
    def send_deposit_confirmation(
        self,
        to_email: str,
        name: str,
        amount: float,
        credits: float,
        game_name: str
    ) -> tuple[bool, str]:
        """Send deposit confirmation email"""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; background: linear-gradient(135deg, #1a0a2e 0%, #2d1b3d 100%); color: #ffffff; padding: 40px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: rgba(45, 27, 61, 0.9); border-radius: 20px; padding: 40px; border: 2px solid #00ff00; }}
                .amount {{ font-size: 48px; color: #00ff00; text-align: center; margin: 20px 0; text-shadow: 0 0 20px rgba(0, 255, 0, 0.5); }}
                .details {{ background: rgba(0, 0, 0, 0.3); padding: 20px; border-radius: 10px; margin: 20px 0; }}
                .button {{ display: inline-block; background: linear-gradient(135deg, #00ff00, #00cc00); color: #000; padding: 15px 40px; text-decoration: none; border-radius: 30px; margin: 20px 0; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1 style="text-align: center; color: #00ff00;">✅ Deposit Confirmed!</h1>
                <div class="amount">${amount:.2f}</div>
                <div class="details">
                    <p><strong>Credits Added:</strong> {credits:.2f}</p>
                    <p><strong>Game:</strong> {game_name}</p>
                    <p><strong>Status:</strong> ✅ Credited to your account</p>
                </div>
                <p style="text-align: center;">
                    <a href="{os.environ.get('FRONTEND_URL', 'https://wahlah-deploy.preview.emergentagent.com')}" class="button">Play Now</a>
                </p>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(
            to_email=to_email,
            subject=f"✅ ${amount:.2f} Deposit Confirmed - WAH-LAH",
            html_content=html
        )
    
    def send_withdrawal_notification(
        self,
        to_email: str,
        name: str,
        amount: float,
        status: str,
        btc_address: Optional[str] = None
    ) -> tuple[bool, str]:
        """Send withdrawal status email"""
        status_color = "#ffd700" if status == "pending" else "#00ff00" if status == "approved" else "#ff4444"
        status_emoji = "⏳" if status == "pending" else "✅" if status == "approved" else "❌"
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; background: linear-gradient(135deg, #1a0a2e 0%, #2d1b3d 100%); color: #ffffff; padding: 40px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: rgba(45, 27, 61, 0.9); border-radius: 20px; padding: 40px; border: 2px solid {status_color}; }}
                .status {{ font-size: 36px; color: {status_color}; text-align: center; margin: 20px 0; }}
                .details {{ background: rgba(0, 0, 0, 0.3); padding: 20px; border-radius: 10px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1 style="text-align: center; color: {status_color};">Withdrawal Update</h1>
                <div class="status">{status_emoji} {status.upper()}</div>
                <div class="details">
                    <p><strong>Amount:</strong> ${amount:.2f}</p>
                    <p><strong>BTC Address:</strong> {btc_address if btc_address else 'N/A'}</p>
                    <p><strong>Status:</strong> {status.replace('_', ' ').title()}</p>
                </div>
                {'<p>Your Bitcoin is on the way! Check your wallet soon.</p>' if status == 'approved' else ''}
                {'<p>Your withdrawal is being reviewed. Large amounts require manual approval for security.</p>' if status == 'pending' else ''}
            </div>
        </body>
        </html>
        """
        
        return self.send_email(
            to_email=to_email,
            subject=f"{status_emoji} Withdrawal {status.title()} - WAH-LAH",
            html_content=html
        )

    def send_welcome_rich(self, to_email: str, name: str) -> tuple[bool, str]:
        """Send a rich HTML welcome email matching the 'Wah-Lah: The Magic Reveal' dark velvet + gold aesthetic."""
        frontend = os.environ.get('FRONTEND_URL', 'https://wah-lah.example.com').rstrip('/')
        html = f"""
        <!doctype html>
        <html>
        <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <title>Welcome to Wah-Lah</title>
        </head>
        <body style="margin:0;padding:0;background:linear-gradient(180deg,#0f0410 0%,#260927 100%);font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial;">
          <table width="100%" cellpadding="0" cellspacing="0" role="presentation">
            <tr>
              <td align="center" style="padding:40px 16px;">
                <table width="600" cellpadding="0" cellspacing="0" role="presentation" style="border-radius:16px;overflow:hidden;background:linear-gradient(180deg,rgba(10,3,18,0.9),rgba(30,10,35,0.95));box-shadow:0 20px 60px rgba(0,0,0,0.6);border:1px solid rgba(212,175,55,0.08);">

                  <tr>
                    <td style="padding:30px 32px 12px;text-align:center;background:linear-gradient(90deg,rgba(212,175,55,0.04),transparent);">
                      <h1 style="margin:0;font-size:28px;letter-spacing:2px;color:#f7e9c9;font-weight:700;text-shadow:0 2px 8px rgba(0,0,0,0.6);">WAH-LAH<span style="color:#d4af37;margin-left:8px;font-weight:800">THE MAGIC REVEAL</span></h1>
                      <p style="margin:6px 0 0;color:#cbb98a;font-size:13px;">Welcome to the velvet room — {name}, your sweepstakes journey begins ✨</p>
                    </td>
                  </tr>

                  <tr>
                    <td style="padding:22px 32px 10px;color:#e9dfc2;line-height:1.6;font-size:15px;">
                      <p style="margin:0 0 12px;">Thanks for joining Wah-Lah. You now have access to sweepstakes entries, exclusive games, and VIP bonuses. Here are a few quick ways to get started:</p>
                      <ul style="margin:0 0 18px 18px;padding:0;color:#e6dab3;">
                        <li style="margin-bottom:8px;">Play premium titles like Fire Kirin & Panda Master</li>
                        <li style="margin-bottom:8px;">Purchase Sweepstakes credit packages — $10, $25, $50, $100</li>
                        <li style="margin-bottom:8px;">Redeem credits or request payouts securely</li>
                      </ul>

                      <div style="text-align:center;margin-top:8px;margin-bottom:6px;">
                        <a href="{frontend}" style="display:inline-block;padding:14px 28px;border-radius:999px;background:linear-gradient(90deg,#d4af37,#f7e9c9);color:#1a0a0a;text-decoration:none;font-weight:700;box-shadow:0 6px 18px rgba(212,175,55,0.18);">Begin the Reveal →</a>
                      </div>

                      <p style="margin:12px 0 0;color:#bfae86;font-size:13px;">If you need help, reply to this email and our support magicians will assist you.</p>
                    </td>
                  </tr>

                  <tr>
                    <td style="background:linear-gradient(90deg,transparent,rgba(212,175,55,0.02));padding:18px 32px;color:#9d8b66;font-size:12px;text-align:center;">
                      <div style="margin-bottom:6px;">WAH-LAH — Play Responsibly • 21+ Members • Void where prohibited</div>
                      <div style="color:#7d6b4e;font-size:11px;">This message was sent from: {self.from_email}</div>
                    </td>
                  </tr>

                </table>
              </td>
            </tr>
          </table>
        </body>
        </html>
        """
        text = f"Welcome to Wah-Lah, {name}! Visit {frontend} to get started."
        return self.send_email(to_email=to_email, subject="Welcome to WAH-LAH — The Magic Reveal", html_content=html, text_content=text)

    def send_password_reset_email(self, to_email: str, name: str, token: str) -> tuple[bool, str]:
        """Send password reset email with secure token link (inline CSS, dark velvet + gold aesthetic)."""
        frontend = os.environ.get('FRONTEND_URL', 'https://wah-lah.example.com').rstrip('/')
        reset_path = os.environ.get('PASSWORD_RESET_PATH', '/reset-password')
        reset_link = f"{frontend}{reset_path}?token={token}"

        html = f"""
        <!doctype html>
        <html>
        <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <title>Password Reset</title>
        </head>
        <body style="margin:0;padding:0;background:#0b0410;font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial;">
          <table width="100%" cellpadding="0" cellspacing="0" role="presentation">
            <tr>
              <td align="center" style="padding:40px 16px;">
                <table width="600" cellpadding="0" cellspacing="0" role="presentation" style="border-radius:12px;background:linear-gradient(180deg,#12051a,#2b0b2f);border:1px solid rgba(212,175,55,0.06);overflow:hidden;">
                  <tr>
                    <td style="padding:24px 28px;text-align:center;">
                      <h2 style="margin:0;color:#f7e9c9;font-size:22px;">Password Reset Requested</h2>
                      <p style="margin:6px 0 0;color:#d6c49a;font-size:13px;">Hi {name}, we received a request to reset your password.</p>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding:18px 28px;color:#e9dfc2;">
                      <p style="margin:0 0 12px;">Click the button below to set a new password. For your safety this link expires in 60 minutes.</p>
                      <div style="text-align:center;margin:18px 0;">
                        <a href="{reset_link}" style="display:inline-block;padding:12px 26px;border-radius:8px;background:linear-gradient(90deg,#d4af37,#f2e1b6);color:#0b0310;font-weight:700;text-decoration:none;">Reset Password</a>
                      </div>
                      <p style="margin:10px 0 0;color:#bfae86;font-size:13px;">If you did not request a password reset, safely ignore this message or contact our support team.</p>
                      <hr style="border:none;border-top:1px solid rgba(255,255,255,0.03);margin:18px 0;" />
                      <p style="color:#9d8b66;font-size:11px;margin:0;">If the button does not work, copy & paste the following link into your browser:</p>
                      <p style="word-break:break-all;color:#bfae86;font-size:12px;">{reset_link}</p>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding:12px 28px 20px;text-align:center;color:#7d6b4e;font-size:11px;">
                      <div>This email was sent from {self.from_email}</div>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>
        </body>
        </html>
        """
        text = f"Reset your password: {reset_link} — This link expires in 60 minutes."
        return self.send_email(to_email=to_email, subject="WAH-LAH Password Reset", html_content=html, text_content=text)

# Global instance
email_service = EmailService()
