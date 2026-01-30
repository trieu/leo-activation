"""
API Route Handlers for LEO Activation Agent.
"""

import logging
from typing import Any, Dict, List, Optional, Union

import psycopg
from fastapi import APIRouter, HTTPException, Body, Path, Query, Depends
from pydantic import BaseModel, Field

# --- IMPORTS ---
from agentic_models.router import AgentRouter
from agentic_tools.alert_center_tools import get_alert_types
from agentic_tools.customer_data_tools import show_all_segments
from agentic_tools.data_enrichment_tools import analyze_segment
from agentic_tools.marketing_tools import get_marketing_events
from agentic_tools.tools import (
    AVAILABLE_TOOLS,
    activate_channel,
    get_current_weather,
    get_date,
    manage_cdp_segment,
)
from agentic_tools.channels.zalo import ZaloOAChannel
from data_workers.sync_segment_profiles import run_synch_profiles_async
from main_configs import DATA_SYNC_API_KEY

# --- DB UTILS ---
# We need these for the /interested endpoint
# from data_workers.pg_profile_repository import get_users_by_ticker_interest
from data_utils.settings import DatabaseSettings

# Import the worker function for sync
try:
    from data_workers.sync_segment_profiles import run_synch_profiles
except ImportError:
    logging.warning("Could not import 'run_synch_profiles'. Sync features will fail if called.")
    def run_synch_profiles(segment_id: str):
        raise NotImplementedError("Worker module not found.")

logger = logging.getLogger("LEO Activation API")

# --- Database Dependency ---
def get_db():
    settings = DatabaseSettings()
    conn = settings.get_pg_connection()
    try:
        yield conn
    finally:
        conn.close()


# ============================================================
# Data Models (Schemas)
# ============================================================

class ChatRequest(BaseModel):
    prompt: Union[str, List[Dict[str, Any]]] = Field(..., description="User query or history")

class ToolCallingRequest(BaseModel):
    tool_name: str
    tool_args: Dict[str, Any] = {}

class SyncRequest(BaseModel):
    segment_id: str
    data_sync_api_key: Optional[str] = None

class ChatResponse(BaseModel):
    answer: str
    debug: Any

class ZaloTestRequest(BaseModel):
    segment_name: str
    message: Optional[str] = None
    kwargs: Optional[Dict[str, Any]] = {}

class InterestedUserResponse(BaseModel):
    profile_id: str
    score: float
    raw_points: float
    last_interaction: Optional[str] = None

class UserProfileInterestResponse(BaseModel):
    """Schema for the 360-view profile endpoint"""
    profile_id: Optional[str] = None
    identities: List[str] = Field(default_factory=list)
    primary_email: Optional[str] = None
    raw_scores: Dict[str, float]
    interest_scores: Dict[str, float]
    segments: List[str]

# Constants
HELP_DOCUMENTATION_URL = '<a href="https://leocdp.com/documents" target="_blank"> https://leocdp.com/documents </a>'
HELP_MESSAGE = f"Please refer to the documentation at {HELP_DOCUMENTATION_URL}"


# ============================================================
# New Tool Definition
# ============================================================

def sync_segment_to_db(segment_id: str) -> str:
    try:
        logger.info(f"Agent triggering sync for segment: {segment_id}")
        run_synch_profiles(segment_id=segment_id)
        return f"Successfully synchronized profiles for segment '{segment_id}'."
    except Exception as e:
        logger.exception(f"Sync failed for segment {segment_id}")
        return f"Failed to synchronize segment '{segment_id}'. Error: {str(e)}"


# ============================================================
# Router Setup
# ============================================================

