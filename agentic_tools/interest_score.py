import logging
from typing import Dict, Any, List
import datetime
import psycopg
from psycopg.rows import dict_row
import os
import json

from data_utils.settings import DatabaseSettings

logger = logging.getLogger("agentic_tools.data_enrichment")

# --- Configuration ---
HALF_LIFE_DAYS = 7.0
SCORE_THRESHOLD = 0.01 
SCORING_K_FACTOR = 100.0

# Get Targets from Environment
TARGET_TENANT = os.getenv("TARGET_TENANT", "master")
TARGET_SEGMENT = os.getenv("TARGET_SEGMENT", "Active in last 3 months")

DUMMY_JOURNEY_MAP_ID = "default_journey_map"
DUMMY_JOURNEY_STAGE_ID = "default_stage"
DUMMY_REC_MODEL = "default_model"

# --- 1. ID RESOLUTION (PostgreSQL Source of Truth) ---
def resolve_ids(conn, tenant_name: str, segment_name: str) -> tuple:
    """
    Resolves human-readable names to UUIDs.
    Since 'cdp_segments' table is missing, we extract the segment ID 
    from the 'segments' JSONB column in 'cdp_profiles'.
    """
    with conn.cursor() as cur:
        # A. Resolve Tenant Name to UUID
        cur.execute("SELECT tenant_id FROM tenant WHERE tenant_name = %s", (tenant_name,))
        t_row = cur.fetchone()
        if not t_row:
            raise ValueError(f"Tenant '{tenant_name}' not found in Postgres.")
        t_uuid = t_row['tenant_id'] if isinstance(t_row, dict) else t_row[0]

        # B. Resolve Segment Name to UUID (via cdp_profiles scan)
        # We look for ANY profile in this tenant that has the target segment name.
        # Query: Find one row where segments array contains an object with {"name": segment_name}
        query = """
            SELECT segments 
            FROM cdp_profiles 
            WHERE tenant_id = %s 
            AND segments @> %s::jsonb 
            LIMIT 1
        """
        # Create the JSON search payload
        search_json = json.dumps([{"name": segment_name}])
        
        cur.execute(query, (t_uuid, search_json))
        row = cur.fetchone()
        
        if not row:
            raise ValueError(f"Segment '{segment_name}' not found in any profile for tenant '{tenant_name}'.")
        
        # Extract the JSON list from the row
        segments_data = row['segments'] if isinstance(row, dict) else row[0]
        
        # Iterate through the JSON array to find the exact ID for the name
        s_uuid = None
        if isinstance(segments_data, str):
            segments_data = json.loads(segments_data)
            
        for seg in segments_data:
            if seg.get('name') == segment_name:
                s_uuid = seg.get('id')
                break
        
        if not s_uuid:
             raise ValueError(f"Could not parse ID for segment '{segment_name}' from profile data.")

        logger.info(f"✅ Resolved IDs - Tenant: {t_uuid}, Segment: {s_uuid}")
        return t_uuid, s_uuid
    

def get_batch_scoring_data(settings: DatabaseSettings, start_time_iso: str, end_time_iso: str, segment_uuid: str) -> List[Dict[str, Any]]:
    """
    Fetches events from ArangoDB.
    CRITICAL CHANGE: No tenant_id in Arango. We filter purely by the resolved Segment UUID.
    """
    db = settings.get_arango_db()
    if not db:
        return []
    
    try:
        # Main Query: Event -> Profile -> Metric
        scoring_query = """
        FOR event IN cdp_trackingevent
            FILTER event.createdAt >= @start_time
            FILTER event.createdAt < @end_time
            
            // Validate Instrument ID (Product ID)
            FILTER HAS(event.eventData, 'instrument_id') 
            FILTER event.eventData.instrument_id != null 
            FILTER event.eventData.instrument_id != ""

            FOR profile IN cdp_profile
                // Link Event to Profile
                FILTER profile.fingerprintId == event.fingerprintId
                
                // SEGMENT FILTER: This is our implicit Tenant Filter.
                // Since the segment_uuid comes from Postgres (scoped to tenant), 
                // only profiles belonging to this tenant's segment will be selected.
                FILTER @segment_id IN profile.inSegments[*].id
                
                FOR metric IN cdp_eventmetric
                    FILTER metric.eventName == event.metricName
                    
                    COLLECT 
                        pid = profile._key, 
                        ticker = event.eventData.instrument_id
                    AGGREGATE 
                        total_points = SUM(metric.score),
                        last_seen = MAX(event.createdAt)
                        
                    RETURN {
                        "profile_id": pid,
                        "ticker": ticker,
                        "points": total_points,
                        "last_seen": last_seen
                    }
        """
        
        bind_vars = {
            'segment_id': segment_uuid,
            'start_time': start_time_iso,
            'end_time': end_time_iso
        }
        
        cursor = db.aql.execute(scoring_query, bind_vars=bind_vars)
        results = [r for r in cursor]
        
        logger.info(f"📥 ArangoDB: Found {len(results)} pairs for segment {segment_uuid}.")
        return results

    except Exception as e:
        logger.error(f"❌ ArangoDB Query failed: {e}")
        return []

