import asyncio
import base64
import httpx
from app.config import get_settings


async def main():
    s = get_settings()

    print("Testando imagen-4.0-fast-generate-001 sem negativePrompt...")
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            "https://generativelanguage.googleapis.com/v1beta/models/imagen-4.0-fast-generate-001:predict",
            headers={"X-goog-api-key": s.gemini_api_key},
            json={
                "instances": [{"prompt": "Professional product photo of a Samsung smartphone on pure white background, studio lighting, e-commerce style, no text, no people, high resolution"}],
                "parameters": {
                    "sampleCount": 2,
                    "aspectRatio": "1:1",
                    "personGeneration": "DONT_ALLOW",
                },
            },
        )
    print("Status:", r.status_code)
    if r.status_code == 200:
        predictions = r.json().get("predictions", [])
        print(f"Imagens retornadas: {len(predictions)}")
        for i, p in enumerate(predictions):
            data = base64.b64decode(p["bytesBase64Encoded"])
            print(f"  Imagem {i+1}: {len(data)} bytes, mime={p.get('mimeType')}")
    else:
        print("Erro:", r.text[:400])


if __name__ == "__main__":
    asyncio.run(main())
