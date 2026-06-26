from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, field_validator


class SellerTitleConfigCreate(BaseModel):
    product_group: str
    title_structure: str
    title_rules: Optional[str] = None
    is_default: bool = False

    @field_validator("product_group")
    @classmethod
    def group_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("product_group não pode ser vazio")
        return v.strip().lower()

    @field_validator("title_structure")
    @classmethod
    def structure_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("title_structure não pode ser vazio")
        return v.strip()


class SellerTitleConfigUpdate(BaseModel):
    title_structure: Optional[str] = None
    title_rules: Optional[str] = None
    is_default: Optional[bool] = None

    @field_validator("title_structure")
    @classmethod
    def structure_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("title_structure não pode ser vazio")
        return v.strip() if v else v


class SellerTitleConfigOut(BaseModel):
    id: UUID
    seller_id: UUID
    product_group: str
    title_structure: str
    title_rules: Optional[str]
    is_default: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
