from datetime import datetime
from typing import Optional
from uuid import uuid4
from sqlalchemy import Boolean, DateTime, ForeignKey, LargeBinary, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base

# --------------------------------------------------------------------------
# Vocabulario da coluna `kind`. Mora aqui, no model, porque mais de um modulo
# (services de variante, worker de imagens, listing_service) precisa decidir
# comportamento a partir do MESMO conjunto de valores — duplicar as strings em
# cada call site foi exatamente o que permitiu que os dois pontos de aprovacao
# em massa esquecessem os candidatos.
# --------------------------------------------------------------------------
COVER_DETERMINISTIC_KIND = "cover_deterministic"
COVER_AI_KIND = "cover_ai"
SPECS_AI_KIND = "specs_ai"

# Unicos kinds que podem ocupar sort_order=0. `promote_cover` valida o alvo
# contra este conjunto E restringe a ele o rebaixamento: uma foto `individual`
# aprovada pelo operador como capa (approve_images atribui sort_order=0 a
# primeira da lista) jamais pode ser despublicada por uma promocao de capa.
PROMOTABLE_COVER_KINDS = frozenset({COVER_DETERMINISTIC_KIND, COVER_AI_KIND})

# Candidatos gerados por IA SOB DEMANDA (Frentes A e B). Nascem
# `approved=False` em sort_order 90/91 e so viram capa por acao humana
# explicita. Toda aprovacao em massa (worker batch, bulk_approve_images) TEM
# de exclui-los: aprovado + ml_picture_id e o filtro que monta o payload de
# fotos da publicacao, entao um candidato aprovado por engano vai ao ar no
# anuncio real.
CANDIDATE_KINDS = frozenset({COVER_AI_KIND, SPECS_AI_KIND})


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
