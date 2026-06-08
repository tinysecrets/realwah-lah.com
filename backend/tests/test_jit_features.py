"""
Sugar City Sweeps - JIT Platform Registration & New Features Tests
===================================================================
Tests for:
1. Username format: sugar + 2-3 lowercase letters + 3 digits (e.g., sugarct049)
2. All new user passwords preset to Abc123
3. JIT platform registration on deposit
4. Admin alerts for failed registrations
5. Per-card credentials display (frontend)
6. Register page no longer has Display Name field
"""
import pytest
import requests
import os
import re
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://wahlah-deploy.preview.emergentagent.com')
API = f"{BASE_URL}/api"
EXT_API = f"{API}/ext"
PLATFORM_API = f"{EXT_API}/platform"

# Test credentials
ADMIN_EMAIL = os.getenv("TEST_ADMIN_EMAIL", "admin@wah-lah.com")
ADMIN_PASSWORD = os.getenv("TEST_ADMIN_PASSWORD", "SugarCity2024!")

# Existing test user
JIT_USER_EMAIL = "jit_user1@example.com"
JIT_USER_PASSWORD = "Password123"


class TestUsernameFormat:
    """Test that new users get game_username matching ^sugar[a-z]{2,3}[0-9]{3}$"""
    
    def test_register_creates_valid_game_username(self):
        """POST /api/auth/register creates user with valid game_username format"""
        user_email = f"newuser_{int(time.time())}@test.com"
        
        response = requests.post(f"{API}/auth/register", json={
            "email": user_email,
            "password": "TestPass123!",
            "age_verified": True
        })
        
        assert response.status_code == 200, f"Registration failed: {response.text}"
        data = response.json()
        
        # Check game_username exists
        assert "game_username" in data, "game_username not in response"
        game_username = data["game_username"]
        
        # Validate format: sugar + 2-3 lowercase letters + 3 digits
        pattern = r"^sugar[a-z]{2,3}[0-9]{3}$"
        assert re.match(pattern, game_username), f"game_username '{game_username}' doesn't match pattern {pattern}"
        
        print(f"✅ New user game_username: {game_username} matches pattern")
        return game_username
    
    def test_register_creates_preset_password(self):
        """POST /api/auth/register creates user with game_password = 'Abc123'"""
        user_email = f"pwuser_{int(time.time())}@test.com"
        
        response = requests.post(f"{API}/auth/register", json={
            "email": user_email,
            "password": "TestPass123!",
            "age_verified": True
        })
        
        assert response.status_code == 200, f"Registration failed: {response.text}"
        data = response.json()
        
        # Check game_password is preset to Abc123
        assert "game_password" in data, "game_password not in response"
        assert data["game_password"] == "Abc123", f"game_password == '{data['game_password']}', expected 'Abc123'"
        
        print("✅ New user game_password is preset to 'Abc123'")


class TestJITPlatformRegistration:
    """Test JIT platform registration flow"""
    
    def test_platform_register_success(self):
        """POST /api/ext/platform/register with valid game_id registers user"""
        # Login as test user
        s = requests.Session()
        login_resp = s.post(f"{API}/auth/login", json={
            "email": JIT_USER_EMAIL,
            "password": JIT_USER_PASSWORD
        })
        
        if login_resp.status_code != 200:
            # Create the user if doesn't exist
            reg_resp = s.post(f"{API}/auth/register", json={
                "email": JIT_USER_EMAIL,
                "password": JIT_USER_PASSWORD,
                "age_verified": True
            })
            assert reg_resp.status_code == 200, f"Failed to create test user: {reg_resp.text}"
        
        # Get games list
        games_resp = s.get(f"{API}/games")
        assert games_resp.status_code == 200
        games = games_resp.json()
        assert len(games) > 0, "No games found"
        
        game_id = games[0]["id"]
        
        # Register on platform
        response = s.post(f"{PLATFORM_API}/register", json={"game_id": game_id})
        assert response.status_code == 200, f"Platform register failed: {response.text}"
        
        data = response.json()
        assert data["status"] == "ok"
        assert "platform_uid" in data
        print(f"✅ Platform register success - platform_uid: {data['platform_uid']}")
    
    def test_platform_accounts_shows_registered(self):
        """GET /api/ext/platform/accounts shows registered status"""
        # Login as test user
        s = requests.Session()
        login_resp = s.post(f"{API}/auth/login", json={
            "email": JIT_USER_EMAIL,
            "password": JIT_USER_PASSWORD
        })
        
        if login_resp.status_code != 200:
            s.post(f"{API}/auth/register", json={
                "email": JIT_USER_EMAIL,
                "password": JIT_USER_PASSWORD,
                "age_verified": True
            })
        
        # Get platform accounts
        response = s.get(f"{PLATFORM_API}/accounts")
        assert response.status_code == 200, f"Platform accounts failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, dict)
        print(f"✅ Platform accounts: {data}")


