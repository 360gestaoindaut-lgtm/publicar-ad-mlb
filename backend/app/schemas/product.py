from decimal import Decimal
from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, field_validator


class ProductCreate(BaseModel):
    sku: str
    description: str
    brand: Optional[str] = None
    model: Optional[str] = None
    ean: Optional[str] = None
    ncm: Optional[str] = None
    fiscal_origin: Optional[int] = None
    icms_cst: Optional[str] = None
    icms_rate: Optional[Decimal] = None
    pis_cst: Optional[str] = None
    cofins_cst: Optional[str] = None
    weight_kg: Optional[Decimal] = None
    length_cm: Optional[int] = None
    width_cm: Optional[int] = None
    height_cm: Optional[int] = None
    acquisition_cost: Optional[Decimal] = None
    product_group: Optional[str] = None
    technical_reference: Optional[str] = None
    vehicle_application: Optional[str] = None
    color: Optional[str] = None
    size: Optional[str] = None
    capacity: Optional[str] = None
    material: Optional[str] = None
    gender: Optional[str] = None

    @field_validator("sku")
    @classmethod
    def sku_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("SKU não pode ser vazio")
        return v.strip()

    @field_validator("description")
    @classmethod
    def description_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Descrição não pode ser vazia")
        return v.strip()

    @field_validator("product_group")
    @classmethod
    def product_group_strip(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() or None if v else None

    @field_validator("fiscal_origin")
    @classmethod
    def fiscal_origin_range(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (0 <= v <= 8):
            raise ValueError("Origem fiscal deve ser um valor entre 0 e 8")
        return v


class ProductUpdate(BaseModel):
    description: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    ean: Optional[str] = None
    ncm: Optional[str] = None
    fiscal_origin: Optional[int] = None

    @field_validator("fiscal_origin")
    @classmethod
    def fiscal_origin_range(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (0 <= v <= 8):
            raise ValueError("Origem fiscal deve ser um valor entre 0 e 8")
        return v
    icms_cst: Optional[str] = None
    icms_rate: Optional[Decimal] = None
    pis_cst: Optional[str] = None
    cofins_cst: Optional[str] = None
    weight_kg: Optional[Decimal] = None
    length_cm: Optional[int] = None
    width_cm: Optional[int] = None
    height_cm: Optional[int] = None
    acquisition_cost: Optional[Decimal] = None
    product_group: Optional[str] = None
    technical_reference: Optional[str] = None
    vehicle_application: Optional[str] = None
    color: Optional[str] = None
    size: Optional[str] = None
    capacity: Optional[str] = None
    material: Optional[str] = None
    gender: Optional[str] = None


class ProductOut(BaseModel):
    id: UUID
    seller_id: UUID
    sku: str
    description: str
    brand: Optional[str] = None
    model: Optional[str] = None
    ean: Optional[str] = None
    ncm: Optional[str] = None
    fiscal_origin: Optional[int] = None
    icms_cst: Optional[str] = None
    icms_rate: Optional[Decimal] = None
    pis_cst: Optional[str] = None
    cofins_cst: Optional[str] = None
    weight_kg: Optional[Decimal] = None
    length_cm: Optional[int] = None
    width_cm: Optional[int] = None
    height_cm: Optional[int] = None
    acquisition_cost: Optional[Decimal] = None
    product_group: Optional[str] = None
    technical_reference: Optional[str] = None
    vehicle_application: Optional[str] = None
    color: Optional[str] = None
    size: Optional[str] = None
    capacity: Optional[str] = None
    material: Optional[str] = None
    gender: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProductPage(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    page_size: int


class ProductUploadResult(BaseModel):
    total: int
    accepted: int
    rejected: int
    errors: list[dict]
