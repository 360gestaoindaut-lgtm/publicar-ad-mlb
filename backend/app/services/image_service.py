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

# Explicitly tell Imagen what NOT to generate — reduces hallucination significantly
_NEGATIVE_PROMPT = (
    "people, hands, animals, plants, leaves, trees, flowers, nature, outdoor, indoor scene, "
    "room, furniture, table, floor, text overlay, watermark, logo, price tag, banner, "
    "promotional text, multiple products, collage, lifestyle photo, shadow, reflection, "
    "colored background, gradient, blur, bokeh, abstract elements"
)


class GeminiImageService:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def generate(self, prompt: str) -> list[bytes]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                _IMAGEN_URL,
                headers={"X-goog-api-key": self.settings.gemini_api_key},
                json={
                    "instances": [{"prompt": prompt}],
                    "parameters": {
                        "sampleCount": 4,
                        "aspectRatio": "1:1",
                        "personGeneration": "DONT_ALLOW",
                        "negativePrompt": _NEGATIVE_PROMPT,
                    },
                },
            )
        resp.raise_for_status()
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
        return w >= _MIN_DIMENSION and h >= _MIN_DIMENSION
    except Exception:
        return False
