import asyncio
from app.workers.celery_app import celery_app


async def _predict_category_async(listing_id: str) -> dict:
    from app.database import worker_session
    from app.models.listing import Listing
    from app.services.category_service import CategoryService
    from sqlalchemy import select

    async with worker_session() as db:
        result = await db.execute(select(Listing).where(Listing.id == listing_id))
        listing = result.scalar_one()

        service = CategoryService(db)
        await service.predict_and_save(listing)
        await db.commit()

    return {"listing_id": listing_id, "category_id": listing.ml_category_id}


@celery_app.task(name="app.workers.tasks.category_tasks.predict_category", bind=True, max_retries=3)
def predict_category(self, listing_id: str) -> dict:
    try:
        return asyncio.run(_predict_category_async(listing_id))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries * 5)
