import json
import logging
import smtplib
import ssl
import requests
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from email.message import EmailMessage
from email.utils import formataddr

from agentic_tools.channels.activation import NotificationChannel
from main_configs import MarketingConfigs

from agentic_tools.channels.helpers import (
    MessageRenderer,
    PRODUCT_RECOMMENDATION_TEMPLATE
)

logger = logging.getLogger(__name__)

# ============================================================
# 1. Data Logic: Profile Loader
# ============================================================

class SegmentProfileLoader:
    """
    Responsible for connecting to the database and retrieving 
    profile data for a specific segment.
    """
    def __init__(self):
        pass

    def fetch_recipients(self, segment_identifier: str) -> List[Dict[str, Any]]:
        """
        Fetches the list of user profiles (dict) for a given segment.
        Returns an empty list if DB is not connected or segment is empty.
        """


        try:
            # TODO: Implement the actual function in cdp_db_utils.py
            recipients = [{"email": "test@example.com", "firstName": "Test"}]
            
            if not recipients:
                logger.warning(f"[ProfileLoader] No recipients found for segment: {segment_identifier}")
                return []
            
            return recipients

        except Exception as e:
            logger.exception(f"[ProfileLoader] Error fetching recipients for '{segment_identifier}': {e}")
            return []


# ============================================================
# 2. Email Logic: The Channel
# ============================================================

