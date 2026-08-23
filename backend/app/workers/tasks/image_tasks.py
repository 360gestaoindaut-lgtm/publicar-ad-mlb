import asyncio
import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _fetch_upload_token(seller, db) -> str:
    from app.services.publish_service import get_valid_access_token
    return await get_valid_access_token(seller, db)


def _prepare_image_for_upload(image_bytes: bytes, requires_white_bg: bool):
    """Padroniza para 1200x1200 e roda o QA do ML antes do upload.

    Devolve `(bytes_prontos, veredito)`. Se o veredito reprovar, os bytes vêm
    None e o chamador registra a linha em listing_images sem subir nada.
    """
    from app.services.image_postprocess_service import normalize_to_square
    from app.services.image_service import ImageValidationResult, validate_image

    normalized = normalize_to_square(image_bytes)
    if normalized is None:
        return None, ImageValidationResult(
            is_valid=False, errors=["bytes não são uma imagem válida"]
        )

    verdict = validate_image(normalized, category_requires_white_bg=requires_white_bg)
    if not verdict.is_valid:
        return None, verdict
    return normalized, verdict


async def _resolve_requires_white_bg(listing) -> bool:
    """Se a categoria-raiz do anúncio exige fundo branco puro na capa."""
    from app.services.category_service import category_requires_white_background
    return await category_requires_white_background(listing.ml_category_id)


async def _append_benefit_cards(
    db, listing, access_token: str, base_photo: bytes, source_sku: str, start_sort_order: int
) -> int:
    """Gera os 3 cards de texto a partir da 1a foto individual bem-sucedida.

    Devolve quantos cards subiram. Nunca levanta: qualquer falha vira log e
    zero cards — o anúncio não pode cair por causa de um card.
    """
    from sqlalchemy import select

    from app.models.listing_attribute import ListingAttribute
    from app.models.listing_image import ListingImage
    from app.services.image_benefit_card_service import render_benefit_card
    from app.services.image_card_copy_service import generate_card_copy
    from app.services.image_service import MLPictureService

    try:
        # Query própria: tocar `listing.attributes` (relacionamento lazy) aqui
        # dentro levantaria MissingGreenlet — ver CLAUDE.md.
        attributes = (
            await db.execute(
                select(ListingAttribute).where(ListingAttribute.listing_id == listing.id)
            )
        ).scalars().all()
        cards = await generate_card_copy(listing, attributes)
    except Exception as exc:
        logger.warning(
            "benefit_cards listing_id=%s sku=%s result=failed reason=%s",
            listing.id,
            source_sku,
            exc,
        )
        return 0

    ml_pic = MLPictureService()
    saved = 0
    for card in cards:
        try:
            card_bytes = render_benefit_card(base_photo, card.title, card.bullets)
            # Card nunca é capa, então fundo branco puro nunca é exigido dele.
            prepared, verdict = _prepare_image_for_upload(card_bytes, requires_white_bg=False)
            if prepared is None:
                logger.warning(
                    "benefit_cards listing_id=%s sku=%s kind=%s result=rejected reason=%s",
                    listing.id,
                    source_sku,
                    card.kind,
                    verdict.reason,
                )
                continue
            ml_picture_id = await ml_pic.upload(prepared, access_token)
            db.add(ListingImage(
                listing_id=listing.id,
                ml_picture_id=ml_picture_id,
                status="uploaded",
                sort_order=start_sort_order + saved,
                kind=card.kind,
                source_sku=source_sku,
            ))
            saved += 1
        except Exception as exc:
            # Um card que falha não derruba os outros nem as imagens já salvas.
            logger.warning(
                "benefit_cards listing_id=%s sku=%s kind=%s result=failed reason=%s",
                listing.id,
                source_sku,
                card.kind,
                exc,
            )

    logger.info(
        "benefit_cards listing_id=%s sku=%s requested=%s saved=%s",
        listing.id,
        source_sku,
        len(cards),
        saved,
    )
    return saved


