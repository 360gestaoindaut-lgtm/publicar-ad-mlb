import base64
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.image_engines.base import ImageEngineUnavailableError
from app.services.image_engines.openai_engine import OpenAIImageEngine, check_openai_health


def _b64_image() -> str:
    return base64.b64encode(b"fake-image-bytes").decode()


class TestOpenAIImageEngineGenerate:
    @pytest.mark.asyncio
    async def test_success_returns_decoded_images(self):
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {"data": [{"b64_json": _b64_image()}]}

        mock_post = AsyncMock(return_value=mock_response)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            engine = OpenAIImageEngine()
            result = await engine.generate("a product photo")

        assert result == [b"fake-image-bytes"]

    @pytest.mark.asyncio
    async def test_429_raises_unavailable_error(self):
        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 429
        mock_response.text = "Rate limited"
        mock_response.request = MagicMock()

        mock_post = AsyncMock(return_value=mock_response)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            engine = OpenAIImageEngine()
            with pytest.raises(ImageEngineUnavailableError):
                await engine.generate("prompt")

    @pytest.mark.asyncio
    async def test_500_raises_unavailable_error(self):
        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.request = MagicMock()

        mock_post = AsyncMock(return_value=mock_response)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            engine = OpenAIImageEngine()
            with pytest.raises(ImageEngineUnavailableError):
                await engine.generate("prompt")

    @pytest.mark.asyncio
    async def test_401_raises_unavailable_error(self):
        """Missing/invalid OPENAI_API_KEY must trigger the same failover-
        confirmation flow as infra outages, not a hard, un-recoverable
        failure with no self-service way to fall back to Gemini."""
        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 401
        mock_response.text = "Invalid API key"
        mock_response.request = MagicMock()

        mock_post = AsyncMock(return_value=mock_response)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            engine = OpenAIImageEngine()
            with pytest.raises(ImageEngineUnavailableError):
                await engine.generate("prompt")

    @pytest.mark.asyncio
    async def test_403_raises_unavailable_error(self):
        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        mock_response.request = MagicMock()

        mock_post = AsyncMock(return_value=mock_response)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            engine = OpenAIImageEngine()
            with pytest.raises(ImageEngineUnavailableError):
                await engine.generate("prompt")

    @pytest.mark.asyncio
    async def test_timeout_raises_unavailable_error(self):
        mock_post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            engine = OpenAIImageEngine()
            with pytest.raises(ImageEngineUnavailableError):
                await engine.generate("prompt")

    @pytest.mark.asyncio
    async def test_content_policy_400_raises_http_status_error_not_unavailable(self):
        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 400
        mock_response.text = "Your request was rejected by content policy"
        mock_response.request = MagicMock()

        mock_post = AsyncMock(return_value=mock_response)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            engine = OpenAIImageEngine()
            with pytest.raises(httpx.HTTPStatusError):
                await engine.generate("prompt")


class TestCheckOpenAIHealth:
    @pytest.mark.asyncio
    async def test_returns_true_on_200(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get = AsyncMock(return_value=mock_response)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.get = mock_get
            assert await check_openai_health() is True

    @pytest.mark.asyncio
    async def test_returns_false_on_error_status(self):
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_get = AsyncMock(return_value=mock_response)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.get = mock_get
            assert await check_openai_health() is False

    @pytest.mark.asyncio
    async def test_returns_false_on_network_exception(self):
        mock_get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.get = mock_get
            assert await check_openai_health() is False
