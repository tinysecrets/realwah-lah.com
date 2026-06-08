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

# Global instance
email_service = EmailService()
