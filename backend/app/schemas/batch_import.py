from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel


class BatchImportRowOut(BaseModel):
    id: UUID
    row_number: int
    sku: str
    listing_id: Optional[UUID]
    status: str
    error_message: Optional[str]

    model_config = {"from_attributes": True}


class BatchImportOut(BaseModel):
    id: UUID
    seller_id: UUID
    filename: str
    total_rows: int
    processed_rows: int
    failed_rows: int
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BatchImportDetail(BatchImportOut):
    rows: list[BatchImportRowOut]
