import io
import pytest
import httpx
from PIL import Image
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.image_service import ensure_dimensions, GeminiImageService, ImageRateLimitError


def _make_jpeg(width: int, height: int) -> bytes:
    img = Image.new("RGB", (width, height), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class TestEnsureDimensions:
    def test_corrupted_bytes_returns_none(self):
        result = ensure_dimensions(b"this-is-not-an-image")
        assert result is None

    def test_empty_bytes_returns_none(self):
        result = ensure_dimensions(b"")
        assert result is None

    def test_small_image_is_upscaled(self):
        small = _make_jpeg(200, 200)
        result = ensure_dimensions(small, target=1024)
        assert result is not None
        img = Image.open(io.BytesIO(result))
        assert min(img.size) >= 1024

    def test_large_image_is_not_downscaled(self):
        large = _make_jpeg(1500, 1500)
        result = ensure_dimensions(large, target=1024)
        assert result is not None
        img = Image.open(io.BytesIO(result))
        assert min(img.size) >= 1024

    def test_returns_jpeg_bytes(self):
        source = _make_jpeg(800, 800)
        result = ensure_dimensions(source, target=1024)
        assert result is not None
        img = Image.open(io.BytesIO(result))
        assert img.format == "JPEG"


class TestGeminiImageService429:
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
            service = GeminiImageService()
            with pytest.raises(ImageRateLimitError):
                await service.generate("test prompt")

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
            service = GeminiImageService()
            with pytest.raises(httpx.HTTPStatusError):
                await service.generate("test prompt")
