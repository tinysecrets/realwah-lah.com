"""
Firebase Secret Manager Integration
Retrieves game platform credentials from Firebase Secret Manager

REQUIREMENTS:
1. Firebase service account JSON in /app/backend/config/firebase-service-account.json
2. Install: pip install firebase-admin google-cloud-secret-manager
3. Set FIREBASE_PROJECT_ID in .env
4. Enable Secret Manager API in Google Cloud Console
"""

import os
import logging
from typing import Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Flag to check if Firebase is available
FIREBASE_AVAILABLE = False

try:
    from firebase_admin import credentials, initialize_app
    from google.cloud import secretmanager
    FIREBASE_AVAILABLE = True
    logger.info("Firebase Admin SDK loaded successfully")
except ImportError:
    logger.warning("Firebase Admin SDK not installed. Using environment variables for credentials.")

class FirebaseSecretManager:
    """
    Retrieves game platform credentials from Firebase Secret Manager.
    Falls back to environment variables if Firebase is not configured.
    """
    
    def __init__(self):
        self.firebase_app = None
        self.secret_client = None
        self.project_id = os.environ.get("FIREBASE_PROJECT_ID", "")
        self.use_firebase = False
        
        if FIREBASE_AVAILABLE:
            self._initialize_firebase()
    
    def _initialize_firebase(self):
        """Initialize Firebase Admin SDK"""
        try:
            # Check for service account file
            service_account_path = Path(__file__).parent.parent / "config" / "firebase-service-account.json"
            
            if service_account_path.exists() and self.project_id:
                # Initialize Firebase Admin
                cred = credentials.Certificate(str(service_account_path))
                self.firebase_app = initialize_app(cred, name="game_secrets")
                
                # Initialize Secret Manager client
                self.secret_client = secretmanager.SecretManagerServiceClient()
                
                self.use_firebase = True
                logger.info(f"✅ Firebase Secret Manager initialized for project: {self.project_id}")
            else:
                logger.warning("Firebase service account not found. Using environment variables.")
        
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {str(e)}")
            logger.warning("Falling back to environment variables")
    
    def get_master_keys(self) -> Dict[str, Dict[str, str]]:
        """
        Retrieve all 6 master keys from Firebase or environment variables.
        
        Returns:
            dict: {
                "fire_kirin": {"username": "...", "password": "..."},
                "juwa": {"username": "...", "password": "..."},
                ...
            }
        """
        platforms = ["fire_kirin", "juwa", "juwa2", "ultra_panda", "panda_master", "orion_stars", "game_vault"]
        master_keys = {}
        
        for platform in platforms:
            if self.use_firebase:
                keys = self._get_from_firebase(platform)
            else:
                keys = self._get_from_env(platform)
            
            if keys["username"] and keys["password"]:
                master_keys[platform] = keys
                logger.info(f"✅ Retrieved credentials for {platform}")
            else:
                logger.warning(f"⚠️ No credentials found for {platform}")
        
        return master_keys
    
    def _get_from_firebase(self, platform: str) -> Dict[str, str]:
        """Retrieve credentials from Firebase Secret Manager"""
        try:
            # Secret naming convention: {platform}_agent_user, {platform}_agent_pass
            username_secret = f"projects/{self.project_id}/secrets/{platform}_agent_user/versions/latest"
            password_secret = f"projects/{self.project_id}/secrets/{platform}_agent_pass/versions/latest"
            
            # Access secrets
            username_response = self.secret_client.access_secret_version(request={"name": username_secret})
            password_response = self.secret_client.access_secret_version(request={"name": password_secret})
            
            return {
                "username": username_response.payload.data.decode('UTF-8'),
                "password": password_response.payload.data.decode('UTF-8')
            }
        
        except Exception as e:
            logger.error(f"Failed to retrieve {platform} from Firebase: {str(e)}")
            return {"username": "", "password": ""}
    
    def _get_from_env(self, platform: str) -> Dict[str, str]:
        """Fallback: Retrieve credentials from environment variables"""
        platform_upper = platform.upper()
        
        return {
            "username": os.environ.get(f"{platform_upper}_AGENT_USER", ""),
            "password": os.environ.get(f"{platform_upper}_AGENT_PASS", "")
        }
    
    def get_platform_credentials(self, platform_id: str) -> Optional[Dict[str, str]]:
        """
        Get credentials for a specific platform.
        
        Args:
            platform_id: Platform identifier (e.g., "fire_kirin")
        
        Returns:
            dict: {"username": "...", "password": "..."} or None
        """
        all_keys = self.get_master_keys()
        return all_keys.get(platform_id)
    
    def verify_connection(self) -> Dict[str, any]:
        """
        Verify Firebase connection and available credentials.
        
        Returns:
            dict: Status information
        """
        master_keys = self.get_master_keys()
        
        return {
            "firebase_enabled": self.use_firebase,
            "project_id": self.project_id if self.use_firebase else None,
            "credentials_source": "Firebase Secret Manager" if self.use_firebase else "Environment Variables",
            "platforms_configured": list(master_keys.keys()),
            "total_platforms": len(master_keys)
        }


# Global instance
firebase_secrets = FirebaseSecretManager()
