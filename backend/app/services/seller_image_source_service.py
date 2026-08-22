import httpx

RAW_PHOTOS_PER_SKU = 2


async def resolve_listing_skus(listing) -> list[str]:
    """Resolve a lista de SKUs componentes do anúncio. Hoje um anúncio sempre
    mapeia para exatamente 1 SKU; retorna uma lista para que os chamadores já
    estejam prontos para quando um projeto de kit fizer isso retornar mais
    de um SKU."""
    return [listing.sku_external_id] if listing.sku_external_id else []


async def fetch_raw_photos(raw_base_url: str, sku: str) -> list[bytes] | None:
    """Baixa as 2 fotos brutas de um SKU a partir do bucket do seller. Retorna
    None se qualquer uma das 2 fotos esperadas estiver faltando ou falhar —
    os chamadores devem tratar isso como "sem fotos brutas disponíveis"."""
    urls = [f"{raw_base_url}/{sku}-{n}.jpg" for n in range(1, RAW_PHOTOS_PER_SKU + 1)]
    photos: list[bytes] = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        for url in urls:
            try:
                resp = await client.get(url)
            except httpx.HTTPError:
                return None
            if resp.status_code != 200:
                return None
            photos.append(resp.content)
    return photos


async def fetch_all_raw_photos(raw_base_url: str, skus: list[str]) -> dict[str, list[bytes]] | None:
    """Busca as fotos brutas de todos os SKUs da lista. Tudo ou nada: retorna
    None se QUALQUER SKU estiver sem as 2 fotos brutas."""
    result: dict[str, list[bytes]] = {}
    for sku in skus:
        photos = await fetch_raw_photos(raw_base_url, sku)
        if photos is None:
            return None
        result[sku] = photos
    return result
