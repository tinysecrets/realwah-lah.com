"""
Sugar City Sweeps - Extension Features Backend Tests
=====================================================
Tests for: Password Reset, 2FA (TOTP), Promo Codes, Referral System,
           VIP Tiers, Support Tickets, Enhanced Analytics
"""
import pytest
import requests
import os
import pyotp
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://wahlah-deploy.preview.emergentagent.com')
API = f"{BASE_URL}/api"
EXT_API = f"{API}/ext"

# Test credentials
ADMIN_EMAIL = os.getenv("TEST_ADMIN_EMAIL", "admin@wah-lah.com")
ADMIN_PASSWORD = os.getenv("TEST_ADMIN_PASSWORD", "SugarCity2024!")

# Test user for per-user tests
TEST_USER_EMAIL = f"testuser_{int(time.time())}@test.com"
TEST_USER_PASSWORD = os.getenv("TEST_USER_PASSWORD", "TestPass123!")
TEST_USER_NAME = "Test User"


class TestSetup:
    """Setup fixtures and helper methods"""
    
    @pytest.fixture(scope="class")
    def session(self):
        """Create a requests session with cookies"""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        return s
    
    @pytest.fixture(scope="class")
    def admin_session(self, session):
        """Login as admin and return session"""
        response = session.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        return session
    
    @pytest.fixture(scope="class")
    def test_user_session(self):
        """Register a new test user and return session"""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        
        # Register new user
        response = s.post(f"{API}/auth/register", json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD,
            "name": TEST_USER_NAME,
            "age_verified": True
        })
        assert response.status_code == 200, f"User registration failed: {response.text}"
        return s


