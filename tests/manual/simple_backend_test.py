#!/usr/bin/env python3
"""
Simple backend test that works like the debug script
"""

import requests
import json

def test_backend_simple():
    base_url = "https://wahlah-deploy.preview.emergentagent.com"
    api_url = f"{base_url}/api"
    
    session = requests.Session()
    
    print("🍬 Sugar City Sweeps - Simple Backend Test")
    print("=" * 60)
    
    tests_passed = 0
    tests_total = 0
    
    # Test 1: API Root
    tests_total += 1
    try:
        response = session.get(f"{api_url}/")
        if response.status_code == 200:
            tests_passed += 1
            print("✅ API Root - PASS")
        else:
            print(f"❌ API Root - FAIL ({response.status_code})")
    except Exception as e:
        print(f"❌ API Root - ERROR: {e}")
    
    # Test 2: Admin Login
    tests_total += 1
    try:
        response = session.post(f"{api_url}/auth/login", json={
            "email": "admin@sugarcitysweeps.com",
            "password": "SugarCity2024!"
        })
        if response.status_code == 200 and response.json().get("role") == "admin":
            tests_passed += 1
            print("✅ Admin Login - PASS")
        else:
            print(f"❌ Admin Login - FAIL ({response.status_code})")
    except Exception as e:
        print(f"❌ Admin Login - ERROR: {e}")
    
    # Test 3: Auth Me
    tests_total += 1
    try:
        response = session.get(f"{api_url}/auth/me")
        if response.status_code == 200:
            tests_passed += 1
            print("✅ Auth Me - PASS")
        else:
            print(f"❌ Auth Me - FAIL ({response.status_code})")
    except Exception as e:
        print(f"❌ Auth Me - ERROR: {e}")
    
    # Test 4: Games
    tests_total += 1
    try:
        response = session.get(f"{api_url}/games")
        if response.status_code == 200 and len(response.json()) == 7:
            tests_passed += 1
            print("✅ Games (7 games) - PASS")
        else:
            print(f"❌ Games - FAIL ({response.status_code}, {len(response.json()) if response.status_code == 200 else 'N/A'} games)")
    except Exception as e:
        print(f"❌ Games - ERROR: {e}")
    
    # Test 5: AMOE Status
    tests_total += 1
    try:
        response = session.get(f"{api_url}/amoe/status")
        if response.status_code == 200:
            tests_passed += 1
            print("✅ AMOE Status - PASS")
        else:
            print(f"❌ AMOE Status - FAIL ({response.status_code})")
    except Exception as e:
        print(f"❌ AMOE Status - ERROR: {e}")
    
    # Test 6: AMOE Claim
    tests_total += 1
    try:
        response = session.post(f"{api_url}/amoe/claim-daily")
        if response.status_code in [200, 400]:  # 400 if already claimed
            tests_passed += 1
            print("✅ AMOE Claim - PASS")
        else:
            print(f"❌ AMOE Claim - FAIL ({response.status_code})")
    except Exception as e:
        print(f"❌ AMOE Claim - ERROR: {e}")
    
    # Test 7: Crypto Info
    tests_total += 1
    try:
        response = session.get(f"{api_url}/payment/crypto-info")
        if response.status_code == 200:
            tests_passed += 1
            print("✅ Crypto Info - PASS")
        else:
            print(f"❌ Crypto Info - FAIL ({response.status_code})")
    except Exception as e:
        print(f"❌ Crypto Info - ERROR: {e}")
    
    # Test 8: Card Info
    tests_total += 1
    try:
        response = session.get(f"{api_url}/payment/card-info")
        if response.status_code == 200:
            tests_passed += 1
            print("✅ Card Info - PASS")
        else:
            print(f"❌ Card Info - FAIL ({response.status_code})")
    except Exception as e:
        print(f"❌ Card Info - ERROR: {e}")
    
    # Test 9: Admin Users
    tests_total += 1
    try:
        response = session.get(f"{api_url}/admin/users")
        if response.status_code == 200:
            tests_passed += 1
            print("✅ Admin Users - PASS")
        else:
            print(f"❌ Admin Users - FAIL ({response.status_code}): {response.text[:100]}")
    except Exception as e:
        print(f"❌ Admin Users - ERROR: {e}")
    
    # Test 10: Admin Stats
    tests_total += 1
    try:
        response = session.get(f"{api_url}/admin/stats")
        if response.status_code == 200:
            tests_passed += 1
            print("✅ Admin Stats - PASS")
        else:
            print(f"❌ Admin Stats - FAIL ({response.status_code}): {response.text[:100]}")
    except Exception as e:
        print(f"❌ Admin Stats - ERROR: {e}")
    
    # Test 11: Admin Transactions
    tests_total += 1
    try:
        response = session.get(f"{api_url}/admin/transactions")
        if response.status_code == 200:
            tests_passed += 1
            print("✅ Admin Transactions - PASS")
        else:
            print(f"❌ Admin Transactions - FAIL ({response.status_code}): {response.text[:100]}")
    except Exception as e:
        print(f"❌ Admin Transactions - ERROR: {e}")
    
    print("\n" + "=" * 60)
    print(f"🏁 SUMMARY: {tests_passed}/{tests_total} tests passed ({tests_passed/tests_total*100:.1f}%)")
    
    return tests_passed == tests_total

if __name__ == "__main__":
    success = test_backend_simple()
    exit(0 if success else 1)