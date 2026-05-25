import requests
import os
import time
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
from threading import Thread, Lock

# Try to import Firebase secrets manager
try:
    from services.firebase_secrets import firebase_secrets
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False

logger = logging.getLogger(__name__)

class SessionManager:
    """
    Manages persistent authenticated sessions with game platform agent backends.
    Handles CSRF tokens, session cookies, and automatic heartbeat to maintain 24/7 login.
    """
    
    def __init__(self, platform_config: Dict[str, Any]):
        self.platform_id = platform_config["id"]
        self.platform_name = platform_config["name"]
        self.agent_url = platform_config["agent_url"]
        self.login_endpoint = platform_config["login_endpoint"]
        self.config = platform_config
        
        # Credentials from environment
        self.username = os.environ.get(platform_config["credentials"]["username_env"], "")
        self.password = os.environ.get(platform_config["credentials"]["password_env"], "")
        
        # Session management
        self.session = requests.Session()
        self.session_lock = Lock()
        self.session_cookie = None
        self.csrf_token = None
        self.last_heartbeat = None
        self.is_authenticated = False
        
        # Heartbeat thread
        self.heartbeat_thread = None
        self.heartbeat_running = False
        
        logger.info(f"SessionManager initialized for {self.platform_name}")
    
    def login(self) -> Tuple[bool, str]:
        """
        Authenticates with the game platform agent backend.
        Returns: (success: bool, message: str)
        """
        if not self.username or not self.password:
            return False, f"Missing credentials for {self.platform_name}. Set environment variables."
        
        with self.session_lock:
            try:
                csrf_token = self._fetch_csrf_token()
                login_data, headers = self._prepare_login_payload(csrf_token)
                
                login_url = f"{self.agent_url}{self.login_endpoint}"
                response = self.session.post(login_url, json=login_data, headers=headers, timeout=15)
                
                return self._handle_login_response(response)
            
            except requests.exceptions.Timeout:
                return False, f"Login timeout for {self.platform_name}"
            except requests.exceptions.ConnectionError:
                return False, f"Connection error to {self.platform_name}"
            except Exception as e:
                logger.error(f"Login error for {self.platform_name}: {str(e)}")
                return False, f"Login error: {str(e)}"
    
    def _fetch_csrf_token(self) -> Optional[str]:
        """Fetch CSRF token from the platform's root page."""
        response = self.session.get(f"{self.agent_url}/", timeout=10)
        csrf_token = self._extract_csrf_token(response)
        if csrf_token:
            self.csrf_token = csrf_token
        return csrf_token
    
    def _prepare_login_payload(self, csrf_token: Optional[str]) -> Tuple[dict, dict]:
        """Build the login request data and headers."""
        login_data = {"username": self.username, "password": self.password}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json"
        }
        if csrf_token:
            login_data["_csrf"] = csrf_token
            headers["X-CSRF-Token"] = csrf_token
        return login_data, headers
    
    def _handle_login_response(self, response) -> Tuple[bool, str]:
        """Process the login response - extract session or report failure."""
        if response.status_code != 200:
            return self._handle_login_failure(response)
        
        # Try cookie-based session first
        session_cookie = (
            self.session.cookies.get("JSESSIONID") or
            self.session.cookies.get("session") or
            self.session.cookies.get("connect.sid")
        )
        
        if session_cookie:
            return self._authenticate_with_cookie(session_cookie)
        
        # Fallback to token-based auth
        return self._try_token_auth(response)
    
    def _authenticate_with_cookie(self, session_cookie: str) -> Tuple[bool, str]:
        """Complete authentication using a session cookie."""
        self.session_cookie = session_cookie
        self.is_authenticated = True
        self.last_heartbeat = datetime.now(timezone.utc)
        logger.info(f"✅ Successfully logged in to {self.platform_name}")
        self._start_heartbeat()
        return True, "Login successful"
    
    def _try_token_auth(self, response) -> Tuple[bool, str]:
        """Attempt token-based authentication from the response body."""
        try:
            data = response.json()
            token = data.get("token") or data.get("access_token")
            if token:
                self.session.headers.update({"Authorization": f"Bearer {token}"})
                self.is_authenticated = True
                self.last_heartbeat = datetime.now(timezone.utc)
                logger.info(f"✅ Successfully logged in to {self.platform_name} (token-based)")
                self._start_heartbeat()
                return True, "Login successful (token-based)"
        except Exception:
            pass
        return False, "Login response missing session cookie/token"
    
    def _handle_login_failure(self, response) -> Tuple[bool, str]:
        """Extract and log error details from a failed login response."""
        error_msg = f"Login failed with status {response.status_code}"
        try:
            error_data = response.json()
            error_msg = error_data.get("error", error_data.get("message", error_msg))
        except Exception:
            error_msg = response.text[:200]
        logger.error(f"❌ Login failed for {self.platform_name}: {error_msg}")
        return False, error_msg
    
    def _extract_csrf_token(self, response: requests.Response) -> Optional[str]:
        """Extract CSRF token from response headers or cookies"""
        # Check headers
        csrf_token = response.headers.get("X-CSRF-Token") or \
                    response.headers.get("CSRF-Token")
        
        if csrf_token:
            return csrf_token
        
        # Check cookies
        csrf_token = response.cookies.get("csrf_token") or \
                    response.cookies.get("XSRF-TOKEN") or \
                    response.cookies.get("_csrf")
        
        if csrf_token:
            return csrf_token
        
        # Parse from HTML meta tag (common in web panels)
        try:
            if 'csrf' in response.text.lower():
                import re
                patterns = [
                    r'<meta name="csrf-token" content="([^"]+)"',
                    r'"csrf":"([^"]+)"',
                    r'csrf_token":\s*"([^"]+)"'
                ]
                for pattern in patterns:
                    match = re.search(pattern, response.text)
                    if match:
                        return match.group(1)
        except Exception:
            pass
        
        return None
    
    def _start_heartbeat(self):
        """Start background heartbeat thread to keep session alive"""
        if self.heartbeat_running:
            return
        
        self.heartbeat_running = True
        self.heartbeat_thread = Thread(target=self._heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()
        logger.info(f"Heartbeat started for {self.platform_name}")
    
    def _heartbeat_loop(self):
        """Background loop to send keep-alive requests."""
        heartbeat_interval = 300  # 5 minutes
        
        while self.heartbeat_running:
            try:
                time.sleep(heartbeat_interval)
                
                if not self.is_authenticated:
                    continue
                
                self._send_heartbeat()
            
            except Exception as e:
                logger.error(f"Heartbeat loop error for {self.platform_name}: {str(e)}")
    
    def _send_heartbeat(self):
        """Send a single heartbeat request, re-login on failure."""
        endpoints = ["/api/heartbeat", "/api/ping", "/api/session/refresh", "/agent/keepalive"]
        
        with self.session_lock:
            try:
                for endpoint in endpoints:
                    try:
                        response = self.session.get(f"{self.agent_url}{endpoint}", timeout=10)
                        if response.status_code < 500:
                            self.last_heartbeat = datetime.now(timezone.utc)
                            logger.debug(f"Heartbeat sent to {self.platform_name}")
                            return
                    except Exception:
                        continue
            except Exception as e:
                logger.warning(f"Heartbeat failed for {self.platform_name}: {str(e)}")
                self.is_authenticated = False
                success, msg = self.login()
                if not success:
                    logger.error(f"Failed to re-login to {self.platform_name}: {msg}")
    
    def make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        retry_on_auth_fail: bool = True
    ) -> Tuple[bool, Any]:
        """
        Make an authenticated request to the platform.
        Returns: (success: bool, response_data: Any)
        """
        if not self.is_authenticated:
            success, msg = self.login()
            if not success:
                return False, {"error": msg}
        
        with self.session_lock:
            try:
                response = self._execute_request(method, endpoint, data, params)
                
                if response is None:
                    return False, {"error": f"Unsupported method: {method}"}
                
                # Handle auth errors with optional retry
                if response.status_code in (401, 403):
                    return self._handle_auth_error(method, endpoint, data, params, retry_on_auth_fail)
                
                return self._parse_response(response)
            
            except requests.exceptions.Timeout:
                return False, {"error": "Request timeout"}
            except requests.exceptions.ConnectionError:
                return False, {"error": "Connection error"}
            except Exception as e:
                logger.error(f"Request error for {self.platform_name}: {str(e)}")
                return False, {"error": str(e)}
    
    def _execute_request(self, method: str, endpoint: str, data, params):
        """Execute an HTTP request to the platform."""
        url = f"{self.agent_url}{endpoint}"
        headers = {}
        if self.csrf_token:
            headers["X-CSRF-Token"] = self.csrf_token
        
        method_upper = method.upper()
        if method_upper == "GET":
            return self.session.get(url, params=params, headers=headers, timeout=15)
        elif method_upper == "POST":
            return self.session.post(url, json=data, params=params, headers=headers, timeout=15)
        elif method_upper == "PUT":
            return self.session.put(url, json=data, params=params, headers=headers, timeout=15)
        elif method_upper == "DELETE":
            return self.session.delete(url, params=params, headers=headers, timeout=15)
        return None
    
    def _handle_auth_error(self, method, endpoint, data, params, retry_on_auth_fail) -> Tuple[bool, Any]:
        """Handle 401/403 responses with optional re-login and retry."""
        if retry_on_auth_fail:
            logger.warning(f"Auth error for {self.platform_name}, attempting re-login")
            self.is_authenticated = False
            success, msg = self.login()
            if success:
                return self.make_request(method, endpoint, data, params, retry_on_auth_fail=False)
        return False, {"error": "Authentication failed"}
    
    def _parse_response(self, response) -> Tuple[bool, Any]:
        """Parse HTTP response into a structured result."""
        try:
            return True, response.json()
        except Exception:
            if 200 <= response.status_code < 300:
                return True, {"status": "success", "raw": response.text}
            else:
                return False, {"error": f"Status {response.status_code}: {response.text[:200]}"}
    
    def logout(self):
        """Logout and cleanup"""
        self.heartbeat_running = False
        self.is_authenticated = False
        if self.heartbeat_thread:
            self.heartbeat_thread.join(timeout=2)
        self.session.close()
        logger.info(f"Logged out from {self.platform_name}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current session status"""
        return {
            "platform_id": self.platform_id,
            "platform_name": self.platform_name,
            "is_authenticated": self.is_authenticated,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "has_session_cookie": bool(self.session_cookie),
            "has_csrf_token": bool(self.csrf_token)
        }
