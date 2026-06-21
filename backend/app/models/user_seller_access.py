from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class UserSellerAccess(Base):
    __tablename__ = "user_seller_access"

    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    seller_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("sellers.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="admin")
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship("User", back_populates="seller_accesses")
    seller: Mapped["Seller"] = relationship("Seller", back_populates="user_accesses")
