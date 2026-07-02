import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.image_engines.base import ImageRateLimitError
from app.services.image_engines.gemini_engine import GeminiImageEngine


class TestGeminiImageEngine429:
    @pytest.mark.asyncio
    async def test_raises_rate_limit_error_on_429(self):
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.is_success = False
        mock_response.text = "Quota exceeded"
        mock_response.request = MagicMock()

        mock_post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            engine = GeminiImageEngine()
            with pytest.raises(ImageRateLimitError):
                await engine.generate("test prompt")

    @pytest.mark.asyncio
    async def test_other_errors_raise_http_status_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.is_success = False
        mock_response.text = "Internal Server Error"
        mock_response.request = MagicMock()

        mock_post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            engine = GeminiImageEngine()
            with pytest.raises(httpx.HTTPStatusError):
                await engine.generate("test prompt")
