from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_db, get_current_user, get_active_seller
from app.models.user import User
from app.models.seller import Seller
from app.models.seller_image_config import SellerImageConfig
from app.schemas.seller_image_config import SellerImageConfigUpsert, SellerImageConfigOut
from app.services.seller_image_config_service import SellerImageConfigService

router = APIRouter(prefix="/sellers/image-config", tags=["seller-image-config"])


def _to_out(cfg: SellerImageConfig) -> SellerImageConfigOut:
    return SellerImageConfigOut(
        id=cfg.id,
        seller_id=cfg.seller_id,
        raw_base_url=cfg.raw_base_url,
        write_bucket_name=cfg.write_bucket_name,
        write_endpoint_url=cfg.write_endpoint_url,
        has_write_credentials=bool(cfg.write_access_key_id_enc and cfg.write_secret_access_key_enc),
        created_at=cfg.created_at,
        updated_at=cfg.updated_at,
    )


@router.get("", response_model=SellerImageConfigOut | None)
async def get_image_config(
    current_user: User = Depends(get_current_user),
    active_seller: Seller = Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    svc = SellerImageConfigService(db, active_seller.id)
    cfg = await svc.get()
    return _to_out(cfg) if cfg else None


@router.put("", response_model=SellerImageConfigOut)
async def upsert_image_config(
    body: SellerImageConfigUpsert,
    current_user: User = Depends(get_current_user),
    active_seller: Seller = Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    svc = SellerImageConfigService(db, active_seller.id)
    cfg = await svc.upsert(body)
    return _to_out(cfg)
