from fastapi import APIRouter
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.listings import router as listings_router
from app.api.v1.endpoints.sellers import router as sellers_router
from app.api.v1.endpoints.import_listings import router as import_router
from app.api.v1.endpoints.products import router as products_router
from app.api.v1.endpoints.seller_title_configs import router as title_configs_router
from app.api.v1.endpoints.listings_bulk import router as listings_bulk_router
from app.api.v1.endpoints.system import router as system_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(health_router)
router.include_router(listings_router)
router.include_router(sellers_router)
router.include_router(import_router)
router.include_router(products_router)
router.include_router(title_configs_router)
router.include_router(listings_bulk_router, prefix="/listings")
router.include_router(system_router)
