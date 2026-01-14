
import logging
import requests
import re
import time
import random
from typing import Dict, Any, Optional, Tuple

from agentic_tools.channels.activation import NotificationChannel
from main_configs import MarketingConfigs

from agentic_tools.channels.helpers import get_emails_from_arango
from data_workers.database import get_arango_db

logger = logging.getLogger(__name__)

class ZaloOAChannel(NotificationChannel):
    def __init__(self, override_token: str = None):
        # -------- Database Connection --------
        try:
            self.db = get_arango_db()
        except Exception as e:
            logger.error(f"[EmailChannel] Failed to connect to ArangoDB on init: {e}")
            self.db = None

        self.zns_url = "https://business.openapi.zalo.me/message/template"
        self.oauth_url = "https://oauth.zaloapp.com/v4/oa/access_token"
        
        self.app_id = MarketingConfigs.ZALO_APP_ID
        self.secret_key = MarketingConfigs.ZALO_APP_SECRET
        self.template_id = MarketingConfigs.ZALO_ZNS_TEMPLATE_ID
        
        # Token Management
        self.access_token = override_token or MarketingConfigs.ZALO_OA_TOKEN
        self.refresh_token = MarketingConfigs.ZALO_OA_REFRESH_TOKEN


    def send(self, recipient_segment: str, message: str = None, **kwargs):
        """
        Main Execution Flow (Test Mode)
        """
        logger.info(f"[Zalo] Starting TEST MODE send to segment: {recipient_segment}")
        
        # 1. Fetch Recipients
        recipients = get_emails_from_arango(self.db, recipient_segment)
        if not recipients:
            return {"status": "warning", "message": f"No profiles found in '{recipient_segment}'"}

        stats = {"sent": 0, "failed": 0, "invalid_phone": 0}

        # 2. Loop & Send
        for p in recipients:
            phone = self._format_phone_for_zalo(p.get('phone'))
            name = p.get('firstName', 'Customer')

            if not phone:
                stats["invalid_phone"] += 1
                continue

            # Construct Payload
            # NOTE: Ensure keys like 'customer_name' match your ZNS Template exactly!
            # 1. Generate a random 6-digit OTP
            generated_otp = str(random.randint(100000, 999999))

            # 2. Construct Payload
            payload = {
                "phone": phone,
                "template_id": self.template_id,
                "template_data": {
                    # Zalo requires the key to match "otp" exactly
                    "otp": generated_otp,
                },
                "tracking_id": f"track_{int(time.time())}_{phone}"
            }

            # 3. Send
            success, error_code, result_msg = self._execute_zns_call(payload)

            if success:
                stats["sent"] += 1
                # NOTE: In real mode, consider saving verified phones
                # self._save_verified_phone(phone, name, result_msg)
            else:
                stats["failed"] += 1
                if error_code == -124:
                    logger.error("❌ YOUR ACCESS TOKEN IS EXPIRED. Please update ZALO_OA_TOKEN in configs.")
                    # In test mode, we break immediately if token is bad to save time
                    return {"status": "error", "message": "Access Token Expired (-124). Update token and retry."}

        return {
            "status": "success", 
            "details": f"Test run complete for {len(recipients)} users.", 
            "stats": stats
        }
    

    def _format_phone_for_zalo(self, phone: str) -> Optional[str]:
        """
        Converts 09xx -> 849xx. Returns None if invalid.
        """
        if not phone:
            return None
        
        # Remove non-digits
        clean_phone = re.sub(r'\D', '', phone)
        
        # Handle 84 prefix
        if clean_phone.startswith('84'):
            return clean_phone
        if clean_phone.startswith('0'):
            return '84' + clean_phone[1:]
            
        return clean_phone
    
    
    def _save_verified_phone(self, phone: str, name: str, msg_id: str):
        """
        Saves successfully reached numbers to 'cdp_verified_phone'.
        Uses UPSERT to avoid duplicates.
        """
        if not self.db: return

        aql_upsert = """
        UPSERT { phone: @phone } 
        INSERT { 
            phone: @phone, 
            firstName: @name, 
            firstVerifiedAt: DATE_ISO8601(DATE_NOW()),
            lastVerifiedAt: DATE_ISO8601(DATE_NOW()),
            lastMsgId: @msg_id,
            channel: 'zalo_zns',
            status: 'active'
        } 
        UPDATE { 
            lastVerifiedAt: DATE_ISO8601(DATE_NOW()),
            lastMsgId: @msg_id,
            firstName: @name,
            status: 'active'
        } 
        IN cdp_verified_phone
        """
        try:
            self.db.aql.execute(aql_upsert, bind_vars={
                'phone': phone, 
                'name': name,
                'msg_id': msg_id
            })
            # logger.info(f"[Zalo] Verified phone saved: {phone}")
        except Exception as e:
            logger.error(f"[Zalo] Failed to save verified phone {phone}: {e}")


    def _refresh_access_token(self) -> bool:
        """Refreshes the token and rotates the Refresh Token."""
        logger.info("[Zalo] Refreshing token...")
        headers = {"secret_key": self.secret_key}
        payload = {
            "refresh_token": self.refresh_token,
            "app_id": self.app_id,
            "grant_type": "refresh_token"
        }

        try:
            resp = requests.post(self.oauth_url, headers=headers, data=payload, timeout=10)
            data = resp.json()

            if "access_token" in data:
                self.access_token = data["access_token"]
                self.refresh_token = data["refresh_token"] 
                # TODO: Save new tokens to persistent storage (DB/File) here!
                return True
            else:
                logger.error(f"[Zalo] Refresh Failed: {data}")
                return False
        except Exception as e:
            logger.error(f"[Zalo] Refresh Exception: {e}")

            return False
        
        
    def _execute_zns_call(self, payload: Dict) -> Tuple[bool, int, str]:
        """
        Executes API call with VERBOSE DEBUGGING.
        """
        # 1. Sanitize Token (Strip whitespace which causes many errors)
        clean_token = self.access_token.strip()
        
        headers = {
            "access_token": clean_token,  # ZNS uses this specific header key
            "Content-Type": "application/json"
        }
        
        # 2. DEBUG LOGS: Print what we are actually sending
        # Mask the token so we can verify it without leaking it entirely
        masked_token = f"{clean_token[:10]}...{clean_token[-10:]}" if len(clean_token) > 20 else "INVALID_SHORT_TOKEN"
        
        logger.info("------------- ZALO DEBUG REQUEST -------------")
        logger.info(f"URL: {self.zns_url}")
        logger.info(f"Token Used: {masked_token}") 
        logger.info(f"Token Length: {len(clean_token)} chars")
        logger.info(f"Payload: {payload}")
        logger.info("----------------------------------------------")

        try:
            resp = requests.post(self.zns_url, json=payload, headers=headers, timeout=15)
            data = resp.json()
            
            # 3. DEBUG LOGS: Print exactly what Zalo replied
            logger.info("------------- ZALO DEBUG RESPONSE ------------")
            logger.info(f"Status Code: {resp.status_code}")
            logger.info(f"Raw Body: {resp.text}")
            logger.info("----------------------------------------------")
            
            error_code = data.get("error", -999)
            message = data.get("message", "Unknown")
            
            if error_code == 0:
                msg_id = data.get("data", {}).get("msg_id", "unknown")
                return True, 0, msg_id

            return False, error_code, message

        except Exception as e:
            logger.error(f"[Zalo Network Error] {e}")
            return False, -999, str(e)

    