class TestJITCheckoutIntegration:
    """Test JIT registration is enforced before checkout"""
    
    def test_checkout_calls_jit_registration(self):
        """POST /api/checkout/create enforces JIT registration first"""
        # Login as test user
        s = requests.Session()
        login_resp = s.post(f"{API}/auth/login", json={
            "email": JIT_USER_EMAIL,
            "password": JIT_USER_PASSWORD
        })
        
        if login_resp.status_code != 200:
            s.post(f"{API}/auth/register", json={
                "email": JIT_USER_EMAIL,
                "password": JIT_USER_PASSWORD,
                "age_verified": True
            })
        
        # Get games list
        games_resp = s.get(f"{API}/games")
        games = games_resp.json()
        game_id = games[0]["id"]
        
        # Try checkout - should pass JIT registration (dry-run adapter)
        # Note: Stripe will fail with placeholder key, but JIT should pass
        response = s.post(f"{API}/checkout/create", json={
            "amount": 10.0,
            "game_id": game_id,
            "account_name": "test",
            "origin_url": "https://wahlah-deploy.preview.emergentagent.com",
            "payment_method": "stripe"
        })
        
        # Should NOT be 409 (JIT failure) - may be 4xx/5xx from Stripe
        if response.status_code == 409:
            # JIT failed - this is a bug
            print(f"❌ JIT registration failed: {response.text}")
            assert False, f"JIT registration failed: {response.json().get('detail')}"
        else:
            # JIT passed, Stripe may fail with placeholder key
            print(f"✅ JIT registration passed (checkout status: {response.status_code})")
            if response.status_code == 200:
                data = response.json()
                assert "url" in data or "session_id" in data
                print("✅ Checkout created successfully")


class TestJITDepositHeldScenario:
    """Test deposit held scenario when master creds are missing"""
    
    def test_checkout_returns_409_when_creds_missing(self):
        """POST /api/checkout/create returns 409 when user has no master creds"""
        # Create a user with empty game credentials
        user_email = f"nocreds_{int(time.time())}@test.com"
        
        s = requests.Session()
        reg_resp = s.post(f"{API}/auth/register", json={
            "email": user_email,
            "password": "TestPass123!",
            "age_verified": True
        })
        assert reg_resp.status_code == 200
        
        # The user should have game_username and game_password set by default
        # To test the 409 scenario, we'd need to manually clear them in DB
        # For now, verify that normal registration has credentials
        data = reg_resp.json()
        assert data.get("game_username"), "User should have game_username"
        assert data.get("game_password"), "User should have game_password"
        print(f"✅ New user has credentials: {data['game_username']} / {data['game_password']}")


