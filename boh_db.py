"""Direct database connection to Kitchen (BOH) for sub-20ms lead delivery.

Instead of HTTP webhook (~100ms), we write directly to the shared BOH database.
PostgreSQL NOTIFY trigger fires automatically, Kitchen picks up the lead instantly.

Flow:
    Takeout INSERT → leads table → pg_notify('new_lead', lead_id)
                                          ↓
                               Kitchen NotifyListener (< 1ms)
                                          ↓
                               LeadMatcher routes to tickets

Requirements:
    - BOH_DATABASE_URL env var (same PostgreSQL instance as Kitchen)
    - Default "other" platform campaign must exist in Kitchen
"""

import os
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, String, DateTime, Integer, Numeric, Boolean, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# Check for BOH database URL
BOH_DATABASE_URL = os.environ.get("BOH_DATABASE_URL")


class BOHBase(DeclarativeBase):
    """Base for BOH ORM models (minimal subset for lead insertion)."""
    pass


class LeadORM(BOHBase):
    """Minimal LeadORM for direct insertion (mirrors Kitchen schema)."""

    __tablename__ = "leads"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    campaign_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    ticket_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    brand_id: Mapped[str] = mapped_column(String(100), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    platform_lead_id: Mapped[str] = mapped_column(String(255), nullable=False)
    form_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="staged")
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    staged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, name="metadata")
    is_waste: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    waste_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    waste_details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    menu_item: Mapped[str | None] = mapped_column(String(100), nullable=True)
    quarters_sold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quarters_remaining: Mapped[int] = mapped_column(Integer, nullable=False, default=4)


class CampaignORM(BOHBase):
    """Minimal CampaignORM for looking up default campaign."""

    __tablename__ = "campaigns"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    ticket_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    brand_id: Mapped[str] = mapped_column(String(100), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)


# Engine and session factory (lazy initialization)
_engine = None
_session_factory = None


def _get_engine():
    """Get or create the async engine."""
    global _engine
    if _engine is None:
        if not BOH_DATABASE_URL:
            raise RuntimeError(
                "BOH_DATABASE_URL environment variable required for direct DB integration. "
                "Set it to the same PostgreSQL connection string used by Kitchen."
            )
        _engine = create_async_engine(BOH_DATABASE_URL, echo=False)
    return _engine


def _get_session_factory():
    """Get or create the session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(_get_engine(), expire_on_commit=False)
    return _session_factory


async def get_boh_session() -> AsyncSession:
    """Get a BOH database session."""
    factory = _get_session_factory()
    return factory()


async def get_default_campaign(session: AsyncSession) -> tuple[UUID, UUID, str] | None:
    """
    Get the default campaign for 'other' platform leads.

    Returns:
        Tuple of (campaign_id, ticket_id, brand_id) or None if not found
    """
    result = await session.execute(
        select(CampaignORM.id, CampaignORM.ticket_id, CampaignORM.brand_id)
        .where(CampaignORM.platform == "other")
        .limit(1)
    )
    row = result.one_or_none()
    if row:
        return row.id, row.ticket_id, row.brand_id
    return None


async def check_duplicate(session: AsyncSession, platform: str, platform_lead_id: str) -> bool:
    """Check if a lead with this platform ID already exists."""
    result = await session.execute(
        select(LeadORM.id).where(
            LeadORM.platform == platform,
            LeadORM.platform_lead_id == platform_lead_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def stage_lead_direct(
    session: AsyncSession,
    campaign_id: UUID,
    ticket_id: UUID,
    brand_id: str,
    menu_item: str,
    platform_lead_id: str,
    form_data: dict,
    geo: str | None = None,
    metadata: dict | None = None,
) -> UUID:
    """
    Stage a lead directly in the BOH database.

    PostgreSQL NOTIFY trigger fires automatically after INSERT.
    Kitchen's NotifyListener picks it up in < 1ms.

    Args:
        session: BOH database session
        campaign_id: Campaign UUID (from get_default_campaign)
        ticket_id: Ticket UUID (from get_default_campaign)
        brand_id: Brand ID (from get_default_campaign)
        menu_item: What type of lead (dscr_refi, dscr_purchase, etc.)
        platform_lead_id: Unique ID for deduplication
        form_data: Contact info (name, email, phone)
        geo: State code (TX, CA, etc.)
        metadata: Additional data (budget, timeline, etc.)

    Returns:
        The staged lead's UUID
    """
    lead_id = uuid4()
    now = datetime.utcnow()

    # Build metadata with geo
    lead_metadata = {
        **(metadata or {}),
        "intake_source": "takeout_chatbot",
        "intake_platform": "takeout",
    }
    if geo:
        lead_metadata["geo"] = geo

    lead = LeadORM(
        id=lead_id,
        campaign_id=campaign_id,
        ticket_id=ticket_id,
        brand_id=brand_id,
        platform="takeout",
        platform_lead_id=platform_lead_id,
        form_data=form_data,
        status="staged",
        captured_at=now,
        staged_at=now,
        metadata_json=lead_metadata,
        menu_item=menu_item,
        quarters_sold=0,
        quarters_remaining=4,
    )

    session.add(lead)
    await session.commit()

    return lead_id


def map_loan_type_to_menu_item(loan_type: str | None) -> str:
    """Map user's loan type to kitchen menu item."""
    mapping = {
        "purchase": "dscr_purchase",
        "cashout": "dscr_cashout",
        "refinance": "dscr_refi",
    }
    return mapping.get(loan_type or "", "dscr_refi")


