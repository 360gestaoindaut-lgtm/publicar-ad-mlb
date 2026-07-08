import base64
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.image_engines.base import ImageEngineUnavailableError
from app.services.image_engines.openai_edit_engine import OpenAIEditEngine


def _b64_image() -> str:
    return base64.b64encode(b"fake-edited-image-bytes").decode()


class TestOpenAIEditEngine:
    @pytest.mark.asyncio
    async def test_success_returns_decoded_images(self):
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {"data": [{"b64_json": _b64_image()}]}

        mock_post = AsyncMock(return_value=mock_response)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            engine = OpenAIEditEngine()
            result = await engine.edit(images=[b"raw-photo-bytes"], prompt="tratamento", n=2)

        assert result == [b"fake-edited-image-bytes"]
        call_kwargs = mock_post.await_args.kwargs
        assert call_kwargs["data"]["n"] == "2"
        assert call_kwargs["data"]["input_fidelity"] == "high"
        assert len(call_kwargs["files"]) == 1

    @pytest.mark.asyncio
    async def test_multiple_input_images_sent_as_multiple_files(self):
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {"data": [{"b64_json": _b64_image()}]}

        mock_post = AsyncMock(return_value=mock_response)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            engine = OpenAIEditEngine()
            await engine.edit(images=[b"photo-a", b"photo-b", b"photo-c"], prompt="capa", n=1)

        call_kwargs = mock_post.await_args.kwargs
        assert len(call_kwargs["files"]) == 3

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
            engine = OpenAIEditEngine()
            with pytest.raises(ImageEngineUnavailableError):
                await engine.edit(images=[b"x"], prompt="p", n=2)

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
            engine = OpenAIEditEngine()
            with pytest.raises(ImageEngineUnavailableError):
                await engine.edit(images=[b"x"], prompt="p", n=2)

    @pytest.mark.asyncio
    async def test_timeout_raises_unavailable_error(self):
        mock_post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            engine = OpenAIEditEngine()
            with pytest.raises(ImageEngineUnavailableError):
                await engine.edit(images=[b"x"], prompt="p", n=2)

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
            engine = OpenAIEditEngine()
            with pytest.raises(httpx.HTTPStatusError):
                await engine.edit(images=[b"x"], prompt="p", n=2)
