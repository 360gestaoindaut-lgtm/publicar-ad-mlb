from decimal import Decimal
from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, field_validator


class ListingCreate(BaseModel):
    sku_external_id: Optional[str] = None
    sku_description: str
    sku_brand: str
    price: Decimal
    stock_quantity: int
    condition: str

    @field_validator("condition")
    @classmethod
    def condition_must_be_valid(cls, v: str) -> str:
        if v not in ("new", "used"):
            raise ValueError("Condição deve ser 'new' ou 'used'")
        return v

    @field_validator("price")
    @classmethod
    def price_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Preço deve ser maior que zero")
        return v

    @field_validator("stock_quantity")
    @classmethod
    def stock_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Estoque deve ser pelo menos 1")
        return v


class ListingSummary(BaseModel):
    id: UUID
    sku_external_id: Optional[str]
    sku_brand: str
    selected_title: Optional[str]
    status: str
    mlb_id: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ListingPage(BaseModel):
    items: list[ListingSummary]
    total: int
    page: int
    page_size: int