async def _try_i2i_generation(db, listing, seller, access_token: str) -> int | None:
    """Tenta o caminho image-to-image (fotos brutas reais do seller). Retorna
    None se o seller não tiver SellerImageConfig ou faltar alguma foto bruta
    — nesses casos o chamador deve cair no texto-imagem existente, inalterado."""
    from sqlalchemy import select
    from app.models.seller_image_config import SellerImageConfig
    from app.models.listing_image import ListingImage
    from app.models.product_image import ProductImage
    from app.services.seller_image_source_service import resolve_listing_skus, fetch_all_raw_photos
    from app.services.image_engines.openai_edit_engine import OpenAIEditEngine
    from app.services.image_service import MLPictureService

    config = (
        await db.execute(
            select(SellerImageConfig).where(SellerImageConfig.seller_id == listing.seller_id)
        )
    ).scalar_one_or_none()
    if config is None:
        return None

    skus = await resolve_listing_skus(listing)
    if not skus:
        return None

    raw_photos_by_sku = await fetch_all_raw_photos(config.raw_base_url, skus)
    if raw_photos_by_sku is None:
        return None

    treatment_prompt = (
        "Professional e-commerce product photo. Pure white background, "
        "studio lighting, product centered and isolated, no text, no watermark, "
        "no people. Keep the exact product from the reference image — same "
        "shape, color, materials and proportions — only improve background, "
        "lighting and framing."
    )

    engine = OpenAIEditEngine()
    ml_pic = MLPictureService()
    saved = 0
    # Fundo branco só é exigido na capa (sort_order 0) — as demais imagens
    # podem ter fundo contextual mesmo nas categorias com padronização rígida.
    requires_white_bg = await _resolve_requires_white_bg(listing)

    # Capa composta — só quando o anúncio tem mais de 1 SKU. Falha na
    # composição não afeta as imagens individuais: a capa é simplesmente
    # pulada, e a 1a imagem individual assume a posição de capa por ordem
    # natural do array `pictures` (sort_order=0).
    if len(skus) > 1:
        all_raw_photos = [photo for sku in skus for photo in raw_photos_by_sku[sku]]
        cover_prompt = (
            "Professional e-commerce product photo showing all the items from "
            "the reference images together, composed in a single realistic scene. "
            "Pure white background, studio lighting, items clearly visible and "
            "proportionate to each other, no text, no watermark, no people."
        )
        try:
            cover_variants = await engine.edit(images=all_raw_photos, prompt=cover_prompt, n=1)
        except Exception:
            cover_variants = []

        for img_bytes in cover_variants:
            prepared, verdict = _prepare_image_for_upload(
                img_bytes, requires_white_bg=requires_white_bg and saved == 0
            )
            if prepared is None:
                db.add(ListingImage(
                    listing_id=listing.id,
                    status="validation_failed",
                    validation_error=verdict.reason,
                    sort_order=saved,
                    kind="cover_composed",
                    source_sku=None,
                ))
                continue
            ml_picture_id = await ml_pic.upload(prepared, access_token)
            db.add(ListingImage(
                listing_id=listing.id,
                ml_picture_id=ml_picture_id,
                status="uploaded",
                sort_order=saved,
                kind="cover_composed",
                source_sku=None,
            ))
            saved += 1

    # Capa determinística — só para 1 SKU, e antes do loop pago. Se a foto
    # bruta tiver fundo uniforme, a capa sai por recorte, sem custo de IA. Se
    # não der, `saved` continua 0 e tudo segue exatamente como antes.
    if len(skus) == 1:
        from app.services.image_deterministic_service import try_deterministic_cover

        only_sku = skus[0]
        cover_bytes = try_deterministic_cover(raw_photos_by_sku[only_sku][0])
        # Sinal binário de acerto/erro para medir a taxa real em produção sem
        # instrumentar o serviço nem persistir nada.
        logger.info(
            "deterministic_cover listing_id=%s seller_id=%s sku=%s result=%s",
            listing.id,
            listing.seller_id,
            only_sku,
            "hit" if cover_bytes is not None else "miss",
        )
        if cover_bytes is not None:
            prepared, verdict = _prepare_image_for_upload(
                cover_bytes, requires_white_bg=requires_white_bg
            )
            if prepared is None:
                db.add(ListingImage(
                    listing_id=listing.id,
                    status="validation_failed",
                    validation_error=verdict.reason,
                    sort_order=saved,
                    kind="cover_deterministic",
                    source_sku=only_sku,
                ))
            else:
                ml_picture_id = await ml_pic.upload(prepared, access_token)
                db.add(ListingImage(
                    listing_id=listing.id,
                    ml_picture_id=ml_picture_id,
                    status="uploaded",
                    sort_order=saved,
                    kind="cover_deterministic",
                    source_sku=only_sku,
                ))
                db.add(ProductImage(
                    seller_id=listing.seller_id,
                    sku=only_sku,
                    ml_picture_id=ml_picture_id,
                    source="deterministic",
                    is_approved=False,
                ))
                saved += 1

    # Imagens individuais — sempre, uma chamada de edição por foto bruta.
    # A 1a que passa no QA e sobe vira a foto-base dos cards de texto.
    first_individual_bytes: bytes | None = None
    for sku in skus:
        for raw_photo in raw_photos_by_sku[sku]:
            variants = await engine.edit(images=[raw_photo], prompt=treatment_prompt, n=2)
            for img_bytes in variants:
                prepared, verdict = _prepare_image_for_upload(
                    img_bytes, requires_white_bg=requires_white_bg and saved == 0
                )
                if prepared is None:
                    db.add(ListingImage(
                        listing_id=listing.id,
                        status="validation_failed",
                        validation_error=verdict.reason,
                        sort_order=saved,
                        kind="individual",
                        source_sku=sku,
                    ))
                    continue
                ml_picture_id = await ml_pic.upload(prepared, access_token)

                db.add(ListingImage(
                    listing_id=listing.id,
                    ml_picture_id=ml_picture_id,
                    status="uploaded",
                    sort_order=saved,
                    kind="individual",
                    source_sku=sku,
                ))
                db.add(ProductImage(
                    seller_id=listing.seller_id,
                    sku=sku,
                    ml_picture_id=ml_picture_id,
                    source="openai_edit",
                    is_approved=False,
                ))
                saved += 1
                if first_individual_bytes is None:
                    first_individual_bytes = prepared

    # Cards de texto — só para 1 SKU e só se alguma individual subiu. Sem foto
    # individual não há base para compor o card, então o passo é pulado.
    if len(skus) == 1 and first_individual_bytes is not None:
        saved += await _append_benefit_cards(
            db,
            listing,
            access_token,
            base_photo=first_individual_bytes,
            source_sku=skus[0],
            start_sort_order=saved,
        )

    return saved


