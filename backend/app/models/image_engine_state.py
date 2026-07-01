from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4
from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ImageEngineState(Base):
    """Linha única (singleton) que guarda qual motor de geração de imagem está ativo."""
    __tablename__ = "image_engine_state"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    current_engine: Mapped[str] = mapped_column(String(20), nullable=False, default="openai")
    last_openai_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    last_switch_to_openai_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
