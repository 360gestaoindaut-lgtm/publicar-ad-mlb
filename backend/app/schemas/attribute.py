from typing import Optional
from pydantic import BaseModel


class AttributeSubmit(BaseModel):
    attribute_id: str
    value_id: Optional[str] = None
    value_name: Optional[str] = None


class AttributesSubmitRequest(BaseModel):
    attributes: list[AttributeSubmit]
