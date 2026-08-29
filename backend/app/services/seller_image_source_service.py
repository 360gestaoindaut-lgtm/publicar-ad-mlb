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
