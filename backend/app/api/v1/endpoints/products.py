from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_db, get_current_user, get_active_seller
from app.schemas.product import ProductOut, ProductPage, ProductUploadResult, ProductCreate, ProductUpdate
from app.services.product_service import ProductService
from app.services.product_import_service import (
    parse_product_csv,
    parse_product_xlsx,
    normalize_product_row,
    validate_product_row,
)

router = APIRouter(prefix="/products", tags=["products"])

_MAX_FILE_BYTES = 10 * 1024 * 1024
_MAX_ROWS = 10_000


@router.post("", response_model=ProductOut, status_code=201)
async def create_product(
    body: ProductCreate,
    current_user=Depends(get_current_user),
    active_seller=Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    service = ProductService(db, seller_id=active_seller.id)
    product = await service.create(body)
    return ProductOut.model_validate(product)


@router.put("/{sku}", response_model=ProductOut)
async def update_product(
    sku: str,
    body: ProductUpdate,
    current_user=Depends(get_current_user),
    active_seller=Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    service = ProductService(db, seller_id=active_seller.id)
    product = await service.update(sku, body)
    return ProductOut.model_validate(product)


@router.post("/upload", response_model=ProductUploadResult, status_code=202)
async def upload_products(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
    active_seller=Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(400, "Arquivo não enviado")

    filename = file.filename.lower()
    if not (filename.endswith(".csv") or filename.endswith(".xlsx")):
        raise HTTPException(400, "Formato não suportado. Use .csv ou .xlsx")

    content = await file.read()
    if len(content) > _MAX_FILE_BYTES:
        raise HTTPException(413, "Arquivo muito grande (máx. 10 MB)")

    raw_rows = parse_product_csv(content) if filename.endswith(".csv") else parse_product_xlsx(content)
    if not raw_rows:
        raise HTTPException(422, "Arquivo vazio ou sem dados reconhecíveis")
    if len(raw_rows) > _MAX_ROWS:
        raise HTTPException(422, f"Máximo de {_MAX_ROWS} linhas por upload")

    service = ProductService(db, seller_id=active_seller.id)
    accepted = 0
    rejected = 0
    errors: list[dict] = []

    for i, raw in enumerate(raw_rows, start=1):
        normalized = normalize_product_row(raw)
        err = validate_product_row(normalized)
        if err:
            rejected += 1
            errors.append({"row": i, "sku": normalized.get("sku") or "", "error": err})
            continue
        try:
            await service.upsert(normalized)
            accepted += 1
        except Exception as exc:
            rejected += 1
            errors.append({"row": i, "sku": normalized.get("sku") or "", "error": str(exc)[:200]})

    return ProductUploadResult(
        total=len(raw_rows),
        accepted=accepted,
        rejected=rejected,
        errors=errors,
    )


@router.get("", response_model=ProductPage)
async def list_products(
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user=Depends(get_current_user),
    active_seller=Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    service = ProductService(db, seller_id=active_seller.id)
    return await service.list_products(search=search, page=page, page_size=page_size)


@router.get("/{sku}", response_model=ProductOut)
async def get_product(
    sku: str,
    current_user=Depends(get_current_user),
    active_seller=Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    service = ProductService(db, seller_id=active_seller.id)
    return await service.get_or_404(sku)
