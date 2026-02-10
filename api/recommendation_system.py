import logging
import os
import psycopg
from typing import List, Dict, Any, Optional, Union
from fastapi import APIRouter, HTTPException, Path, Query, Depends
from pydantic import BaseModel, Field

# --- IMPORTS ---
from data_utils.settings import DatabaseSettings

# Import Workers (The Logic Layer)
# We handle import errors gracefully to prevent crashing if workers aren't ready
try:
    from agentic_tools.interest_score import (
        resolve_ids, 
        get_interested_users, 
        get_profile_affinity
    )
    from agentic_tools.next_best_action import get_next_best_action
except ImportError as e:
    import logging
    logging.warning(f"⚠️ Worker modules missing: {e}. Recommendation endpoints will fail.")

# --- LOGGING ---
logger = logging.getLogger("LEO Recommendation API")

# --- ROUTER SETUP ---
router = APIRouter(
    prefix="/recommendation",
    tags=["Recommendation System"]
)

# --- DEPENDENCIES ---
def get_db():
    settings = DatabaseSettings()
    conn = settings.get_pg_connection()
    try:
        yield conn
    finally:
        conn.close()

# --- DATA MODELS (Response Schemas) ---

class InterestedUserResponse(BaseModel):
    profile_id: str
    score: float
    raw_points: float

class UserProfileInterestResponse(BaseModel):
    """Schema for the 360-view profile endpoint"""
    profile_id: Optional[str] = None
    identities: List[str] = Field(default_factory=list)
    primary_email: Optional[str] = None
    raw_scores: Dict[str, float]
    interest_scores: Dict[str, float]
    segments: List[str]

class NextBestActionResponse(BaseModel):
    """Standardized response for the NBA decision engine."""
    profile_id: str
    ticker: Optional[str] = None
    action: str = Field(..., description="The recommended action (e.g., STRONG_BUY, WATCHLIST)")
    channel: str = Field(..., description="The engagement channel (e.g., PUSH, EMAIL)")
    confidence_score: float
    reason: str


# ============================================================
# API ENDPOINTS
# ============================================================

# 1. FIND AUDIENCE (Who likes this stock?)
@router.get("/interested/{ticker}", response_model=List[InterestedUserResponse])
async def get_interested_users_endpoint(
    ticker: str,
    min_score: float = Query(0.5, description="Minimum score 0.0-1.0"),
    conn: psycopg.Connection = Depends(get_db)
):
    """
    Finds users interested in a specific ticker (e.g., 'AAPL').
    Useful for: Targeted Campaigns (e.g., "Send update to everyone watching NVDA").
    """
    try:
        # Resolve Tenant Context (Secure)
        target_tenant = os.getenv("TARGET_TENANT", "master")
        # Reuse resolve_ids logic to get the correct Tenant UUID
        tenant_uuid, _ = resolve_ids(conn, target_tenant, "Active in last 3 months")

        # Call Worker
        raw_results = get_interested_users(conn, tenant_uuid, ticker, min_score)
        
        # Map to Pydantic (Worker returns list of dicts)
        return [InterestedUserResponse(**r) for r in raw_results]

    except Exception as e:
        logger.error(f"❌ Audience Query Error for '{ticker}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 2. PROFILE 360 (What does this user like?)
@router.get("/profile_affinity/{lookup_key}", response_model=UserProfileInterestResponse)
async def get_profile_affinity_endpoint(
    lookup_key: str = Path(..., description="Profile ID, Email, or Identity"),
    conn: psycopg.Connection = Depends(get_db)
):
    """
    Gets a 360-view of a user: Identity + Calculated Interest Scores.
    Useful for: Customer Support Dashboard or User Profile Page.
    """
    try:
        # Resolve Tenant Context
        target_tenant = os.getenv("TARGET_TENANT", "master")
        tenant_uuid, _ = resolve_ids(conn, target_tenant, "Active in last 3 months")

        # Call Worker
        data = get_profile_affinity(conn, tenant_uuid, lookup_key)
        
        if not data:
            # Return empty structure if not found
            return UserProfileInterestResponse(
                profile_id=None, identities=[], raw_scores={}, interest_scores={}, segments=[]
            )
            
        return UserProfileInterestResponse(**data)

    except Exception as e:
        logger.error(f"❌ Profile Lookup Error for '{lookup_key}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 3. NEXT BEST ACTION (What should we do with them?)
@router.get("/nba/{user_id}", response_model=NextBestActionResponse)
async def get_nba_endpoint(
    user_id: str = Path(..., description="The target User Profile ID"),
    conn: psycopg.Connection = Depends(get_db)
):
    """
    Calculates the single best action to take for a user based on 
    their highest interest score and segment persona.
    Useful for: Marketing Triggers (e.g., "Show this Banner").
    """
    try:
        # Resolve Tenant Context
        target_tenant = os.getenv("TARGET_TENANT", "master")
        tenant_uuid, _ = resolve_ids(conn, target_tenant, "Active in last 3 months")

        # Call Worker (Logic Engine)
        result = get_next_best_action(conn, tenant_uuid, user_id)

        return NextBestActionResponse(
            profile_id=result["profile_id"],
            ticker=result["ticker"],
            action=result["action"],
            channel=result["channel"],
            confidence_score=result["confidence_score"],
            reason=result["reason"]
        )

    except Exception as e:
        logger.error(f"❌ NBA Error for '{user_id}': {e}")
        raise HTTPException(status_code=500, detail=str(e))