from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.image_card_copy_service import (
    CARD_KINDS,
    MAX_BULLET_CHARS,
    MAX_TITLE_CHARS,
    CardCopy,
    _build_source,
    generate_card_copy,
)


def _listing(**overrides) -> SimpleNamespace:
    defaults = dict(
        id="listing-1",
        selected_title="Furadeira de Impacto 750W Bivolt",
        sku_description="Furadeira de impacto profissional 750W bivolt com maleta",
        sku_brand="Vonder",
        sku_model="FI-750",
        price="199.90",     # nunca deve aparecer em _build_source
        stock_quantity=42,  # idem
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _attr(attribute_name: str, value_name: str | None) -> SimpleNamespace:
    return SimpleNamespace(attribute_name=attribute_name, value_name=value_name)


def _well_formed_response() -> dict:
    return {
        "benefits": {
            "title": "Mais potencia no trabalho",
            "bullets": ["750W de potencia real", "Uso profissional diario"],
        },
        "usage": {
            "title": "Facil de usar",
            "bullets": ["Empunhe e acione o gatilho", "Ajuste a velocidade conforme a tarefa"],
        },
        "specs": {
            "title": "Especificacoes",
            "bullets": ["750W", "Bivolt", "Acompanha maleta"],
        },
    }


class TestGenerateCardCopyHappyPath:
    @pytest.mark.asyncio
    async def test_well_formed_response_returns_three_cards_in_order(self):
        mock_ai = AsyncMock()
        mock_ai.generate_card_copy = AsyncMock(return_value=_well_formed_response())

        with patch("app.services.ai.service.get_ai_provider", return_value=mock_ai):
            result = await generate_card_copy(_listing(), attributes=[])

        assert [c.kind for c in result] == list(CARD_KINDS)
        assert all(isinstance(c, CardCopy) for c in result)
        mock_ai.generate_card_copy.assert_awaited_once()


class TestTruncation:
    @pytest.mark.asyncio
    async def test_title_over_40_chars_is_truncated(self):
        response = _well_formed_response()
        response["benefits"]["title"] = "Um titulo de beneficio absurdamente longo demais"
        assert len(response["benefits"]["title"]) > MAX_TITLE_CHARS

        mock_ai = AsyncMock()
        mock_ai.generate_card_copy = AsyncMock(return_value=response)

        with patch("app.services.ai.service.get_ai_provider", return_value=mock_ai):
            result = await generate_card_copy(_listing(), attributes=[])

        benefits = next(c for c in result if c.kind == "card_benefits")
        assert len(benefits.title) <= MAX_TITLE_CHARS
        # Truncamento no limite de palavra: corta no ultimo espaco dentro do
        # limite, nunca no meio de uma palavra.
        assert benefits.title == "Um titulo de beneficio absurdamente"

    @pytest.mark.asyncio
    async def test_bullet_over_50_chars_is_truncated(self):
        response = _well_formed_response()
        long_bullet = "Este bullet de especificacao tem oitenta caracteres de puro enchimento aqui"
        assert len(long_bullet) > MAX_BULLET_CHARS
        response["specs"]["bullets"] = [long_bullet, "750W", "Bivolt"]

        mock_ai = AsyncMock()
        mock_ai.generate_card_copy = AsyncMock(return_value=response)

        with patch("app.services.ai.service.get_ai_provider", return_value=mock_ai):
            result = await generate_card_copy(_listing(), attributes=[])

        specs = next(c for c in result if c.kind == "card_specs")
        assert len(specs.bullets[0]) <= MAX_BULLET_CHARS


class TestAngleDropping:
    @pytest.mark.asyncio
    async def test_angle_with_only_one_bullet_is_dropped_others_survive(self):
        response = _well_formed_response()
        response["usage"]["bullets"] = ["Só um bullet"]

        mock_ai = AsyncMock()
        mock_ai.generate_card_copy = AsyncMock(return_value=response)

        with patch("app.services.ai.service.get_ai_provider", return_value=mock_ai):
            result = await generate_card_copy(_listing(), attributes=[])

        kinds = [c.kind for c in result]
        assert "card_usage" not in kinds
        assert "card_benefits" in kinds
        assert "card_specs" in kinds
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_angle_with_empty_title_is_dropped_others_survive(self):
        response = _well_formed_response()
        response["specs"]["title"] = "   "

        mock_ai = AsyncMock()
        mock_ai.generate_card_copy = AsyncMock(return_value=response)

        with patch("app.services.ai.service.get_ai_provider", return_value=mock_ai):
            result = await generate_card_copy(_listing(), attributes=[])

        kinds = [c.kind for c in result]
        assert "card_specs" not in kinds
        assert len(result) == 2


class TestResilience:
    @pytest.mark.asyncio
    async def test_provider_exception_returns_empty_list_never_raises(self):
        mock_ai = AsyncMock()
        mock_ai.generate_card_copy = AsyncMock(side_effect=RuntimeError("boom"))

        with patch("app.services.ai.service.get_ai_provider", return_value=mock_ai):
            result = await generate_card_copy(_listing(), attributes=[])

        assert result == []

    @pytest.mark.asyncio
    async def test_missing_key_only_present_angles_returned(self):
        response = _well_formed_response()
        del response["usage"]

        mock_ai = AsyncMock()
        mock_ai.generate_card_copy = AsyncMock(return_value=response)

        with patch("app.services.ai.service.get_ai_provider", return_value=mock_ai):
            result = await generate_card_copy(_listing(), attributes=[])

        kinds = [c.kind for c in result]
        assert kinds == ["card_benefits", "card_specs"]


class TestBuildSource:
    def test_includes_title_description_brand_model_and_attributes_excludes_price(self):
        listing = _listing()
        attributes = [
            _attr("Cor", "Vermelho"),
            _attr("Voltagem", None),  # sem value_name -> descartado
            _attr("Potência", "750W"),
        ]

        source = _build_source(listing, attributes)

        assert source["selected_title"] == listing.selected_title
        assert source["sku_description"] == listing.sku_description
        assert source["sku_brand"] == listing.sku_brand
        assert source["sku_model"] == listing.sku_model
        assert source["attributes"] == [
            {"attribute_name": "Cor", "value_name": "Vermelho"},
            {"attribute_name": "Potência", "value_name": "750W"},
        ]
        assert "price" not in source
        assert "stock_quantity" not in source

    def test_handles_none_attributes(self):
        source = _build_source(_listing(), None)
        assert source["attributes"] == []
