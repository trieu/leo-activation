import logging
import sys
import os
import json
import psycopg
from typing import Dict, Any, List, Tuple

# --- Imports ---
from data_utils.settings import DatabaseSettings

# REUSE: Import strict logic from the existing worker
try:
    from agentic_tools.interest_score import resolve_ids
except ImportError:
    try:
        from interest_score import resolve_ids
    except ImportError:
        logging.error("CRITICAL: Could not import 'resolve_ids' from interest_score.py")
        sys.exit(1)

logger = logging.getLogger("agentic_tools.nba_engine")

# --- Configuration ---
SCORE_THRESHOLD_HOT = 0.5
SCORE_THRESHOLD_WARM = 0.2
PERSONA_ACTIVE_TRADER = "High-Frequency Traders"

# Context
TARGET_TENANT = os.getenv("TARGET_TENANT", "master")
TARGET_SEGMENT = os.getenv("TARGET_SEGMENT", "Active in last 3 months")

# --- CORE LOGIC (Pure Python) ---
def determine_action(score: float, segment_names: list) -> Tuple[str, str, str]:
    """
    Pure logic function: Decides the Action based on Score + Segments.
    Returns: (Action, Channel, Reason)
    """
    is_active_trader = PERSONA_ACTIVE_TRADER in segment_names

    if score >= SCORE_THRESHOLD_HOT:
        return "STRONG_BUY", "PUSH_NOTIFICATION", f"High Urgency (Score: {score:.2f})"
    
    elif SCORE_THRESHOLD_WARM <= score < SCORE_THRESHOLD_HOT:
        if is_active_trader:
            return "MOMENTUM_ALERT", "IN_APP_BANNER", f"Active Trader Interest (Score: {score:.2f})"
        else:
            return "WATCHLIST_SUGGESTION", "EMAIL_DIGEST", f"Passive Investor Interest (Score: {score:.2f})"
            
    return "WAIT", "NONE", "Score below threshold"

# --- SINGLE LOOKUP (Read-Only for API) ---
def get_next_best_action(conn, tenant_uuid: str, profile_id: str) -> Dict[str, Any]:
    """
    Calculates the NBA on-the-fly for a specific user. 
    Does NOT write to DB (API is Read-Only).
    """
    query = """
        SELECT 
            r.product_id, 
            r.interest_score, 
            p.segments
        FROM product_recommendations r
        JOIN cdp_profiles p ON r.profile_id = p.profile_id 
                           AND r.tenant_id = p.tenant_id
        WHERE r.tenant_id = %s 
          AND r.profile_id = %s
          AND r.interest_score > %s
        ORDER BY r.interest_score DESC
        LIMIT 1;
    """
    with conn.cursor() as cur:
        cur.execute(query, (str(tenant_uuid), profile_id, SCORE_THRESHOLD_WARM))
        row = cur.fetchone()

        if not row:
            return {
                "profile_id": profile_id,
                "ticker": None,
                "action": "WAIT",
                "channel": "NONE",
                "confidence_score": 0.0,
                "reason": "No interest scores above threshold."
            }

        if isinstance(row, dict):
            ticker = row['product_id']
            score = float(row['interest_score'])
            raw_segments = row['segments']
        else:
            ticker = row[0]
            score = float(row[1])
            raw_segments = row[2]

        segment_names = []
        if raw_segments:
            data = raw_segments if isinstance(raw_segments, list) else json.loads(raw_segments)
            segment_names = [s.get('name') for s in data if isinstance(s, dict)]

        action, channel, reason = determine_action(score, segment_names)

        return {
            "profile_id": profile_id,
            "ticker": ticker,
            "action": action,
            "channel": channel,
            "confidence_score": score,
            "reason": reason
        }

