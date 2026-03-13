
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


def get_user_contact_from_cdp(segment_id: str) -> Optional[list]:
    """
    Placeholder function to fetch user contacts from CDP based on segment_id.
    In real implementation, this should query the actual CDP system.
    """
    # For demonstration, return a static list
    dummy_data = [
        {"phone": "0912345678", "firstName": "Alice"},
        {"phone": "0987654321", "firstName": "Bob"},
        {"phone": "0123456789", "firstName": "Charlie"},
    ]
    return dummy_data

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
        Fetches the list of encrypted Zalo user_ids who currently follow the OA.
        Handles pagination automatically up to the specified limit.
        """
        url = "https://openapi.zalo.me/v3.0/oa/user/getlist"
        clean_token = self.access_token.strip()
        headers = {
            "access_token": clean_token,
            "Content-Type": "application/json"
        }

        all_followers = []
        offset = 0
        batch_size = 50 # Zalo's maximum allowed count per request

        logger.info(f"[Zalo] Fetching up to {limit} followers...")

        while len(all_followers) < limit:
            # Construct the query parameter
            data_param = {
                "offset": offset,
                "count": batch_size,
                "is_follower": "true" # Strictly filter by active followers
            }
            
            # URL encode the JSON string as required by Zalo GET requests
            encoded_data = urllib.parse.quote(json.dumps(data_param))
            request_url = f"{url}?data={encoded_data}"

            try:
                resp = requests.get(request_url, headers=headers, timeout=15)
                data = resp.json()
                
                error_code = data.get("error", -999)
                
                # Handle Token Expiration
                if error_code in [-124, -216]:
                    logger.warning(f"[Zalo] Token invalid/expired (Error {error_code}). Refreshing...")
                    if self._refresh_access_token():
                        # CRITICAL: Inject the brand new token into the headers for the retry
                        headers["access_token"] = self.access_token.strip()
                        continue # Retry the exact same offset
                    else:
                        logger.error("[Zalo] Refresh failed. You need to manually generate a new token.")
                        break # Stop if refresh fails

                if error_code != 0:
                    logger.error(f"[Zalo] Failed to fetch followers. Error: {error_code} - {data.get('message')}")
                    break

                # Parse the successful response
                users = data.get("data", {}).get("users", [])
                if not users:
                    break # No more users to fetch

                all_followers.extend(users)
                offset += batch_size
                
                # Be polite to Zalo's rate limits
                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[Zalo] Network Error while fetching followers: {e}")
                break

        # Return exactly the limit requested
        return all_followers[:limit]

    def get_user_detail(self, user_id: str) -> dict:
        """
        Fetches detailed profile info (name, avatar, etc.) for a specific user_id.
        """
        url = "https://openapi.zalo.me/v3.0/oa/user/detail"
        clean_token = self.access_token.strip()
        headers = {
            "access_token": clean_token,
            "Content-Type": "application/json"
        }
        
        data_param = {"user_id": user_id}
        encoded_data = urllib.parse.quote(json.dumps(data_param))
        request_url = f"{url}?data={encoded_data}"

        try:
            resp = requests.get(request_url, headers=headers, timeout=10)
            data = resp.json()
            
            if data.get("error") == 0:
                # Zalo returns the profile inside the 'data' object
                return data.get("data", {})
            else:
                logger.warning(f"[Zalo] Failed to fetch details for {user_id}: {data.get('message')}")
                return {}
                
        except Exception as e:
            logger.error(f"[Zalo] Network error fetching details for {user_id}: {e}")
            return {}
        
    def send_text_with_image(self, zalo_user_id: str, text_content: str, image_url: str) -> tuple[bool, int, str]:
        """
        Sends a message containing both text and an image via the CS endpoint.
        Requires the user to have interacted within the last 7 days.
        """
        url = "https://openapi.zalo.me/v3.0/oa/message/cs"
        
        payload = {
            "recipient": {
                "user_id": zalo_user_id
            },
            "message": {
                "text": text_content,
                "attachment": {
                    "type": "template",
                    "payload": {
                        "template_type": "media",
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
        
        return self._execute_api_post(url, payload)
        
    def send(self, segment_id: str, message: str = None, **kwargs):
        """
        Main Execution Flow (Test Mode)
        """
        logger.info(f"[Zalo] Starting TEST MODE send to segment: {segment_id}")
        
        # 1. Fetch Recipients
        recipients = get_user_contact_from_cdp(segment_id)
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

    
    # --------------------------------------------------------
    # Promotional Messages (Tin Truyền Thông)
    # --------------------------------------------------------

    def send_promotion(self, zalo_user_id: str, template_data: Dict[str, Any]) -> Tuple[bool, int, str]:
        url = "https://openapi.zalo.me/v3.0/oa/message/promotion"
        
        payload = {
            "recipient": {"user_id": zalo_user_id},
            "message": {
                "attachment": {
                    "type": "template",
                    "payload": {
                        "template_type": "promotion",
                        "elements": [
                            {
                                "type": "header",
                                "content": template_data.get("title")[:100] # Zalo has strict length limits
                            },
                            {
                                "type": "text",
                                "content": template_data.get("subtitle")[:500]
                            }
                        ],
                        "buttons": [
                            {
                                "title": "Xem ngay",
                                "type": "oa.open.url",
                                "payload": {"url": template_data.get("url")}
                            }
                        ]
                    }
                }
            }
        }
        # Note: I removed the 'banner' element. Sometimes a broken Image URL triggers -233.
        # If this works, add the banner back slowly.
        return self._execute_api_post(url, payload)

    def send_article_promotion(self, zalo_user_id: str, article_id: str) -> Tuple[bool, int, str]:
        """
        Sends a rich Article (like the CellphoneS one) to a user.
        The article must already be created/published in your OA Manager.
        """
        url = "https://openapi.zalo.me/v3.0/oa/message/promotion"
        
        payload = {
            "recipient": {"user_id": zalo_user_id},
            "message": {
                "attachment": {
                    "type": "template",
                    "payload": {
                        "template_type": "media", # Media type is used for Articles
                        "elements": [{
                            "media_type": "article",
                            "attachment_id": article_id
                        }]
                    }
                }
            }
        }
        return self._execute_api_post(url, payload)

    def send_article_media(self, zalo_user_id: str, article_id: str):
        """
        Sends a rich Article (media type) to a specific user.
        """
        url = "https://openapi.zalo.me/v3.0/oa/message/cs"
        
        payload = {
            "recipient": {"user_id": zalo_user_id},
            "message": {
                "attachment": {
                    "type": "template",
                    "payload": {
                        "template_type": "media",
                        "elements": [{
                            "media_type": "article",
                            "attachment_id": article_id # Your Article ID from Phase 2
                        }]
                    }
                }
            }
        }
        return self._execute_api_post(url, payload)
    
    def send_article_link(self, zalo_user_id: str, article_url: str):
            """
            Sends an Article as a rich-preview link using the CS endpoint.
            Note: Because it uses the CS endpoint, the user must have interacted within 7 days.
            """
            url = "https://openapi.zalo.me/v3.0/oa/message/cs"
            
            payload = {
                "recipient": {"user_id": zalo_user_id},
                "message": {
                    # Zalo will automatically convert this link into a beautiful 
                    # visual card in the user's chat window!
                    "text": f"🚀 Danh mục cổ phiếu tiềm năng dành riêng cho bạn:\n{article_url}"
                }
            }
            return self._execute_api_post(url, payload)
            
    def check_user_quota(self, zalo_user_id: str):
        url = "https://openapi.zalo.me/v3.0/oa/quota/message"
        payload = {"user_id": zalo_user_id}
        
        clean_token = self.access_token.strip()
        headers = {"access_token": clean_token, "Content-Type": "application/json"}
        
        resp = requests.post(url, json=payload, headers=headers)
        data = resp.json()
        
        if data.get("error") == 0:
            quota = data.get("data", {}).get("promotion", {})
            print(f"📊 Promotion Quota for User {zalo_user_id}:")
            print(f"   Daily: {quota.get('daily_remain')}/{quota.get('daily_total')}")
            print(f"   Monthly: {quota.get('monthly_remain')}/{quota.get('monthly_total')}")
        else:
            print(f"❌ Could not fetch quota: {data.get('message')} (Error {data.get('error')})")

    def _execute_api_post(
        self, url: str, payload: Dict[str, Any]
    ) -> Tuple[bool, int, str]:
        """Generic POST against any Zalo OA API endpoint.

        Reuses the current ``access_token`` (with whitespace stripped) and
        returns the same ``(success, error_code, message)`` triple as
        ``_execute_zns_call``.
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

            if error_code == 0:
                msg_id: str = data.get("data", {}).get("msg_id", "unknown")
                return True, 0, msg_id

            return False, error_code, message

        except Exception as e:
            logger.error(f"[Zalo Network Error] {e}")
            return False, -999, str(e)

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
            
            # Case 1: Success
            if error_code == 0:
                msg_id = data.get("data", {}).get("msg_id", "unknown")
                return True, 0, msg_id

            # Case 2: Token Expired (-124) or Invalid (-14014 sometimes)
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