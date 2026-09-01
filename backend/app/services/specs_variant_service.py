"""Frente B: ficha tecnica renderizada por IA, gerada sob demanda.

Nada aqui roda automaticamente — o pipeline batch/manual continua produzindo
o `card_specs` por `_append_benefit_cards` (composicao Pillow, sem custo de
IA) exatamente como hoje. Este servico so e acionado quando um humano chama
o endpoint dedicado; o resultado e um CANDIDATO para comparacao A/B com o
`card_specs` ja existente, nunca uma substituicao automatica.

A ficha tecnica IA parte SEMPRE dos bytes que ja subiram para o ML na capa
deterministica (`ListingImage.image_bytes`, kind="cover_deterministic"),
nunca de uma foto bruta re-derivada nem do card Pillow ja renderizado —
mesma fonte e mesmo motivo da variante de capa (Frente A): a capa
deterministica nunca passou por IA, entao o rotulo do produto nela e fiel.

A copy (titulo + bullets) NAO e inventada aqui NEM por LLM: vem de
`build_specs_card`, que monta os bullets direto do `value_name` dos
atributos — o mesmo texto que o `card_specs` Pillow usa. O motor de IA entra
so para a composicao visual (foto + layout); o texto chega a ele pronto.

Antes esta funcao chamava `generate_card_copy` e dependia do LLM devolver um
angulo `card_specs` utilizavel. Isso somava um modo de falha ("a copy nao
veio, tente de novo") e, pior, punha texto estocastico numa ficha tecnica:
o tipo do perfume do SKU 37 saiu parafraseado numa execucao e correto em
outra. Ficha tecnica e dado, nao redacao.
"""
import logging

from sqlalchemy import select

from app.models.listing_attribute import ListingAttribute
from app.models.listing_image import SPECS_AI_KIND, ListingImage
from app.services.cover_variant_service import _load_latest_deterministic_cover

logger = logging.getLogger(__name__)

SPECS_AI_SORT_ORDER = 91  # fora da faixa 0..N da galeria, ao lado de COVER_AI_SORT_ORDER=90


class SpecsVariantError(RuntimeError):
    """Nao ha capa deterministica com bytes salvos, ou os atributos nao formam uma ficha."""


def _build_specs_prompt(title: str, bullets: list[str]) -> str:
    """Prompt VERBATIM na estrutura da SPEC (Frente B) — mesma clausula
    CRITICAL de `cover_variant_service._COVER_PROMPT_RICH`, pelo mesmo motivo: o
    texto impresso no produto (marca, volume, unidade) nao pode ser
    reescrito pela IA so porque ela esta compondo um card ao redor dele.
    """
    bullets_block = "\n".join(f"- {b}" for b in bullets)
    return (
        "Compose a technical-specs card for an e-commerce product listing,\n"
        "using this exact product photo as the visual anchor.\n\n"
        f'Render the title "{title}" prominently, and below or beside it these\n'
        "bullet points as a clean vertical list, exactly as given, verbatim —\n"
        "do not translate, paraphrase, correct or invent additional specs:\n"
        f"{bullets_block}\n\n"
        "Layout: keep the product photo clearly visible and unobstructed; place\n"
        "the title and bullets in a legible text block, clean sans-serif font,\n"
        "high contrast, no clutter, no extra decorative elements.\n\n"
        "FORBIDDEN — the product itself must be pixel-faithful to the reference:\n"
        "do not redraw, reshape, recolor, rotate or relight the product body; do not\n"
        "add, remove or move any object; do not introduce props, hands or\n"
        "unrelated backgrounds.\n\n"
        "CRITICAL: do not alter, redraw, translate, correct or re-render ANY text\n"
        "printed on the product or its packaging. Brand names, product names, volumes\n"
        "and measurement units must be preserved exactly as they appear, character for\n"
        "character. Never change a number or a unit. If any text is unreadable, keep it\n"
        "unreadable rather than inventing plausible text.\n\n"
        "The result must be recognisable as the same photograph of the same physical\n"
        "unit, now composed into a clean specs card."
    )


async def generate_specs_variant(db, listing, access_token: str) -> ListingImage:
    """Gera 1 candidato de ficha tecnica IA a partir dos bytes SALVOS da capa.

    Levanta `SpecsVariantError` antes de tocar no motor de IA se: (a) nao
    houver capa deterministica com bytes salvos, ou (b) os atributos do
    anuncio nao renderem `MIN_BULLETS` linhas de ficha — nos dois casos um
    request que nao pode ter sucesso nao deve chamar um motor pago.
    """
    from app.services.image_card_copy_service import build_specs_card
    from app.services.image_engines.openai_edit_engine import OpenAIEditEngine
    from app.services.image_service import MLPictureService
    from app.workers.tasks.image_tasks import _prepare_image_for_upload

    # Mesma busca da Frente A, e pelo mesmo motivo: pode haver MAIS DE UMA
    # linha `cover_deterministic` (nada apaga ListingImage, e cada passada de
    # `_try_i2i_generation` insere uma, inclusive uma `validation_failed` sem
    # bytes). `scalar_one_or_none` estouraria `MultipleResultsFound` — 500
    # opaco no lugar do 409 deliberado. Ver o docstring do helper.
    cover = await _load_latest_deterministic_cover(db, listing)

    if cover is None or cover.image_bytes is None:
        raise SpecsVariantError(
            "capa deterministica sem bytes salvos — anuncio gerado antes desta funcionalidade"
        )

    # Query propria (nao `listing.attributes`): relacionamento lazy levantaria
    # MissingGreenlet fora de uma sessao com contexto async ativo — ver CLAUDE.md.
    attributes = (
        await db.execute(
            select(ListingAttribute).where(ListingAttribute.listing_id == listing.id)
        )
    ).scalars().all()

    specs_copy = build_specs_card(attributes)
    if specs_copy is None:
        raise SpecsVariantError(
            "atributos insuficientes para montar a ficha tecnica deste anuncio"
        )

    prompt = _build_specs_prompt(specs_copy.title, specs_copy.bullets)

    engine = OpenAIEditEngine()
    variants = await engine.edit(images=[cover.image_bytes], prompt=prompt, n=1)
    generated_bytes = variants[0]

    # Ficha tecnica nunca e capa, entao fundo branco puro nunca e exigido dela
    # — mesma regra ja aplicada aos cards Pillow em `_append_benefit_cards`.
    prepared, verdict = _prepare_image_for_upload(generated_bytes, requires_white_bg=False)

    if prepared is None:
        candidate = ListingImage(
            listing_id=listing.id,
            status="validation_failed",
            validation_error=verdict.reason,
            approved=False,
            sort_order=SPECS_AI_SORT_ORDER,
            kind=SPECS_AI_KIND,
            source_sku=cover.source_sku,
            # Mesma razao da Frente A: candidato reprovado continua revisavel.
            # Sem `ml_picture_id` — nada subiu para o ML.
            image_bytes=generated_bytes,
        )
        db.add(candidate)
        await db.commit()
        logger.info("specs_variant listing_id=%s result=rejected", listing.id)
        return candidate

    ml_pic = MLPictureService()
    ml_picture_id = await ml_pic.upload(prepared, access_token)

    candidate = ListingImage(
        listing_id=listing.id,
        ml_picture_id=ml_picture_id,
        status="uploaded",
        approved=False,
        sort_order=SPECS_AI_SORT_ORDER,
        kind=SPECS_AI_KIND,
        source_sku=cover.source_sku,
        image_bytes=prepared,
    )
    db.add(candidate)
    await db.commit()
    logger.info("specs_variant listing_id=%s result=uploaded", listing.id)
    return candidate
