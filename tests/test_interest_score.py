import logging
import sys
from typing import Dict, Any, List

import datetime
from psycopg.rows import dict_row
import psycopg
import os

# 1. Setup Path to find your modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_models import dbo_tenant
from data_utils.settings import DatabaseSettings

logger = logging.getLogger("agentic_tools.data_enrichment.interest_score")

HALF_LIFE_DAYS = 7.0
SCORE_THRESHOLD = 0.01 # Delete if score drops below this

# CONSTANT: The "Half-Way" Point.
# At 100 raw points, the user has a 0.5 (50%) interest score.
# At 1000 raw points, the user has a 0.9 (90%) interest score.
SCORING_K_FACTOR = 100.0

# --- 4. POSTGRES FETCHING LOGIC ---
def get_batch_scoring_data(settings: DatabaseSettings, tenant_id: str, segment_id: str, start_updated_at: str, end_updated_at: str) -> List[Dict[str, Any]]:
    """
    Fetches events and resolves them to the Profile _key (profile_id).
    """
    db = settings.get_pg_connection()
    if not db:
        return []
    
    try:
      
        # B. TODO update Query: cdp_profiles.segments @> %s::jsonb and updated_at BETWEEN %s AND %s 
        scoring_query = """

        """
        
        results = []
        
       
        return results

    except Exception as e:
        logger.error(f"❌ ArangoDB Query failed: {e}")
        return []

# --- 5. POSTGRES UPSERT LOGIC ---
def run_batch_scoring_job(settings: DatabaseSettings, tenant_id: str, segment_id: str,  start_time: str, end_time: str):
    """
    Orchestrates the fetch from Arango and the Upsert to Postgres.
    """
    
    # A. Fetch Data
    batch_data = get_batch_scoring_data(settings, tenant_id, segment_id, start_time, end_time)
    
    if not batch_data:
        logger.info("✅ Job finished: No relevant events found in this window.")
        return

    # B. Process Upserts
    conn = settings.get_pg_connection()
    try:
        with conn.cursor() as cur:
            for entry in batch_data:
                profile_id = entry['profile_id']
                product_id = entry['product_id']
                product_type = entry['product_type']
                total_event_score = entry['total_event_score'] # Raw points (e.g. 5.0)
                
                last_event_time = datetime.datetime.fromisoformat(entry['last_seen'].replace("Z", "+00:00"))

                # 1. Fetch Existing RAW Score
                cur.execute("SELECT raw_score, last_interaction_at FROM product_recommendations WHERE profile_id = %s AND product_id = %s AND tenant_id = %s AND product_type = %s", (profile_id, product_id, tenant_id, product_type))
                record = cur.fetchone()
                
                final_raw_score = 0.0
                
                if record:
                    # UPDATE path
                    current_raw = record['raw_score']
                    prev_interaction = record['last_interaction_at']
                    
                    if prev_interaction.tzinfo is None:
                        prev_interaction = prev_interaction.replace(tzinfo=datetime.timezone.utc)
                    
                    # 2. Apply Time Decay to RAW Score
                    time_diff = last_event_time - prev_interaction
                    days_elapsed = max(time_diff.total_seconds() / 86400.0, 0)
                    decay_factor = 0.5 ** (days_elapsed / HALF_LIFE_DAYS)
                    
                    decayed_raw = current_raw * decay_factor
                    
                    # 3. Add New Points
                    final_raw_score = decayed_raw + total_event_score
                else:
                    # INSERT path
                    final_raw_score = total_event_score

                # 4. Calculate Normalized Interest Score (0 to 1)
                # Formula: Raw / (Raw + K)
                final_interest_score = final_raw_score / (final_raw_score + SCORING_K_FACTOR)
                
                # 5. Upsert Both Scores
                if record:
                    
                    cur.execute("""
                        UPDATE product_recommendations 
                        SET raw_score = %s, interest_score = %s, last_interaction_at = %s, updated_at = NOW()
                        WHERE profile_id = %s AND product_id = %s AND tenant_id = %s AND product_type = %s
                    """, (final_raw_score, final_interest_score, last_event_time, profile_id, product_id, tenant_id, product_type))
                else:
                    cur.execute("""
                        INSERT INTO product_recommendations 
                        (profile_id, product_id, raw_score, interest_score, last_interaction_at, tenant_id, product_type)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (profile_id, product_id, final_raw_score, final_interest_score, last_event_time, tenant_id, product_type))
            
            # Commit transaction for the whole batch
            conn.commit()
            logger.info("✅ Batch Upsert Complete.")
            
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Batch Job Failed: {e}")
    finally:
        conn.close()



def run_garbage_collection(settings: DatabaseSettings):
    """
    Deletes rows where the calculated time-decayed score is below the threshold.
    """
    conn = settings.get_pg_connection()
    try:
        # Math: If CurrentScore < Threshold, Delete.
        # We calculate the decay directly in SQL to be efficient.
        # 604800.0 is the number of seconds in 7 days (Half-Life reference)
        
        query = """
            DELETE FROM product_recommendations
            WHERE interest_score < %s;
        """
        
        with conn.cursor() as cur:
            cur.execute(query, (SCORE_THRESHOLD,))
            deleted_count = cur.rowcount

        conn.commit()
            
        logger.info(f"🧹 Garbage Collection: Removed {deleted_count} rows (Score < {SCORE_THRESHOLD}).")
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Garbage collection failed: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # 1. Initialize Settings
    settings = DatabaseSettings()
    tenant_id = dbo_tenant.get_default_tenant_id(settings=settings)
    
    print("--- 1. Running Garbage Collection ---")
    run_garbage_collection(settings)
    
    # 3. Calculate "Previous Hour" Window
    # Logic: If now is 10:45, window is 09:00:00 -> 10:00:00
    now = datetime.datetime.now(datetime.timezone.utc)
    window_end = now.replace(minute=0, second=0, microsecond=0)
    window_start = window_end - datetime.timedelta(hours=1)
    
    start_str = window_start.isoformat()
    end_str = window_end.isoformat()
    
    logger.info(f"🚀 Starting Batch Job for Window: {start_str} to {end_str}")
    
    # 4. Run Job
    run_batch_scoring_job(settings, tenant_id, "all-profiles", start_str, end_str)