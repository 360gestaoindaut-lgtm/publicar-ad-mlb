from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.image_engine_state import ImageEngineState
from app.services.image_engines.base import ImageEngineProvider


async def get_engine_state(db: AsyncSession) -> ImageEngineState:
    result = await db.execute(select(ImageEngineState))
    return result.scalar_one()


def get_engine_instance(name: str) -> ImageEngineProvider:
    if name == "openai":
        from app.services.image_engines.openai_engine import OpenAIImageEngine
        return OpenAIImageEngine()
    from app.services.image_engines.gemini_engine import GeminiImageEngine
    return GeminiImageEngine()


def get_engine_label(name: str) -> str:
    if name == "openai":
        from app.config import get_settings
        return f"OpenAI · {get_settings().openai_image_model}"
    return "Gemini · imagen-4.0-fast"