# --- BATCH PROCESSOR (Writes Action to DB) ---
def run_batch_nba_update(settings: DatabaseSettings):
    """
    1. Scans Tenant for top prospects.
    2. Calculates Next Best Action.
    3. UPDATES the 'next_best_action' column in 'product_recommendations'.
    """
    conn = settings.get_pg_connection()
    updated_count = 0
    
    try:
        # 1. Resolve Context
        tenant_uuid, _ = resolve_ids(conn, TARGET_TENANT, TARGET_SEGMENT)
        
        logger.info(f"🚀 Starting Batch NBA Update for Tenant: {TARGET_TENANT}")

        # 2. Bulk Fetch Query (Top 1 Product Per User)
        # CRITICAL: We fetch the composite PK columns (journey_map_id, etc.) 
        # to ensure we update the EXACT row that triggered the score.
        batch_query = """
            SELECT DISTINCT ON (r.profile_id)
                r.profile_id,
                r.product_id, 
                r.journey_map_id,
                r.journey_stage_id,
                r.recommendation_model,
                r.interest_score, 
                p.segments
            FROM product_recommendations r
            JOIN cdp_profiles p ON r.profile_id = p.profile_id 
                               AND r.tenant_id = p.tenant_id
            WHERE r.tenant_id = %s 
              AND r.interest_score >= %s
            ORDER BY r.profile_id, r.interest_score DESC;
        """

        # 3. Prepared Update Statement
        update_sql = """
            UPDATE product_recommendations
            SET next_best_action = %s,
                updated_at = NOW()
            WHERE tenant_id = %s
              AND profile_id = %s
              AND product_id = %s
              AND journey_map_id = %s
              AND journey_stage_id = %s
              AND recommendation_model = %s;
        """

        with conn.cursor() as cur:
            # A. Fetch Candidates
            cur.execute(batch_query, (str(tenant_uuid), SCORE_THRESHOLD_WARM))
            rows = cur.fetchall() # Fetch all to iterate safely while updating
            
            logger.info(f"🔍 Found {len(rows)} candidates for NBA assignment.")

            # B. Iterate & Update
            for row in rows:
                # Unpack (Handle DictRow vs Tuple)
                if isinstance(row, dict):
                    p_id = row['profile_id']
                    prod_id = row['product_id']
                    j_map = row['journey_map_id']
                    j_stage = row['journey_stage_id']
                    rec_model = row['recommendation_model']
                    score = float(row['interest_score'])
                    raw_segments = row['segments']
                else:
                    p_id, prod_id, j_map, j_stage, rec_model, score, raw_segments = row

                # Parse Segments
                segment_names = []
                if raw_segments:
                    data = raw_segments if isinstance(raw_segments, list) else json.loads(raw_segments)
                    segment_names = [s.get('name') for s in data if isinstance(s, dict)]

                # Determine Action
                action, _, _ = determine_action(score, segment_names)
                
                # C. Execute Update
                if action != "WAIT":
                    cur.execute(update_sql, (
                        action,         # SET next_best_action
                        str(tenant_uuid),
                        p_id,
                        prod_id,
                        j_map,
                        j_stage,
                        rec_model
                    ))
                    updated_count += 1
            
            conn.commit()
        
        logger.info(f"✅ Batch Update Complete. Updated {updated_count} rows with Next Best Action.")

    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Batch NBA Update Failed: {e}")
    finally:
        conn.close()

# --- ENTRY POINT ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    settings = DatabaseSettings()
    
    # CLI Mode: Single Profile Lookup (Read-Only Test)
    if len(sys.argv) > 1:
        target_profile_id = sys.argv[1]
        conn = settings.get_pg_connection()
        try:
            tenant_uuid, _ = resolve_ids(conn, TARGET_TENANT, TARGET_SEGMENT)
            result = get_next_best_action(conn, tenant_uuid, target_profile_id)
            print(json.dumps(result, indent=2))
        finally:
            conn.close()
    else:
        # Batch Mode: Update Database
        run_batch_nba_update(settings)