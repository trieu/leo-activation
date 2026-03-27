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
_SQL_PORTFOLIO_USERS = """
    SELECT DISTINCT
        p.profile_id,
        p.primary_email,
        pt.base_account_id
    FROM cdp_profiles p
    CROSS JOIN LATERAL jsonb_array_elements(p.segments) AS s
    LEFT JOIN portfolios pt ON pt.profile_id = p.profile_id
    WHERE s->>'name' = ANY(%s)
"""


# --- ENDPOINTS ---
@router.get("/users", response_model=List[PortfolioUserResponse])
async def get_portfolio_users(
    env: Optional[str] = Query(
        None,
        description="Filter by environment: 'uat', 'prod', or omit for all",
        enum=["uat", "prod"],
    ),
    conn: psycopg.Connection = Depends(get_db),
):
    """
    List users with their portfolio base_account_id, filtered by segment.
    - **uat**: UAT 1invest Users only
    - **prod**: Production 1invest Users only
    - **omit**: both segments
    """
    segment_map = {
        "uat": ["UAT 1invest Users"],
        "prod": ["Production 1invest Users"],
    }
    segments = segment_map.get(env, ["UAT 1invest Users", "Production 1invest Users"])

    try:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(_SQL_PORTFOLIO_USERS, (segments,))
            rows = cur.fetchall()
        return [PortfolioUserResponse(**r) for r in rows]
    except Exception as e:
        logger.error("Portfolio users query failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