async def _generate_images_async(listing_id: str) -> dict:
    from sqlalchemy import select

    from app.database import worker_session
    from app.models.listing import Listing
    from app.models.listing_image import ListingImage
    from app.models.product_image import ProductImage
    from app.models.seller import Seller
    from app.services.ai.service import get_ai_provider
    from app.services.image_service import MLPictureService

    async with worker_session() as db:
        listing = (
            await db.execute(select(Listing).where(Listing.id == listing_id))
        ).scalar_one()

        # Guard de idempotência: se o status já avançou (retry ou dispatch duplo), abortar.
        if listing.status != "generating_images":
            return {"listing_id": listing_id, "skipped": True}

        sku = listing.sku_external_id or ""

        # Verifica se já existem imagens aprovadas para este SKU neste seller
        if sku:
            existing = (
                await db.execute(
                    select(ProductImage)
                    .where(
                        ProductImage.seller_id == listing.seller_id,
                        ProductImage.sku == sku,
                        ProductImage.is_approved == True,
                    )
                    .order_by(ProductImage.created_at.asc())
                )
            ).scalars().all()

            if existing:
                for i, pi in enumerate(existing):
                    db.add(ListingImage(
                        listing_id=listing.id,
                        ml_picture_id=pi.ml_picture_id,
                        status="uploaded",
                        approved=True,
                        sort_order=i,
                    ))
                if listing.created_via == "batch":
                    listing.status = "generating_description"
                    await db.commit()
                else:
                    listing.status = "pending_image_approval"
                    await db.commit()
                return {"listing_id": listing_id, "images_reused": len(existing)}

        # Sem imagens existentes — gera com IA
        from datetime import datetime, timezone
        from app.services.image_engines.base import ImageEngineUnavailableError
        from app.services.image_engines.openai_engine import check_openai_health
        from app.services.image_engines.service import get_engine_instance, get_engine_state

        seller = (
            await db.execute(select(Seller).where(Seller.id == listing.seller_id))
        ).scalar_one()
        access_token = await _fetch_upload_token(seller, db)

        i2i_saved = await _try_i2i_generation(db, listing, seller, access_token)
        if i2i_saved is not None:
            if i2i_saved == 0:
                raise RuntimeError("Nenhuma imagem válida foi gerada pelo motor 'openai_edit'")
            if listing.created_via == "batch":
                images = (await db.execute(
                    select(ListingImage).where(
                        ListingImage.listing_id == listing.id,
                        ListingImage.status == "uploaded",
                    )
                )).scalars().all()
                for img in images:
                    img.approved = True
                prod_imgs = (await db.execute(
                    select(ProductImage).where(
                        ProductImage.seller_id == listing.seller_id,
                        ProductImage.sku == sku,
                    )
                )).scalars().all()
                for pi in prod_imgs:
                    pi.is_approved = True
                listing.status = "generating_description"
                await db.commit()
            else:
                listing.status = "pending_image_approval"
                await db.commit()
            return {"listing_id": listing_id, "images_saved": i2i_saved, "source": "i2i"}

        engine_state = await get_engine_state(db)

        if engine_state.current_engine == "gemini" and await check_openai_health():
            engine_state.current_engine = "openai"
            engine_state.last_openai_error = None
            engine_state.last_switch_to_openai_at = datetime.now(timezone.utc)
            await db.commit()

        ai = get_ai_provider()
        prompt = await ai.generate_image_prompt(
            brand=listing.sku_brand,
            title=listing.selected_title or "",
            description=listing.sku_description,
        )

        engine = get_engine_instance(engine_state.current_engine)
        source_label = engine_state.current_engine

        try:
            raw_images = await engine.generate(prompt)
        except ImageEngineUnavailableError as exc:
            engine_state.last_openai_error = str(exc)[:500]
            await db.commit()
            listing.failed_step = listing.status
            listing.status = "pending_image_engine_confirmation"
            listing.error_message = str(exc)[:500]
            await db.commit()
            return {"listing_id": listing_id, "pending_image_engine_confirmation": True}

        ml_pic = MLPictureService()
        saved = 0
        requires_white_bg = await _resolve_requires_white_bg(listing)

        for img_bytes in raw_images:
            prepared, verdict = _prepare_image_for_upload(
                img_bytes, requires_white_bg=requires_white_bg and saved == 0
            )
            if prepared is None:
                db.add(ListingImage(
                    listing_id=listing.id,
                    status="validation_failed",
                    validation_error=verdict.reason,
                    sort_order=saved,
                ))
                continue

            ml_picture_id = await ml_pic.upload(prepared, access_token)

            db.add(ListingImage(
                listing_id=listing.id,
                ml_picture_id=ml_picture_id,
                status="uploaded",
                sort_order=saved,
            ))

            # Registra no índice SKU→imagem (não aprovada ainda)
            if sku:
                db.add(ProductImage(
                    seller_id=listing.seller_id,
                    sku=sku,
                    ml_picture_id=ml_picture_id,
                    source=source_label,
                    is_approved=False,
                ))

            saved += 1

        if saved == 0:
            raise RuntimeError(f"Nenhuma imagem válida foi gerada pelo motor '{source_label}'")

        if listing.created_via == "batch":
            # Auto-aprovar todas as imagens geradas e suas entradas no índice SKU→imagem
            images = (await db.execute(
                select(ListingImage).where(
                    ListingImage.listing_id == listing.id,
                    ListingImage.status == "uploaded",
                )
            )).scalars().all()
            for img in images:
                img.approved = True
            if sku:
                prod_imgs = (await db.execute(
                    select(ProductImage).where(
                        ProductImage.seller_id == listing.seller_id,
                        ProductImage.sku == sku,
                    )
                )).scalars().all()
                for pi in prod_imgs:
                    pi.is_approved = True
            listing.status = "generating_description"
            await db.commit()
        else:
            listing.status = "pending_image_approval"
            await db.commit()

    return {"listing_id": listing_id, "images_saved": saved}


