"""Descoberta de fotos brutas: 2 e o minimo, nao o teto.

Antes o codigo so buscava `{sku}-1.jpg` e `{sku}-2.jpg`, entao seller com
3-10 fotos por SKU tinha as extras ignoradas. Agora a quantidade e descoberta
por sondagem, mantendo as 2 primeiras como obrigatorias.
"""
import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.seller_image_source_service import (
    RAW_PHOTOS_MAX,
    RAW_PHOTOS_MIN,
    fetch_raw_photos,
)

BASE = "https://bucket.exemplo/sku"


def _cliente(por_url):
    """Cliente httpx falso: `por_url` mapeia URL -> resposta ou excecao."""
    cli = MagicMock()

    async def get(url):
        item = por_url.get(url)
        if item is None:
            r = MagicMock(); r.status_code = 404; r.content = b""
            return r
        if isinstance(item, Exception):
            raise item
        r = MagicMock(); r.status_code = 200; r.content = item
        return r

    cli.get = AsyncMock(side_effect=get)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=cli)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx, cli


def _urls(sku, quantas):
    return {f"{BASE}/{sku}-{n}.jpg": f"foto{n}".encode() for n in range(1, quantas + 1)}


class TestDescoberta:
    @pytest.mark.asyncio
    async def test_exatamente_2_fotos_comportamento_identico_ao_antigo(self):
        """Seller minimo: nada pode mudar para ele."""
        ctx, cli = _cliente(_urls("A", 2))
        with patch("httpx.AsyncClient", return_value=ctx):
            fotos = await fetch_raw_photos(BASE, "A")

        assert fotos == [b"foto1", b"foto2"]
        # sondou a 3a e parou; nao pode varrer ate o teto a toa
        assert cli.get.await_count == 3

    @pytest.mark.asyncio
    async def test_cinco_fotos_todas_descobertas(self):
        ctx, cli = _cliente(_urls("B", 5))
        with patch("httpx.AsyncClient", return_value=ctx):
            fotos = await fetch_raw_photos(BASE, "B")

        assert len(fotos) == 5
        assert fotos == [b"foto1", b"foto2", b"foto3", b"foto4", b"foto5"]

    @pytest.mark.asyncio
    async def test_falta_a_foto_1_devolve_none_mesmo_tendo_2_e_3(self):
        """As 2 primeiras sao obrigatorias — ter as outras nao compensa."""
        mapa = {
            f"{BASE}/C-2.jpg": b"foto2",
            f"{BASE}/C-3.jpg": b"foto3",
        }
        ctx, _ = _cliente(mapa)
        with patch("httpx.AsyncClient", return_value=ctx):
            assert await fetch_raw_photos(BASE, "C") is None

    @pytest.mark.asyncio
    async def test_falta_a_foto_2_devolve_none(self):
        ctx, _ = _cliente({f"{BASE}/D-1.jpg": b"foto1", f"{BASE}/D-3.jpg": b"foto3"})
        with patch("httpx.AsyncClient", return_value=ctx):
            assert await fetch_raw_photos(BASE, "D") is None

    @pytest.mark.asyncio
    async def test_para_no_teto_e_nao_sonda_indefinidamente(self):
        """Bucket com mais fotos que o teto: para em RAW_PHOTOS_MAX."""
        ctx, cli = _cliente(_urls("E", RAW_PHOTOS_MAX + 5))
        with patch("httpx.AsyncClient", return_value=ctx):
            fotos = await fetch_raw_photos(BASE, "E")

        assert len(fotos) == RAW_PHOTOS_MAX
        assert cli.get.await_count == RAW_PHOTOS_MAX

    @pytest.mark.asyncio
    async def test_erro_de_rede_numa_obrigatoria_devolve_none(self):
        ctx, _ = _cliente({f"{BASE}/F-1.jpg": httpx.ConnectError("sem rede")})
        with patch("httpx.AsyncClient", return_value=ctx):
            assert await fetch_raw_photos(BASE, "F") is None

    @pytest.mark.asyncio
    async def test_erro_de_rede_numa_extra_nao_derruba_o_sku(self):
        """Falha transitoria na 3a nao pode invalidar um SKU que tem o minimo."""
        mapa = _urls("G", 2)
        mapa[f"{BASE}/G-3.jpg"] = httpx.ConnectError("timeout")
        ctx, _ = _cliente(mapa)
        with patch("httpx.AsyncClient", return_value=ctx):
            fotos = await fetch_raw_photos(BASE, "G")

        assert fotos == [b"foto1", b"foto2"], "usa o que veio, nao devolve None"

    def test_o_minimo_continua_2(self):
        """Trava contra alguem 'melhorar' o minimo sem perceber o impacto."""
        assert RAW_PHOTOS_MIN == 2


