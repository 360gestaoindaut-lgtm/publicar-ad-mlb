from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.dependencies import get_db, get_current_user, get_active_seller
from app.models.listing import Listing
from app.models.listing_description import ListingDescription
from app.models.listing_title import ListingTitle
from app.models.listing_attribute import ListingAttribute
from app.models.listing_job import ListingJob
from app.models.listing_image import ListingImage
from app.schemas.listing import (
    ImageApproveRequest,
    ImageOut,
    ListingCreate,
    ListingDetail,
    ListingPage,
    ListingSummary,
)
from app.schemas.attribute import AttributesSubmitRequest
from app.services.listing_service import ListingService

router = APIRouter(prefix="/listings", tags=["listings"])


async def _load_detail(db: AsyncSession, listing: Listing) -> ListingDetail:
    from app.schemas.listing import TitleOption, AttributeOut, JobOut

    titles = (await db.execute(
        select(ListingTitle).where(ListingTitle.listing_id == listing.id)
        .order_by(ListingTitle.ai_score.desc().nullslast())
    )).scalars().all()

    attributes = (await db.execute(
        select(ListingAttribute).where(ListingAttribute.listing_id == listing.id)
        .order_by(ListingAttribute.is_required.desc(), ListingAttribute.attribute_name)
    )).scalars().all()

    images = (await db.execute(
        select(ListingImage).where(ListingImage.listing_id == listing.id)
        .order_by(ListingImage.sort_order)
    )).scalars().all()

    jobs = (await db.execute(
        select(ListingJob).where(ListingJob.listing_id == listing.id)
        .order_by(ListingJob.created_at.desc())
    )).scalars().all()

    desc_row = (await db.execute(
        select(ListingDescription).where(ListingDescription.listing_id == listing.id)
    )).scalar_one_or_none()

    return ListingDetail(
        id=listing.id,
        sku_external_id=listing.sku_external_id,
        sku_brand=listing.sku_brand,
        selected_title=listing.selected_title,
        status=listing.status,
        created_via=listing.created_via,
        mlb_id=listing.mlb_id,
        created_at=listing.created_at,
        updated_at=listing.updated_at,
        sku_description=listing.sku_description,
        price=listing.price,
        stock_quantity=listing.stock_quantity,
        condition=listing.condition,
        listing_type_id=listing.listing_type_id,
        ml_category_id=listing.ml_category_id,
        error_message=listing.error_message,
        description_html=desc_row.description_html if desc_row else None,
        titles=[TitleOption.model_validate(t) for t in titles],
        attributes=[AttributeOut.model_validate(a) for a in attributes],
        images=[ImageOut.model_validate(i) for i in images],
        jobs=[JobOut.model_validate(j) for j in jobs],
    )


@router.post("", response_model=ListingSummary, status_code=201)
async def create_listing(
    data: ListingCreate,
    current_user=Depends(get_current_user),
    active_seller=Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    return await ListingService(db).create(data, current_user, active_seller)


@router.get("", response_model=ListingPage)
async def list_listings(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    active_seller=Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    return await ListingService(db).list_listings(active_seller.id, status, page, page_size)


@router.get("/{listing_id}", response_model=ListingDetail)
async def get_listing(
    listing_id: UUID,
    active_seller=Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    listing = await ListingService(db).get_or_404(listing_id, active_seller.id)
    return await _load_detail(db, listing)


@router.delete("/{listing_id}", status_code=204)
async def delete_listing(
    listing_id: UUID,
    active_seller=Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    await ListingService(db).delete(listing_id, active_seller.id)


@router.post("/{listing_id}/pipeline/start", response_model=ListingSummary)
async def start_pipeline(
    listing_id: UUID,
    active_seller=Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    svc = ListingService(db)
    listing = await svc.get_or_404(listing_id, active_seller.id)
    await svc.start_pipeline(listing)
    return ListingSummary.model_validate(listing)


@router.post("/{listing_id}/pipeline/retry", response_model=ListingSummary)
async def retry_pipeline(
    listing_id: UUID,
    active_seller=Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    svc = ListingService(db)
    listing = await svc.get_or_404(listing_id, active_seller.id)
    await svc.retry_pipeline(listing)
    return ListingSummary.model_validate(listing)


@router.post("/{listing_id}/titles/{title_id}/select", response_model=ListingSummary)
async def select_title(
    listing_id: UUID,
    title_id: UUID,
    active_seller=Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    svc = ListingService(db)
    listing = await svc.get_or_404(listing_id, active_seller.id)
    await svc.select_title(listing, title_id)
    return ListingSummary.model_validate(listing)


@router.put("/{listing_id}/attributes", response_model=ListingSummary)
async def submit_attributes(
    listing_id: UUID,
    body: AttributesSubmitRequest,
    active_seller=Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    svc = ListingService(db)
    listing = await svc.get_or_404(listing_id, active_seller.id)
    await svc.submit_attributes(listing, [a.model_dump() for a in body.attributes])
    return ListingSummary.model_validate(listing)


@router.post("/{listing_id}/pipeline/generate_images", response_model=ListingSummary)
async def generate_images(
    listing_id: UUID,
    active_seller=Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    svc = ListingService(db)
    listing = await svc.get_or_404(listing_id, active_seller.id)
    await svc.trigger_image_generation(listing)
    return ListingSummary.model_validate(listing)


@router.post("/{listing_id}/images/approve", response_model=ListingSummary)
async def approve_images(
    listing_id: UUID,
    body: ImageApproveRequest,
    active_seller=Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    svc = ListingService(db)
    listing = await svc.get_or_404(listing_id, active_seller.id)
    await svc.approve_images(listing, body.approved_ids)
    return ListingSummary.model_validate(listing)


@router.post("/{listing_id}/pipeline/publish", response_model=ListingSummary)
async def publish_listing(
    listing_id: UUID,
    active_seller=Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    svc = ListingService(db)
    listing = await svc.get_or_404(listing_id, active_seller.id)
    await svc.trigger_publish(listing)
    return ListingSummary.model_validate(listing)
