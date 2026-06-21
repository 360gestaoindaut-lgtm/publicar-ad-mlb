import asyncio

from app.workers.celery_app import celery_app


async def _process_batch_async(batch_id: str) -> dict:
    from decimal import Decimal
    from sqlalchemy import select, update as sa_update

    from app.database import worker_session
    from app.models.batch_import import BatchImport, BatchImportRow
    from app.models.listing import Listing
    from app.services.batch_import_service import normalize_row, validate_row

    async with worker_session() as db:
        batch = (
            await db.execute(select(BatchImport).where(BatchImport.id == batch_id))
        ).scalar_one()

        batch.status = "running"
        await db.commit()

        rows = (
            await db.execute(
                select(BatchImportRow)
                .where(BatchImportRow.batch_id == batch.id, BatchImportRow.status == "pending")
                .order_by(BatchImportRow.row_number)
            )
        ).scalars().all()

        processed = 0
        failed = 0

        for row in rows:
            try:
                normalized = normalize_row(row.raw_data or {})
                err = validate_row(normalized)
                if err:
                    row.status = "failed"
                    row.error_message = err
                    failed += 1
                    continue

                price = normalized["preco"] or Decimal("0.01")

                listing = Listing(
                    seller_id=batch.seller_id,
                    created_by=batch.created_by,
                    sku_external_id=normalized["sku"],
                    sku_description=normalized["descricao"],
                    sku_brand=normalized["marca"],
                    price=price,
                    stock_quantity=normalized["estoque"],
                    condition=normalized["condicao"],
                    listing_type_id=normalized["tipo_anuncio"],
                    status="generating_title",
                    created_via="batch",
                )
                db.add(listing)
                await db.flush()

                row.listing_id = listing.id
                row.status = "processing"
                processed += 1

                from app.workers.tasks.ai_tasks import generate_title
                generate_title.apply_async(
                    args=[str(listing.id)],
                    kwargs={
                        "batch_mode": True,
                        "ean": normalized.get("ean"),
                        "seo_context": normalized.get("seo_context"),
                    },
                )

            except Exception as exc:
                row.status = "failed"
                row.error_message = str(exc)[:500]
                failed += 1

        batch.processed_rows = processed
        batch.failed_rows = failed

        if failed == 0:
            batch.status = "running"
        elif processed == 0:
            batch.status = "error"
        else:
            batch.status = "partial_error" if failed > 0 else "running"

        await db.commit()

    return {"batch_id": batch_id, "processed": processed, "failed": failed}


@celery_app.task(name="app.workers.tasks.batch_tasks.process_batch", bind=True, max_retries=0)
def process_batch(self, batch_id: str) -> dict:
    return asyncio.run(_process_batch_async(batch_id))
