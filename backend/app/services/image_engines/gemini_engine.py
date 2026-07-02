import base64
import httpx

from app.config import get_settings
from app.services.image_engines.base import (
    ImageEngineProvider,
    ImageRateLimitError,
    PROMPT_SUFFIX,
)

_IMAGEN_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "imagen-4.0-fast-generate-001:predict"
)


class GeminiImageEngine(ImageEngineProvider):
    def __init__(self) -> None:
        self.settings = get_settings()

    async def generate(self, prompt: str) -> list[bytes]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                _IMAGEN_URL,
                headers={"X-goog-api-key": self.settings.gemini_api_key},
                json={
                    "instances": [{"prompt": prompt + PROMPT_SUFFIX}],
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
