from datetime import datetime
from typing import Optional
from uuid import uuid4
from sqlalchemy import Boolean, DateTime, ForeignKey, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class ListingImage(Base):
    __tablename__ = "listing_images"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    listing_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("listings.id"), nullable=False)
    freepik_job_id: Mapped[Optional[str]] = mapped_column(String(200))
    url_r2: Mapped[Optional[str]] = mapped_column(Text)
    ml_picture_id: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="generating")
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="individual")
    source_sku: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    r2_write_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    listing: Mapped["Listing"] = relationship("Listing", back_populates="images")
