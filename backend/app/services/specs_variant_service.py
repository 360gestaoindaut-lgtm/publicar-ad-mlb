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
    """Prompt do card de ficha tecnica, na linguagem visual APROVADA no piloto.

    A referencia sao os `card-01..08` gerados por `~/Desktop/piloto-cards-ia/
    gerar.py` e validados pelo Gabriel: bloco de cor amostrado do proprio
    produto, textura de papel, luz radial suave, painel neutro embaixo com
    titulo dominante e cada linha precedida de um icone de linha ilustrado.

    Duas adaptacoes conscientes em relacao ao piloto — copiar literalmente
    daria um card pior:

    1. QUADRADO, nao 3:4. O piloto rodou com `size="768x1024"`, mas
       `OpenAIEditEngine` pede sempre o maior QUADRADO do modelo (1200x1200
       no gpt-image-2) e `_prepare_image_for_upload` normaliza para quadrado
       de qualquer forma. Um 3:4 chegaria ao ML com tarja branca em cima e
       embaixo. As proporcoes de "dois tercos / um terco" viram ~60/40.

    2. O piloto tinha 3 bullets de BENEFICIO redigidos a mao, com icone
       nomeado um a um ("a droplet, a brand seal, a bottle"). Aqui o conteudo
       e ficha tecnica ("Rotulo: valor", 2 a 3 linhas, ate 50 chars), e os
       atributos variam por categoria — nao da para nomear o icone de cada
       linha, entao a instrucao pede um icone cujo sentido acompanhe a linha.

    A clausula CRITICAL vem do piloto palavra por palavra: e a licao da Fase
    5c, quando o motor reescreveu "100ml" como "160ml" e "wepink" como
    "weoink" num anuncio real.

    O QUE MUDOU EM RELACAO AO PROMPT ANTERIOR, e por que: o prompt anterior
    pedia "no clutter, no extra decorative elements" e proibia "relight" e
    "unrelated backgrounds". Isso e o oposto do estilo aprovado, que TROCA o
    fundo por um bloco de cor e RE-ILUMINA a cena. Manter as duas coisas
    juntas seria a mesma auto-contradicao que fazia a Frente A ser reprovada
    por construcao (ver `_pick_prompt` em `cover_variant_service`): pedir ao
    motor exatamente aquilo que a instrucao seguinte proibe. A fidelidade que
    importa — forma, cor e TEXTO IMPRESSO do produto — continua exigida; o
    que se liberou explicitamente foi so a encenacao ao redor dele.
    """
    linhas = "\n".join(f'  {i}. "{b}"' for i, b in enumerate(bullets, start=1))
    return (
        "Design a premium e-commerce specification card in SQUARE format for a\n"
        "product listing, built around the product in the reference image.\n\n"
        "LAYOUT\n"
        "- Upper ~60%: the product from the reference image, standing on a soft\n"
        "  studio surface with a gentle contact shadow, filling the space\n"
        "  confidently.\n"
        "- Background behind the product: a large colour block sampled from the\n"
        "  product itself, with a subtle paper-like texture and a soft radial\n"
        "  light behind it. Not flat white.\n"
        "- Lower ~40%: a clean panel in a light neutral tone that contrasts with\n"
        "  the colour block, holding the title and the specification lines.\n\n"
        "TEXT TO RENDER (Brazilian Portuguese, exactly as written, verbatim —\n"
        "do not translate, paraphrase, correct, reorder or invent additional\n"
        "specifications)\n"
        f'- Headline, large and bold: "{title}"\n'
        "- Specification lines, each preceded by a small illustrated line icon\n"
        "  whose meaning matches that line:\n"
        f"{linhas}\n\n"
        "TYPOGRAPHY\n"
        "- Modern geometric sans-serif. Clear hierarchy: headline dominant,\n"
        "  specification lines calm and readable. Generous margins. Nothing\n"
        "  cropped at the edges.\n\n"
        "ALLOWED — staging around the product: replace the background with the\n"
        "colour block described above, add studio lighting and a contact shadow,\n"
        "and adjust framing.\n\n"
        "FORBIDDEN — the product must keep its identity: do not reshape, recolor\n"
        "or re-proportion the product body; do not add, remove or move any\n"
        "object; no props, hands, logos, watermarks, prices or badges, and no\n"
        "decorative elements beyond the icons and the panel described above.\n\n"
        "CRITICAL: do not alter, redraw, translate, correct or re-render ANY text\n"
        "printed on the product or its packaging. Brand names, product names, volumes\n"
        "and measurement units must be preserved exactly as they appear, character for\n"
        "character. Never change a number or a unit. If any text is unreadable, keep it\n"
        "unreadable rather than inventing plausible text.\n\n"
        "The product must remain recognisable as the same physical unit from the\n"
        "reference photograph, now composed into a finished specification card."
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
