import asyncio
import base64
import io

import httpx
from PIL import Image

from app.config import get_settings

_IMAGEN_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "imagen-4.0-fast-generate-001:predict"
)
ML_PICTURES_URL = "https://api.mercadolibre.com/pictures/items/upload"
_MIN_DIMENSION = 500       # ML minimum accepted
_RECOMMENDED_DIM = 1024    # Gemini Imagen 4 output (acceptable for ML, below ideal 1200)
_MAX_BYTES = 10 * 1024 * 1024

# Sufixo adicionado ao prompt positivo — Imagen 4 removeu suporte a negativePrompt
_PROMPT_SUFFIX = (
    " Strict requirements: pure white (#FFFFFF) background only, product isolated and centered, "
    "no people, no hands, no text, no watermarks, no banners, no plants, no leaves, "
    "no furniture, no rooms, no shadows, no lifestyle elements, no extra products."
)


class ImageRateLimitError(Exception):
    """Raised when Imagen API returns HTTP 429 — signals Celery to use longer backoff."""


class GeminiImageService:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def generate(self, prompt: str) -> list[bytes]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                _IMAGEN_URL,
                headers={"X-goog-api-key": self.settings.gemini_api_key},
                json={
                    "instances": [{"prompt": prompt + _PROMPT_SUFFIX}],
                    "parameters": {
                        "sampleCount": 4,
                        "aspectRatio": "1:1",
                        "personGeneration": "DONT_ALLOW",
                    },
                },
            )
        if not resp.is_success:
            if resp.status_code == 429:
                raise ImageRateLimitError(
                    f"Imagen API rate limit (429): {resp.text[:300]}"
                )
            raise httpx.HTTPStatusError(
                f"Imagen API {resp.status_code}: {resp.text[:600]}",
                request=resp.request,
                response=resp,
            )
        predictions = resp.json().get("predictions", [])
        return [base64.b64decode(p["bytesBase64Encoded"]) for p in predictions]


class MLPictureService:
    async def upload(self, image_bytes: bytes, access_token: str) -> str:
        last_exc: Exception = RuntimeError("ML CDN upload failed")
        async with httpx.AsyncClient(timeout=60.0) as client:
            for attempt in range(3):
                if attempt > 0:
                    await asyncio.sleep(5 * (2 ** (attempt - 1)))
                try:
                    resp = await client.post(
                        ML_PICTURES_URL,
                        headers={"Authorization": f"Bearer {access_token}"},
                        files={"file": ("image.jpg", image_bytes, "image/jpeg")},
                    )
                    if resp.status_code < 500:
                        resp.raise_for_status()
                        return resp.json()["id"]
                    last_exc = RuntimeError(f"ML CDN {resp.status_code}: {resp.text}")
                except Exception as exc:
                    last_exc = exc
        raise last_exc


def validate_image(image_bytes: bytes) -> bool:
    if len(image_bytes) > _MAX_BYTES:
        return False
    try:
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        return min(w, h) > 0
    except Exception:
        return False


def ensure_dimensions(image_bytes: bytes, target: int = _RECOMMENDED_DIM) -> bytes | None:
    """Upscale to target×target if smaller; always returns JPEG bytes. Returns None if bytes are corrupted."""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return None
    w, h = img.size
    if w < target or h < target:
        scale = target / min(w, h)
        img = img.resize((max(int(w * scale), target), max(int(h * scale), target)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()