async def send_lead_to_kitchen(lead_data: dict, session_id: str) -> UUID | None:
    """
    Send captured lead data to Kitchen via direct DB insert.

    This is the main entry point called from app.py when the submit_lead
    tool is invoked.

    Args:
        lead_data: Structured data from submit_lead tool:
            {
                "geo": "TX",
                "loan_type": "refinance",
                "budget_min": 200000,
                "budget_max": 500000,
                "timeline": "30 days",
                "contact": {"name": "...", "email": "...", "phone": "..."}
            }
        session_id: Chainlit session ID for deduplication

    Returns:
        Lead UUID if successful, None if failed
    """
    if not BOH_DATABASE_URL:
        print("WARNING: BOH_DATABASE_URL not set, lead not sent to kitchen")
        return None

    try:
        async with await get_boh_session() as session:
            # Get default campaign for takeout leads
            campaign_info = await get_default_campaign(session)
            if not campaign_info:
                print("ERROR: No default 'other' campaign found in Kitchen. Create one first.")
                return None

            campaign_id, ticket_id, brand_id = campaign_info

            # Generate unique platform_lead_id
            platform_lead_id = f"takeout_{session_id}_{datetime.utcnow().timestamp()}"

            # Check for duplicate
            if await check_duplicate(session, "takeout", platform_lead_id):
                print(f"WARNING: Duplicate lead: {platform_lead_id}")
                return None

            # Extract contact info
            contact = lead_data.get("contact", {})
            form_data = {
                "name": contact.get("name", ""),
                "email": contact.get("email", ""),
                "phone": contact.get("phone", ""),
            }

            # Build metadata
            metadata = {
                "budget_min": lead_data.get("budget_min"),
                "budget_max": lead_data.get("budget_max"),
                "timeline": lead_data.get("timeline"),
                "loan_type": lead_data.get("loan_type"),
                "session_id": session_id,
            }

            # Stage the lead
            lead_id = await stage_lead_direct(
                session=session,
                campaign_id=campaign_id,
                ticket_id=ticket_id,
                brand_id=brand_id,
                menu_item=map_loan_type_to_menu_item(lead_data.get("loan_type")),
                platform_lead_id=platform_lead_id,
                form_data=form_data,
                geo=lead_data.get("geo"),
                metadata=metadata,
            )

            print(f"Lead staged successfully: {lead_id}")
            return lead_id

    except Exception as e:
        print(f"ERROR staging lead: {e}")
        return None
