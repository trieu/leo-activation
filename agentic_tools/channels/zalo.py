
import json
import logging
import re
import time
import random
import requests
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from agentic_tools.channels.activation import NotificationChannel
from agentic_tools.channels.templates.zalo.models import ZaloMessageTemplate, ZaloSuggestedStockTemplate, StockRecommendation

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
    # CONNECTOR_KEY = "leo-zalo-connector"
    # COLLECTION_NAME = "cdp_agent"
    CONNECTOR_KEY = "leo_zalo_connector"
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

    def send_text_with_image(
        self,
        zalo_user_id: str,
        template: ZaloMessageTemplate,
        text_override: Optional[str] = None,
        image_override: Optional[str] = None,
    ) -> Tuple[bool, int, str]:
        """
        Sends a template-driven message (text + image + optional buttons) via the CS endpoint.
        Pass text_override or image_override to personalise a template at send time.
        MUST use the 'media' template_type to avoid Zalo's -233 error.
        """
        url = "https://openapi.zalo.me/v3.0/oa/message/cs"
        text = text_override or template.text
        image = image_override or template.image_url

        payload = {
            "recipient": {"user_id": zalo_user_id},
            "message": {
                "text": text,
                "attachment": {
                    "type": "template",
                    "payload": {
                        "template_type": "media",
                        "elements": [{"media_type": "image", "url": image}],
                    },
                },
            },
        }

        if template.buttons:
            payload["message"]["attachment"]["payload"]["buttons"] = [
                b.model_dump() for b in template.buttons
            ]

        return self._execute_api_post(url, payload)

    def send_suggested_stock(
        self,
        zalo_user_id: str,
        template: ZaloSuggestedStockTemplate,
        stocks: Optional[List[StockRecommendation]] = None,
    ) -> Tuple[bool, int, str]:
        """
        Fetches top stock recommendations from the analysis API and sends them
        as a formatted Zalo CS message with image and interactive buttons.

        If `stocks` is provided, skips the API fetch and uses the given list directly.
        """
        if stocks is None:
            try:
                resp = requests.get(
                    "https://news-analysis.innotech.vn/api/v1/stock/recommend_stock",
                    timeout=10,
                )
                data = resp.json()
                raw = data.get("recommendations", [])
                stocks = [StockRecommendation(**r) for r in raw]
            except Exception as e:
                logger.error(f"[Zalo] Failed to fetch stock recommendations: {e}")
                return False, -999, str(e)

        if not stocks:
            return False, -998, "No stock recommendations available."

        s = stocks[0]
        lines = [
            f"📊 Cổ phiếu tiềm năng hôm nay: {s.symbol}",
            f"Sàn: {s.exchange} | Ngành: {s.industry} | Score: {s.score:.1f}\n",
            "📋 Lý do phân tích:",
        ]
        for reason in s.reasons:
            lines.append(f"  - {reason}")

        lines.append(f"\n👉 Xem chi tiết tại: {template.view_url}")
        text = "\n".join(lines)

        url = "https://openapi.zalo.me/v3.0/oa/message/cs"
        payload = {
            "recipient": {"user_id": zalo_user_id},
            "message": {
                "text": text,
                "attachment": {
                    "type": "template",
                    "payload": {
                        "template_type": "media",
                        "elements": [{"media_type": "image", "url": template.image_url}],
                    },
                },
            },
        }

        if template.buttons:
            payload["message"]["attachment"]["payload"]["buttons"] = [
                b.model_dump() for b in template.buttons
            ]

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
        
    def send(self, recipient_segment: str, message: str, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError("Use send_text_with_image() for OA messaging.")


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

            # 🚨 THE SAFETY NET: Catch Expired or Invalid Token
            # -216: token expired, -124: token invalid/wrong
            if error_code in (-216, -124):
                logger.warning(f"[Zalo API] Caught {error_code} Invalid/Expired Token. Triggering auto-refresh...")
                
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
        logger.info("[Zalo Refresh] === START TOKEN REFRESH ===")

        # 1. CRITICAL: Fetch the latest Refresh Token from DB right now
        logger.debug("[Zalo Refresh] Step 1: Loading latest tokens from DB...")
        self._load_tokens_from_db()

        if not self.refresh_token:
            logger.error("[Zalo Refresh] ABORT: No Refresh Token available (DB & Config empty).")
            return False

        logger.info(
            f"[Zalo Refresh] Step 2: Calling OAuth endpoint={self.oauth_url}, "
            f"app_id={self.app_id}, "
            f"secret_key={'...'+self.secret_key[-6:] if self.secret_key else 'MISSING'}, "
            f"refresh_token_length={len(self.refresh_token)}, "
            f"refresh_token=...{self.refresh_token[-8:]}, "
            f"refresh_token_first8={self.refresh_token[:8]}..."
        )
        headers = {"secret_key": self.secret_key}
        payload = {
            "refresh_token": self.refresh_token,
            "app_id": self.app_id,
            "grant_type": "refresh_token"
        }

        try:
            resp = requests.post(self.oauth_url, headers=headers, data=payload, timeout=15)
            data = resp.json()
            logger.info(f"[Zalo Refresh] OAuth response status={resp.status_code}, body={data}")

            if "access_token" in data:
                new_at = data["access_token"]
                new_rt = data["refresh_token"]
                logger.info(f"[Zalo Refresh] Step 3: OAuth SUCCESS. new_access_token=...{new_at[-8:]}, new_refresh_token=...{new_rt[-8:]}")

                # Update Memory
                self.access_token = new_at
                self.refresh_token = new_rt

                # Update Database
                logger.debug("[Zalo Refresh] Step 4: Saving new tokens to DB...")
                self._save_tokens_to_db(new_at, new_rt)
                logger.info("[Zalo Refresh] === REFRESH COMPLETE (SUCCESS) ===")
                return True
            else:
                logger.error(f"[Zalo Refresh] OAuth FAILED. error={data.get('error')}, reason={data.get('error_reason')}, description={data.get('error_description')}, full_response={data}")
                return False
        except Exception as e:
            logger.error(f"[Zalo Refresh] EXCEPTION during OAuth call: {type(e).__name__}: {e}")
            return False


    def _load_tokens_from_db(self):
        """
        Fetches the latest tokens from 'cdp_agent' collection.
        """
        if not self.db:
            logger.warning("[Zalo Load] No DB client. Skipping DB token load.")
            return

        logger.debug(f"[Zalo Load] Fetching _key='{self.CONNECTOR_KEY}' from '{self.COLLECTION_NAME}'...")
        try:
            doc = self.db.collection(self.COLLECTION_NAME).get(self.CONNECTOR_KEY)
            if doc:
                cfg = doc.get("configs", {})
                logger.info(f"[Zalo Load] DB configs keys: {list(cfg.keys())}")
                loaded_at = cfg.get("zalo_oa_token")
                loaded_rt = cfg.get("zalo_refresh_token")
                logger.info(
                    f"[Zalo Load] Tokens loaded from DB. "
                    f"access_token={'...'+loaded_at[-8:] if loaded_at else 'MISSING'}, "
                    f"refresh_token={'...'+loaded_rt[-8:] if loaded_rt else 'MISSING'}, "
                    f"refresh_token_length={len(loaded_rt) if loaded_rt else 0}, "
                    f"refresh_token_type={type(loaded_rt).__name__}"
                )
                self.access_token = loaded_at or self.access_token
                self.refresh_token = loaded_rt or self.refresh_token
            else:
                logger.warning(f"[Zalo Load] No document found with _key='{self.CONNECTOR_KEY}'. Using static configs.")
        except Exception as e:
            logger.error(f"[Zalo Load] DB read FAILED: {type(e).__name__}: {e}")


    def _save_tokens_to_db(self, new_access_token: str, new_refresh_token: str):
        """
        Persists the NEW tokens to 'cdp_agent'.
        CRITICAL: Zalo Refresh Tokens are single-use. We must save the new one.
        """
        if not self.db:
            logger.warning("[Zalo Save] No DB client. Tokens were NOT persisted!")
            return

        logger.debug(f"[Zalo Save] Saving tokens to _key='{self.CONNECTOR_KEY}'. access=...{new_access_token[-8:]}, refresh=...{new_refresh_token[-8:]}")
        try:
            collection = self.db.collection(self.COLLECTION_NAME)
            doc = collection.get(self.CONNECTOR_KEY)
            if not doc:
                logger.error(f"[Zalo Save] CRITICAL: No document with _key='{self.CONNECTOR_KEY}'. Tokens were NOT saved!")
                return

            configs = doc.get("configs", {})
            old_at = configs.get("zalo_oa_token", "")
            old_rt = configs.get("zalo_refresh_token", "")
            logger.debug(
                f"[Zalo Save] Overwriting old tokens. "
                f"old_access=...{old_at[-8:] if old_at else 'EMPTY'}, "
                f"old_refresh=...{old_rt[-8:] if old_rt else 'EMPTY'}"
            )

            configs["zalo_oa_token"] = new_access_token
            configs["zalo_refresh_token"] = new_refresh_token
            collection.update({"_key": self.CONNECTOR_KEY, "configs": configs, "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})

            # Verify the write by reading back
            verify_doc = collection.get(self.CONNECTOR_KEY)
            verify_cfg = verify_doc.get("configs", {}) if verify_doc else {}
            saved_at = verify_cfg.get("zalo_oa_token", "")
            saved_rt = verify_cfg.get("zalo_refresh_token", "")
            if saved_at == new_access_token and saved_rt == new_refresh_token:
                logger.info(f"[Zalo Save] VERIFIED: Tokens saved and confirmed in DB. access=...{saved_at[-8:]}, refresh=...{saved_rt[-8:]}")
            else:
                logger.error(f"[Zalo Save] MISMATCH: Write succeeded but read-back differs! expected_access=...{new_access_token[-8:]}, got=...{saved_at[-8:] if saved_at else 'EMPTY'}")
        except Exception as e:
            logger.error(f"[Zalo Save] CRITICAL: DB write FAILED: {type(e).__name__}: {e}. Next run will fail!")

    
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

    # ==========================================
    # BATCH DISPATCH METHODS
    # ==========================================

    _PROMO_ELIGIBILITY_SQL = """
        SELECT DISTINCT ON (p.profile_id)
            p.profile_id,
            p.media_channels,
            r.product_id  AS ticker,
            r.interest_score
        FROM product_recommendations r
        JOIN cdp_profiles p
            ON  r.profile_id = p.profile_id
            AND r.tenant_id  = p.tenant_id
        WHERE r.tenant_id = %s
          AND r.interest_score > %s
          AND EXISTS (
                SELECT 1 FROM jsonb_array_elements_text(p.media_channels) AS ch
                WHERE ch LIKE 'zalo_user_id:%%'
              )
          AND (p.event_statistics ->> %s)::int > %s
        ORDER BY p.profile_id, r.interest_score DESC
    """

    _SUGGESTED_STOCK_SQL = """
        SELECT DISTINCT ON (p.profile_id)
            p.profile_id,
            p.media_channels,
            r.product_id  AS ticker,
            r.interest_score
        FROM product_recommendations r
        JOIN cdp_profiles p
            ON  r.profile_id = p.profile_id
            AND r.tenant_id  = p.tenant_id
        WHERE r.tenant_id      = %s
          AND r.product_id     = ANY(%s)
          AND r.interest_score >= %s
          AND EXISTS (
                SELECT 1 FROM jsonb_array_elements_text(p.media_channels) AS ch
                WHERE ch LIKE 'zalo_user_id:%%'
              )
        ORDER BY p.profile_id, r.interest_score DESC
    """

    def dispatch_promo_batch(
        self,
        conn,
        tenant_uuid: str,
        redis_client,
        today_str: str,
    ) -> Dict[str, int]:
        """Send Zalo promotional messages to all eligible users. Returns stats dict."""
        import os

        interest_threshold: float = MarketingConfigs.ZALO_PROMO_INTEREST_THRESHOLD
        event_count_threshold: int = MarketingConfigs.ZALO_PROMO_EVENT_COUNT_THRESHOLD
        event_key_pattern: str = os.getenv("ZALO_PROMO_EVENT_KEY_PATTERN", "id_default_journey-page-view")
        stats: Dict[str, int] = {"eligible": 0, "sent": 0, "skipped": 0, "failed": 0}

        with conn.cursor() as cur:
            cur.execute(
                self._PROMO_ELIGIBILITY_SQL,
                (tenant_uuid, interest_threshold, event_key_pattern, event_count_threshold),
            )
            rows = [
                {"profile_id": r[0], "media_channels": r[1], "ticker": r[2], "interest_score": float(r[3])}
                for r in cur.fetchall()
            ]

        stats["eligible"] = len(rows)
        logger.info("[Zalo Promo] Found %d eligible users.", len(rows))

        for row in rows:
            profile_id: str = row["profile_id"]
            zalo_uid = extract_zalo_user_id(row["media_channels"])
            if not zalo_uid:
                stats["skipped"] += 1
                continue

            rl_key = f"leo:zalo_promo:{profile_id}:{today_str}"
            if redis_client.get(rl_key):
                stats["skipped"] += 1
                continue

            ticker: str = row["ticker"]
            score: float = row["interest_score"]
            template_data = {
                "title": f"{ticker} — Cập nhật mới",
                "subtitle": f"Interest score: {score:.2f}",
                "image_url": "",
                "url": "",
            }

            success, error_code, msg = self.send_promotional_message(
                zalo_uid, MarketingConfigs.ZALO_ZNS_TEMPLATE_ID, template_data
            )

            delivery_status = "sent" if success else "failed"
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO delivery_log
                        (tenant_id, marketing_event_id, profile_id, channel,
                         delivery_status, provider_response, sent_at)
                    VALUES (%s, %s, %s, 'zalo_promo', %s, %s, %s)
                    """,
                    (
                        tenant_uuid,
                        f"zalo_promo_{ticker}_{today_str}",
                        profile_id,
                        delivery_status,
                        json.dumps({"error_code": error_code, "message": msg}),
                        datetime.now(timezone.utc) if success else None,
                    ),
                )
            conn.commit()

            if success:
                redis_client.setex(rl_key, 86400, "1")
                stats["sent"] += 1
            else:
                stats["failed"] += 1
                logger.warning("[Zalo Promo] Failed for %s (ticker=%s): %d — %s", profile_id, ticker, error_code, msg)

        logger.info(
            "[Zalo Promo] Done. eligible=%d sent=%d skipped=%d failed=%d",
            stats["eligible"], stats["sent"], stats["skipped"], stats["failed"],
        )
        return stats

    def dispatch_suggested_stock_batch(
        self,
        conn,
        tenant_uuid: str,
        redis_client,
        today_str: str,
        stock_map: Dict,
    ) -> Dict[str, int]:
        """Send best-match stock recommendation to each eligible Zalo user. Returns stats dict."""
        from agentic_tools.channels.templates.zalo.suggested_stock import SUGGESTED_STOCK_TEMPLATE

        interest_threshold: float = 0.5
        top_tickers = list(stock_map.keys())
        stats: Dict[str, int] = {"eligible": 0, "sent": 0, "skipped": 0, "failed": 0}

        with conn.cursor() as cur:
            cur.execute(self._SUGGESTED_STOCK_SQL, (tenant_uuid, top_tickers, interest_threshold))
            rows = [
                {"profile_id": r[0], "media_channels": r[1], "ticker": r[2], "interest_score": float(r[3])}
                for r in cur.fetchall()
            ]

        stats["eligible"] = len(rows)
        logger.info("[Zalo Suggested] Found %d eligible profiles.", len(rows))

        for row in rows:
            profile_id: str = row["profile_id"]
            zalo_uid = extract_zalo_user_id(row["media_channels"])
            if not zalo_uid:
                stats["skipped"] += 1
                continue

            rl_key = f"leo:zalo_suggested:{profile_id}:{today_str}"
            if redis_client.get(rl_key):
                stats["skipped"] += 1
                continue

            matched_stock = stock_map.get(row["ticker"])
            stocks_to_send = [matched_stock] if matched_stock else [next(iter(stock_map.values()))]

            success, error_code, msg = self.send_suggested_stock(
                zalo_user_id=zalo_uid,
                template=SUGGESTED_STOCK_TEMPLATE,
                stocks=stocks_to_send,
            )

            delivery_status = "sent" if success else "failed"
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO delivery_log
                        (tenant_id, marketing_event_id, profile_id, channel,
                         delivery_status, provider_response, sent_at)
                    VALUES (%s, %s, %s, 'zalo_suggested_stock', %s, %s, %s)
                    """,
                    (
                        tenant_uuid,
                        f"zalo_suggested_{row['ticker']}_{today_str}",
                        profile_id,
                        delivery_status,
                        json.dumps({"error_code": error_code, "message": msg}),
                        datetime.now(timezone.utc) if success else None,
                    ),
                )
            conn.commit()

            if success:
                redis_client.setex(rl_key, 86400, "1")
                stats["sent"] += 1
            else:
                stats["failed"] += 1
                logger.warning(
                    "[Zalo Suggested] Failed for %s (ticker=%s): %d — %s",
                    profile_id, row["ticker"], error_code, msg,
                )

        logger.info(
            "[Zalo Suggested] Done. eligible=%d sent=%d skipped=%d failed=%d",
            stats["eligible"], stats["sent"], stats["skipped"], stats["failed"],
        )
        return stats

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