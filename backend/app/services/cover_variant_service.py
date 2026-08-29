"""Frente A: variante ambientada da capa, gerada sob demanda por IA.

Nada aqui roda automaticamente — o pipeline batch/manual continua produzindo
a capa por `_try_i2i_generation` (recorte determinístico, sem custo de IA)
exatamente como hoje. Este serviço só é acionado quando um humano chama o
endpoint dedicado, revisa o resultado e decide se ele deve virar a capa
publicada (promoção é a Frente B, fora deste arquivo).

A variante parte SEMPRE dos bytes que já subiram para o ML na capa
determinística (`ListingImage.image_bytes`), nunca de uma re-derivação da foto
bruta — o seller pode ter trocado a foto depois, e nesse caso a variante
precisa continuar fiel ao que está publicado, não ao que está no bucket hoje.
"""
import logging

from sqlalchemy import select

from app.models.listing_image import ListingImage

logger = logging.getLogger(__name__)

COVER_AI_KIND = "cover_ai"
COVER_AI_SORT_ORDER = 90  # fora da faixa 0..N da galeria


class CoverVariantError(RuntimeError):
    """Nao ha capa deterministica com bytes salvos para este anuncio."""


# Prompt VERBATIM da SPEC (Frente A) — a cláusula CRITICAL não é enfeite, ver
# `_NO_TEXT_EDIT_RULE` em `image_tasks.py` para o precedente do mesmo risco.
_COVER_PROMPT = (
    "Place this exact product photo into a subtle studio environment.\n\n"
    "ALLOWED: replace the flat white background with a soft neutral gradient or a\n"
    "subtle surface texture; add gentle directional lighting and a soft contact\n"
    "shadow beneath the product; adjust framing margins only.\n\n"
    "FORBIDDEN — the product itself must be pixel-faithful to the reference:\n"
    "do not redraw, reshape, recolor, rotate or relight the product body; do not\n"
    "add, remove or move any object; do not introduce props, hands, backgrounds\n"
    "with objects, logos, badges, borders or decorative elements.\n\n"
    "CRITICAL: do not alter, redraw, translate, correct or re-render ANY text\n"
    "printed on the product or its packaging. Brand names, product names, volumes\n"
    "and measurement units must be preserved exactly as they appear, character for\n"
    "character. Never change a number or a unit. If any text is unreadable, keep it\n"
    "unreadable rather than inventing plausible text.\n\n"
    "The result must be recognisable as the same photograph of the same physical\n"
    "unit, only better lit and better staged."
)


async def generate_cover_variant(db, listing, access_token: str) -> ListingImage:
    """Gera 1 variante ambientada a partir dos bytes SALVOS da capa.

    Levanta `CoverVariantError` antes de tocar no motor de IA se não houver
    capa determinística com bytes salvos — chamar um motor pago para um
    request que não pode ter sucesso seria desperdício.
    """
    from app.services.image_engines.openai_edit_engine import OpenAIEditEngine
    from app.services.image_service import MLPictureService
    from app.workers.tasks.image_tasks import (
        _prepare_image_for_upload,
        _resolve_requires_white_bg,
    )

    # `.first()` em vez de `scalar_one_or_none()`: um listing com pipeline
    # reprocessado (retry) pode, em tese, acumular mais de uma linha
    # cover_deterministic — pegar a mais recente não quebra em vez de levantar
    # MultipleResultsFound por uma condição de dado alheia a esta feature.
    cover = (
        await db.execute(
            select(ListingImage)
            .where(
                ListingImage.listing_id == listing.id,
                ListingImage.kind == "cover_deterministic",
            )
            .order_by(ListingImage.created_at.desc())
        )
    ).scalars().first()

    if cover is None or cover.image_bytes is None:
        raise CoverVariantError(
            "capa deterministica sem bytes salvos — anuncio gerado antes desta funcionalidade"
        )

    engine = OpenAIEditEngine()
    variants = await engine.edit(images=[cover.image_bytes], prompt=_COVER_PROMPT, n=1)
    generated_bytes = variants[0]

    # A variante pode virar capa (sort_order=0) se for promovida, então a
    # mesma regra de fundo branco puro da capa vale para ela.
    requires_white_bg = await _resolve_requires_white_bg(listing)
    prepared, verdict = _prepare_image_for_upload(
        generated_bytes, requires_white_bg=requires_white_bg
    )

    if prepared is None:
        candidate = ListingImage(
            listing_id=listing.id,
            status="validation_failed",
            validation_error=verdict.reason,
            approved=False,
            sort_order=COVER_AI_SORT_ORDER,
            kind=COVER_AI_KIND,
            source_sku=cover.source_sku,
        )
        db.add(candidate)
        await db.commit()
        logger.info("cover_variant listing_id=%s result=rejected", listing.id)
        return candidate

    ml_pic = MLPictureService()
    ml_picture_id = await ml_pic.upload(prepared, access_token)

    candidate = ListingImage(
        listing_id=listing.id,
        ml_picture_id=ml_picture_id,
        status="uploaded",
        approved=False,
        sort_order=COVER_AI_SORT_ORDER,
        kind=COVER_AI_KIND,
        source_sku=cover.source_sku,
        image_bytes=prepared,
    )
    db.add(candidate)
    await db.commit()
    logger.info("cover_variant listing_id=%s result=uploaded", listing.id)
    return candidate
