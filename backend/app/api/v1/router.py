from fastapi import APIRouter
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.listings import router as listings_router
from app.api.v1.endpoints.sellers import router as sellers_router
from app.api.v1.endpoints.import_listings import router as import_router
from app.api.v1.endpoints.products import router as products_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(health_router)
router.include_router(listings_router)
router.include_router(sellers_router)
router.include_router(import_router)
router.include_router(products_router)
