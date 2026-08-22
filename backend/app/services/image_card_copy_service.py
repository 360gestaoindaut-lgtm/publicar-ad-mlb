"""Copy (titulo + bullets) dos 3 cards de imagem, gerada por LLM.

Modulo separado de `image_deterministic_service.py` de proposito: aquele
modulo e sobre recorte de pixels, este e sobre texto. Nao ha relacao entre
os dois alem de ambos alimentarem o mesmo pipeline de imagens.

Roda ANTES de `generate_description` no pipeline (SPEC-006), entao a
materia-prima disponivel e so o titulo escolhido, a descricao do ERP, marca,
modelo e os atributos ja confirmados — nada de descricao gerada, nada de
preco/estoque. O prompt (`build_card_copy_prompt`) carrega a regra de nao
inventar especificacao tecnica porque esse material de origem e magro.

O servico NAO confia no LLM: toda resposta passa por saneamento estrito
antes de virar `CardCopy`. Qualquer falha — do provider, de rede, de JSON,
de formato — e engolida e vira lista vazia, nunca excecao. O anuncio tem que
seguir publicavel mesmo sem os cards.
"""
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Ordem = sort_order das imagens de card no anuncio.
CARD_KINDS = ("card_benefits", "card_usage", "card_specs")

_KEY_BY_KIND = {
    "card_benefits": "benefits",
    "card_usage": "usage",
    "card_specs": "specs",
}

MAX_TITLE_CHARS = 40
MAX_BULLET_CHARS = 50
MIN_BULLETS = 2
MAX_BULLETS = 3


@dataclass(frozen=True)
class CardCopy:
    kind: str          # um de CARD_KINDS
    title: str
    bullets: list[str]


def _truncate(text: str, max_chars: int) -> str:
    """Corta `text` em `max_chars`, preferindo o limite de palavra.

    Se der para cortar num espaco dentro do limite, corta ali (sem deixar
    fragmento de palavra pendurado). Se a primeira "palavra" sozinha ja
    estoura o limite, corta seco — sem reticencias, pra nao deixar marcador
    de truncamento orfao no meio da palavra.
    """
    text = text.strip()
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        return truncated[:last_space].rstrip()
    return truncated


def _build_source(listing, attributes: list | None) -> dict:
    """Monta o dicionario de origem para o prompt de copy dos cards.

    Só o que já existe nesse ponto do pipeline: titulo escolhido, descricao
    do ERP, marca, modelo e atributos com valor confirmado. Sem preco nem
    estoque — nao tem relacao com a copy dos cards e so daria mais material
    para o LLM tentar (erradamente) transformar em "beneficio".
    """
    attrs = [
        {"attribute_name": a.attribute_name, "value_name": a.value_name}
        for a in (attributes or [])
        if getattr(a, "value_name", None)
    ]
    return {
        "selected_title": listing.selected_title,
        "sku_description": listing.sku_description,
        "sku_brand": listing.sku_brand,
        "sku_model": listing.sku_model,
        "attributes": attrs,
    }


def _sanitize_angle(kind: str, raw_angle) -> "CardCopy | None":
    """Valida e normaliza um angulo (benefits/usage/specs) devolvido pelo LLM.

    Devolve None (angulo descartado) para qualquer coisa que nao vira um
    card publicavel — melhor um card a menos do que um card com titulo vazio
    ou bullet apagado.
    """
    if not isinstance(raw_angle, dict):
        logger.info("card_copy kind=%s result=dropped reason=formato_invalido", kind)
        return None

    title = raw_angle.get("title")
    if not isinstance(title, str) or not title.strip():
        logger.info("card_copy kind=%s result=dropped reason=titulo_vazio", kind)
        return None
    title = _truncate(title, MAX_TITLE_CHARS)

    bullets_raw = raw_angle.get("bullets")
    bullets: list[str] = []
    if isinstance(bullets_raw, list):
        for item in bullets_raw:
            if not isinstance(item, str) or not item.strip():
                continue
            bullets.append(_truncate(item, MAX_BULLET_CHARS))
            if len(bullets) >= MAX_BULLETS:
                break

    if len(bullets) < MIN_BULLETS:
        logger.info(
            "card_copy kind=%s result=dropped reason=bullets_insuficientes count=%s",
            kind, len(bullets),
        )
        return None

    return CardCopy(kind=kind, title=title, bullets=bullets)


async def generate_card_copy(listing, attributes: list | None = None) -> list["CardCopy"]:
    """Copy dos 3 cards, na ordem de CARD_KINDS.

    Resiliente por angulo: um angulo ruim e descartado, os outros seguem.
    Resiliente no todo: qualquer excecao (provider, HTTP, JSON, chave
    faltando) vira log + lista vazia. Nunca levanta excecao — o pipeline de
    imagens nao pode travar por causa de copy de card.
    """
    from app.services.ai.service import get_ai_provider

    try:
        source = _build_source(listing, attributes)
        provider = get_ai_provider()
        raw = await provider.generate_card_copy(source)
    except Exception as exc:
        logger.warning(
            "card_copy listing_id=%s result=failed reason=%s",
            getattr(listing, "id", None), exc,
        )
        return []

    if not isinstance(raw, dict):
        logger.warning(
            "card_copy listing_id=%s result=failed reason=resposta_nao_e_dict",
            getattr(listing, "id", None),
        )
        return []

    results: list[CardCopy] = []
    for kind in CARD_KINDS:
        angle = _sanitize_angle(kind, raw.get(_KEY_BY_KIND[kind]))
        if angle is not None:
            results.append(angle)
    return results
