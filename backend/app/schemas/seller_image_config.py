from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, field_validator


class SellerImageConfigUpsert(BaseModel):
    raw_base_url: str
    write_bucket_name: Optional[str] = None
    write_endpoint_url: Optional[str] = None
    write_access_key_id: Optional[str] = None
    write_secret_access_key: Optional[str] = None

    @field_validator("raw_base_url")
    @classmethod
    def base_url_not_empty(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not v:
            raise ValueError("raw_base_url não pode ser vazio")
        return v


class SellerImageConfigOut(BaseModel):
    id: UUID
    seller_id: UUID
    raw_base_url: str
    write_bucket_name: Optional[str]
    write_endpoint_url: Optional[str]
    has_write_credentials: bool
    created_at: datetime
    updated_at: datetime
