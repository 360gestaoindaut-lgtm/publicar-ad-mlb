"""Testes da Task 1 (SPEC frentes A/B — capa e ficha): persistencia dos bytes
da capa deterministica em `ListingImage.image_bytes`.

Escopo deliberadamente estreito: so a capa deterministica popula a coluna.
Individuais e cards continuam com `image_bytes=None` — a variante de capa
(frente futura) so precisa da capa, e persistir bytes de toda imagem seria
custo de armazenamento sem uso conhecido.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.image_service import ImageValidationResult


def _passthrough_prepare(image_bytes, requires_white_bg):
    """Substitui o pos-processamento + QA nos testes: aprova e devolve os bytes."""
    return image_bytes, ImageValidationResult(is_valid=True, errors=[])


def _make_listing():
    listing = MagicMock()
    listing.id = "lid"
    listing.seller_id = "sid"
    listing.sku_external_id = "SKU0001"
    listing.created_via = "manual"
    return listing


def _make_i2i_db(attributes=None):
    """Mock de sessao que responde tanto a query do SellerImageConfig quanto
    a query de ListingAttribute que `_append_benefit_cards` dispara."""
    mock_config = MagicMock()
    mock_config.raw_base_url = "https://pub-xxx.r2.dev/sku"

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_config
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.execute.return_value.scalars.return_value.all.return_value = (
        attributes if attributes is not None else []
    )
    added = []
    mock_db.add = MagicMock(side_effect=added.append)
    return mock_db, added


class TestCoverDeterministicBytesPersistence:
    @pytest.mark.asyncio
    async def test_capa_deterministica_grava_os_mesmos_bytes_do_upload(self):
        """image_bytes da capa == exatamente o que foi enviado ao ML."""
        from app.services.image_card_copy_service import CARD_KINDS
        from app.workers.tasks.image_tasks import _try_i2i_generation

        mock_db, added = _make_i2i_db([MagicMock()])
        cover_bytes = b"capa-deterministica-bytes-exatos"

        with patch(
            "app.services.seller_image_source_service.fetch_all_raw_photos",
            new_callable=AsyncMock,
            return_value={"SKU0001": [b"raw1"]},
        ), patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as mock_engine_cls, patch(
            "app.workers.tasks.image_tasks._resolve_requires_white_bg",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "app.workers.tasks.image_tasks._prepare_image_for_upload",
            side_effect=_passthrough_prepare,
        ), patch(
            "app.services.image_deterministic_service.try_deterministic_cover",
            return_value=cover_bytes,
        ), patch(
            "app.services.image_card_copy_service.generate_card_copy",
            new_callable=AsyncMock,
            return_value=[
                MagicMock(kind=kind, title="t", bullets=["a", "b"]) for kind in CARD_KINDS
            ],
        ), patch(
            "app.services.image_benefit_card_service.render_benefit_card",
            side_effect=[b"card-a", b"card-b", b"card-c"],
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(return_value=[b"ind-1", b"ind-2"])
            mock_ml_cls.return_value.upload = AsyncMock(
                side_effect=["capa", "pic1", "pic2", "c1", "c2", "c3"]
            )
            await _try_i2i_generation(mock_db, _make_listing(), MagicMock(), "token")

        covers = [o for o in added if getattr(o, "kind", None) == "cover_deterministic"]
        assert len(covers) == 1
        assert covers[0].image_bytes == cover_bytes

    @pytest.mark.asyncio
    async def test_individuais_e_cards_ficam_com_image_bytes_nulo(self):
        """Escopo e so a capa: individuais e cards nao ganham a coluna preenchida."""
        from app.services.image_card_copy_service import CARD_KINDS
        from app.workers.tasks.image_tasks import _try_i2i_generation

        mock_db, added = _make_i2i_db([MagicMock()])

        with patch(
            "app.services.seller_image_source_service.fetch_all_raw_photos",
            new_callable=AsyncMock,
            return_value={"SKU0001": [b"raw1"]},
        ), patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as mock_engine_cls, patch(
            "app.workers.tasks.image_tasks._resolve_requires_white_bg",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "app.workers.tasks.image_tasks._prepare_image_for_upload",
            side_effect=_passthrough_prepare,
        ), patch(
            "app.services.image_deterministic_service.try_deterministic_cover",
            return_value=b"capa-deterministica-bytes-exatos",
        ), patch(
            "app.services.image_card_copy_service.generate_card_copy",
            new_callable=AsyncMock,
            return_value=[
                MagicMock(kind=kind, title="t", bullets=["a", "b"]) for kind in CARD_KINDS
            ],
        ), patch(
            "app.services.image_benefit_card_service.render_benefit_card",
            side_effect=[b"card-a", b"card-b", b"card-c"],
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(return_value=[b"ind-1", b"ind-2"])
            mock_ml_cls.return_value.upload = AsyncMock(
                side_effect=["capa", "pic1", "pic2", "c1", "c2", "c3"]
            )
            await _try_i2i_generation(mock_db, _make_listing(), MagicMock(), "token")

        nao_capa = [
            o for o in added
            if type(o).__name__ == "ListingImage" and o.kind != "cover_deterministic"
        ]
        assert len(nao_capa) == 5, "2 individuais + 3 cards"
        assert all(o.image_bytes is None for o in nao_capa)
