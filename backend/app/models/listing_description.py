from datetime import datetime
from uuid import uuid4
from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class ListingDescription(Base):
    __tablename__ = "listing_descriptions"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    listing_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listings.id"), nullable=False, unique=True
    )
    description_html: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    listing: Mapped["Listing"] = relationship("Listing", back_populates="description")
