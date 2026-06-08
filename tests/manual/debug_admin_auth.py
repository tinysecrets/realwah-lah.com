#!/usr/bin/env python3
"""
Debug admin authentication issue
"""

import requests
import json

def debug_admin_auth():
    base_url = "https://wahlah-deploy.preview.emergentagent.com"
    api_url = f"{base_url}/api"
    
    session = requests.Session()
    
    print("🔍 Debugging Admin Authentication")
    print("=" * 50)
    
    # Step 1: Login as admin
    print("\n1. Admin Login:")
    login_response = session.post(f"{api_url}/auth/login", json={
        "email": "admin@sugarcitysweeps.com",
        "password": "SugarCity2024!"
    })
    
    print(f"   Status: {login_response.status_code}")
    print(f"   Response: {login_response.json()}")
    print(f"   Cookies received: {dict(login_response.cookies)}")
    print(f"   Session cookies: {dict(session.cookies)}")
    
    # Step 2: Check /auth/me
    print("\n2. Check /auth/me:")
    me_response = session.get(f"{api_url}/auth/me")
    print(f"   Status: {me_response.status_code}")
    print(f"   Response: {me_response.json()}")
    print(f"   Session cookies sent: {dict(session.cookies)}")
    
    # Step 3: Try admin endpoint with explicit cookie
    print("\n3. Try admin endpoint:")
    admin_response = session.get(f"{api_url}/admin/users")
    print(f"   Status: {admin_response.status_code}")
    print(f"   Response: {admin_response.text[:200]}")
    
    # Step 4: Try with manual cookie header
    print("\n4. Try with manual Cookie header:")
    access_token = session.cookies.get('access_token')
    if access_token:
        print(f"   Access token: {access_token[:50]}...")
        manual_response = requests.get(f"{api_url}/admin/users", 
                                     cookies={'access_token': access_token})
        print(f"   Status: {manual_response.status_code}")
        print(f"   Response: {manual_response.text[:200]}")
    else:
        print("   No access_token cookie found!")

if __name__ == "__main__":
    debug_admin_auth()