from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4
from sqlalchemy import DateTime, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin


class BatchImport(Base, TimestampMixin):
    __tablename__ = "batch_imports"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    seller_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sellers.id"), nullable=False, index=True)
    created_by: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    rows: Mapped[list["BatchImportRow"]] = relationship(
        "BatchImportRow", back_populates="batch", cascade="all, delete-orphan"
    )


class BatchImportRow(Base):
    __tablename__ = "batch_import_rows"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("batch_imports.id"), nullable=False, index=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    listing_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("listings.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    raw_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    batch: Mapped["BatchImport"] = relationship("BatchImport", back_populates="rows")
