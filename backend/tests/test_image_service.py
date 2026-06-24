import io
import pytest
from PIL import Image

from app.services.image_service import ensure_dimensions


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
