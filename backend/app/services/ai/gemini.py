import json
import re
import httpx
from app.config import get_settings
from app.services.ai.base import AIProvider
from app.services.ai.prompts import build_title_prompt, build_description_prompt, build_image_prompt_request

_BASE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _extract_json(text: str) -> str:
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text).strip()
    start = text.find('{')
    end = text.rfind('}') + 1
    if start >= 0 and end > start:
        text = text[start:end]
    # Substitui caracteres de controle por espaço
    text = re.sub(r'[\x00-\x1f\x7f]', ' ', text)
    # Tenta parsear diretamente; se falhar, usa json-repair
    try:
        import json as _json
        _json.loads(text)
        return text
    except Exception:
        try:
            from json_repair import repair_json
            return repair_json(text)
        except Exception:
            return text


class GeminiProvider(AIProvider):
    def __init__(self) -> None:
        self.settings = get_settings()

    async def generate_titles(
        self,
        sku_description: str,
        sku_brand: str,
        condition: str,
        ean: str | None = None,
        seo_context: str | None = None,
        batch_mode: bool = False,
    ) -> list[dict]:
        prompt = build_title_prompt(sku_description, sku_brand, condition, ean, seo_context, batch_mode)
        text = await self._call(prompt, max_tokens=500 if batch_mode else 2000, temperature=0.6)
        if batch_mode:
            parsed = json.loads(_extract_json(text))
            title = parsed.get("title", "").strip()[:60]
            return [{"title": title, "score": None, "rationale": "batch_auto"}]
        return json.loads(_extract_json(text))["titles"]

    async def generate_description(self, listing_data: dict) -> str:
        prompt = build_description_prompt(listing_data)
        return await self._call(prompt, max_tokens=2000, temperature=0.6)

    async def generate_image_prompt(self, brand: str, title: str, description: str) -> str:
        prompt = build_image_prompt_request(brand, title, description)
        return (await self._call(prompt, max_tokens=200, temperature=0.3)).strip()

    async def _call(self, prompt: str, max_tokens: int, temperature: float) -> str:
        url = _BASE.format(model=self.settings.gemini_model)
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                headers={"X-goog-api-key": self.settings.gemini_api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
                },
            )
        response.raise_for_status()
        parts = response.json()["candidates"][0]["content"]["parts"]
        # Filtra parts de "thinking" (gemini-2.5-flash/-pro emite pensamentos separados)
        return "".join(p.get("text", "") for p in parts if not p.get("thought", False))
