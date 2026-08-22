import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.image_engines.gemini_engine import GeminiImageEngine
from app.services.image_engines.openai_engine import OpenAIImageEngine


class TestGetEngineState:
    @pytest.mark.asyncio
    async def test_returns_the_single_row(self):
        from app.services.image_engines.service import get_engine_state

        mock_state = MagicMock()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_state
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_engine_state(mock_db)

        assert result is mock_state


class TestGetEngineInstance:
    def test_returns_openai_engine(self):
        from app.services.image_engines.service import get_engine_instance

        assert isinstance(get_engine_instance("openai"), OpenAIImageEngine)

    def test_returns_gemini_engine(self):
        from app.services.image_engines.service import get_engine_instance

        assert isinstance(get_engine_instance("gemini"), GeminiImageEngine)


class TestGetEngineLabel:
    def test_openai_label_includes_configured_model(self):
        from app.services.image_engines.service import get_engine_label

        from app.config import get_settings

        label = get_engine_label("openai")
        assert "OpenAI" in label
        assert get_settings().openai_image_model in label

    def test_gemini_label(self):
        from app.services.image_engines.service import get_engine_label

        assert get_engine_label("gemini") == "Gemini · imagen-4.0-fast"
