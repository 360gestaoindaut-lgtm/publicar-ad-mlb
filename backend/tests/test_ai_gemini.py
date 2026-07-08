import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.ai.gemini import GeminiProvider


def _mock_gemini_response(text: str) -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": text}]}}]
    }
    return response


class TestGenerateTitles:
    @pytest.mark.asyncio
    async def test_success_returns_titles_list(self):
        text = (
            '{"titles": [{"title": "Suporte Celular Veicular", "score": 9.2, '
            '"rationale": "bom"}]}'
        )
        mock_post = AsyncMock(return_value=_mock_gemini_response(text))
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            provider = GeminiProvider()
            titles = await provider.generate_titles(
                sku_description="Suporte veicular", sku_brand="Genérico", condition="new",
            )

        assert titles == [{"title": "Suporte Celular Veicular", "score": 9.2, "rationale": "bom"}]

    @pytest.mark.asyncio
    async def test_raises_clear_error_when_gemini_returns_prose_not_json(self):
        """Reproduz o bug real: quando o Gemini responde em prosa (sem JSON),
        json_repair transforma o texto inteiro numa string JSON vazia, e antes
        disso o código quebrava com um TypeError genérico ao indexar ["titles"]
        numa string. Agora deve levantar um erro claro em vez disso."""
        text = "Aqui estão os títulos sugeridos para o produto solicitado."
        mock_post = AsyncMock(return_value=_mock_gemini_response(text))
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            provider = GeminiProvider()
            with pytest.raises(RuntimeError, match="não retornou"):
                await provider.generate_titles(
                    sku_description="Suporte veicular", sku_brand="Genérico", condition="new",
                )

    @pytest.mark.asyncio
    async def test_batch_mode_raises_clear_error_when_gemini_returns_prose(self):
        text = "Desculpe, não posso gerar isso."
        mock_post = AsyncMock(return_value=_mock_gemini_response(text))
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            provider = GeminiProvider()
            with pytest.raises(RuntimeError, match="não retornou"):
                await provider.generate_titles(
                    sku_description="Suporte veicular", sku_brand="Genérico", condition="new",
                    batch_mode=True,
                )
