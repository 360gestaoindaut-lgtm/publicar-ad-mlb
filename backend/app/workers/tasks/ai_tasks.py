import asyncio
from app.workers.celery_app import celery_app


async def _generate_title_async(listing_id: str) -> dict:
    from app.database import worker_session
    from app.models.listing import Listing
    from app.models.listing_title import ListingTitle
    from app.services.ai.service import get_ai_provider
    from sqlalchemy import select

    async with worker_session() as db:
        result = await db.execute(select(Listing).where(Listing.id == listing_id))
        listing = result.scalar_one()

        provider = get_ai_provider()
        titles = await provider.generate_titles(
            sku_description=listing.sku_description,
            sku_brand=listing.sku_brand,
            condition=listing.condition,
        )

        for t in titles:
            db.add(ListingTitle(
                listing_id=listing.id,
                title_text=t["title"],
                ai_score=t.get("score"),
            ))

        listing.status = "pending_title_approval"
        await db.commit()

    return {"listing_id": listing_id, "titles_generated": len(titles)}


async def _generate_description_async(listing_id: str) -> dict:
    from app.database import worker_session
    from app.models.listing import Listing
    from app.models.listing_attribute import ListingAttribute
    from app.models.listing_description import ListingDescription
    from app.services.ai.service import get_ai_provider
    from sqlalchemy import select

    async with worker_session() as db:
        result = await db.execute(select(Listing).where(Listing.id == listing_id))
        listing = result.scalar_one()

        attrs_result = await db.execute(
            select(ListingAttribute).where(ListingAttribute.listing_id == listing.id)
        )
        attributes = [
            {"attribute_name": a.attribute_name, "value_name": a.value_name}
            for a in attrs_result.scalars().all()
            if a.value_name
        ]

        provider = get_ai_provider()
        description_html = await provider.generate_description({
            "selected_title": listing.selected_title,
            "sku_brand": listing.sku_brand,
            "sku_description": listing.sku_description,
            "condition": listing.condition,
            "attributes": attributes,
        })

        existing = await db.execute(
            select(ListingDescription).where(ListingDescription.listing_id == listing.id)
        )
        desc = existing.scalar_one_or_none()
        if desc:
            desc.description_html = description_html
        else:
            db.add(ListingDescription(listing_id=listing.id, description_html=description_html))

        listing.status = "ready_to_publish"
        await db.commit()

    return {"listing_id": listing_id}


@celery_app.task(name="app.workers.tasks.ai_tasks.generate_title", bind=True, max_retries=3)
def generate_title(self, listing_id: str) -> dict:
    try:
        return asyncio.run(_generate_title_async(listing_id))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries * 5)


@celery_app.task(name="app.workers.tasks.ai_tasks.generate_description", bind=True, max_retries=3)
def generate_description(self, listing_id: str) -> dict:
    try:
        return asyncio.run(_generate_description_async(listing_id))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries * 5)
