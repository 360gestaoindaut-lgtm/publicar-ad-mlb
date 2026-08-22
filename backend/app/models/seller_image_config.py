import uuid
from typing import Optional
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class SellerImageConfig(Base, TimestampMixin):
    __tablename__ = "seller_image_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    raw_base_url: Mapped[str] = mapped_column(Text, nullable=False)
    write_bucket_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    write_endpoint_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    write_access_key_id_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    write_secret_access_key_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
