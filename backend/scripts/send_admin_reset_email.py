#!/usr/bin/env python3
import os
import json
import secrets
import time
from pathlib import Path
import requests

TARGET_EMAIL = "REDACTED_EMAIL"
FRONTEND = os.environ.get('FRONTEND_URL', 'https://wah-lah.example.com').rstrip('/')
RESET_PATH = os.environ.get('PASSWORD_RESET_PATH', '/reset-password')
RESEND_KEY = os.environ.get('RESEND_API_KEY', '').strip()
FROM = os.environ.get('EMAIL_FROM') or os.environ.get('CUSTOM_EMAIL_FROM') or 'WAH-LAH <onboarding@resend.dev>'

# generate token
token = secrets.token_urlsafe(24)
expires = int(time.time()) + 3600

# persist token for reference
tmpdir = Path('backend/tmp')
tmpdir.mkdir(parents=True, exist_ok=True)
store_file = tmpdir / 'reset_tokens.json'
if store_file.exists():
    try:
        data = json.loads(store_file.read_text())
    except Exception:
        data = {}
else:
    data = {}

# store as simple record
data[TARGET_EMAIL] = {'token': token, 'expires': expires}
store_file.write_text(json.dumps(data, indent=2))

reset_link = f"{FRONTEND}{RESET_PATH}?token={token}"

# build HTML (matching email_service template)
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
              <p style="margin:6px 0 0;color:#d6c49a;font-size:13px;">Hi, we received a request to reset your password.</p>
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
              <div>This email was sent from {FROM}</div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

# write preview
preview_file = tmpdir / f'password_reset_{TARGET_EMAIL.replace("@","_at_")}.html'
preview_file.write_text(html)
print(f"Preview written to {preview_file}")

# attempt to send via Resend if key present
if RESEND_KEY:
    payload = {
        "from": FROM,
        "to": [TARGET_EMAIL],
        "subject": "WAH-LAH Password Reset",
        "html": html,
        "text": f"Reset your password: {reset_link} — This link expires in 60 minutes."
    }
    headers = {
        "Authorization": "Bearer " + RESEND_KEY,
        "Content-Type": "application/json"
    }
    try:
        resp = requests.post('https://api.resend.com/emails', json=payload, headers=headers, timeout=10)
        print('Resend response:', resp.status_code, resp.text[:400])
        if resp.status_code in (200,201):
            print('Email sent via Resend')
        else:
            print('Resend send failed')
    except Exception as e:
        print('Error sending via Resend:', e)
else:
    print('RESEND_API_KEY not configured; email not sent. Preview saved.')
