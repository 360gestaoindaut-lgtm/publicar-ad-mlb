import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
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
    current_user: User = Depends(get_current_user),
    active_seller: Seller = Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    svc = SellerTitleConfigService(db, active_seller.id)
    configs = await svc.list()
    return [SellerTitleConfigOut.model_validate(c) for c in configs]


@router.post("", response_model=SellerTitleConfigOut, status_code=status.HTTP_201_CREATED)
async def create_title_config(
    body: SellerTitleConfigCreate,
    current_user: User = Depends(get_current_user),
    active_seller: Seller = Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    svc = SellerTitleConfigService(db, active_seller.id)
    try:
        result = await svc.create(body)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Já existe uma configuração para este grupo de produtos")
    return SellerTitleConfigOut.model_validate(result)


@router.put("/{config_id}", response_model=SellerTitleConfigOut)
async def update_title_config(
    config_id: uuid.UUID,
    body: SellerTitleConfigUpdate,
    current_user: User = Depends(get_current_user),
    active_seller: Seller = Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    svc = SellerTitleConfigService(db, active_seller.id)
    try:
        result = await svc.update(config_id, body)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Já existe uma configuração para este grupo de produtos")
    return SellerTitleConfigOut.model_validate(result)


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_title_config(
    config_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    active_seller: Seller = Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    svc = SellerTitleConfigService(db, active_seller.id)
    await svc.delete(config_id)
