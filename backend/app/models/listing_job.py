from datetime import datetime
from typing import Optional
from uuid import uuid4
from sqlalchemy import DateTime, ForeignKey, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class ListingJob(Base):
    __tablename__ = "listing_jobs"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    listing_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("listings.id"), nullable=False)
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    payload_in: Mapped[Optional[dict]] = mapped_column(JSONB)
    payload_out: Mapped[Optional[dict]] = mapped_column(JSONB)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    listing: Mapped["Listing"] = relationship("Listing", back_populates="jobs")
