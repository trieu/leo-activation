"""
Data model and tenant context utilities.

This module defines:
- Tenant ORM model
- Session-level tenant resolver for PostgreSQL RLS
"""

from __future__ import annotations

import logging
import uuid
from typing import Final

import psycopg
from psycopg.rows import dict_row
from sqlalchemy import String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin

# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------

DEFAULT_TENANT_NAME: Final[str] = "master"
TENANT_STATUS_ACTIVE: Final[str] = "active"

# ---------------------------------------------------------------------
# ORM Model
# ---------------------------------------------------------------------


class Tenant(Base, TimestampMixin):
    """
    Tenant represents an isolated logical customer boundary.

    Used in combination with PostgreSQL RLS via `app.current_tenant_id`.
    """

    __tablename__ = "tenant"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    tenant_name: Mapped[str] = mapped_column(
        String,
        nullable=False,
        server_default=text(f"'{DEFAULT_TENANT_NAME}'"),
    )

    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        server_default=text(f"'{TENANT_STATUS_ACTIVE}'"),
    )

    # --------------------------------------------------
    # Keycloak integration
    # --------------------------------------------------

    keycloak_realm: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    keycloak_client_id: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    keycloak_org_id: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    # --------------------------------------------------
    # Extensible metadata
    # --------------------------------------------------

    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    __table_args__ = (
        UniqueConstraint(
            "keycloak_realm",
            "tenant_name",
            name="uq_tenant_keycloak_realm",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Tenant tenant_id={self.tenant_id} "
            f"tenant_name='{self.tenant_name}' "
            f"status='{self.status}'>"
        )


# ---------------------------------------------------------------------
# Tenant Context Resolver (PostgreSQL RLS)
# ---------------------------------------------------------------------


def resolve_and_set_default_tenant(
    conn: psycopg.Connection,
    tenant_name: str = DEFAULT_TENANT_NAME,
) -> uuid.UUID:
    """
    Resolve tenant_id by tenant_name and bind it to the current
    PostgreSQL session using `set_config`.

    This is required for Row-Level Security (RLS) enforcement.

    Parameters
    ----------
    conn : psycopg.Connection
        Active psycopg v3 connection
    tenant_name : str
        Logical tenant name

    Returns
    -------
    uuid.UUID
        Resolved tenant_id

    Raises
    ------
    RuntimeError
        If tenant does not exist
    """

    sql_resolve = """
        SELECT tenant_id
        FROM tenant
        WHERE tenant_name = %s
        LIMIT 1
    """

    sql_set_context = """
        SELECT set_config('app.current_tenant_id', %s, true)
    """

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql_resolve, (tenant_name,))
        row = cur.fetchone()

        if row is None:
            raise RuntimeError(
                f"Tenant '{tenant_name}' not found; "
                "cannot establish RLS context"
            )

        tenant_id: uuid.UUID = row["tenant_id"]

        # Bind tenant to session for RLS
        cur.execute(sql_set_context, (str(tenant_id),))

    conn.commit()

    logger.info(
        "PostgreSQL session bound to tenant '%s' (%s)",
        tenant_name,
        tenant_id,
    )

    return tenant_id
