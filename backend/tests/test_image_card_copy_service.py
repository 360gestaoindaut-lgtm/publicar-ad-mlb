from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.image_card_copy_service import (
    CARD_KINDS,
    MAX_BULLET_CHARS,
    MAX_TITLE_CHARS,
    CardCopy,
    _banned_reason,
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


def _specs_attributes() -> list[SimpleNamespace]:
    """Atributos que rendem uma ficha tecnica.

    O `card_specs` deixou de vir do LLM: e montado por `build_specs_card` a
    partir do `value_name` dos atributos. Testes que esperam os 3 cards
    precisam fornecer atributos — com a lista vazia o card de specs
    legitimamente nao existe. Ver `test_specs_card_deterministic.py`.
    """
    return [
        SimpleNamespace(attribute_id="BRAND", attribute_name="Marca",
                        value_name="Vonder", value_id=None),
        SimpleNamespace(attribute_id="MODEL", attribute_name="Modelo",
                        value_name="FI-750", value_id=None),
        SimpleNamespace(attribute_id="POWER", attribute_name="Potência",
                        value_name="750 W", value_id="9001"),
    ]


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
            result = await generate_card_copy(_listing(), attributes=_specs_attributes())

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
        """Veiculo trocado de `specs` para `benefits` de proposito: o truncamento
        e do sanitizador do LLM, e `card_specs` nao passa mais por ele. Deixar
        o caso em specs testaria um caminho que nao existe."""
        response = _well_formed_response()
        long_bullet = "Este bullet de beneficio tem oitenta caracteres de puro enchimento aqui ok"
        assert len(long_bullet) > MAX_BULLET_CHARS
        response["benefits"]["bullets"] = [long_bullet, "750W", "Bivolt"]

        mock_ai = AsyncMock()
        mock_ai.generate_card_copy = AsyncMock(return_value=response)

        with patch("app.services.ai.service.get_ai_provider", return_value=mock_ai):
            result = await generate_card_copy(_listing(), attributes=[])

        benefits = next(c for c in result if c.kind == "card_benefits")
        assert len(benefits.bullets[0]) <= MAX_BULLET_CHARS


class TestAngleDropping:
    @pytest.mark.asyncio
    async def test_angle_with_only_one_bullet_is_dropped_others_survive(self):
        response = _well_formed_response()
        response["usage"]["bullets"] = ["Só um bullet"]

        mock_ai = AsyncMock()
        mock_ai.generate_card_copy = AsyncMock(return_value=response)

        with patch("app.services.ai.service.get_ai_provider", return_value=mock_ai):
            result = await generate_card_copy(_listing(), attributes=_specs_attributes())

        kinds = [c.kind for c in result]
        assert "card_usage" not in kinds
        assert "card_benefits" in kinds
        assert "card_specs" in kinds
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_angle_with_empty_title_is_dropped_others_survive(self):
        """Veiculo trocado de `specs` para `usage`: com specs, este teste
        continuava PASSANDO depois da mudanca, mas pelo motivo errado — o card
        sumia por nao haver atributos, e nao por causa do titulo vazio. Um
        teste que passa sem exercitar a regra e pior que um que falha."""
        response = _well_formed_response()
        response["usage"]["title"] = "   "

        mock_ai = AsyncMock()
        mock_ai.generate_card_copy = AsyncMock(return_value=response)

        with patch("app.services.ai.service.get_ai_provider", return_value=mock_ai):
            result = await generate_card_copy(_listing(), attributes=_specs_attributes())

        kinds = [c.kind for c in result]
        assert "card_usage" not in kinds
        assert kinds == ["card_benefits", "card_specs"]


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
            result = await generate_card_copy(_listing(), attributes=_specs_attributes())

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


# --------------------------------------------------------------------------
# Denylist de conteudo: o ML proibe preco, contato, promessa de entrega e
# superlativo nao comprovavel DENTRO da imagem. O prompt ja proibe, mas em
# modo batch a imagem e auto-aprovada e publicada sem revisao humana.
# --------------------------------------------------------------------------


class TestContentDenylistUnit:
    @pytest.mark.parametrize(
        "texto,padrao",
        [
            ("Leve hoje por R$ 199,90 a vista", "preco_moeda"),
            ("Apenas 199,90 no pagamento a vista", "preco_numerico"),
            ("Compre em https://loja.exemplo.com", "url"),
            ("Peca pelo www.exemplo.com.br", "url"),
            ("Chame no (11) 98888-7777", "telefone"),
            ("Frete gratis para todo o Brasil", "promessa_de_entrega"),
            ("Frete grátis para todo o Brasil", "promessa_de_entrega"),
            ("FRETE  GRATIS em todos os pedidos", "promessa_de_entrega"),
            ("O melhor do mercado em conforto", "superlativo"),
        ],
    )
    def test_conteudo_proibido_e_detectado(self, texto, padrao):
        assert _banned_reason(texto) == padrao

    @pytest.mark.parametrize(
        "texto",
        [
            # Especificacao legitima nao pode ser confundida com preco: um
            # falso positivo aqui apaga um bullet bom em producao.
            "Bateria de 12V com autonomia prolongada",
            "Espessura de 3,5cm em madeira macica",
            "Capacidade de 500ml com tampa rosqueada",
            "Alcance de 1,5 m sem perda de sinal",
            "Alcance de 12,50 m em campo aberto",
            "Cabo de 3,50 m em nylon trancado",
            "Peso de 1,25 kg com a base incluida",
            "Volume util de 12,50 l no compartimento",
            "Tela de 6,50 pol com brilho ajustavel",
            "Bateria de 5000mAh com carga rapida",
            "Motor de 1500 W com tres velocidades",
            "Reducao de 99,9% das bacterias",
            "Mantém bebidas geladas por até doze horas",
        ],
    )
    def test_conteudo_legitimo_nao_e_derrubado(self, texto):
        assert _banned_reason(texto) is None


class TestContentDenylistSanitizer:
    @pytest.mark.asyncio
    async def test_bullet_proibido_cai_e_o_angulo_sobrevive(self):
        response = _well_formed_response()
        response["benefits"]["bullets"] = [
            "750W de potencia real",
            "Leve hoje por R$ 199,90",
            "Uso profissional diario",
        ]

        mock_ai = AsyncMock()
        mock_ai.generate_card_copy = AsyncMock(return_value=response)
        with patch("app.services.ai.service.get_ai_provider", return_value=mock_ai):
            result = await generate_card_copy(_listing(), attributes=_specs_attributes())

        assert [c.kind for c in result] == list(CARD_KINDS)
        benefits = next(c for c in result if c.kind == "card_benefits")
        assert benefits.bullets == ["750W de potencia real", "Uso profissional diario"]

    @pytest.mark.asyncio
    async def test_angulo_cai_quando_sobram_menos_que_min_bullets(self):
        response = _well_formed_response()
        response["benefits"]["bullets"] = [
            "Frete gratis para todo o Brasil",
            "Uso profissional diario",
        ]

        mock_ai = AsyncMock()
        mock_ai.generate_card_copy = AsyncMock(return_value=response)
        with patch("app.services.ai.service.get_ai_provider", return_value=mock_ai):
            result = await generate_card_copy(_listing(), attributes=_specs_attributes())

        assert [c.kind for c in result] == ["card_usage", "card_specs"]

    @pytest.mark.asyncio
    async def test_titulo_proibido_derruba_o_angulo_inteiro(self):
        response = _well_formed_response()
        response["benefits"]["title"] = "O melhor do mercado"

        mock_ai = AsyncMock()
        mock_ai.generate_card_copy = AsyncMock(return_value=response)
        with patch("app.services.ai.service.get_ai_provider", return_value=mock_ai):
            result = await generate_card_copy(_listing(), attributes=_specs_attributes())

        assert [c.kind for c in result] == ["card_usage", "card_specs"]

    @pytest.mark.asyncio
    async def test_truncamento_nao_lava_conteudo_proibido(self):
        """O preco cai fora dos 50 caracteres no truncamento — mesmo assim o
        bullet e descartado: o filtro roda no texto cru, senao bastaria o LLM
        empurrar o preco pro fim da frase pra publicar preco na imagem."""
        bullet = "Uso profissional diario em obra pesada e oficina por R$ 199,90"
        assert bullet.index("R$") > MAX_BULLET_CHARS

        response = _well_formed_response()
        response["benefits"]["bullets"] = [
            "750W de potencia real",
            bullet,
            "Maleta rigida inclusa",
        ]

        mock_ai = AsyncMock()
        mock_ai.generate_card_copy = AsyncMock(return_value=response)
        with patch("app.services.ai.service.get_ai_provider", return_value=mock_ai):
            result = await generate_card_copy(_listing(), attributes=[])

        benefits = next(c for c in result if c.kind == "card_benefits")
        assert benefits.bullets == ["750W de potencia real", "Maleta rigida inclusa"]

    @pytest.mark.asyncio
    async def test_copy_legitima_com_medidas_passa_intacta(self):
        """Veiculo trocado de `specs` para `benefits`: a denylist so roda no
        texto do LLM, e specs deixou de vir dele."""
        response = _well_formed_response()
        bullets = [
            "Espessura de 3,5cm em madeira macica",
            "Alcance de 12,50 m em campo aberto",
            "Bateria de 12V com 5000mAh",
        ]
        response["benefits"]["bullets"] = bullets

        mock_ai = AsyncMock()
        mock_ai.generate_card_copy = AsyncMock(return_value=response)
        with patch("app.services.ai.service.get_ai_provider", return_value=mock_ai):
            result = await generate_card_copy(_listing(), attributes=[])

        benefits = next(c for c in result if c.kind == "card_benefits")
        assert benefits.bullets == bullets


class TestFailureLogging:
    """A excecao do provider morre aqui por design; o traceback neste log e a
    unica forma de saber em producao se foi provider, rede, JSON ou chave
    faltando — `reason=%s` sozinho nao distingue nenhum desses casos."""

    @pytest.mark.asyncio
    async def test_falha_do_provider_loga_com_traceback(self, caplog):
        import logging

        mock_ai = AsyncMock()
        mock_ai.generate_card_copy = AsyncMock(side_effect=RuntimeError("timeout do provider"))

        with caplog.at_level(logging.WARNING, logger="app.services.image_card_copy_service"), \
                patch("app.services.ai.service.get_ai_provider", return_value=mock_ai):
            result = await generate_card_copy(_listing(), attributes=[])

        assert result == []
        rec = next(r for r in caplog.records if "result=failed" in r.getMessage())
        assert rec.exc_info is not None
        assert rec.exc_info[0] is RuntimeError