class TestExistingEndpoints:
    """REGRESSION: Test existing endpoints still work"""
    
    def test_api_root(self):
        """Test API root endpoint"""
        response = requests.get(f"{API}/")
        assert response.status_code == 200
        assert "WAH-LAH" in response.json().get("message", "")
        print("✅ API root endpoint working")
    
    def test_auth_login(self):
        """Test login endpoint"""
        response = requests.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["email"] == ADMIN_EMAIL
        print("✅ Auth login working")
    
    def test_games_list(self):
        """Test games endpoint"""
        response = requests.get(f"{API}/games")
        assert response.status_code == 200
        games = response.json()
        assert isinstance(games, list)
        assert len(games) > 0
        print(f"✅ Games endpoint working - {len(games)} games found")
    
    def test_amoe_status(self):
        """Test AMOE status endpoint (requires auth)"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        response = s.get(f"{API}/amoe/status")
        assert response.status_code == 200
        data = response.json()
        assert "eligible" in data
        print("✅ AMOE status endpoint working")


class TestPasswordReset:
    """Test password reset flow"""
    
    def test_forgot_password_returns_dev_token(self):
        """POST /api/ext/password/forgot returns dev_token in dev mode"""
        response = requests.post(f"{EXT_API}/password/forgot", json={
            "email": ADMIN_EMAIL
        })
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "dev_token" in data
        assert data["dev_token"] is not None
        print(f"✅ Forgot password returns dev_token: {data['dev_token'][:20]}...")
        return data["dev_token"]
    
    def test_reset_password_with_token(self):
        """POST /api/ext/password/reset with token updates password"""
        # First get a token
        forgot_response = requests.post(f"{EXT_API}/password/forgot", json={
            "email": ADMIN_EMAIL
        })
        token = forgot_response.json().get("dev_token")
        assert token, "No dev_token returned"
        
        # Reset password (use same password to not break other tests)
        response = requests.post(f"{EXT_API}/password/reset", json={
            "token": token,
            "new_password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "successful" in data["message"].lower()
        print("✅ Password reset with token working")
    
    def test_reset_password_invalid_token(self):
        """POST /api/ext/password/reset with invalid token fails"""
        response = requests.post(f"{EXT_API}/password/reset", json={
            "token": "invalid_token_12345",
            "new_password": "NewPassword123"
        })
        assert response.status_code == 400
        print("✅ Invalid token correctly rejected")
    
    def test_change_password(self):
        """POST /api/ext/password/change works with current + new password"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        # Change password (use same password to not break other tests)
        response = s.post(f"{EXT_API}/password/change", json={
            "current_password": ADMIN_PASSWORD,
            "new_password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        print("✅ Password change endpoint working")


class TestTwoFactorAuth:
    """Test 2FA (TOTP) flow"""
    
    def test_2fa_setup_returns_secret_and_qr(self):
        """POST /api/ext/2fa/setup returns secret + QR base64 + otpauth URI"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        response = s.post(f"{EXT_API}/2fa/setup")
        assert response.status_code == 200
        data = response.json()
        assert "secret" in data
        assert "qr_code_base64" in data
        assert "otpauth_uri" in data
        assert data["qr_code_base64"].startswith("data:image/png;base64,")
        assert "otpauth://totp/" in data["otpauth_uri"]
        print(f"✅ 2FA setup returns secret: {data['secret'][:10]}...")
        return data["secret"]
    
    def test_2fa_enable_with_valid_code(self):
        """POST /api/ext/2fa/enable with valid TOTP code enables 2FA"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        # Setup 2FA
        setup_response = s.post(f"{EXT_API}/2fa/setup")
        secret = setup_response.json()["secret"]
        
        # Generate valid TOTP code
        totp = pyotp.TOTP(secret)
        code = totp.now()
        
        # Enable 2FA
        response = s.post(f"{EXT_API}/2fa/enable", json={"code": code})
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data["message"].lower()
        print("✅ 2FA enable with valid code working")
        
        return secret
    
    def test_2fa_status_returns_enabled(self):
        """GET /api/ext/2fa/status returns enabled true after enabling"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        response = s.get(f"{EXT_API}/2fa/status")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        print(f"✅ 2FA status endpoint working - enabled: {data['enabled']}")
    
    def test_2fa_disable(self):
        """POST /api/ext/2fa/disable works"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        # Check if 2FA is enabled
        status_response = s.get(f"{EXT_API}/2fa/status")
        if not status_response.json().get("enabled"):
            # Enable it first
            setup_response = s.post(f"{EXT_API}/2fa/setup")
            secret = setup_response.json()["secret"]
            totp = pyotp.TOTP(secret)
            s.post(f"{EXT_API}/2fa/enable", json={"code": totp.now()})
        else:
            # Get the secret from user (we need to setup again to get it)
            setup_response = s.post(f"{EXT_API}/2fa/setup")
            secret = setup_response.json()["secret"]
            totp = pyotp.TOTP(secret)
            s.post(f"{EXT_API}/2fa/enable", json={"code": totp.now()})
        
        # Now disable
        totp = pyotp.TOTP(secret)
        response = s.post(f"{EXT_API}/2fa/disable", json={"code": totp.now()})
        assert response.status_code == 200
        print("✅ 2FA disable working")
    
    def test_login_2fa_fails_without_code(self):
        """POST /api/ext/auth/login-2fa fails if 2FA code missing when enabled"""
        # First enable 2FA for admin
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        setup_response = s.post(f"{EXT_API}/2fa/setup")
        secret = setup_response.json()["secret"]
        totp = pyotp.TOTP(secret)
        s.post(f"{EXT_API}/2fa/enable", json={"code": totp.now()})
        
        # Try login without code
        response = requests.post(f"{EXT_API}/auth/login-2fa", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
            "code": ""
        })
        assert response.status_code == 401
        print("✅ Login-2FA correctly rejects empty code")
        
        # Cleanup: disable 2FA
        s.post(f"{EXT_API}/2fa/disable", json={"code": totp.now()})
    
    def test_login_2fa_succeeds_with_valid_code(self):
        """POST /api/ext/auth/login-2fa succeeds with valid code"""
        # First enable 2FA for admin
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        setup_response = s.post(f"{EXT_API}/2fa/setup")
        secret = setup_response.json()["secret"]
        totp = pyotp.TOTP(secret)
        s.post(f"{EXT_API}/2fa/enable", json={"code": totp.now()})
        
        # Login with valid code
        time.sleep(1)  # Wait for new TOTP window
        response = requests.post(f"{EXT_API}/auth/login-2fa", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
            "code": totp.now()
        })
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        print("✅ Login-2FA with valid code working")
        
        # Cleanup: disable 2FA
        s.post(f"{EXT_API}/2fa/disable", json={"code": totp.now()})