class EmailChannel(NotificationChannel):
    """
    Email channel supporting Brevo, SendGrid, and SMTP.
    Decoupled from database logic.
    """

    def __init__(self):
        # Config setup only - No DB connections here
        self.provider = MarketingConfigs.EMAIL_PROVIDER or "smtp"

        # -------- Brevo Config --------
        self.brevo_api_key = MarketingConfigs.BREVO_API_KEY
        self.brevo_from_email = MarketingConfigs.BREVO_FROM_EMAIL
        self.brevo_from_name = MarketingConfigs.BREVO_FROM_NAME or "Notification"

        # -------- SendGrid Config --------
        self.sendgrid_api_key = MarketingConfigs.SENDGRID_API_KEY
        self.sendgrid_from = MarketingConfigs.SENDGRID_FROM

        # -------- SMTP Config --------
        self.smtp_host = MarketingConfigs.SMTP_HOST or "smtp.gmail.com"
        self.smtp_port = MarketingConfigs.SMTP_PORT or 587
        self.smtp_username = MarketingConfigs.SMTP_USERNAME
        self.smtp_password = MarketingConfigs.SMTP_PASSWORD
        self.smtp_use_tls = MarketingConfigs.SMTP_USE_TLS

    # ---------------------------------------------------------
    # Provider: Brevo
    # ---------------------------------------------------------
    def send_via_brevo_api(self, recipients: List[str], subject: str, html_body: str, timeout: int = 10) -> Dict[str, Any]:
        if not self.brevo_api_key:
            return {"status": "error", "provider": "brevo", "message": "BREVO_API_KEY not set"}

        payload = {
            "sender": {"email": self.brevo_from_email, "name": self.brevo_from_name},
            "to": [{"email": r} for r in recipients],
            "subject": subject,
            "htmlContent": html_body,
        }
        headers = {
            "accept": "application/json",
            "api-key": self.brevo_api_key,
            "content-type": "application/json",
        }

        try:
            resp = requests.post("https://api.brevo.com/v3/smtp/email", json=payload, headers=headers, timeout=timeout)
            if resp.status_code >= 400:
                logger.error(f"Brevo API error {resp.status_code}: {resp.text}")
                return {"status": "error", "provider": "brevo", "message": resp.text}
            
            return {"status": "success", "provider": "brevo", "message_id": resp.json().get("messageId")}
        except Exception as e:
            return {"status": "error", "provider": "brevo", "message": str(e)}

    # ---------------------------------------------------------
    # Provider: SendGrid
    # ---------------------------------------------------------
    def send_via_sendgrid_api(self, recipients: List[str], subject: str, body: str, timeout: int = 8) -> Dict[str, Any]:
        if not self.sendgrid_api_key:
            return {"status": "error", "provider": "sendgrid", "message": "SENDGRID_API_KEY not set"}

        from_email = self.sendgrid_from or self.smtp_username
        payload = {
            "personalizations": [{"to": [{"email": r} for r in recipients], "subject": subject}],
            "from": {"email": from_email},
            "content": [{"type": "text/html", "value": body}], # Changed to text/html for consistency
        }
        headers = {"Authorization": f"Bearer {self.sendgrid_api_key}", "Content-Type": "application/json"}

        try:
            resp = requests.post("https://api.sendgrid.com/v3/mail/send", json=payload, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return {"status": "success", "provider": "sendgrid"}
        except Exception as e:
            return {"status": "error", "provider": "sendgrid", "message": str(e)}

    # ---------------------------------------------------------
    # Provider: SMTP
    # ---------------------------------------------------------
    def send_via_smtp(self, recipients: List[str], subject: str, body: str, timeout: int = 10) -> Dict[str, Any]:
        if not self.smtp_username or not self.smtp_password:
            return {"status": "error", "message": "SMTP credentials missing"}

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["To"] = ", ".join(recipients)
        msg["From"] = formataddr(("Notification", self.smtp_username))
        msg.set_content(body, subtype='html')

        ctx = ssl.create_default_context()
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=timeout) as server:
                server.ehlo()
                if self.smtp_use_tls:
                    server.starttls(context=ctx)
                    server.ehlo()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)
            return {"status": "success", "provider": "smtp"}
        except Exception as e:
            logger.error(f"SMTP Error: {e}")
            return {"status": "error", "provider": "smtp", "message": str(e)}

    # ---------------------------------------------------------
    # Batch Dispatch
    # ---------------------------------------------------------

    _EMAIL_STOCK_SQL = """
        SELECT
            p.profile_id,
            p.primary_email,
            r.product_id    AS ticker,
            r.interest_score
        FROM product_recommendations r
        JOIN cdp_profiles p
            ON  r.profile_id = p.profile_id
            AND r.tenant_id  = p.tenant_id
        WHERE r.tenant_id      = %s
          AND r.product_id     = ANY(%s)
          AND r.interest_score >= %s
          AND p.primary_email  IS NOT NULL
        ORDER BY p.profile_id, r.interest_score DESC
    """

    def dispatch_suggested_stock_batch(
        self,
        conn,
        tenant_uuid: str,
        redis_client,
        today_str: str,
        stock_map: Dict,
    ) -> Dict[str, int]:
        """Send personalised stock pick emails to each eligible user. Returns stats dict."""
        from agentic_tools.channels.helpers import MessageRenderer
        from agentic_tools.channels.templates.email.stock_picks import (
            EMAIL_STOCK_PICKS_SUBJECT,
            EMAIL_STOCK_PICKS_HTML,
        )

        interest_threshold: float = 0.5
        top_tickers = list(stock_map.keys())
        stats: Dict[str, int] = {"eligible": 0, "sent": 0, "skipped": 0, "failed": 0}

        with conn.cursor() as cur:
            cur.execute(self._EMAIL_STOCK_SQL, (tenant_uuid, top_tickers, interest_threshold))
            rows = cur.fetchall()

        # Group all matching stocks per user
        profile_stocks: Dict[str, Dict] = defaultdict(lambda: {"email": None, "stocks": []})
        for r in rows:
            pid, email, ticker = r["profile_id"], r["primary_email"], r["ticker"]
            profile_stocks[pid]["email"] = email
            if ticker in stock_map:
                profile_stocks[pid]["stocks"].append(stock_map[ticker])

        stats["eligible"] = len(profile_stocks)
        logger.info("[Email Suggested] Found %d eligible profiles.", len(profile_stocks))

        renderer = MessageRenderer()

        for profile_id, data in profile_stocks.items():
            email = data["email"]
            stocks = data["stocks"]

            if not email or not stocks:
                stats["skipped"] += 1
                continue

            rl_key = f"leo:email_suggested:{profile_id}:{today_str}"
            if redis_client.get(rl_key):
                stats["skipped"] += 1
                continue

            html_body = renderer.render_email_template(
                EMAIL_STOCK_PICKS_HTML,
                profile={"email": email},
                stocks=stocks,
            )

            res = self.send_via_smtp([email], EMAIL_STOCK_PICKS_SUBJECT, html_body)

            success = res.get("status") == "success"
            delivery_status = "sent" if success else "failed"

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO delivery_log
                        (tenant_id, marketing_event_id, profile_id, channel,
                         delivery_status, provider_response, sent_at)
                    VALUES (%s, %s, %s, 'email_suggested_stock', %s, %s, %s)
                    """,
                    (
                        tenant_uuid,
                        f"email_suggested_{today_str}",
                        profile_id,
                        delivery_status,
                        json.dumps(res),
                        datetime.now(timezone.utc) if success else None,
                    ),
                )
            conn.commit()

            if success:
                redis_client.setex(rl_key, 86400, "1")
                stats["sent"] += 1
            else:
                stats["failed"] += 1
                logger.warning("[Email Suggested] Failed for %s: %s", email, res.get("message"))

        logger.info(
            "[Email Suggested] Done. eligible=%d sent=%d skipped=%d failed=%d",
            stats["eligible"], stats["sent"], stats["skipped"], stats["failed"],
        )
        return stats

    # ---------------------------------------------------------
    # Orchestrator
    # ---------------------------------------------------------
    def send(self, recipient_segment: str, message: str = None, **kwargs: Any) -> Dict[str, Any]:
        """
        1. Loads Profile Data (using SegmentProfileLoader)
        2. Renders Template (Personalization)
        3. Sends Email via configured provider
        """
        logger.info(f"[Email] Starting campaign for segment: {recipient_segment}")

        # --- Step 1: Prepare Logic ---
        subject = kwargs.get("subject") or "Special Offer"
        timeout = kwargs.get("timeout", 10)
        provider = kwargs.get("provider", self.provider).lower()
        
        template_content = message if (message and message.strip()) else PRODUCT_RECOMMENDATION_TEMPLATE

        # --- Step 2: Load Data ---
        # Instantiate the loader here ensures freshness of DB connection per request
        loader = SegmentProfileLoader()
        recipient_objects = loader.fetch_recipients(recipient_segment)

        if not recipient_objects:
            return {"status": "skipped", "reason": "no_recipients_found"}

        # --- Step 3: Iterate and Send ---
        logger.info(f"[Email] Sending to {len(recipient_objects)} recipients via {provider}...")
        
        stats = {"success": 0, "failed": 0}

        for user in recipient_objects:
            email = user.get("email")
            if not email:
                continue

            # Personalize content
            renderer = MessageRenderer()
            personalized_body = renderer.render_email_template(template_content, user)

            # Route to provider
            try:
                if provider == "brevo":
                    res = self.send_via_brevo_api([email], subject, personalized_body, timeout)
                elif provider == "sendgrid":
                    res = self.send_via_sendgrid_api([email], subject, personalized_body, timeout)
                else:
                    res = self.send_via_smtp([email], subject, personalized_body, timeout)

                if res.get("status") == "success":
                    stats["success"] += 1
                else:
                    stats["failed"] += 1
                    logger.warning(f"Failed to send to {email}: {res.get('message')}")

            except Exception as e:
                logger.exception(f"Unexpected error sending to {email}")
                stats["failed"] += 1

        # --- Step 4: Summary ---
        logger.info(f"[Email] Completed. Success: {stats['success']}, Failed: {stats['failed']}")
        
        return {
            "status": "completed",
            "segment": recipient_segment,
            "total_attempted": len(recipient_objects),
            **stats
        }