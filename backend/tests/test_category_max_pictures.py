"""Teto de fotos por categoria: aceitar o ML nao e confiar nele.

`get_category_max_pictures` le `settings.max_pictures_per_item` do ML e o
`publish_service` usa esse valor para cortar o array de fotos. Devolver None
significa "nao sei" — o chamador cai em `ML_MAX_PICTURES_FALLBACK` (12).

O que estes testes travam: valor ausente, negativo, booleano ou ABSURDO nunca
podem virar teto. Sem o cap de sanidade, uma resposta corrompida (ou um campo
que mude de semantica no ML) faria a publicacao tentar subir centenas de fotos.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.category_service import (
    ML_MAX_PICTURES_SANITY_CAP,
    get_category_max_pictures,
)


def _client_returning(payload):
    """httpx.AsyncClient falso cujo GET devolve `payload` como JSON."""
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=payload)
    cli = MagicMock()
    cli.get = AsyncMock(return_value=resp)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=cli)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


async def _call(payload):
    with patch("httpx.AsyncClient", return_value=_client_returning(payload)):
        return await get_category_max_pictures("MLB1234")


class TestSanityCap:
    @pytest.mark.asyncio
    async def test_valor_normal_passa(self):
        assert await _call({"settings": {"max_pictures_per_item": 12}}) == 12

    @pytest.mark.asyncio
    async def test_valor_no_limite_do_cap_ainda_passa(self):
        """A fronteira e inclusiva — o cap rejeita o que esta ACIMA dele."""
        payload = {"settings": {"max_pictures_per_item": ML_MAX_PICTURES_SANITY_CAP}}
        assert await _call(payload) == ML_MAX_PICTURES_SANITY_CAP

    @pytest.mark.asyncio
    async def test_valor_absurdo_vira_nao_sei(self):
        payload = {"settings": {"max_pictures_per_item": ML_MAX_PICTURES_SANITY_CAP + 1}}
        assert await _call(payload) is None, (
            "sem isto, o publish_service usaria o valor absurdo como teto"
        )

    @pytest.mark.asyncio
    async def test_valor_gigante_vira_nao_sei(self):
        assert await _call({"settings": {"max_pictures_per_item": 99999}}) is None

    @pytest.mark.asyncio
    async def test_zero_e_negativo_viram_nao_sei(self):
        assert await _call({"settings": {"max_pictures_per_item": 0}}) is None
        assert await _call({"settings": {"max_pictures_per_item": -5}}) is None

    @pytest.mark.asyncio
    async def test_booleano_nao_vira_teto_de_1(self):
        """`isinstance(True, int)` e True em Python — o cap nao pode virar 1."""
        assert await _call({"settings": {"max_pictures_per_item": True}}) is None

    @pytest.mark.asyncio
    async def test_campo_ausente_vira_nao_sei(self):
        assert await _call({"settings": {}}) is None
        assert await _call({}) is None

    @pytest.mark.asyncio
    async def test_categoria_vazia_nao_chama_o_ml(self):
        ctx = _client_returning({"settings": {"max_pictures_per_item": 12}})
        with patch("httpx.AsyncClient", return_value=ctx) as cli_cls:
            assert await get_category_max_pictures("") is None
        cli_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_cap_e_no_minimo_o_limite_padrao_do_ml(self):
        """Trava contra baixar o cap para menos que o teto real do ML."""
        assert ML_MAX_PICTURES_SANITY_CAP >= 12
