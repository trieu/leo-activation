"""Portfolio API endpoints for LEO Activation."""

import logging
from typing import List, Optional

import psycopg
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel

from data_utils.settings import DatabaseSettings

logger = logging.getLogger("LEO Portfolio API")

# --- ROUTER SETUP ---
router = APIRouter(
    prefix="/portfolio",
    tags=["Portfolio"],
)


# --- DEPENDENCIES ---
def get_db():
    settings = DatabaseSettings()
    conn = settings.get_pg_connection()
    try:
        yield conn
    finally:
        conn.close()


# --- DATA MODELS ---
class PortfolioUserResponse(BaseModel):
    profile_id: str
    primary_email: Optional[str] = None
    base_account_id: Optional[str] = None


# --- SQL ---
_SQL_LOOKUP_USER = """
    SELECT DISTINCT
        p.profile_id,
        p.primary_email,
        pt.base_account_id
    FROM cdp_profiles p
    LEFT JOIN portfolios pt ON pt.profile_id = p.profile_id
    WHERE (p.primary_email = %s OR p.profile_id = %s OR pt.base_account_id = %s)
"""

_SQL_LOOKUP_USER_SEGMENT = _SQL_LOOKUP_USER + """
    AND EXISTS (
        SELECT 1 FROM jsonb_array_elements(p.segments) AS s
        WHERE s->>'name' = ANY(%s)
    )
"""

_SEGMENT_MAP = {
    "uat": ["UAT 1invest Users"],
    "prod": ["Production 1invest Users"],
}
_SEGMENT_ALL = ["UAT 1invest Users", "Production 1invest Users"]


# --- ENDPOINTS ---
@router.get("/user", response_model=List[PortfolioUserResponse])
async def get_portfolio_user(
    lookup: str = Query(
        ...,
        description="Search value: email, profile_id, or base_account_id",
    ),
    env: Optional[str] = Query(
        None,
        description="Filter by environment: 'uat', 'prod', or omit for all",
        enum=["uat", "prod"],
    ),
    conn: psycopg.Connection = Depends(get_db),
):
    """
    Look up a user by email, profile_id, or base_account_id.
    Returns profile_id, primary_email, and base_account_id.
    - **uat**: UAT 1invest Users only
    - **prod**: Production 1invest Users only
    - **omit**: no segment filter
    """
    try:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            if env:
                segments = _SEGMENT_MAP[env]
                cur.execute(_SQL_LOOKUP_USER_SEGMENT, (lookup, lookup, lookup, segments))
            else:
                cur.execute(_SQL_LOOKUP_USER, (lookup, lookup, lookup))
            rows = cur.fetchall()
        return [PortfolioUserResponse(**r) for r in rows]
    except Exception as e:
        logger.error("Portfolio user lookup failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