class TestFonteDaPosicao4:
    """Posicao 4 ("Detalhes") do esquema de 5 posicoes.

    Ver docs/superpowers/specs/esquema-5-posicoes.md. A funcao so ESCOLHE a
    fonte — nao trata, nao recorta, nao chama IA.
    """

    def test_com_fotos_extras_usa_a_terceira(self):
        from app.services.seller_image_source_service import pick_detail_source

        foto, veio_de_extra = pick_detail_source([b"f1", b"f2", b"f3", b"f4"])

        assert foto == b"f3", "a regra e simples e documentada: a 3a foto"
        assert veio_de_extra is True

    def test_com_exatamente_3_fotos_ja_usa_a_terceira(self):
        from app.services.seller_image_source_service import pick_detail_source

        assert pick_detail_source([b"f1", b"f2", b"f3"]) == (b"f3", True)

    def test_so_o_minimo_cai_no_fallback_e_avisa(self):
        """Sem extra, o chamador PRECISA saber que e reaproveitamento."""
        from app.services.seller_image_source_service import pick_detail_source

        foto, veio_de_extra = pick_detail_source([b"f1", b"f2"])

        assert veio_de_extra is False, (
            "a flag e o que permite ao chamador nao forcar um 'detalhe' que a "
            "foto nao mostra"
        )
        assert foto == b"f2", "a ultima, para nao repetir a fonte da posicao 2"

    def test_nao_usa_foto_que_alimenta_a_posicao_2_quando_ha_extra(self):
        from app.services.seller_image_source_service import pick_detail_source

        foto, _ = pick_detail_source([b"f1", b"f2", b"f3"])

        assert foto not in (b"f1", b"f2"), (
            "havendo extra, a posicao 4 nao pode repetir a fonte da posicao 2"
        )

    def test_lista_vazia_e_erro_de_programacao(self):
        from app.services.seller_image_source_service import pick_detail_source

        with pytest.raises(ValueError):
            pick_detail_source([])


class TestProducaoNaoConsomeFotosExtras:
    """O loop de individuais em producao continua limitado ao minimo.

    `fetch_raw_photos` e compartilhada com o piloto e passou a devolver ate 10
    fotos. Sem o corte, um seller com 5 fotos geraria 10 individuais em vez de
    4 — 2.5x o custo de IA e 14 imagens contra o teto de 12 do ML.
    """

    @pytest.mark.asyncio
    async def test_cinco_fotos_ainda_geram_quatro_individuais(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.services.image_service import ImageValidationResult
        from app.workers.tasks.image_tasks import _try_i2i_generation

        listing = MagicMock()
        listing.id = "lid"; listing.seller_id = "sid"
        listing.sku_external_id = "SKU1"; listing.created_via = "manual"

        db = AsyncMock()
        cfg = MagicMock(); cfg.raw_base_url = "https://b/x"
        res = MagicMock(); res.scalar_one_or_none = MagicMock(return_value=cfg)
        db.execute = AsyncMock(return_value=res); db.add = MagicMock()

        cinco = {"SKU1": [b"f1", b"f2", b"f3", b"f4", b"f5"]}

        with patch(
            "app.services.seller_image_source_service.fetch_all_raw_photos",
            new_callable=AsyncMock, return_value=cinco,
        ), patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as engine_cls, patch(
            "app.workers.tasks.image_tasks._resolve_requires_white_bg",
            new_callable=AsyncMock, return_value=False,
        ), patch(
            "app.workers.tasks.image_tasks._prepare_image_for_upload",
            side_effect=lambda b, requires_white_bg: (b, ImageValidationResult(is_valid=True, errors=[])),
        ), patch(
            "app.services.image_deterministic_service.try_deterministic_cover",
            return_value=None,
        ), patch(
            "app.workers.tasks.image_tasks._append_benefit_cards",
            new_callable=AsyncMock, return_value=0,
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as ml_cls:
            engine_cls.return_value.edit = AsyncMock(return_value=[b"v1", b"v2"])
            ml_cls.return_value.upload = AsyncMock(side_effect=[f"p{i}" for i in range(20)])
            salvas = await _try_i2i_generation(db, listing, MagicMock(), "token")

        assert engine_cls.return_value.edit.await_count == 2, (
            "2 chamadas ao motor (as 2 primeiras fotos), nao 5 — o corte "
            "[:RAW_PHOTOS_MIN] e o que impede a explosao de custo"
        )
        assert salvas == 4, "4 individuais, exatamente como antes da descoberta"
