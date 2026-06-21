import json
import httpx
from app.config import get_settings
from app.services.ai.base import AIProvider
from app.services.ai.prompts import build_title_prompt, build_description_prompt, build_image_prompt_request

_BASE = "https://api.anthropic.com/v1/messages"


class ClaudeProvider(AIProvider):
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
        text = await self._call(prompt, max_tokens=200 if batch_mode else 500, temperature=0.6)
        if batch_mode:
            title = text.strip().replace('"', '').replace("'", '')[:60]
            return [{"title": title, "score": None, "rationale": "batch_auto"}]
        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(text)["titles"]

    async def generate_description(self, listing_data: dict) -> str:
        prompt = build_description_prompt(listing_data)
        return await self._call(prompt, max_tokens=2000, temperature=0.6)

    async def generate_image_prompt(self, brand: str, title: str, description: str) -> str:
        prompt = build_image_prompt_request(brand, title, description)
        return (await self._call(prompt, max_tokens=200, temperature=0.3)).strip()

    async def _call(self, prompt: str, max_tokens: int, temperature: float) -> str:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                _BASE,
                headers={
                    "x-api-key": self.settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.settings.claude_model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        response.raise_for_status()
        return response.json()["content"][0]["text"]
