import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_db, get_current_user, get_active_seller
from app.models.user import User
from app.models.seller import Seller
from app.schemas.seller_title_config import (
    SellerTitleConfigCreate, SellerTitleConfigUpdate, SellerTitleConfigOut
)
from app.services.seller_title_config_service import SellerTitleConfigService

router = APIRouter(prefix="/title-configs", tags=["title-configs"])


@router.get("", response_model=list[SellerTitleConfigOut])
async def list_title_configs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    seller: Seller = Depends(get_active_seller),
):
    svc = SellerTitleConfigService(db, seller.id)
    return await svc.list()


@router.post("", response_model=SellerTitleConfigOut, status_code=status.HTTP_201_CREATED)
async def create_title_config(
    payload: SellerTitleConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    seller: Seller = Depends(get_active_seller),
):
    svc = SellerTitleConfigService(db, seller.id)
    return await svc.create(payload)


@router.put("/{config_id}", response_model=SellerTitleConfigOut)
async def update_title_config(
    config_id: uuid.UUID,
    payload: SellerTitleConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    seller: Seller = Depends(get_active_seller),
):
    svc = SellerTitleConfigService(db, seller.id)
    return await svc.update(config_id, payload)


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_title_config(
    config_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    seller: Seller = Depends(get_active_seller),
):
    svc = SellerTitleConfigService(db, seller.id)
    await svc.delete(config_id)
