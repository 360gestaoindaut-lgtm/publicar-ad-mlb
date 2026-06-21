import asyncio
import json
import httpx
from app.config import get_settings


async def main():
    s = get_settings()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{s.gemini_model}:generateContent"
    prompt = 'Responda EXCLUSIVAMENTE em JSON valido sem markdown: {"titles": [{"title": "teste", "score": 9.0}]}'
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            url,
            headers={"X-goog-api-key": s.gemini_api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2000},
            },
        )
    print("STATUS:", r.status_code)
    data = r.json()
    parts = data["candidates"][0]["content"]["parts"]
    text = "".join(p.get("text", "") for p in parts)
    print("FINISH:", data["candidates"][0]["finishReason"])
    print("TEXT:", text)


if __name__ == "__main__":
    asyncio.run(main())
