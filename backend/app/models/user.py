from uuid import uuid4
from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    seller_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sellers.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="operator")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    seller: Mapped["Seller"] = relationship("Seller", back_populates="users")
    listings: Mapped[list["Listing"]] = relationship(
        "Listing", back_populates="created_by_user", foreign_keys="[Listing.created_by]"
    )