# --- 3. POSTGRES UPSERT LOGIC ---
def run_batch_scoring_job(settings: DatabaseSettings, start_time: str, end_time: str):
    """
    Orchestrates the ID resolution, Arango fetch, and Postgres upsert.
    """
    conn = settings.get_pg_connection()
    try:
        # A. Resolve IDs
        tenant_uuid, segment_uuid = resolve_ids(conn, TARGET_TENANT, TARGET_SEGMENT)
        
        # B. Fetch Data
        batch_data = get_batch_scoring_data(settings, start_time, end_time, segment_uuid)
        
        if not batch_data:
            logger.info("✅ Job finished: No relevant events found.")
            return

        # C. Process Upserts
        with conn.cursor() as cur:
            for entry in batch_data:
                profile_id = entry['profile_id']
                product_id = entry['ticker']
                incoming_points = entry['points']
                
                last_event_time = datetime.datetime.fromisoformat(entry['last_seen'].replace("Z", "+00:00"))

                # 1. Fetch Existing Score
                # MUST include all PK columns in the WHERE clause to find the exact unique row
                cur.execute("""
                    SELECT raw_score, last_interaction_at 
                    FROM product_recommendations 
                    WHERE profile_id = %s 
                      AND product_id = %s 
                      AND tenant_id = %s
                      AND journey_map_id = %s
                      AND journey_stage_id = %s
                      AND recommendation_model = %s
                """, (profile_id, product_id, tenant_uuid, 
                      DUMMY_JOURNEY_MAP_ID, DUMMY_JOURNEY_STAGE_ID, DUMMY_REC_MODEL))
                
                record = cur.fetchone()
                final_raw_score = 0.0
                
                if record:
                    if isinstance(record, dict):
                        current_raw = record['raw_score'] or 0.0
                        prev_interaction = record['last_interaction_at']
                    else:
                        current_raw = record[0] or 0.0
                        prev_interaction = record[1]

                    if prev_interaction and prev_interaction.tzinfo is None:
                        prev_interaction = prev_interaction.replace(tzinfo=datetime.timezone.utc)
                    if not prev_interaction:
                         prev_interaction = last_event_time

                    time_diff = last_event_time - prev_interaction
                    days_elapsed = max(time_diff.total_seconds() / 86400.0, 0)
                    decay_factor = 0.5 ** (days_elapsed / HALF_LIFE_DAYS)
                    
                    final_raw_score = (current_raw * decay_factor) + incoming_points
                else:
                    final_raw_score = incoming_points

                # 2. Normalize Score
                final_interest_score = final_raw_score / (final_raw_score + SCORING_K_FACTOR)
                
                # 3. Upsert
                # ADDED: recommendation_model to INSERT and ON CONFLICT
                upsert_sql = """
                    INSERT INTO product_recommendations (
                        tenant_id, profile_id, product_id, 
                        journey_map_id, journey_stage_id, recommendation_model,
                        raw_score, interest_score, last_interaction_at, updated_at,
                        recommendation_context,
                        product_type, product_url, rank_position, 
                        model_version, reason_codes
                    )
                    VALUES (
                        %s, %s, %s, 
                        %s, %s, %s,
                        %s, %s, %s, NOW(),
                        NULL, 
                        NULL, NULL, NULL, 
                        NULL, NULL
                    )
                    ON CONFLICT (tenant_id, profile_id, product_id, journey_map_id, journey_stage_id, recommendation_model) 
                    DO UPDATE SET 
                        raw_score = EXCLUDED.raw_score, 
                        interest_score = EXCLUDED.interest_score, 
                        last_interaction_at = EXCLUDED.last_interaction_at, 
                        updated_at = NOW();
                """
                
                cur.execute(upsert_sql, (
                    tenant_uuid, profile_id, product_id,
                    DUMMY_JOURNEY_MAP_ID, DUMMY_JOURNEY_STAGE_ID, DUMMY_REC_MODEL,
                    final_raw_score, final_interest_score, last_event_time
                ))
            
            conn.commit()
            logger.info("✅ Batch Upsert Complete.")
            
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Batch Job Failed: {e}")
    finally:
        conn.close()

# --- 4. GARBAGE COLLECTION ---
def run_garbage_collection(settings: DatabaseSettings):
    conn = settings.get_pg_connection()
    try:
        query = "DELETE FROM product_recommendations WHERE interest_score < %s"
        with conn.cursor() as cur:
            cur.execute(query, (SCORE_THRESHOLD,))
            deleted_count = cur.rowcount
        conn.commit()
        logger.info(f"🧹 GC: Removed {deleted_count} rows.")
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ GC Failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    settings = DatabaseSettings()
    
    print("--- 1. Running Garbage Collection ---")
    run_garbage_collection(settings)
    
    # 2. Calculate Window
    now = datetime.datetime.now(datetime.timezone.utc)
    window_end = now.replace(minute=0, second=0, microsecond=0)
    window_start = window_end - datetime.timedelta(hours=150)
    
    start_str = window_start.isoformat()
    end_str = window_end.isoformat()
    
    logger.info(f"🚀 Starting Job for Tenant: {TARGET_TENANT}")
    logger.info(f"📅 Window: {start_str} to {end_str}")
    
    run_batch_scoring_job(settings, start_str, end_str)