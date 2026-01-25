import uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, text, UniqueConstraint

from .base import Base, TimestampMixin

class Tenant(Base, TimestampMixin):
    __tablename__ = "tenant"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, 
        server_default=text("gen_random_uuid()")
    )
    tenant_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'active'")
    )
    
    # Keycloak Integration
    keycloak_realm: Mapped[str] = mapped_column(String, nullable=False)
    keycloak_client_id: Mapped[str] = mapped_column(String, nullable=False)
    keycloak_org_id: Mapped[str | None] = mapped_column(String)
    
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, server_default=text("'{}'"))

    __table_args__ = (
        UniqueConstraint("keycloak_realm", "tenant_name", name="uq_tenant_keycloak_realm"),
    )

    def __repr__(self):
        return f"<Tenant(id={self.tenant_id}, name='{self.tenant_name}')>"