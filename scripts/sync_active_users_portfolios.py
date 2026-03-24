"""
Temporary sync: extract portfolio + holdings data from front-end
behavioral events in ArangoDB and upsert into PostgreSQL.

Runs as a standalone script OR via Celery beat.
Will be retired once the CDC pipeline is restored.
"""
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

from data_utils.settings import DatabaseSettings
from agentic_tools.recommendation_system.interest_score import resolve_ids

logger = logging.getLogger(__name__)

# --------------------------------------------------
# Constants
# --------------------------------------------------

ACCOUNT_TYPE_MAP = {
    "1": "CASH",
    "2": "MARGIN",
    "6": "MARGIN",
    "8": "DERIVATIVES",
}

CUTOFF_DAYS = 90

# --------------------------------------------------
# AQL Queries
# --------------------------------------------------

AQL_LOGIN_ACCOUNTS = """
FOR event IN cdp_trackingevent
    FILTER event.metricName == "login-success"
    FILTER event.createdAt >= @cutoff
    FILTER HAS(event.eventData, "account_id")
    FILTER event.eventData.account_id != null
    FILTER event.eventData.account_id != ""

    LET ref_id = (
        event.refProfileId != null AND event.refProfileId != ""
        ? event.refProfileId
        : event.fingerprintId
    )
    FILTER ref_id != null

    COLLECT
        account_id = event.eventData.account_id,
        profile_id = ref_id
    AGGREGATE
        last_seen   = MAX(event.createdAt),
        latest_nav  = LAST(event.eventData.nav),
        latest_cash = LAST(event.eventData.cash_total)

    RETURN {
        account_id:  account_id,
        profile_id:  profile_id,
        nav:         latest_nav,
        cash_total:  latest_cash,
        last_seen:   last_seen
    }
"""

AQL_ASSET_VIEWS = """
FOR event IN cdp_trackingevent
    FILTER event.metricName == "asset-detail-view"
    FILTER event.createdAt >= @cutoff
    FILTER HAS(event.eventData, "current_account_id")
    FILTER event.eventData.current_account_id != null

    LET ref_id = (
        event.refProfileId != null AND event.refProfileId != ""
        ? event.refProfileId
        : event.fingerprintId
    )
    FILTER ref_id != null

    COLLECT
        account_id = event.eventData.current_account_id,
        symbol     = event.eventData.symbol,
        profile_id = ref_id
    AGGREGATE
        last_seen      = MAX(event.createdAt),
        latest_qty     = LAST(event.eventData.quantity),
        latest_avg     = LAST(event.eventData.avg_price),
        latest_current = LAST(event.eventData.current_price)

    FILTER symbol != null AND symbol != ""

    RETURN {
        account_id:    account_id,
        symbol:        symbol,
        profile_id:    profile_id,
        quantity:      latest_qty,
        avg_price:     latest_avg,
        current_price: latest_current,
        last_seen:     last_seen
    }
"""

# --------------------------------------------------
# SQL UPSERTs
# --------------------------------------------------

UPSERT_PORTFOLIO_SQL = """
INSERT INTO portfolios (
    tenant_id, account_id, base_account_id, account_type, account_suffix,
    profile_id, nav, cash_total, source_timestamp
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (tenant_id, account_id) DO UPDATE SET
    nav              = EXCLUDED.nav,
    cash_total       = EXCLUDED.cash_total,
    source_timestamp = EXCLUDED.source_timestamp,
    updated_at       = now()
WHERE portfolios.source_timestamp IS NULL
   OR EXCLUDED.source_timestamp > portfolios.source_timestamp;
"""

UPSERT_HOLDING_SQL = """
INSERT INTO portfolio_holdings (
    tenant_id, account_id, symbol, quantity, avg_price, current_price, source_timestamp
)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (tenant_id, account_id, symbol) DO UPDATE SET
    quantity         = EXCLUDED.quantity,
    avg_price        = EXCLUDED.avg_price,
    current_price    = EXCLUDED.current_price,
    source_timestamp = EXCLUDED.source_timestamp,
    updated_at       = now()
WHERE portfolio_holdings.source_timestamp IS NULL
   OR EXCLUDED.source_timestamp > portfolio_holdings.source_timestamp;
"""

# --------------------------------------------------
# Transform helpers
# --------------------------------------------------


def parse_account_id(raw_account_id: str) -> dict:
    """
    Parse "100000012" → base="10000001", suffix="2", type="MARGIN".
    Last character is the suffix; everything before is the base.
    """
    raw = str(raw_account_id).strip()
    if len(raw) < 2:
        return {
            "account_id": raw,
            "base_account_id": raw,
            "account_suffix": "0",
            "account_type": "UNKNOWN",
        }
    suffix = raw[-1]
    base = raw[:-1]
    return {
        "account_id": raw,
        "base_account_id": base,
        "account_suffix": suffix,
        "account_type": ACCOUNT_TYPE_MAP.get(suffix, "UNKNOWN"),
    }


