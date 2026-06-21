import asyncio
from app.workers.celery_app import celery_app


async def _predict_category_async(listing_id: str, ean: str | None = None) -> dict:
    from app.database import worker_session
    from app.models.listing import Listing
    from app.services.category_service import CategoryService
    from sqlalchemy import select

    async with worker_session() as db:
        result = await db.execute(select(Listing).where(Listing.id == listing_id))
        listing = result.scalar_one()

        service = CategoryService(db)
        await service.predict_and_save(listing, ean=ean)
        await db.commit()

        # Batch: avança automaticamente para geração de imagens sem esperar aprovação humana
        if listing.created_via == "batch" and listing.status == "pending_description":
            listing.status = "generating_images"
            await db.commit()
            from app.workers.tasks.image_tasks import generate_images
            generate_images.delay(listing_id)

    return {"listing_id": listing_id, "category_id": listing.ml_category_id}


async def _mark_failed(listing_id: str) -> None:
    from app.database import worker_session
    from app.models.listing import Listing
    from sqlalchemy import select

    async with worker_session() as db:
        listing = (await db.execute(select(Listing).where(Listing.id == listing_id))).scalar_one_or_none()
        if listing:
            listing.status = "failed"
            await db.commit()


@celery_app.task(name="app.workers.tasks.category_tasks.predict_category", bind=True, max_retries=3)
def predict_category(self, listing_id: str, ean: str | None = None) -> dict:
    try:
        return asyncio.run(_predict_category_async(listing_id, ean=ean))
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            asyncio.run(_mark_failed(listing_id))
            raise
        raise self.retry(exc=exc, countdown=2 ** self.request.retries * 5)
