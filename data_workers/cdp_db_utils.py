import logging
from typing import Any, Dict, List
from pathlib import Path

# Initialize logger for this module
logger = logging.getLogger(__name__)


def get_user_contact_from_cdp(db_connection: Any, segment_name: str) -> List[Dict[str, str]]:
    """
    Fetches a list of user contact information belonging to a specific segment.
    Returns: [{ 'email':'...', 'phone': '...', 'firstName': '...', 'lastName': '...'}, ...]
    """
    if not db_connection:
        logger.error("[EmailHelper] Database connection is not available.")
        return []

    try:
        # 1. Resolve Segment Name to ID
        segment_query = "FOR s IN cdp_segment FILTER s.name == @segment_name RETURN s._key"
        cursor_seg = db_connection.aql.execute(segment_query, bind_vars={'segment_name': segment_name})
        found_ids = [s for s in cursor_seg]

        if not found_ids:
            logger.warning(f"[ArangoDB] Segment '{segment_name}' not found.")
            return []
        
        target_segment_id = found_ids[0]
        logger.info(f"[ArangoDB] Resolving recipients for Segment ID: {target_segment_id}")

        # 2. Fetch Profile Data (Email + First Name)
        profile_query = """
        FOR p IN cdp_profile
            FILTER @segment_id IN p.inSegments[*].id
            FILTER (p.primaryPhone != null AND p.primaryPhone != "") OR (p.primaryEmail != null AND p.primaryEmail != "")
            RETURN {
                "email": p.primaryEmail,
                "phone": p.primaryPhone,
                "firstName": p.firstName,
                "lastName": p.lastName
            }
        """
        
        cursor_prof = db_connection.aql.execute(profile_query, bind_vars={'segment_id': target_segment_id})
        recipients = [r for r in cursor_prof]
        
        logger.info(f"[ArangoDB] Found {len(recipients)} profiles for personalization.")
        return recipients

    except Exception as e:
        logger.error(f"[ArangoDB] Query failed: {e}")
        return []