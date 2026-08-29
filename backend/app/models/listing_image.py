from datetime import datetime
from typing import Optional
from uuid import uuid4
from sqlalchemy import Boolean, DateTime, ForeignKey, LargeBinary, SmallInteger, String, Text, func
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
    validation_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Bytes exatos que subiram para o ML, guardados para que variantes por IA
    # partam do MESMO arquivo publicado — nao de uma re-derivacao. Re-derivar seria
    # identico enquanto a foto bruta nao mudasse, mas o seller PODE trocar a foto
    # (aconteceu com 37-2.jpg), e ai a variante sairia de uma imagem diferente da
    # que esta no anuncio, sem ninguem perceber. Nullable, sem backfill: registros
    # antigos ficam com NULL. Hoje populam esta coluna: `cover_deterministic`
    # (sempre), `cover_ai` e `specs_ai` (candidatos por IA, quando o upload
    # da variante tem sucesso) — nao populam: `individual`, `card_benefits`,
    # `card_usage`, `card_specs`.
    image_bytes: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)

    # Tempo que um humano levou conferindo a versao gerada por IA contra o dado
    # real. Instrumentacao manual, amostra de 10-15 SKUs — nao e analytics.
    review_seconds: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)

    listing: Mapped["Listing"] = relationship("Listing", back_populates="images")