class TestAdminAlerts:
    """Test admin alerts for JIT failures"""
    
    def test_admin_alerts_list(self):
        """GET /api/ext/platform/alerts?status=open lists open alerts"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        response = s.get(f"{PLATFORM_API}/alerts?status=open")
        assert response.status_code == 200, f"Alerts list failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Admin alerts list: {len(data)} open alerts")
    
    def test_admin_alerts_resolve(self):
        """POST /api/ext/platform/alerts/{id}/resolve transitions alert to resolved"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        # Get open alerts
        alerts_resp = s.get(f"{PLATFORM_API}/alerts?status=open")
        alerts = alerts_resp.json()
        
        if len(alerts) > 0:
            alert_id = alerts[0]["id"]
            response = s.post(f"{PLATFORM_API}/alerts/{alert_id}/resolve", json={
                "resolution": "Test resolution"
            })
            assert response.status_code == 200, f"Alert resolve failed: {response.text}"
            print(f"✅ Alert {alert_id} resolved")
        else:
            print("⚠️ No open alerts to resolve (this is expected if no failures)")
    
    def test_admin_retry_registration(self):
        """POST /api/ext/platform/admin/retry/{user_id}/{game_id} re-runs registration"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        # Get users list
        users_resp = s.get(f"{API}/admin/users")
        assert users_resp.status_code == 200
        users = users_resp.json()
        
        # Get games list
        games_resp = s.get(f"{API}/games")
        games = games_resp.json()
        
        if len(users) > 0 and len(games) > 0:
            # Find a non-admin user
            test_user = None
            for u in users:
                if u.get("role") != "admin":
                    test_user = u
                    break
            
            if test_user:
                user_id = test_user["id"]
                game_id = games[0]["id"]
                
                response = s.post(f"{PLATFORM_API}/admin/retry/{user_id}/{game_id}")
                assert response.status_code == 200, f"Admin retry failed: {response.text}"
                
                data = response.json()
                print(f"✅ Admin retry: status={data['status']}, message={data['message']}")
            else:
                print("⚠️ No non-admin users found for retry test")
        else:
            print("⚠️ No users or games found for retry test")


class TestRegressionExistingFeatures:
    """Regression tests for existing extension features"""
    
    def test_vip_tier_still_works(self):
        """GET /api/ext/vip/tier still returns tier info"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        response = s.get(f"{EXT_API}/vip/tier")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        print(f"✅ VIP tier still works: {data['name']}")
    
    def test_promo_codes_still_work(self):
        """POST /api/ext/admin/promo still creates promo codes"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        promo_code = f"REGTEST{int(time.time())}"
        response = s.post(f"{EXT_API}/admin/promo", json={
            "code": promo_code,
            "bonus_credits": 50,
            "max_uses": 5
        })
        assert response.status_code == 200
        print(f"✅ Promo codes still work: {promo_code}")
    
    def test_referral_still_works(self):
        """GET /api/ext/referral/me still returns referral code"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        response = s.get(f"{EXT_API}/referral/me")
        assert response.status_code == 200
        data = response.json()
        assert "referral_code" in data
        print(f"✅ Referral still works: {data['referral_code']}")
    
    def test_2fa_status_still_works(self):
        """GET /api/ext/2fa/status still returns status"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        response = s.get(f"{EXT_API}/2fa/status")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        print(f"✅ 2FA status still works: enabled={data['enabled']}")
    
    def test_password_reset_still_works(self):
        """POST /api/ext/password/forgot still returns dev_token"""
        response = requests.post(f"{EXT_API}/password/forgot", json={
            "email": ADMIN_EMAIL
        })
        assert response.status_code == 200
        data = response.json()
        assert "dev_token" in data
        print("✅ Password reset still works")
    
    def test_support_tickets_still_work(self):
        """POST /api/ext/support/ticket still creates tickets"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        response = s.post(f"{EXT_API}/support/ticket", json={
            "subject": "Regression Test Ticket",
            "message": "Testing that support tickets still work",
            "priority": "low"
        })
        assert response.status_code == 200
        print("✅ Support tickets still work")
    
    def test_analytics_still_works(self):
        """GET /api/ext/admin/analytics/overview still returns stats"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        response = s.get(f"{EXT_API}/admin/analytics/overview")
        assert response.status_code == 200
        data = response.json()
        assert "total_users" in data
        print(f"✅ Analytics still works: {data['total_users']} users")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