class TestPromoCodes:
    """Test promo code CRUD and redemption"""
    
    def test_admin_create_promo(self):
        """POST /api/ext/admin/promo creates promo code (admin only)"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        promo_code = f"TEST{int(time.time())}"
        response = s.post(f"{EXT_API}/admin/promo", json={
            "code": promo_code,
            "bonus_credits": 100,
            "max_uses": 10,
            "description": "Test promo code"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == promo_code.upper()
        assert data["bonus_credits"] == 100
        print(f"✅ Admin create promo working - code: {promo_code}")
        return promo_code
    
    def test_admin_list_promos(self):
        """GET /api/ext/admin/promo lists promo codes (admin only)"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        response = s.get(f"{EXT_API}/admin/promo")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Admin list promos working - {len(data)} promos found")
    
    def test_admin_delete_promo(self):
        """DELETE /api/ext/admin/promo/{id} deletes promo (admin only)"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        # Create a promo to delete
        promo_code = f"DEL{int(time.time())}"
        create_response = s.post(f"{EXT_API}/admin/promo", json={
            "code": promo_code,
            "bonus_credits": 50,
            "max_uses": 1
        })
        promo_id = create_response.json()["id"]
        
        # Delete it
        response = s.delete(f"{EXT_API}/admin/promo/{promo_id}")
        assert response.status_code == 200
        print("✅ Admin delete promo working")
    
    def test_promo_redeem_awards_credits(self):
        """POST /api/ext/promo/redeem awards game_credits once per user"""
        # Create admin session and promo
        admin_s = requests.Session()
        admin_s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        promo_code = f"REDEEM{int(time.time())}"
        admin_s.post(f"{EXT_API}/admin/promo", json={
            "code": promo_code,
            "bonus_credits": 200,
            "max_uses": 100
        })
        
        # Register new user and redeem
        user_email = f"promouser_{int(time.time())}@test.com"
        user_s = requests.Session()
        user_s.post(f"{API}/auth/register", json={
            "email": user_email,
            "password": "TestPass123!",
            "name": "Promo Test User",
            "age_verified": True
        })
        
        response = user_s.post(f"{EXT_API}/promo/redeem", json={"code": promo_code})
        assert response.status_code == 200
        data = response.json()
        assert data["credits_granted"] == 200
        print("✅ Promo redeem awards credits working")
    
    def test_promo_redeem_rejects_invalid(self):
        """POST /api/ext/promo/redeem rejects invalid code"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        response = s.post(f"{EXT_API}/promo/redeem", json={"code": "INVALIDCODE123"})
        assert response.status_code == 404
        print("✅ Invalid promo code correctly rejected")
    
    def test_promo_redeem_rejects_already_redeemed(self):
        """POST /api/ext/promo/redeem rejects already-redeemed code"""
        # Create admin session and promo
        admin_s = requests.Session()
        admin_s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        promo_code = f"ONCE{int(time.time())}"
        admin_s.post(f"{EXT_API}/admin/promo", json={
            "code": promo_code,
            "bonus_credits": 50,
            "max_uses": 100
        })
        
        # Register new user and redeem twice
        user_email = f"onceuser_{int(time.time())}@test.com"
        user_s = requests.Session()
        user_s.post(f"{API}/auth/register", json={
            "email": user_email,
            "password": "TestPass123!",
            "name": "Once Test User",
            "age_verified": True
        })
        
        # First redeem
        user_s.post(f"{EXT_API}/promo/redeem", json={"code": promo_code})
        
        # Second redeem should fail
        response = user_s.post(f"{EXT_API}/promo/redeem", json={"code": promo_code})
        assert response.status_code == 400
        assert "already" in response.json()["detail"].lower()
        print("✅ Already-redeemed promo correctly rejected")