def create_api_router(agent_router: AgentRouter) -> APIRouter:
    router = APIRouter()

    # 1. Tools Setup
    tools = [
        get_date, get_current_weather, get_marketing_events, get_alert_types,
        manage_cdp_segment, activate_channel, analyze_segment, show_all_segments,
        sync_segment_to_db
    ]
    
    tools_map = AVAILABLE_TOOLS.copy()
    local_tools = {
        "show_all_segments": show_all_segments,
        "analyze_segment": analyze_segment,
        "sync_segment_to_db": sync_segment_to_db,
    }
    for name, func in local_tools.items():
        if name not in tools_map:
            tools_map[name] = func

    # --------------------------------------------------------
    # 1. Tool Calling
    # --------------------------------------------------------
    @router.post("/tool_calling", response_model=ChatResponse)
    async def tool_calling_endpoint(payload: ToolCallingRequest):
        try:
            if payload.tool_name not in tools_map:
                raise HTTPException(status_code=400, detail=f"Tool '{payload.tool_name}' not found.")
            
            response = agent_router.handle_tool_calling(
                tool_calling_json={"tool_name": payload.tool_name, "args": payload.tool_args},
                tools=tools, tools_map=tools_map
            )
            return ChatResponse(answer=response["answer"], debug=response["debug"])
        except Exception as e:
            logger.exception("Tool calling failed")
            raise HTTPException(status_code=500, detail=str(e))

    # --------------------------------------------------------
    # 2. Chat
    # --------------------------------------------------------
    @router.post("/chat", response_model=ChatResponse)
    async def chat_endpoint(payload: ChatRequest):
        try:
            input_content = payload.prompt
            if isinstance(input_content, str):
                if input_content.strip().lower() == "help":
                    return ChatResponse(answer=HELP_MESSAGE, debug={})
                messages = [{"role": "user", "content": input_content.strip()}]
            else:
                messages = input_content

            response = agent_router.handle_message(messages, tools=tools, tools_map=tools_map)
            return ChatResponse(answer=response["answer"], debug=response["debug"])
        except Exception as e:
            logger.exception("Chat failed")
            raise HTTPException(status_code=500, detail=str(e))

    # --------------------------------------------------------
    # 3. Sync
    # --------------------------------------------------------
    @router.post("/data/sync-segment")
    async def sync_segment_endpoint(request: SyncRequest):
        if request.data_sync_api_key != DATA_SYNC_API_KEY:
            raise HTTPException(status_code=401, detail="Invalid API key")
        count = await run_synch_profiles_async(segment_id=request.segment_id)
        return {"status": "success", "synced": count}

    # --------------------------------------------------------
    # 4. Zalo Test
    # --------------------------------------------------------
    @router.post("/test/zalo-direct")
    async def test_zalo_direct(request: ZaloTestRequest):
        zalo = ZaloOAChannel()
        res = zalo.send(request.segment_name, request.message, **request.kwargs)
        return {"status": "completed", "channel_response": res}

    # --------------------------------------------------------
    # 5. Interested Users (By Ticker)
    # --------------------------------------------------------
    @router.get("/interested/{ticker}", response_model=List[InterestedUserResponse])
    async def get_interested_users_api(
        ticker: str,
        min_score: float = Query(0.5, description="Minimum score 0.0-1.0"),
        conn: psycopg.Connection = Depends(get_db)
    ):
        """
        Finds users interested in a specific ticker (e.g., 'AAPL') with explicit SQL 
        for debugging and robustness.
        """
        # 1. Sanitize Input
        clean_ticker = ticker.upper().strip()
        response_list = []

        # 2. SQL Query (Joins Scores with Profile Data)
        # We assume 'product_id' stores the ticker symbol
        sql = """
            SELECT 
                profile_id,
                interest_score,
                raw_score
            FROM product_recommendations
            WHERE product_id = %s 
              AND interest_score >= %s
            ORDER BY interest_score DESC
            LIMIT 50
        """

        try:
            cursor = conn.cursor()
            cursor.execute(sql, (clean_ticker, min_score))
            rows = cursor.fetchall()
            
            for row in rows:
                # 3. Robust Data Parsing (Handles Dict or Tuple rows)
                if isinstance(row, (tuple, list)):
                    # Tuple Order: 0=id, 1=interest, 2=raw, 3=last_interaction
                    p_id = row[0]
                    i_score = row[1]
                    r_score = row[2]
                else:
                    # Dictionary Access
                    p_id = row['profile_id']
                    i_score = row['interest_score']
                    r_score = row['raw_score']

                # 4. Map to Pydantic Model
                response_list.append({
                    "profile_id": p_id,
                    "score": float(i_score) if i_score is not None else 0.0,
                    "raw_points": float(r_score) if r_score is not None else 0.0,
                })
            
            cursor.close()
            return response_list

        except Exception as e:
            # 5. Explicit Error Logging
            logger.error(f"❌ [SQL Error] Failed to fetch interested users for '{clean_ticker}': {e}")
            raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")

    # --------------------------------------------------------
    # 6. Profile Affinity (Direct SQL Implementation)
    # --------------------------------------------------------
    @router.get("/profile_affinity/{lookup_key}", response_model=UserProfileInterestResponse)
    async def get_user_profile_data(
        lookup_key: str = Path(..., description="Profile ID, Email, or Identity"),
        conn: psycopg.Connection = Depends(get_db)
    ):
        clean_key = lookup_key.strip()
        
        # Containers
        profile_id = None
        primary_email = None
        final_identities: List[str] = []
        final_segments: List[str] = []
        raw_map: Dict[str, float] = {}
        interest_map: Dict[str, float] = {}

        try:
            # A. FIND PROFILE
            profile_sql = """
                SELECT profile_id, primary_email, identities, segments
                FROM cdp_profiles
                WHERE profile_id = %s OR primary_email = %s OR identities::jsonb ? %s
                LIMIT 1
            """
            cursor = conn.cursor()
            cursor.execute(profile_sql, (clean_key, clean_key, clean_key))
            row = cursor.fetchone()
            
            if row:
                # Handle cases where row might be a Tuple OR a Dict (Safety check)
                if isinstance(row, (tuple, list)):
                    # Fallback for tuple cursor
                    profile_id = row[0]
                    primary_email = row[1]
                    raw_ids = row[2]
                    raw_segs = row[3]
                else:
                    # Standard Dict cursor access (Likely your case)
                    profile_id = row['profile_id']
                    primary_email = row['primary_email']
                    raw_ids = row['identities']
                    raw_segs = row['segments']
                
                # Parse Identities
                if isinstance(raw_ids, list):
                    final_identities = [
                        i for i in raw_ids 
                        if isinstance(i, str) and (i.startswith("email:") or i.startswith("phone:"))
                    ]
                
                # Parse Segments
                if isinstance(raw_segs, list):
                    final_segments = [
                        s.get("name") for s in raw_segs 
                        if isinstance(s, dict) and s.get("name")
                    ]
                cursor.close()
            else:
                cursor.close()
                logger.warning(f"Profile not found: {clean_key}")
                return UserProfileInterestResponse(
                    profile_id=None, identities=[], raw_scores={}, interest_scores={}, segments=[]
                )

            # B. FETCH SCORES
            if profile_id:
                score_sql = """
                    SELECT product_id, raw_score, interest_score 
                    FROM product_recommendations WHERE profile_id = %s
                """
                cursor = conn.cursor()
                cursor.execute(score_sql, (profile_id,))
                rows = cursor.fetchall()
                
                for r in rows:
                    # Handle Dict/Tuple for scores too
                    if isinstance(r, (tuple, list)):
                        p_id, raw, interest = r[0], r[1], r[2]
                    else:
                        p_id = r['product_id']
                        raw = r['raw_score']
                        interest = r['interest_score']

                    if p_id:
                        raw_map[p_id] = float(raw or 0.0)
                        interest_map[p_id] = float(interest or 0.0)
                cursor.close()

        except Exception as e:
            # Enhanced logging to see the type if it fails again
            logger.error(f"SQL Error for {clean_key} | Type: {type(e)} | Msg: {e}")
            raise HTTPException(status_code=500, detail=f"Database Error: {str(e)}")

        return UserProfileInterestResponse(
            profile_id=profile_id,
            identities=final_identities,
            primary_email=primary_email,
            raw_scores=raw_map,
            interest_scores=interest_map,
            segments=final_segments
        )

    # ========================================================
    # ⚠️ THIS WAS MISSING: RETURN THE ROUTER OBJECT
    # ========================================================
    return router