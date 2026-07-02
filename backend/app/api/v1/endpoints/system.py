from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.dependencies import get_db, get_current_user
from app.models.image_engine_state import ImageEngineState
from app.models.listing import Listing
from app.schemas.system import ImageEngineStateOut
from app.services.image_engines.service import get_engine_label

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/image-engine", response_model=ImageEngineStateOut)
async def get_image_engine(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    engine_state = (await db.execute(select(ImageEngineState))).scalar_one()

    pending_result = await db.execute(
        select(Listing.id).where(Listing.status == "pending_image_engine_confirmation")
    )
    pending_ids = [str(row[0]) for row in pending_result.all()]

    return ImageEngineStateOut(
        current_engine=engine_state.current_engine,
        engine_label=get_engine_label(engine_state.current_engine),
        pending_confirmation_count=len(pending_ids),
        pending_listing_ids=pending_ids,
        last_openai_error=engine_state.last_openai_error,
        last_switch_to_openai_at=engine_state.last_switch_to_openai_at,
    )