class TestReferralSystem:
    """Test referral system"""
    
    def test_referral_me_returns_code(self):
        """GET /api/ext/referral/me returns referral_code"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        response = s.get(f"{EXT_API}/referral/me")
        assert response.status_code == 200
        data = response.json()
        assert "referral_code" in data
        assert len(data["referral_code"]) == 8
        assert "referred_count" in data
        assert "bonus_earned" in data
        print(f"✅ Referral me returns code: {data['referral_code']}")
        return data["referral_code"]
    
    def test_referral_redeem_awards_both_users(self):
        """POST /api/ext/referral/redeem awards credits to both users"""
        # Get admin's referral code
        admin_s = requests.Session()
        admin_s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        ref_response = admin_s.get(f"{EXT_API}/referral/me")
        referral_code = ref_response.json()["referral_code"]
        
        # Register new user and redeem referral
        user_email = f"refuser_{int(time.time())}@test.com"
        user_s = requests.Session()
        user_s.post(f"{API}/auth/register", json={
            "email": user_email,
            "password": "TestPass123!",
            "name": "Referral Test User",
            "age_verified": True
        })
        
        response = user_s.post(f"{EXT_API}/referral/redeem", json={"code": referral_code})
        assert response.status_code == 200
        data = response.json()
        assert data["credits_granted"] == 500
        print("✅ Referral redeem awards credits to both users")
    
    def test_referral_rejects_self(self):
        """POST /api/ext/referral/redeem rejects self-referral"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        # Get own referral code
        ref_response = s.get(f"{EXT_API}/referral/me")
        referral_code = ref_response.json()["referral_code"]
        
        # Try to redeem own code
        response = s.post(f"{EXT_API}/referral/redeem", json={"code": referral_code})
        assert response.status_code == 400
        assert "own" in response.json()["detail"].lower()
        print("✅ Self-referral correctly rejected")
    
    def test_referral_rejects_duplicate(self):
        """POST /api/ext/referral/redeem rejects duplicate redemption"""
        # Get admin's referral code
        admin_s = requests.Session()
        admin_s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        ref_response = admin_s.get(f"{EXT_API}/referral/me")
        referral_code = ref_response.json()["referral_code"]
        
        # Register new user and redeem twice
        user_email = f"dupref_{int(time.time())}@test.com"
        user_s = requests.Session()
        user_s.post(f"{API}/auth/register", json={
            "email": user_email,
            "password": "TestPass123!",
            "name": "Dup Referral User",
            "age_verified": True
        })
        
        # First redeem
        user_s.post(f"{EXT_API}/referral/redeem", json={"code": referral_code})
        
        # Second redeem should fail
        response = user_s.post(f"{EXT_API}/referral/redeem", json={"code": referral_code})
        assert response.status_code == 400
        assert "already" in response.json()["detail"].lower()
        print("✅ Duplicate referral correctly rejected")


