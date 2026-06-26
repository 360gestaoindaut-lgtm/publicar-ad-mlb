# backend/app/schemas/bulk.py
from uuid import UUID
from pydantic import BaseModel, field_validator


class BulkListingRequest(BaseModel):
    listing_ids: list[UUID]

    @field_validator("listing_ids")
    @classmethod
    def not_empty(cls, v: list[UUID]) -> list[UUID]:
        if not v:
            raise ValueError("listing_ids não pode ser vazio")
        if len(v) > 200:
            raise ValueError("máximo 200 listings por operação")
        return v


class BulkAttributeRequest(BaseModel):
    listing_ids: list[UUID]
    attribute_id: str
    value_name: str
    value_id: str | None = None

    @field_validator("listing_ids")
    @classmethod
    def not_empty(cls, v: list[UUID]) -> list[UUID]:
        if not v:
            raise ValueError("listing_ids não pode ser vazio")
        if len(v) > 200:
            raise ValueError("máximo 200 listings por operação")
        return v

    @field_validator("attribute_id", "value_name")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("campo não pode ser vazio")
        return v.strip()


class BulkItemResult(BaseModel):
    listing_id: UUID
    success: bool
    error: str | None = None


class BulkResult(BaseModel):
    processed: int
    failed: int
    results: list[BulkItemResult]


class AttributeItem(BaseModel):
    attribute_id: str
    attribute_name: str
    value_name: str | None
    value_id: str | None
    is_required: bool

    model_config = {"from_attributes": True}


class ListingAttributesRow(BaseModel):
    listing_id: UUID
    sku_external_id: str
    selected_title: str | None
    ml_category_id: str | None
    status: str
    attributes: list[AttributeItem]

    model_config = {"from_attributes": True}
