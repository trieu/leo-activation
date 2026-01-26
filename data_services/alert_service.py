import uuid
import logging
from decimal import Decimal
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import select
from jinja2 import Template

# Imports based on your project structure
from data_models.dbo_alert import AlertRule, MarketSnapshot, AlertStatusEnum
from data_models.dbo_execution import DeliveryLog, MessageTemplate
from data_models.dbo_cdp import CdpProfile 

logger = logging.getLogger(__name__)

def evaluate_condition(current_price: Decimal, condition: dict) -> bool:
    """Helper to evaluate JSONB logic conditions (e.g. {'operator': '>', 'value': 150})"""
    if current_price is None or not condition:
        return False
        
    operator = condition.get("operator")
    # robust conversion to Decimal
    try:
        target_value = Decimal(str(condition.get("value", 0)))
    except:
        return False
    
    if operator == ">":
        return current_price > target_value
    elif operator == ">=":
        return current_price >= target_value
    elif operator == "<":
        return current_price < target_value
    elif operator == "<=":
        return current_price <= target_value
    elif operator == "==":
        return current_price == target_value
    
    return False

def render_message(template_str: str, context: dict) -> str:
    """Renders a Jinja2 string with the provided context."""
    if not template_str:
        return ""
    try:
        return Template(template_str).render(**context)
    except Exception as e:
        logger.error(f"Template rendering failed: {e}")
        return template_str

def do_alerting_all_matched_profile(session: Session, tenant_id: uuid.UUID):
    """
    Core Logic:
    1. Scan active AlertRules for the given tenant.
    2. Join with MarketSnapshot (live prices) and CdpProfile (user contact info).
    3. If condition met, fetch MessageTemplate and generating DeliveryLog.
    """
    logger.info(f"Starting alert check for tenant {tenant_id}")

    # 1. Query: Join Rules -> Market Data -> Profile
    # Fetch only ACTIVE rules for this tenant
    stmt = (
        select(AlertRule, MarketSnapshot, CdpProfile)
        .join(MarketSnapshot, AlertRule.symbol == MarketSnapshot.symbol)
        .join(CdpProfile, AlertRule.profile_id == CdpProfile.profile_id)
        .where(
            AlertRule.tenant_id == tenant_id,
            AlertRule.status == AlertStatusEnum.ACTIVE
        )
    )
    
    results = session.execute(stmt).all()

    # 2. Pre-fetch Templates to avoid N+1 queries
    # We grab the latest version of 'price_alert' templates for email/web_push
    templates_stmt = (
        select(MessageTemplate)
        .where(
            MessageTemplate.tenant_id == tenant_id,
            MessageTemplate.status == 'approved',
            MessageTemplate.template_name.in_(['price_alert_email', 'price_alert_push'])
        )
    )
    templates = session.execute(templates_stmt).scalars().all()
    
    # Map templates by channel for easy lookup
    template_map = {t.channel: t for t in templates}
    
    generated_alerts = []

    # 3. Process Rules
    for rule, market, profile in results:
        
        # Check if rule logic is met
        is_triggered = evaluate_condition(market.price, rule.condition_logic)
        
        if is_triggered:
            logger.info(f"Rule {rule.rule_id} triggered for {profile.primary_email}")
            
            # Prepare Context for Template
            context = {
                "first_name": profile.first_name,
                "symbol": rule.symbol,
                "current_price": f"{market.price:,.2f}",
                "target_price": rule.condition_logic.get("value"),
                "alert_id": rule.rule_id
            }

            # --- PROCESS EMAIL ---
            # Check if user has EMAIL channel enabled and if we have a template
            if profile.media_channels and "EMAIL" in profile.media_channels and "email" in template_map:
                tmpl = template_map["email"]
                
                subject = render_message(tmpl.subject_template, context)
                # body = render_message(tmpl.body_template, context) # If you need body later
                
                # Create Log (Simulating Send)
                log = DeliveryLog(
                    tenant_id=tenant_id,
                    event_id=f"ALERT_{rule.rule_id}_{datetime.now().timestamp()}",
                    profile_id=profile.profile_id,
                    channel="email",
                    delivery_status="SENT", # In real app, pending -> worker -> sent
                    provider_response={"mock_id": "aws_ses_123"},
                    sent_at=datetime.now()
                )
                session.add(log)
                generated_alerts.append(f"EMAIL sent to {profile.primary_email}: {subject}")

            # --- PROCESS WEB PUSH ---
            if profile.media_channels and "WEB_PUSH" in profile.media_channels and "web_push" in template_map:
                tmpl = template_map["web_push"]
                
                # title = render_message(tmpl.subject_template, context)
                body = render_message(tmpl.body_template, context)
                
                # Create Log
                log = DeliveryLog(
                    tenant_id=tenant_id,
                    event_id=f"ALERT_{rule.rule_id}_{datetime.now().timestamp()}",
                    profile_id=profile.profile_id,
                    channel="web_push",
                    delivery_status="SENT",
                    provider_response={"mock_id": "firebase_fcm_456"},
                    sent_at=datetime.now()
                )
                session.add(log)
                generated_alerts.append(f"PUSH sent to {profile.profile_id}: {body}")
    
    # Note: We do NOT commit here. The Context Manager in the caller will commit.
    return generated_alerts