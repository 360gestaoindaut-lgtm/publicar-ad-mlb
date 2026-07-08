import base64
import httpx

from app.config import get_settings
from app.services.image_engines.base import ImageEngineUnavailableError

_OPENAI_EDITS_URL = "https://api.openai.com/v1/images/edits"


class OpenAIEditEngine:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def edit(self, images: list[bytes], prompt: str, n: int) -> list[bytes]:
        files = [
            ("image[]", (f"input_{i}.jpg", img, "image/jpeg"))
            for i, img in enumerate(images)
        ]
        data = {
            "model": self.settings.openai_image_model,
            "prompt": prompt,
            "n": str(n),
            "quality": "medium",
            "input_fidelity": "high",
            "output_format": "jpeg",
        }
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(
                    _OPENAI_EDITS_URL,
                    headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
                    data=data,
                    files=files,
                )
        except httpx.TimeoutException as exc:
            raise ImageEngineUnavailableError(f"Timeout ao chamar a OpenAI (edits): {exc}") from exc

        if not resp.is_success:
            if resp.status_code in (401, 403, 429) or resp.status_code >= 500:
                raise ImageEngineUnavailableError(
                    f"OpenAI Edits API {resp.status_code}: {resp.text[:600]}"
                )
            raise httpx.HTTPStatusError(
                f"OpenAI Edits API {resp.status_code}: {resp.text[:600]}",
                request=resp.request,
                response=resp,
            )

        data_resp = resp.json().get("data", [])
        return [base64.b64decode(item["b64_json"]) for item in data_resp]
