
import logging
import requests
import re
import time
import random
from typing import Dict, Any, Optional, Tuple
import urllib.parse
import json

from agentic_tools.channels.activation import NotificationChannel


from main_configs import MarketingConfigs


logger = logging.getLogger(__name__)

_ZALO_ID_PREFIX = "zalo_user_id:"


def extract_zalo_user_id(media_channels: list) -> Optional[str]:
    """Extract the encrypted Zalo user_id from a media_channels string array.

    The CDP stores the Zalo ID as ``"zalo_user_id:<encrypted_id>"`` alongside
    plain channel labels such as ``"facebook"`` or ``"zalo"``.

    Returns the bare ID string, or ``None`` if no Zalo entry is found.
    """
    for entry in media_channels:
        if isinstance(entry, str) and entry.startswith(_ZALO_ID_PREFIX):
            return entry[len(_ZALO_ID_PREFIX):]
    return None


class ZaloOAChannel(NotificationChannel):
    # Constants for DB Lookup
    CONNECTOR_NAME = "LEO Zalo Connector"
    COLLECTION_NAME = "cdp_dataconnector"

    def __init__(self, override_token: str = None, db_client=None):
        # Assign the passed DB client directly
        self.db = db_client 
        
        self.zns_url = "https://business.openapi.zalo.me/message/template"
        self.oauth_url = "https://oauth.zaloapp.com/v4/oa/access_token"
        
        self.app_id = MarketingConfigs.ZALO_APP_ID
        self.secret_key = MarketingConfigs.ZALO_APP_SECRET
        self.template_id = MarketingConfigs.ZALO_ZNS_TEMPLATE_ID
        
        self.access_token = override_token or MarketingConfigs.ZALO_OA_TOKEN
        self.refresh_token = MarketingConfigs.ZALO_OA_REFRESH_TOKEN

        # Now, if you passed a db_client, it will actually load the tokens!
        if self.db:
            self._load_tokens_from_db()
        else:
            logger.warning("[Zalo] No DB client provided. Falling back to static configs.")


    def get_oa_followers(self, limit: int = 50) -> list:
        """
        Fetches the raw Zalo User IDs (UIDs) of people currently following your OA.
        
        Note: Zalo only returns the UID here. To get their name or avatar, 
        you must pass these UIDs into `get_user_detail()`.
        """
        url = "https://openapi.zalo.me/v3.0/oa/user/getlist"
        headers = {"access_token": self.access_token.strip(), "Content-Type": "application/json"}

        all_followers = []
        offset = 0
        batch_size = 50 # Zalo's strict max per request

        while len(all_followers) < limit:
            data_param = {"offset": offset, "count": batch_size, "is_follower": "true"}
            encoded_data = urllib.parse.quote(json.dumps(data_param))
            request_url = f"{url}?data={encoded_data}"

            try:
                resp = requests.get(request_url, headers=headers, timeout=15)
                data = resp.json()
                error_code = data.get("error", -999)
                
                # Handle Expired Token
                if error_code in [-124, -216]:
                    if self._refresh_access_token():
                        headers["access_token"] = self.access_token.strip()
                        continue # Retry same offset with new token
                    break
                
                if error_code != 0:
                    logger.error(f"[Zalo] Failed to fetch followers: {data.get('message')}")
                    break

                users = data.get("data", {}).get("users", [])
                if not users:
                    break

                all_followers.extend(users)
                offset += batch_size
                time.sleep(0.5) # Rate limiting protection

            except Exception as e:
                logger.error(f"[Zalo Network Error] {e}")
                break

        return all_followers[:limit]
    

    def get_user_detail(self, user_id: str) -> dict:
        """
        Fetches the rich profile (Display Name, Avatar, and Shared Phone Number) 
        for a specific Zalo User ID.
        """
        url = "https://openapi.zalo.me/v3.0/oa/user/detail"
        headers = {"access_token": self.access_token.strip(), "Content-Type": "application/json"}
        
        data_param = {"user_id": user_id}
        request_url = f"{url}?data={urllib.parse.quote(json.dumps(data_param))}"

        try:
            resp = requests.get(request_url, headers=headers, timeout=10)
            data = resp.json()
            if data.get("error") == 0:
                return data.get("data", {})
            return {}
        except Exception as e:
            logger.error(f"[Zalo] Network error fetching details for {user_id}: {e}")
            return {}
        
    def check_user_quota(self, user_id: str) -> dict:
        """
        Diagnostic tool: Checks how many promotional messages you are still 
        allowed to send to this specific user this month.
        """
        url = "https://openapi.zalo.me/v3.0/oa/quota/message"
        payload = {"user_id": user_id}
        headers = {"access_token": self.access_token.strip(), "Content-Type": "application/json"}
        
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            return resp.json()
        except Exception as e:
            return {"error": -1, "message": str(e)}
        
        
    # ==========================================
    # MESSAGING METHODS
    # ==========================================

    def send_text_with_image(self, zalo_user_id: str, text_content: str, image_url: str, buttons: list = None) -> tuple[bool, int, str]:
        """
        Sends a message containing text, an image, and optional interactive buttons.
        MUST use the 'media' template to avoid Zalo's -233 Error on the CS endpoint.
        """
        url = "https://openapi.zalo.me/v3.0/oa/message/cs"
        
        payload = {
            "recipient": {"user_id": zalo_user_id},
            "message": {
                "text": text_content, # The text sits outside the attachment in the 'media' type
                "attachment": {
                    "type": "template",
                    "payload": {
                        "template_type": "media", # <-- THIS IS THE CRITICAL FIX
                        "elements": [
                            {
                                "media_type": "image",
                                "url": image_url
                            }
                        ]
                    }
                }
            }
        }
        
        # Safely inject buttons if they are provided
        if buttons:
            payload["message"]["attachment"]["payload"]["buttons"] = buttons
            
        return self._execute_api_post(url, payload)

    def send_promotional_message(self, zalo_user_id: str, template_id: str, template_data: Dict[str, Any]) -> Tuple[bool, int, str]:
        """
        Sends a purely promotional message (ZBS Template) to a user.
        This bypasses the 7-day interaction rule but consumes your OA's monthly promotional quota.
        
        Args:
            zalo_user_id: The recipient's Zalo ID.
            template_id: The approved ZBS Template ID (from ZCA).
            template_data: Dictionary of variables matching your template design.
            
        Returns: Tuple of (Success Boolean, Error Code, Message ID or Error string)
        """
        url = "https://openapi.zalo.me/v3.0/oa/message/promotion"
        
        payload = {
            "recipient": {"user_id": zalo_user_id},
            "message": {
                "template_id": template_id,
                "template_data": template_data
            }
        }
        
        # Leverages your robust token-refreshing engine!
        return self._execute_api_post(url, payload)


    def send_simple_text(self, zalo_user_id: str, text_content: str) -> tuple[bool, int, str]:
        """
        Sends a standard, free text message via the CS endpoint.
        Used primarily by the webhook to auto-reply to user interactions.
        """
        url = "https://openapi.zalo.me/v3.0/oa/message/cs"
        
        payload = {
            "recipient": {"user_id": zalo_user_id},
            "message": {"text": text_content}
        }
        
        return self._execute_api_post(url, payload)
        
    def send(self, segment_id: str, message: str = None, **kwargs):
        """
        Main Execution Flow (Test Mode)
        """
        logger.info(f"[Zalo] Starting TEST MODE send to segment: {segment_id}")
        
        # 1. Fetch Recipients
        recipients = self.get_segment_contacts(segment_id)
        if not recipients:
            return {"status": "warning", "message": f"No profiles found in '{segment_id}'"}

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

            # 3. Attempt 1 Send
            success, error_code, result_msg = self._execute_zns_call(payload)

            # 4. Auto-Refresh Logic
            if not success and error_code == -124:
                logger.warning(f"[Zalo] Token expired for {phone}. Refreshing and Retrying...")
                if self._refresh_access_token():
                    # Attempt 2 (Retry with new token)
                    success, error_code, result_msg = self._execute_zns_call(payload)
                else:
                    logger.error("[Zalo] Token refresh failed. Aborting retry.")

            # 5. Handle Final Result
            if success:
                stats["sent"] += 1
                # NOTE: In real mode, consider saving verified phones
                # self._save_verified_phone(phone, name, result_msg)
            else:
                stats["failed"] += 1
                logger.warning(f"[Zalo] Failed to send to {phone}. Error: {error_code} - {result_msg}")

        return {
            "status": "success", 
            "details": f"Run complete. Sent: {stats['sent']}, Failed: {stats['failed']}", 
            "stats": stats
        }


    # ==========================================
    # INTERNAL UTILITIES & TOKEN MANAGEMENT
    # ==========================================

    def _execute_api_post(
        self, url: str, payload: Dict[str, Any]
    ) -> Tuple[bool, int, str]:
        """Generic POST against any Zalo OA API endpoint.

        Reuses the current ``access_token`` (with whitespace stripped).
        Automatically catches -216 (Expired Token), refreshes via DB, 
        and retries the request seamlessly.
        """
        clean_token: str = self.access_token.strip()
        headers: Dict[str, str] = {
            "access_token": clean_token,
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            data: Dict[str, Any] = resp.json()

            error_code: int = data.get("error", -999)
            message: str = data.get("message", "Unknown")

            # 🚨 THE SAFETY NET: Catch Expired Token
            if error_code == -216:
                logger.warning(f"[Zalo API] Caught -216 Expired Token. Triggering auto-refresh...")
                
                if self._refresh_access_token():
                    # Refresh succeeded! Update headers with the NEW token
                    headers["access_token"] = self.access_token.strip()
                    logger.info("[Zalo API] Retrying original request with new token...")
                    
                    # Fire the exact same payload again
                    retry_resp = requests.post(url, json=payload, headers=headers, timeout=15)
                    retry_data = retry_resp.json()
                    
                    retry_error: int = retry_data.get("error", -999)
                    retry_message: str = retry_data.get("message", "Unknown")
                    
                    if retry_error == 0:
                        # Note: Zalo APIs sometimes use 'msg_id', sometimes 'message_id'
                        data_block = retry_data.get("data", {})
                        msg_id: str = data_block.get("message_id", data_block.get("msg_id", "unknown"))
                        return True, 0, msg_id
                    else:
                        return False, retry_error, retry_message
                else:
                    return False, -216, "Token expired and auto-refresh failed."

            # Normal Execution (Token was valid)
            if error_code == 0:
                data_block = data.get("data", {})
                msg_id: str = data_block.get("message_id", data_block.get("msg_id", "unknown"))
                return True, 0, msg_id

            return False, error_code, message

        except Exception as e:
            logger.error(f"[Zalo Network Error] {e}")
            return False, -999, str(e)
        

    def _refresh_access_token(self) -> bool:
        """
        1. Reads latest Refresh Token from DB.
        2. Calls Zalo OAuth.
        3. Saves new tokens to DB.
        """
        logger.info("[Zalo] Access Token invalid/expired. Preparing to refresh...")
        
        # 1. CRITICAL: Fetch the latest Refresh Token from DB right now
        # This prevents using a stale token if another process updated it.
        self._load_tokens_from_db()
        
        if not self.refresh_token:
            logger.error("[Zalo] No Refresh Token available (DB & Config empty). Cannot refresh.")
            return False

        headers = {"secret_key": self.secret_key}
        payload = {
            "refresh_token": self.refresh_token,
            "app_id": self.app_id,
            "grant_type": "refresh_token"
        }

        try:
            resp = requests.post(self.oauth_url, headers=headers, data=payload, timeout=15)
            data = resp.json()

            if "access_token" in data:
                new_at = data["access_token"]
                new_rt = data["refresh_token"]
                
                # Update Memory
                self.access_token = new_at
                self.refresh_token = new_rt 
                
                # Update Database
                self._save_tokens_to_db(new_at, new_rt)
                return True
            else:
                logger.error(f"[Zalo] Refresh Failed. Response: {data}")
                return False
        except Exception as e:
            logger.error(f"[Zalo] Refresh Exception: {e}")
            return False


    def _load_tokens_from_db(self):
        """
        Fetches the latest tokens from 'cdp_dataconnector' collection.
        """
        if not self.db: return

        try:
            aql = f"""
            FOR d IN {self.COLLECTION_NAME}
                FILTER d.name == @name
                RETURN d.configs
            """
            cursor = self.db.aql.execute(aql, bind_vars={'name': self.CONNECTOR_NAME})
            configs = list(cursor)
            
            if configs and len(configs) > 0:
                cfg = configs[0]
                self.access_token = cfg.get("zalo_oa_token", self.access_token)
                self.refresh_token = cfg.get("zalo_refresh_token", self.refresh_token)
                logger.info("[Zalo] Successfully loaded tokens from DB.")
            else:
                logger.warning(f"[Zalo] No connector found with name '{self.CONNECTOR_NAME}'. Using static configs.")
        except Exception as e:
            logger.error(f"[Zalo] Failed to load tokens from DB: {e}")


    def _save_tokens_to_db(self, new_access_token: str, new_refresh_token: str):
        """
        Persists the NEW tokens to 'cdp_dataconnector'.
        CRITICAL: Zalo Refresh Tokens are single-use. We must save the new one.
        """
        if not self.db: return

        try:
            # We use MERGE to update only the specific fields inside 'configs' object
            aql = f"""
            FOR d IN {self.COLLECTION_NAME}
                FILTER d.name == @name
                UPDATE d WITH {{
                    configs: MERGE(d.configs, {{
                        zalo_oa_token: @at,
                        zalo_refresh_token: @rt
                    }}),
                    updatedAt: DATE_ISO8601(DATE_NOW())
                }} IN {self.COLLECTION_NAME}
            """
            self.db.aql.execute(aql, bind_vars={
                'name': self.CONNECTOR_NAME,
                'at': new_access_token,
                'rt': new_refresh_token
            })
            logger.info("[Zalo] ✅ New tokens saved to Database successfully.")
        except Exception as e:
            logger.error(f"[Zalo] ❌ CRITICAL: Failed to save new tokens to DB! Next run will fail. Error: {e}")

    
    # ==========================================
    # ZNS & PHONE NUMBER UTILITIES
    # ==========================================

    def _format_phone_for_zalo(self, phone: str) -> Optional[str]:
        """
        Formats a standard Vietnamese phone number (09xx) to Zalo's required (849xx) format.
        Strips all non-numeric characters.
        """
        if not phone:
            return None
        
        # Remove anything that isn't a digit (spaces, dashes, + signs)
        clean_phone = ''.join(filter(str.isdigit, phone))
        
        if clean_phone.startswith('84'):
            return clean_phone
        if clean_phone.startswith('0'):
            return '84' + clean_phone[1:]
            
        return clean_phone

    def _save_verified_phone(self, phone: str, name: str, msg_id: str):
        """
        Upserts successfully reached phone numbers to the 'cdp_verified_phone' collection.
        This allows the CDP to know which phone numbers are active on Zalo.
        """
        if not self.db: 
            return

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
                'name': name or "Unknown",
                'msg_id': msg_id
            })
            # logger.info(f"[CDP] Verified Zalo phone saved: {phone}")
        except Exception as e:
            logger.error(f"[CDP] Failed to save verified phone {phone}: {e}")

    def get_segment_contacts(self, segment_id: str) -> list:
        """
        Queries ArangoDB to fetch the phone numbers and names of users in a specific segment.
        Replaces the old dummy 'get_user_contact_from_cdp' function.
        """
        if not self.db:
            logger.warning("[CDP] No DB connection. Returning empty segment.")
            return []
            
        try:
            # Note: Update this AQL to match your actual CDP schema!
            aql = """
            FOR user IN cdp_profiles
                FILTER @segment_id IN user.segments
                FILTER user.phone != null
                RETURN { phone: user.phone, firstName: user.firstName }
            """
            cursor = self.db.aql.execute(aql, bind_vars={'segment_id': segment_id})
            return list(cursor)
        except Exception as e:
            logger.error(f"[CDP DB Error] Failed to fetch segment {segment_id}: {e}")
            return []