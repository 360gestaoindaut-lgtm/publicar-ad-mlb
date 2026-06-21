import asyncio

from app.workers.celery_app import celery_app


async def _generate_images_async(listing_id: str) -> dict:
    from sqlalchemy import select

    from app.core.security import decrypt_value
    from app.database import worker_session
    from app.models.listing import Listing
    from app.models.listing_image import ListingImage
    from app.models.product_image import ProductImage
    from app.models.seller import Seller
    from app.services.ai.service import get_ai_provider
    from app.services.image_service import GeminiImageService, MLPictureService, validate_image

    async with worker_session() as db:
        listing = (
            await db.execute(select(Listing).where(Listing.id == listing_id))
        ).scalar_one()

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
                    from app.workers.tasks.ai_tasks import generate_description
                    generate_description.delay(listing_id)
                else:
                    listing.status = "pending_image_approval"
                    await db.commit()
                return {"listing_id": listing_id, "images_reused": len(existing)}

        # Sem imagens existentes — gera com IA
        seller = (
            await db.execute(select(Seller).where(Seller.id == listing.seller_id))
        ).scalar_one()
        access_token = decrypt_value(seller.access_token_enc)

        ai = get_ai_provider()
        prompt = await ai.generate_image_prompt(
            brand=listing.sku_brand,
            title=listing.selected_title or "",
            description=listing.sku_description,
        )

        raw_images = await GeminiImageService().generate(prompt)
        ml_pic = MLPictureService()
        saved = 0

        for img_bytes in raw_images:
            if not validate_image(img_bytes):
                continue

            ml_picture_id = await ml_pic.upload(img_bytes, access_token)

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
                    source="gemini",
                    is_approved=False,
                ))

            saved += 1

        if saved == 0:
            raise RuntimeError("Nenhuma imagem válida foi gerada pelo Gemini Imagen")

        if listing.created_via == "batch":
            # Auto-aprovar todas as imagens geradas e suas entradas no índice SKU→imagem
            images = (await db.execute(
                select(ListingImage).where(ListingImage.listing_id == listing.id)
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
            from app.workers.tasks.ai_tasks import generate_description
            generate_description.delay(listing_id)
        else:
            listing.status = "pending_image_approval"
            await db.commit()

    return {"listing_id": listing_id, "images_saved": saved}


async def _mark_failed(listing_id: str, error: str) -> None:
    from app.database import worker_session
    from app.models.listing import Listing
    from sqlalchemy import select
    async with worker_session() as db:
        listing = (await db.execute(select(Listing).where(Listing.id == listing_id))).scalar_one_or_none()
        if listing:
            listing.status = "failed"
            listing.error_message = error[:500] if hasattr(listing, "error_message") else None
            await db.commit()


@celery_app.task(name="app.workers.tasks.image_tasks.generate_images", bind=True, max_retries=2)
def generate_images(self, listing_id: str) -> dict:
    try:
        return asyncio.run(_generate_images_async(listing_id))
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            asyncio.run(_mark_failed(listing_id, str(exc)))
            raise
        raise self.retry(exc=exc, countdown=2 ** self.request.retries * 5)


@celery_app.task(name="app.workers.tasks.image_tasks.upload_images_to_ml", bind=True, max_retries=3)
def upload_images_to_ml(self, listing_id: str) -> dict:
    raise NotImplementedError("Use generate_images task")
