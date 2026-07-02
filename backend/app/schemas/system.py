from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ImageEngineStateOut(BaseModel):
    current_engine: str
    engine_label: str
    pending_confirmation_count: int
    pending_listing_ids: list[str]
    last_openai_error: Optional[str]
    last_switch_to_openai_at: Optional[datetime]
