"""Frente A: variante ambientada da capa, gerada sob demanda por IA.

Nada aqui roda automaticamente — o pipeline batch/manual continua produzindo
a capa por `_try_i2i_generation` (recorte determinístico, sem custo de IA)
exatamente como hoje. Este serviço só é acionado quando um humano chama o
endpoint dedicado, revisa o resultado e decide se ele deve virar a capa
publicada (a promoção — `promote_cover`, abaixo — também é Frente A).

A variante parte SEMPRE dos bytes que já subiram para o ML na capa
determinística (`ListingImage.image_bytes`), nunca de uma re-derivação da foto
bruta — o seller pode ter trocado a foto depois, e nesse caso a variante
precisa continuar fiel ao que está publicado, não ao que está no bucket hoje.
"""
import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import defer

from app.models.listing_image import (
    COVER_AI_KIND,
    COVER_DETERMINISTIC_KIND,
    PROMOTABLE_COVER_KINDS,
    ListingImage,
)

logger = logging.getLogger(__name__)

COVER_AI_SORT_ORDER = 90  # fora da faixa 0..N da galeria
COVER_SORT_ORDER = 0

# Reexportado do model para nao duplicar as strings do vocabulario de `kind`.
_PROMOTABLE_KINDS = PROMOTABLE_COVER_KINDS


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


async def _load_latest_deterministic_cover(db, listing):
    """A capa deterministica MAIS RECENTE que tenha bytes salvos.

    Nao usa `scalar_one_or_none`: um anuncio pode ter VARIAS linhas
    `cover_deterministic`. Nada no sistema apaga `ListingImage`, e cada
    passada de `_try_i2i_generation` insere uma — inclusive uma linha
    `validation_failed` com `image_bytes=None` quando a QA reprova. Uma
    segunda passada (retry_pipeline -> submit_attributes -> generate_images,
    ou `confirm_image_engine("retry_openai")`) cria a segunda linha, e ai
    `scalar_one_or_none` estouraria `MultipleResultsFound` — um 500 opaco no
    lugar do 409 deliberado.

    `image_bytes.isnot(None)` exclui as linhas sem bytes (que nunca serviriam
    de origem para a variante), e `created_at DESC` escolhe a capa mais nova
    — que e a que esta publicada e, portanto, a certa para variar.

    Esta e a UNICA query de `ListingImage` que carrega `image_bytes` de
    proposito: e aqui que os bytes sao consumidos.
    """
    return (
        await db.execute(
            select(ListingImage)
            .where(
                ListingImage.listing_id == listing.id,
                ListingImage.kind == COVER_DETERMINISTIC_KIND,
                ListingImage.image_bytes.isnot(None),
            )
            .order_by(ListingImage.created_at.desc())
            .limit(1)
        )
    ).scalars().first()


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

    cover = await _load_latest_deterministic_cover(db, listing)

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


async def promote_cover(db, listing, image_id: UUID) -> None:
    """Troca qual imagem ocupa sort_order=0 na galeria (Frente A).

    A imagem alvo precisa ser deste anuncio e ter `kind` em
    `{"cover_deterministic", "cover_ai"}` — senao 422 (ex.: tentar promover
    uma foto `individual` ou de `card`). Se o `image_id` nao pertencer a este
    anuncio, 404 (mesma semantica de "nao encontrado" usada em
    `ListingService.get_or_404`).

    A imagem promovida passa a `approved=True, sort_order=0`. Toda linha de
    kind PROMOVIVEL que hoje ocupa `sort_order=0` e nao e o alvo volta a ser
    candidata (`approved=False, sort_order=COVER_AI_SORT_ORDER`) — nunca e
    apagada, so troca de lugar, pra o operador poder promover de volta
    depois. As demais imagens da galeria (individuais, cards) nao sao
    tocadas.

    O filtro por `kind` no rebaixamento NAO e cosmetico: `sort_order=0` nao
    e exclusividade das capas. `ListingService.approve_images` reatribui
    `sort_order` pela ordem de `approved_ids`, entao a PRIMEIRA imagem
    aprovada pelo operador fica em 0 — e ela costuma ser uma `individual`.
    Sem o filtro, promover uma `cover_ai` rebaixaria essa foto para
    `approved=False, sort_order=90`, removendo silenciosamente do anuncio
    uma foto que ja esta publicada.

    Alem do filtro na query, o laco confere o `kind` de cada linha antes de
    escrever: rebaixar e uma escrita destrutiva (despublica uma foto), entao
    a regra e verificada onde a mutacao acontece, e nao so onde as linhas
    sao lidas.

    Rebaixa TODAS as linhas de capa em sort_order=0 (nao so "a" capa atual,
    via `scalar_one_or_none`), porque duas requisicoes concorrentes de promocao
    no mesmo anuncio (duplo clique, retry, duas abas) podem terminar com mais
    de uma imagem em sort_order=0 — sem isso, a proxima chamada estouraria
    `MultipleResultsFound`, um 500 opaco. Rebaixar a lista inteira faz a
    funcao se autocurar: se o estado ja estiver corrompido, a proxima
    promocao conserta em vez de quebrar.

    `with_for_update()` bloqueia essas linhas ate o commit (ou rollback)
    desta transacao, serializando promocoes concorrentes no mesmo anuncio —
    e o que impede a corrida acima de acontecer dai em diante (o
    autocuramento cobre o estado que uma corrida ANTERIOR a este guard possa
    ter deixado para tras).

    Idempotente: promover quem ja esta em sort_order=0 e sem duplicatas para
    rebaixar e um no-op (nao escreve no banco).
    """
    target = (
        await db.execute(
            select(ListingImage)
            .options(defer(ListingImage.image_bytes))
            .where(
                ListingImage.id == image_id,
                ListingImage.listing_id == listing.id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()

    if target is None:
        raise HTTPException(status_code=404, detail="Imagem nao encontrada neste anuncio")

    if target.kind not in _PROMOTABLE_KINDS:
        raise HTTPException(
            status_code=422,
            detail="Somente a capa deterministica ou a variante gerada por IA podem ser promovidas a capa",
        )

    others_at_cover = (
        await db.execute(
            select(ListingImage)
            .options(defer(ListingImage.image_bytes))
            .where(
                ListingImage.listing_id == listing.id,
                ListingImage.sort_order == COVER_SORT_ORDER,
                ListingImage.kind.in_(_PROMOTABLE_KINDS),
                ListingImage.id != target.id,
            )
            .order_by(ListingImage.id)
            .with_for_update()
        )
    ).scalars().all()

    changed = False
    demoted_ids = []

    for demoted in others_at_cover:
        # Guard redundante de proposito: a query ja filtra, mas rebaixar
        # despublica uma foto, entao a regra vale onde a escrita acontece.
        if demoted.kind not in _PROMOTABLE_KINDS:
            continue
        demoted.approved = False
        demoted.sort_order = COVER_AI_SORT_ORDER
        demoted_ids.append(demoted.id)
        changed = True

    if target.sort_order != COVER_SORT_ORDER or not target.approved:
        target.approved = True
        target.sort_order = COVER_SORT_ORDER
        changed = True

    if not changed:
        return

    await db.commit()
    logger.info(
        "cover_promote listing_id=%s promoted_id=%s demoted_ids=%s",
        listing.id,
        target.id,
        demoted_ids,
    )
