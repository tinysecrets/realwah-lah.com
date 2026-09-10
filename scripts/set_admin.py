#!/usr/bin/env python3
"""Create or reset the WAH-LAH admin account.

Uses the same bcrypt format as backend/server.py and reads MongoDB settings
from the repository root .env. The password is read from ADMIN_PASSWORD when
present, otherwise prompted interactively. Plaintext credentials are never
written to the repository or printed.
"""
from pathlib import Path
import getpass
import os
from datetime import datetime, timezone

import bcrypt
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

uri = os.getenv("MONGODB_URI") or os.getenv("MONGO_URL") or os.getenv("MONGO_URI")
if not uri:
    raise SystemExit("ERROR: MONGODB_URI, MONGO_URL, or MONGO_URI is not set in .env")

db_name = os.getenv("DB_NAME", "wahlah_prod")
email = (os.getenv("ADMIN_EMAIL") or input("Admin email [admin@wah-lah.com]: ")).strip().lower() or "admin@wah-lah.com"
name = (input("Admin display name [WAH-LAH Admin]: ").strip() or "WAH-LAH Admin")

password = os.getenv("ADMIN_PASSWORD")
if password:
    print("Using ADMIN_PASSWORD from the environment; plaintext password will not be printed.")
else:
    password = getpass.getpass("New admin password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("ERROR: Passwords do not match")

if not password:
    raise SystemExit("ERROR: Password cannot be empty")
if len(password) < 8:
    raise SystemExit("ERROR: Use at least 8 characters")

password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
now = datetime.now(timezone.utc).isoformat()

client = MongoClient(uri, serverSelectionTimeoutMS=10000)
try:
    client.admin.command("ping")
    db = client[db_name]
    users = db.users

    existing = users.find_one({"email": email})
    update = {
        "$set": {
            "email": email,
            "name": name,
            "role": "admin",
            "password_hash": password_hash,
            "updated_at": now,
        },
        "$setOnInsert": {
            "sugar_tokens": 0,
            "game_credits": 0,
            "credits": 0.0,
            "age_verified": True,
            "game_accounts": {},
            "game_username": "",
            "game_password": "",
            "last_amoe_claim": None,
            "created_at": now,
        },
    }
    users.update_one({"email": email}, update, upsert=True)
    user = users.find_one({"email": email}, {"password_hash": 0})

    action = "updated" if existing else "created"
    print(f"SUCCESS: admin account {action}")
    print(f"Email: {user['email']}")
    print(f"Role:  {user.get('role')}")
    print(f"DB:    {db_name}")
    print("Password hash stored with bcrypt; plaintext password was not saved or printed.")
finally:
    client.close()
