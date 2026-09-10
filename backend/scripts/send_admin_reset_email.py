#!/usr/bin/env python3
"""Trigger the application's real password-reset flow for the admin account.

This script deliberately does not generate, store, or print reset tokens. The
backend remains the single source of truth for token generation, hashing,
expiry, persistence, and Resend delivery.
"""
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

email = (os.getenv("ADMIN_EMAIL") or "").strip().lower()
if not email:
    email = input("Admin email: ").strip().lower()
if not email:
    raise SystemExit("ERROR: Admin email is required")

backend_url = (
    os.getenv("BACKEND_URL")
    or os.getenv("API_BASE_URL")
    or "https://api.wah-lah.com"
).rstrip("/")

endpoint = f"{backend_url}/api/ext/password/forgot"
try:
    response = requests.post(endpoint, json={"email": email}, timeout=15)
except requests.RequestException as exc:
    raise SystemExit(f"ERROR: Could not reach password-reset API: {exc}")

if not 200 <= response.status_code < 300:
    raise SystemExit(f"ERROR: Password-reset API returned HTTP {response.status_code}")

print("SUCCESS: password-reset request accepted")
print(f"Admin email: {email}")
print("The reset token was generated and handled by the backend; it was not stored or printed by this script.")
