import asyncio

from app.workers.celery_app import celery_app


async def _generate_images_async(listing_id: str) -> dict:
    from sqlalchemy import select

    from app.core.security import decrypt_value
    from app.database import worker_session
    from app.models.listing import Listing
    from app.models.listing_image import ListingImage
    from app.models.seller import Seller
    from app.services.ai.service import get_ai_provider
    from app.services.image_service import (
        GeminiImageService,
        MLPictureService,
        validate_image,
    )

    async with worker_session() as db:
        listing = (
            await db.execute(select(Listing).where(Listing.id == listing_id))
        ).scalar_one()

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
            saved += 1

        if saved == 0:
            raise RuntimeError("Nenhuma imagem válida foi gerada pelo Gemini Imagen")

        listing.status = "pending_image_approval"
        await db.commit()

    return {"listing_id": listing_id, "images_saved": saved}


@celery_app.task(name="app.workers.tasks.image_tasks.generate_images", bind=True, max_retries=2)
def generate_images(self, listing_id: str) -> dict:
    try:
        return asyncio.run(_generate_images_async(listing_id))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries * 5)


@celery_app.task(name="app.workers.tasks.image_tasks.upload_images_to_ml", bind=True, max_retries=3)
def upload_images_to_ml(self, listing_id: str) -> dict:
    raise NotImplementedError("Use generate_images task")
