"""
APS API Connector Module
Handles authentication and API communication with Autodesk Platform Services
"""
import requests
import base64
import time
import logging

logger = logging.getLogger(__name__)


class APSConnector:
    """Handles all APS API interactions"""
    
    def __init__(self, client_id, client_secret, base_url):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url
        self.token = None
        self.token_expires_at = 0
    
    def get_token(self):
        """Get OAuth token (with caching)"""
        if self.token and time.time() < self.token_expires_at:
            return self.token
        
        logger.info("Requesting new OAuth token...")
        url = f"{self.base_url}/authentication/v2/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
            "scope": "data:read data:write data:create viewables:read"
        }
        
        try:
            r = requests.post(url, headers=headers, data=data, timeout=30)
            r.raise_for_status()
            result = r.json()
            
            self.token = result["access_token"]
            self.token_expires_at = time.time() + result.get("expires_in", 3600) - 60
            
            logger.info("✅ Authentication successful")
            return self.token
            
        except Exception as e:
            logger.error(f"❌ Authentication failed: {e}")
            raise
    
    def encode_urn(self, urn):
        """Base64 encode URN (URL-safe, no padding)"""
        encoded = base64.urlsafe_b64encode(urn.encode("utf-8")).decode("utf-8")
        return encoded.rstrip("=")
    
    def translate_model(self, version_urn):
        """Start model translation to SVF"""
        token = self.get_token()
        encoded_urn = self.encode_urn(version_urn)
        
        url = f"{self.base_url}/modelderivative/v2/designdata/job"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "x-ads-force": "true"
        }
        
        payload = {
            "input": {"urn": encoded_urn},
            "output": {
                "formats": [
                    {
                        "type": "svf",
                        "views": ["2d", "3d"]
                    }
                ]
            }
        }
        
        logger.info("Starting model translation...")
        
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if r.status_code in [200, 201]:
                logger.info("✅ Translation job started")
                return True
            elif r.status_code == 409:
                logger.info("ℹ️  Translation already completed")
                return True
            else:
                logger.error(f"❌ Translation failed: {r.status_code} - {r.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Translation request failed: {e}")
            return False
    
    def wait_for_translation(self, urn, timeout=600):
        """Wait for translation to complete"""
        token = self.get_token()
        encoded_urn = self.encode_urn(urn)
        url = f"{self.base_url}/modelderivative/v2/designdata/{encoded_urn}/manifest"
        headers = {"Authorization": f"Bearer {token}"}
        
        logger.info("Waiting for translation to complete...")
        start_time = time.time()
        stuck_count = 0
        
        while time.time() - start_time < timeout:
            try:
                r = requests.get(url, headers=headers, timeout=30)
                
                if r.status_code == 200:
                    manifest = r.json()
                    status = manifest.get("status")
                    progress = manifest.get("progress", "unknown")
                    
                    logger.info(f"Status: {status}, Progress: {progress}")
                    
                    if status == "success":
                        logger.info("✅ Translation completed successfully")
                        return True
                    elif status == "failed":
                        logger.error("❌ Translation failed")
                        return False
                    elif status in ["inprogress", "pending"]:
                        if progress == "complete" or "99%" in str(progress):
                            stuck_count += 1
                            if stuck_count >= 5:
                                derivatives = manifest.get("derivatives", [])
                                if any(d.get("children") for d in derivatives):
                                    logger.info("✅ Derivatives available, proceeding...")
                                    return True
                        else:
                            stuck_count = 0
                        
                        time.sleep(10)
                else:
                    time.sleep(10)
                    
            except Exception as e:
                logger.error(f"Error checking status: {e}")
                time.sleep(10)
        
        logger.error("⏰ Translation timeout")
        return False
    
    def get_metadata(self, urn):
        """Get model metadata (viewables)"""
        token = self.get_token()
        encoded_urn = self.encode_urn(urn)
        url = f"{self.base_url}/modelderivative/v2/designdata/{encoded_urn}/metadata"
        headers = {"Authorization": f"Bearer {token}"}
        
        try:
            r = requests.get(url, headers=headers, timeout=30)
            r.raise_for_status()
            metadata = r.json()
            
            viewables = metadata["data"]["metadata"]
            logger.info(f"✅ Retrieved {len(viewables)} viewable(s)")
            return metadata
            
        except Exception as e:
            logger.error(f"❌ Failed to get metadata: {e}")
            return None
    
    def get_properties(self, urn, guid):
        """Get properties for a specific viewable GUID"""
        token = self.get_token()
        encoded_urn = self.encode_urn(urn)
        url = f"{self.base_url}/modelderivative/v2/designdata/{encoded_urn}/metadata/{guid}/properties"
        headers = {"Authorization": f"Bearer {token}"}
        
        try:
            r = requests.get(url, headers=headers, timeout=60)
            r.raise_for_status()
            props = r.json()
            
            if "data" in props and "collection" in props["data"]:
                count = len(props["data"]["collection"])
                logger.info(f"✅ Retrieved properties for {count} objects")
                return props
            else:
                logger.warning("⚠️  No property collection found")
                return None
                
        except Exception as e:
            logger.error(f"❌ Failed to get properties: {e}")
            return None