def safe_numeric(val, default=0) -> float:
    """Coerce messy FE values to float, defaulting to 0."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


# --------------------------------------------------
# Row builders
# --------------------------------------------------


def _build_portfolio_rows(login_events, tenant_id, valid_pids):
    rows = []
    for evt in login_events:
        pid = evt.get("profile_id")
        if pid not in valid_pids:
            continue
        parsed = parse_account_id(evt["account_id"])
        rows.append((
            tenant_id,
            parsed["account_id"],
            parsed["base_account_id"],
            parsed["account_type"],
            parsed["account_suffix"],
            pid,
            safe_numeric(evt.get("nav")),
            safe_numeric(evt.get("cash_total")),
            evt.get("last_seen"),
        ))
    return rows


def _build_holding_rows(asset_events, tenant_id, valid_pids, valid_account_ids):
    rows = []
    for evt in asset_events:
        pid = evt.get("profile_id")
        aid = str(evt.get("account_id", ""))
        if pid not in valid_pids:
            continue
        if aid not in valid_account_ids:
            continue
        rows.append((
            tenant_id,
            aid,
            evt["symbol"],
            safe_numeric(evt.get("quantity")),
            safe_numeric(evt.get("avg_price")),
            safe_numeric(evt.get("current_price")),
            evt.get("last_seen"),
        ))
    return rows


# --------------------------------------------------
# Upsert executors
# --------------------------------------------------


def _upsert_portfolios(conn, rows: list) -> int:
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(UPSERT_PORTFOLIO_SQL, rows)
    return len(rows)


def _upsert_holdings(conn, rows: list) -> int:
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(UPSERT_HOLDING_SQL, rows)
    return len(rows)


# --------------------------------------------------
# Core orchestrator
# --------------------------------------------------


def sync_active_users_portfolios(
    *,
    tenant_name: Optional[str] = None,
    segment_name: Optional[str] = None,
) -> dict:
    """
    Extract portfolio data from ArangoDB FE events and upsert into PG.
    Returns {"portfolios": int, "holdings": int, "skipped": int}.
    """
    tenant_name = tenant_name or os.getenv("TARGET_TENANT", "master")
    segment_name = segment_name or os.getenv("TARGET_SEGMENT", "Active in last 3 months")

    settings = DatabaseSettings()
    conn = settings.get_pg_connection()

    try:
        # 1. Resolve tenant
        tenant_uuid, _ = resolve_ids(conn, tenant_name, segment_name)
        tenant_id = str(tenant_uuid)

        # 2. Query ArangoDB
        cutoff = (datetime.now(timezone.utc) - timedelta(days=CUTOFF_DAYS)).isoformat()
        db = settings.get_arango_db()

        login_events = list(db.aql.execute(AQL_LOGIN_ACCOUNTS, bind_vars={"cutoff": cutoff}))
        asset_events = list(db.aql.execute(AQL_ASSET_VIEWS, bind_vars={"cutoff": cutoff}))
        logger.info(
            "Fetched %d login accounts, %d asset views from ArangoDB",
            len(login_events), len(asset_events),
        )

        if not login_events and not asset_events:
            logger.info("No events found. Nothing to sync.")
            return {"portfolios": 0, "holdings": 0, "skipped": 0}

        # 3. Orphan filter — only keep profile_ids that exist in PG
        all_profile_ids = list({
            e["profile_id"] for e in login_events + asset_events
            if e.get("profile_id")
        })
        with conn.cursor() as cur:
            cur.execute(
                "SELECT profile_id FROM cdp_profiles WHERE profile_id = ANY(%s)",
                (all_profile_ids,),
            )
            valid_pids = {row["profile_id"] for row in cur.fetchall()}

        skipped = len(all_profile_ids) - len(valid_pids)
        if skipped:
            logger.warning("Skipping %d orphaned profile(s) not in cdp_profiles", skipped)

        # 4. Upsert portfolios
        portfolio_rows = _build_portfolio_rows(login_events, tenant_id, valid_pids)
        p_count = _upsert_portfolios(conn, portfolio_rows)

        # 5. Collect valid account_ids for FK safety
        valid_account_ids = {row[1] for row in portfolio_rows}  # index 1 = account_id

        # 6. Upsert holdings (filtered by valid profiles AND valid accounts)
        holding_rows = _build_holding_rows(asset_events, tenant_id, valid_pids, valid_account_ids)
        h_count = _upsert_holdings(conn, holding_rows)

        conn.commit()
        logger.info("Sync complete: %d portfolios, %d holdings upserted", p_count, h_count)
        return {"portfolios": p_count, "holdings": h_count, "skipped": skipped}

    except Exception as exc:
        conn.rollback()
        logger.exception("Portfolio sync failed")
        raise exc
    finally:
        conn.close()


# --------------------------------------------------
# CLI entry point
# --------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )
    result = sync_active_users_portfolios()
    print(f"Done: {result}")
