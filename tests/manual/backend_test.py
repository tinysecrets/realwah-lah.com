#!/usr/bin/env python3

import requests
import sys
import json
from datetime import datetime

class SugarCitySweepsAPITester:
    def __init__(self, base_url="https://wahlah-deploy.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.session = requests.Session()
        self.admin_token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_test(self, name, success, details="", expected_status=200, actual_status=None):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name}")
        else:
            print(f"❌ {name} - {details}")
        
        self.test_results.append({
            "test": name,
            "success": success,
            "details": details,
            "expected_status": expected_status,
            "actual_status": actual_status
        })

    def test_api_root(self):
        """Test API root endpoint"""
        try:
            response = self.session.get(f"{self.api_url}/")
            success = response.status_code == 200
            self.log_test("API Root Endpoint", success, 
                         f"Status: {response.status_code}", 200, response.status_code)
            return success
        except Exception as e:
            self.log_test("API Root Endpoint", False, f"Exception: {str(e)}")
            return False

    def test_admin_login(self):
        """Test admin login with credentials from test_credentials.md"""
        try:
            login_data = {
                "email": "admin@sugarcitysweeps.com",
                "password": "SugarCity2024!"
            }
            response = self.session.post(f"{self.api_url}/auth/login", json=login_data)
            success = response.status_code == 200
            
            if success:
                # Store cookies for subsequent requests
                self.session.cookies.update(response.cookies)
                data = response.json()
                self.log_test("Admin Login", True, f"Logged in as: {data.get('name', 'Unknown')}")
            else:
                self.log_test("Admin Login", False, 
                             f"Status: {response.status_code}, Response: {response.text[:200]}")
            
            return success
        except Exception as e:
            self.log_test("Admin Login", False, f"Exception: {str(e)}")
            return False

    def test_games_endpoint(self):
        """Test GET /api/games - should return 7 games"""
        try:
            response = self.session.get(f"{self.api_url}/games")
            success = response.status_code == 200
            
            if success:
                games = response.json()
                game_count = len(games)
                expected_count = 7
                success = game_count == expected_count
                
                if success:
                    game_names = [game['name'] for game in games]
                    self.log_test("Games Endpoint", True, 
                                 f"Found {game_count} games: {', '.join(game_names)}")
                else:
                    self.log_test("Games Endpoint", False, 
                                 f"Expected {expected_count} games, got {game_count}")
            else:
                self.log_test("Games Endpoint", False, 
                             f"Status: {response.status_code}")
            
            return success
        except Exception as e:
            self.log_test("Games Endpoint", False, f"Exception: {str(e)}")
            return False

    def test_amoe_status(self):
        """Test GET /api/amoe/status - AMOE eligibility check"""
        try:
            response = self.session.get(f"{self.api_url}/amoe/status")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                eligible = data.get('eligible', False)
                self.log_test("AMOE Status", True, 
                             f"Eligible: {eligible}, Hours remaining: {data.get('hours_remaining', 'N/A')}")
            else:
                self.log_test("AMOE Status", False, 
                             f"Status: {response.status_code}")
            
            return success
        except Exception as e:
            self.log_test("AMOE Status", False, f"Exception: {str(e)}")
            return False

    def test_stripe_checkout_creation(self):
        """Test POST /api/checkout/create - Stripe checkout session creation"""
        try:
            # First get a game ID
            games_response = self.session.get(f"{self.api_url}/games")
            if games_response.status_code != 200:
                self.log_test("Stripe Checkout Creation", False, "Could not fetch games for test")
                return False
            
            games = games_response.json()
            if not games:
                self.log_test("Stripe Checkout Creation", False, "No games available for test")
                return False
            
            game_id = games[0]['id']  # Use first game
            
            checkout_data = {
                "amount": 10.0,
                "game_id": game_id,
                "account_name": "test_account",
                "origin_url": self.base_url,
                "payment_method": "stripe"
            }
            
            response = self.session.post(f"{self.api_url}/checkout/create", json=checkout_data)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                has_url = 'url' in data and data['url'].startswith('https://checkout.stripe.com')
                has_session_id = 'session_id' in data and data['session_id'].startswith('cs_live_')
                
                if has_url and has_session_id:
                    self.log_test("Stripe Checkout Creation", True, 
                                 f"Live session created: {data['session_id'][:20]}...")
                else:
                    self.log_test("Stripe Checkout Creation", False, 
                                 f"Missing URL or session_id in response: {data}")
                    success = False
            else:
                self.log_test("Stripe Checkout Creation", False, 
                             f"Status: {response.status_code}, Response: {response.text[:200]}")
            
            return success
        except Exception as e:
            self.log_test("Stripe Checkout Creation", False, f"Exception: {str(e)}")
            return False

    def test_crypto_payment_info(self):
        """Test GET /api/payment/crypto-info - Bitcoin and Lightning addresses"""
        try:
            response = self.session.get(f"{self.api_url}/payment/crypto-info")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                btc_address = data.get('btc_address', '')
                lightning_address = data.get('lightning_address', '')
                
                has_btc = btc_address.startswith('bc1')
                has_lightning = lightning_address.startswith('lnbc')
                
                if has_btc and has_lightning:
                    self.log_test("Crypto Payment Info", True, 
                                 f"BTC: {btc_address[:20]}..., Lightning: {lightning_address[:20]}...")
                else:
                    self.log_test("Crypto Payment Info", False, 
                                 f"Invalid addresses - BTC: {btc_address[:20]}, Lightning: {lightning_address[:20]}")
                    success = False
            else:
                self.log_test("Crypto Payment Info", False, 
                             f"Status: {response.status_code}")
            
            return success
        except Exception as e:
            self.log_test("Crypto Payment Info", False, f"Exception: {str(e)}")
            return False

    def test_card_payment_info(self):
        """Test GET /api/payment/card-info - Cash App tag"""
        try:
            response = self.session.get(f"{self.api_url}/payment/card-info")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                tag = data.get('tag', '')
                
                if tag.startswith('$'):
                    self.log_test("Card Payment Info", True, f"Cash App tag: {tag}")
                else:
                    self.log_test("Card Payment Info", False, f"Invalid tag format: {tag}")
                    success = False
            else:
                self.log_test("Card Payment Info", False, 
                             f"Status: {response.status_code}")
            
            return success
        except Exception as e:
            self.log_test("Card Payment Info", False, f"Exception: {str(e)}")
            return False

    def test_admin_users(self):
        """Test GET /api/admin/users - Admin endpoint for user list"""
        try:
            response = self.session.get(f"{self.api_url}/admin/users")
            success = response.status_code == 200
            
            if success:
                users = response.json()
                user_count = len(users)
                self.log_test("Admin Users Endpoint", True, f"Found {user_count} users")
            else:
                self.log_test("Admin Users Endpoint", False, 
                             f"Status: {response.status_code}, Response: {response.text[:200]}")
            
            return success
        except Exception as e:
            self.log_test("Admin Users Endpoint", False, f"Exception: {str(e)}")
            return False

    def test_admin_stats(self):
        """Test GET /api/admin/stats - Admin dashboard stats"""
        try:
            response = self.session.get(f"{self.api_url}/admin/stats")
            success = response.status_code == 200
            
            if success:
                stats = response.json()
                required_fields = ['total_users', 'total_transactions', 'completed_transactions', 'total_revenue']
                has_all_fields = all(field in stats for field in required_fields)
                
                if has_all_fields:
                    self.log_test("Admin Stats Endpoint", True, 
                                 f"Users: {stats['total_users']}, Revenue: ${stats['total_revenue']:.2f}")
                else:
                    missing = [f for f in required_fields if f not in stats]
                    self.log_test("Admin Stats Endpoint", False, f"Missing fields: {missing}")
                    success = False
            else:
                self.log_test("Admin Stats Endpoint", False, 
                             f"Status: {response.status_code}")
            
            return success
        except Exception as e:
            self.log_test("Admin Stats Endpoint", False, f"Exception: {str(e)}")
            return False

    def test_user_registration(self):
        """Test user registration flow"""
        try:
            # Create a test user
            timestamp = datetime.now().strftime("%H%M%S")
            test_email = f"test_user_{timestamp}@example.com"
            
            registration_data = {
                "email": test_email,
                "password": "TestPass123!",
                "name": f"TestUser{timestamp}",
                "age_verified": True
            }
            
            response = self.session.post(f"{self.api_url}/auth/register", json=registration_data)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                has_required_fields = all(field in data for field in ['id', 'email', 'name', 'role'])
                
                if has_required_fields:
                    self.log_test("User Registration", True, 
                                 f"Created user: {data['name']} ({data['email']})")
                else:
                    self.log_test("User Registration", False, "Missing required fields in response")
                    success = False
            else:
                self.log_test("User Registration", False, 
                             f"Status: {response.status_code}, Response: {response.text[:200]}")
            
            return success
        except Exception as e:
            self.log_test("User Registration", False, f"Exception: {str(e)}")
            return False

    def run_all_tests(self):
        """Run all backend API tests"""
        print("🧪 Starting Sugar City Sweeps Backend API Tests")
        print("=" * 60)
        
        # Test basic connectivity
        if not self.test_api_root():
            print("❌ API not accessible, stopping tests")
            return False
        
        # Test admin authentication
        if not self.test_admin_login():
            print("❌ Admin login failed, some tests will be skipped")
        
        # Test public endpoints
        self.test_games_endpoint()
        self.test_amoe_status()
        self.test_crypto_payment_info()
        self.test_card_payment_info()
        
        # Test Stripe integration (requires authentication)
        self.test_stripe_checkout_creation()
        
        # Test admin endpoints (requires admin auth)
        self.test_admin_users()
        self.test_admin_stats()
        
        # Test user registration
        self.test_user_registration()
        
        # Print summary
        print("\n" + "=" * 60)
        print(f"📊 Test Summary: {self.tests_passed}/{self.tests_run} tests passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests passed! Backend is fully functional.")
            return True
        else:
            failed_tests = [r for r in self.test_results if not r['success']]
            print(f"❌ {len(failed_tests)} tests failed:")
            for test in failed_tests:
                print(f"   - {test['test']}: {test['details']}")
            return False

def main():
    tester = SugarCitySweepsAPITester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())