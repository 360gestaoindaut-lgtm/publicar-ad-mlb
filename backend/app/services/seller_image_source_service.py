import logging

import httpx

logger = logging.getLogger(__name__)

# Minimo OBRIGATORIO. Faltando `{sku}-1.jpg` ou `{sku}-2.jpg`, o SKU e tratado
# como "sem fotos brutas" e o pipeline cai no caminho antigo — comportamento
# inalterado desde sempre.
RAW_PHOTOS_MIN = 2

# Teto de sondagem. As fotos sao descobertas por tentativa (nao ha listagem no
# bucket publico), entao precisa de um limite para nao sondar indefinidamente.
# 10 cobre com folga o seller de operacao madura sem custar mais que 8
# requisicoes extras no pior caso.
RAW_PHOTOS_MAX = 10

# Mantido por compatibilidade: era o teto rigido antigo, hoje e so o minimo.
RAW_PHOTOS_PER_SKU = RAW_PHOTOS_MIN


async def resolve_listing_skus(listing) -> list[str]:
    """Resolve a lista de SKUs componentes do anúncio. Hoje um anúncio sempre
    mapeia para exatamente 1 SKU; retorna uma lista para que os chamadores já
    estejam prontos para quando um projeto de kit fizer isso retornar mais
    de um SKU."""
    return [listing.sku_external_id] if listing.sku_external_id else []


async def fetch_raw_photos(raw_base_url: str, sku: str) -> list[bytes] | None:
    """Descobre e baixa as fotos brutas de um SKU no bucket do seller.

    Sonda `{sku}-1.jpg`, `-2.jpg`, `-3.jpg`... ate o primeiro ausente ou ate
    `RAW_PHOTOS_MAX`. O bucket e publico e sem listagem, entao descobrir por
    tentativa e a unica forma de saber quantas fotos existem.

    As `RAW_PHOTOS_MIN` primeiras sao OBRIGATORIAS: faltando qualquer uma
    delas, devolve None e o SKU e tratado como "sem fotos brutas" — mesmo
    comportamento de antes. Da terceira em diante sao BONUS: a ausencia
    encerra a descoberta sem invalidar nada.

    Seller de operacao madura pode ter 3-10 fotos por SKU; o teto rigido de 2
    que existia antes ignorava todas as extras.
    """
    photos: list[bytes] = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        for n in range(1, RAW_PHOTOS_MAX + 1):
            obrigatoria = n <= RAW_PHOTOS_MIN
            url = f"{raw_base_url}/{sku}-{n}.jpg"
            try:
                resp = await client.get(url)
            except httpx.HTTPError as exc:
                if obrigatoria:
                    return None
                # Falha de rede numa foto extra e ambigua (pode ser
                # transitoria). Encerrar a descoberta e usar o que ja veio e
                # melhor que derrubar um SKU que tem o minimo.
                logger.warning(
                    "raw_photos sku=%s n=%s result=erro_rede_em_extra reason=%s",
                    sku, n, exc,
                )
                break
            if resp.status_code != 200:
                if obrigatoria:
                    return None
                break
            photos.append(resp.content)

    logger.info("raw_photos sku=%s encontradas=%s", sku, len(photos))
    return photos


async def fetch_all_raw_photos(raw_base_url: str, skus: list[str]) -> dict[str, list[bytes]] | None:
    """Busca as fotos brutas de todos os SKUs da lista. Tudo ou nada: retorna
    None se QUALQUER SKU estiver sem o minimo de fotos brutas."""
    result: dict[str, list[bytes]] = {}
    for sku in skus:
        photos = await fetch_raw_photos(raw_base_url, sku)
        if photos is None:
            return None
        result[sku] = photos
    return result


# Posição 4 do esquema de 5 posições — "Detalhes".
# Ver docs/superpowers/specs/esquema-5-posicoes.md.
#
# Regra deliberadamente simples: a 3ª foto, se existir. Não há heurística de
# "qual extra é a melhor para detalhe" e não deve haver por ora — decidir isso
# sem dado real de quantos sellers têm 3+ fotos seria inventar critério. É
# revisitável quando esse dado existir.
DETAIL_SOURCE_INDEX = 2  # 0-based: a 3ª foto


def pick_detail_source(photos: list[bytes]) -> tuple[bytes, bool]:
    """Escolhe a foto de origem da posição 4 ("Detalhes").

    Devolve `(foto, veio_de_extra)`. O segundo elemento importa: `True`
    significa fonte dedicada (uma foto que o seller subiu além do mínimo e que
    NÃO alimenta a posição 2); `False` significa que só existem as 2 mínimas e
    estamos reaproveitando — o chamador pode decidir tratar diferente, ou até
    pular a posição 4, em vez de forçar um "detalhe" que a foto não mostra.

    Não faz zoom nem recorte: só seleciona a fonte. O tratamento é do chamador.
    """
    if not photos:
        raise ValueError("pick_detail_source exige ao menos uma foto")

    if len(photos) > DETAIL_SOURCE_INDEX:
        return photos[DETAIL_SOURCE_INDEX], True

    # Só o mínimo: usa a última disponível. A posição 2 tende a sair da 1ª, então
    # pegar a última evita que as duas posições mostrem exatamente a mesma foto.
    return photos[-1], False