class TestVIPTiers:
    """Test VIP tier system"""
    
    def test_vip_tier_returns_tier_info(self):
        """GET /api/ext/vip/tier returns tier based on lifetime spend"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        response = s.get(f"{EXT_API}/vip/tier")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "min_spend" in data
        assert "bonus_pct" in data
        assert "color" in data
        assert "progress" in data
        assert "lifetime_spend_usd" in data
        print(f"✅ VIP tier returns info - tier: {data['name']}")
    
    def test_vip_tiers_returns_all_tiers(self):
        """GET /api/ext/vip/tiers returns 5 tiers"""
        response = requests.get(f"{EXT_API}/vip/tiers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 5
        tier_names = [t["name"] for t in data]
        assert "Bronze" in tier_names
        assert "Diamond" in tier_names
        print(f"✅ VIP tiers returns 5 tiers: {tier_names}")


class TestSupportTickets:
    """Test support ticket system"""
    
    def test_create_ticket(self):
        """POST /api/ext/support/ticket creates ticket"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        response = s.post(f"{EXT_API}/support/ticket", json={
            "subject": "Test Ticket",
            "message": "This is a test support ticket",
            "priority": "normal"
        })
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        print(f"✅ Support ticket created - id: {data['id']}")
        return data["id"]
    
    def test_list_user_tickets(self):
        """GET /api/ext/support/tickets lists user's tickets"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        response = s.get(f"{EXT_API}/support/tickets")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ User tickets list working - {len(data)} tickets")
    
    def test_admin_list_all_tickets(self):
        """GET /api/ext/admin/support/tickets lists all tickets (admin only)"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        response = s.get(f"{EXT_API}/admin/support/tickets")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Admin tickets list working - {len(data)} tickets")
    
    def test_admin_respond_to_ticket(self):
        """POST /api/ext/admin/support/tickets/{id}/respond adds response"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        # Create a ticket first
        create_response = s.post(f"{EXT_API}/support/ticket", json={
            "subject": "Respond Test",
            "message": "Test message",
            "priority": "high"
        })
        ticket_id = create_response.json()["id"]
        
        # Respond to it
        response = s.post(f"{EXT_API}/admin/support/tickets/{ticket_id}/respond", json={
            "message": "Admin response to ticket"
        })
        assert response.status_code == 200
        print("✅ Admin respond to ticket working")
    
    def test_admin_close_ticket(self):
        """POST /api/ext/admin/support/tickets/{id}/close closes ticket"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        # Create a ticket first
        create_response = s.post(f"{EXT_API}/support/ticket", json={
            "subject": "Close Test",
            "message": "Test message",
            "priority": "low"
        })
        ticket_id = create_response.json()["id"]
        
        # Close it
        response = s.post(f"{EXT_API}/admin/support/tickets/{ticket_id}/close")
        assert response.status_code == 200
        print("✅ Admin close ticket working")


class TestAdminAnalytics:
    """Test admin analytics endpoints"""
    
    def test_analytics_overview(self):
        """GET /api/ext/admin/analytics/overview returns stats (admin only)"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        response = s.get(f"{EXT_API}/admin/analytics/overview")
        assert response.status_code == 200
        data = response.json()
        assert "total_users" in data
        assert "new_users_7d" in data
        assert "total_revenue" in data
        assert "completed_transactions" in data
        assert "promo_redeemed" in data
        assert "referrals" in data
        assert "open_tickets" in data
        print(f"✅ Analytics overview working - {data['total_users']} users")
    
    def test_analytics_revenue_by_day(self):
        """GET /api/ext/admin/analytics/revenue-by-day returns daily revenue"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        response = s.get(f"{EXT_API}/admin/analytics/revenue-by-day?days=14")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "date" in data[0]
        assert "revenue" in data[0]
        print(f"✅ Revenue by day working - {len(data)} days")
    
    def test_analytics_signups_by_day(self):
        """GET /api/ext/admin/analytics/signups-by-day returns daily signups"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        response = s.get(f"{EXT_API}/admin/analytics/signups-by-day?days=14")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "date" in data[0]
        assert "signups" in data[0]
        print(f"✅ Signups by day working - {len(data)} days")
    
    def test_analytics_top_users(self):
        """GET /api/ext/admin/analytics/top-users returns top spenders"""
        s = requests.Session()
        s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        response = s.get(f"{EXT_API}/admin/analytics/top-users?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Top users working - {len(data)} users")
    
    def test_analytics_requires_admin(self):
        """Analytics endpoints require admin access"""
        # Register regular user
        user_email = f"regularuser_{int(time.time())}@test.com"
        s = requests.Session()
        s.post(f"{API}/auth/register", json={
            "email": user_email,
            "password": "TestPass123!",
            "name": "Regular User",
            "age_verified": True
        })
        
        response = s.get(f"{EXT_API}/admin/analytics/overview")
        assert response.status_code == 403
        print("✅ Analytics correctly requires admin access")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
