from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.dependencies import get_db, get_current_user, get_active_seller
from app.models.listing import Listing
from app.models.listing_description import ListingDescription
from app.models.seller import Seller
from app.models.listing_title import ListingTitle
from app.models.listing_attribute import ListingAttribute
from app.models.listing_job import ListingJob
from app.models.listing_image import ListingImage
from app.schemas.listing import (
    ImageApproveRequest,
    ImageEngineConfirmRequest,
    ImageOut,
    ListingCreate,
    ListingDetail,
    ListingPage,
    ListingSummary,
)
from app.schemas.attribute import AttributesSubmitRequest
from app.services.listing_service import ListingService
from app.services.publish_service import PublishService

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
    page_size: int = Query(20, ge=1, le=200),
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


@router.post("/{listing_id}/pipeline/confirm_image_engine", response_model=ListingSummary)
async def confirm_image_engine(
    listing_id: UUID,
    body: ImageEngineConfirmRequest,
    active_seller=Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    svc = ListingService(db)
    listing = await svc.get_or_404(listing_id, active_seller.id)
    await svc.confirm_image_engine(listing, body.action)
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


@router.post("/{listing_id}/activate")
async def activate_listing(
    listing_id: UUID,
    active_seller=Depends(get_active_seller),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Listing).where(
            Listing.id == listing_id,
            Listing.seller_id == active_seller.id,
        )
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Anúncio não encontrado")
    if listing.status != "published_paused":
        raise HTTPException(status_code=422, detail="Anúncio não está pausado")

    seller_result = await db.execute(select(Seller).where(Seller.id == active_seller.id))
    seller = seller_result.scalar_one()

    await PublishService(db).activate_listing(listing, seller)
    return {"status": "published"}


@router.post("/{listing_id}/images/cover-ai-variant", response_model=ImageOut, status_code=201)
async def generate_cover_ai_variant(
    listing_id: UUID,
    active_seller=Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    """Gera sob demanda a variante ambientada da capa (Frente A).

    Nasce como candidato não aprovado (`approved=False`) — não muda o anúncio
    automaticamente. Um humano revisa e decide se promove (Frente B).
    """
    from app.services.cover_variant_service import CoverVariantError, generate_cover_variant
    from app.services.image_engines.base import ImageEngineUnavailableError
    from app.services.publish_service import get_valid_access_token

    svc = ListingService(db)
    listing = await svc.get_or_404(listing_id, active_seller.id)
    access_token = await get_valid_access_token(active_seller, db)
    try:
        candidate = await generate_cover_variant(db, listing, access_token)
    except CoverVariantError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ImageEngineUnavailableError as exc:
        # 502, não 500: quem falhou foi um provedor externo (OpenAI) que este
        # endpoint expõe como gateway — mesmo status usado em publish_service.py
        # para falhas da API do ML. Condição transiente e retryable: o
        # operador clicou num botão pago e precisa saber que pode tentar de
        # novo, não que o endpoint está quebrado. Nenhuma ListingImage chega a
        # ser gravada neste caminho — a falha acontece antes de qualquer
        # db.add() no serviço.
        raise HTTPException(
            status_code=502,
            detail=f"Motor de imagem indisponível no momento — tente novamente em instantes. ({exc})",
        )
    return ImageOut.model_validate(candidate)


@router.post("/{listing_id}/images/{image_id}/promote-cover", response_model=ListingSummary)
async def promote_cover(
    listing_id: UUID,
    image_id: UUID,
    active_seller=Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    """Decide qual imagem ocupa a capa do anúncio (Frente B).

    A imagem escolhida — capa determinística ou variante IA — assume
    `sort_order=0` e `approved=True`; a que estava lá volta a ser candidata
    (`approved=False`, `sort_order=90`), nunca é apagada. O restante da
    galeria não é tocado. Nada aqui roda automaticamente: só troca de lugar
    quando um humano chama este endpoint.
    """
    from app.services.cover_variant_service import promote_cover as _promote_cover

    svc = ListingService(db)
    listing = await svc.get_or_404(listing_id, active_seller.id)
    await _promote_cover(db, listing, image_id)
    return ListingSummary.model_validate(listing)
