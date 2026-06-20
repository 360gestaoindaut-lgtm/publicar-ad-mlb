from datetime import datetime
from typing import Optional
from uuid import uuid4
from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class ListingAttribute(Base):
    __tablename__ = "listing_attributes"
    __table_args__ = (UniqueConstraint("listing_id", "attribute_id", name="uq_listing_attribute"),)

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    listing_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("listings.id"), nullable=False)
    attribute_id: Mapped[str] = mapped_column(String(100), nullable=False)
    attribute_name: Mapped[str] = mapped_column(String(200), nullable=False)
    value_id: Mapped[Optional[str]] = mapped_column(String(200))
    value_name: Mapped[Optional[str]] = mapped_column(String(500))
    attribute_type: Mapped[str] = mapped_column(String(30), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source: Mapped[str] = mapped_column(String(10), nullable=False)  # 'ai' ou 'seller'
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    listing: Mapped["Listing"] = relationship("Listing", back_populates="attributes")
