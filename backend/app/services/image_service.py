import asyncio
import io

import httpx
from PIL import Image

ML_PICTURES_URL = "https://api.mercadolibre.com/pictures/items/upload"
_MIN_DIMENSION = 500       # ML minimum accepted
_RECOMMENDED_DIM = 1024    # tamanho alvo após upscale (aceitável para ML, abaixo do ideal 1200)
_MAX_BYTES = 10 * 1024 * 1024


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
