from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.dependencies import get_db, get_current_user, get_active_seller
from app.models.batch_import import BatchImport, BatchImportRow
from app.schemas.batch_import import BatchImportDetail, BatchImportOut, BatchImportRowOut
from app.services.batch_import_service import normalize_row, parse_csv, parse_xlsx, validate_row
from uuid import UUID

router = APIRouter(prefix="/import", tags=["import"])

_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
_MAX_ROWS = 5_000


@router.post("", response_model=BatchImportOut, status_code=202)
async def upload_batch(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
    active_seller=Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    if file.filename is None:
        raise HTTPException(status_code=400, detail="Arquivo não enviado")

    filename = file.filename.lower()
    if not (filename.endswith(".csv") or filename.endswith(".xlsx")):
        raise HTTPException(status_code=400, detail="Formato não suportado. Use .csv ou .xlsx")

    content = await file.read()
    if len(content) > _MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="Arquivo muito grande (máx. 10 MB)")

    if filename.endswith(".csv"):
        raw_rows = parse_csv(content)
    else:
        raw_rows = parse_xlsx(content)

    if not raw_rows:
        raise HTTPException(status_code=422, detail="Arquivo vazio ou sem dados reconhecíveis")

    if len(raw_rows) > _MAX_ROWS:
        raise HTTPException(status_code=422, detail=f"Máximo de {_MAX_ROWS} linhas por importação")

    batch = BatchImport(
        seller_id=active_seller.id,
        created_by=current_user.id,
        filename=file.filename,
        total_rows=len(raw_rows),
        status="pending",
    )
    db.add(batch)
    await db.flush()

    for i, raw in enumerate(raw_rows, start=1):
        normalized = normalize_row(raw)
        error = validate_row(normalized)
        db.add(BatchImportRow(
            batch_id=batch.id,
            row_number=i,
            sku=normalized["sku"] or f"row_{i}",
            status="failed" if error else "pending",
            error_message=error,
            raw_data=raw,  # armazena strings originais; worker re-normaliza (Decimal não é JSON-serializável)
        ))

    await db.commit()
    await db.refresh(batch)

    # Enfileira o worker apenas se houver linhas válidas
    valid_count = sum(1 for r in raw_rows if not validate_row(normalize_row(r)))
    if valid_count > 0:
        from app.workers.tasks.batch_tasks import process_batch
        process_batch.delay(str(batch.id))

    return batch


@router.get("", response_model=list[BatchImportOut])
async def list_batches(
    active_seller=Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BatchImport)
        .where(BatchImport.seller_id == active_seller.id)
        .order_by(BatchImport.created_at.desc())
        .limit(50)
    )
    return result.scalars().all()


@router.get("/{batch_id}", response_model=BatchImportDetail)
async def get_batch(
    batch_id: UUID,
    active_seller=Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    batch = (
        await db.execute(
            select(BatchImport).where(
                BatchImport.id == batch_id,
                BatchImport.seller_id == active_seller.id,
            )
        )
    ).scalar_one_or_none()

    if not batch:
        raise HTTPException(status_code=404, detail="Importação não encontrada")

    rows = (
        await db.execute(
            select(BatchImportRow)
            .where(BatchImportRow.batch_id == batch.id)
            .order_by(BatchImportRow.row_number)
        )
    ).scalars().all()

    return BatchImportDetail(
        id=batch.id,
        seller_id=batch.seller_id,
        filename=batch.filename,
        total_rows=batch.total_rows,
        processed_rows=batch.processed_rows,
        failed_rows=batch.failed_rows,
        status=batch.status,
        created_at=batch.created_at,
        updated_at=batch.updated_at,
        rows=[BatchImportRowOut.model_validate(r) for r in rows],
    )