async def _mark_failed(listing_id: str, error: str) -> None:
    import logging
    logger = logging.getLogger(__name__)
    try:
        from app.database import worker_session
        from app.models.listing import Listing
        from sqlalchemy import select
        async with worker_session() as db:
            listing = (
                await db.execute(select(Listing).where(Listing.id == listing_id))
            ).scalar_one_or_none()
            if listing and listing.status != "failed":
                listing.failed_step = listing.status  # capture column for UI routing
                listing.status = "failed"
                listing.error_message = error[:500]
                await db.commit()
    except Exception as mark_exc:
        logger.error(
            "Could not mark listing %s as failed (original error: %s): %s",
            listing_id,
            error,
            mark_exc,
        )


@celery_app.task(name="app.workers.tasks.image_tasks.generate_images", bind=True, max_retries=2)
def generate_images(self, listing_id: str) -> dict:
    try:
        return asyncio.run(_generate_images_async(listing_id))
    except Exception as exc:
        from app.services.image_engines.base import ImageRateLimitError
        countdown = (
            60 * (2 ** self.request.retries)   # 60s, 120s — muito mais longo para 429
            if isinstance(exc, ImageRateLimitError)
            else 2 ** self.request.retries * 5  # 5s, 10s — erros comuns
        )
        if self.request.retries >= self.max_retries:
            asyncio.run(_mark_failed(listing_id, str(exc)))
            raise
        raise self.retry(exc=exc, countdown=countdown)


@celery_app.task(name="app.workers.tasks.image_tasks.upload_images_to_ml", bind=True, max_retries=3)
def upload_images_to_ml(self, listing_id: str) -> dict:
    raise NotImplementedError("Use generate_images task")
