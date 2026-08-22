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


class TestTryI2iGeneration:
    @pytest.mark.asyncio
    async def test_returns_none_when_seller_has_no_config(self):
        from app.workers.tasks.image_tasks import _try_i2i_generation

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # sem SellerImageConfig
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await _try_i2i_generation(mock_db, _make_listing(), MagicMock(), "token")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_raw_photos_missing(self):
        from app.workers.tasks.image_tasks import _try_i2i_generation

        mock_config = MagicMock()
        mock_config.raw_base_url = "https://pub-xxx.r2.dev/sku"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.services.seller_image_source_service.fetch_all_raw_photos",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await _try_i2i_generation(mock_db, _make_listing(), MagicMock(), "token")

        assert result is None

    @pytest.mark.asyncio
    async def test_generates_4_individual_images_for_single_sku(self):
        from app.workers.tasks.image_tasks import _try_i2i_generation

        mock_config = MagicMock()
        mock_config.raw_base_url = "https://pub-xxx.r2.dev/sku"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock()

        raw_photos = {"SKU0001": [b"raw1", b"raw2"]}

        with patch(
            "app.services.seller_image_source_service.fetch_all_raw_photos",
            new_callable=AsyncMock,
            return_value=raw_photos,
        ), patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as mock_engine_cls, patch(
            "app.workers.tasks.image_tasks._prepare_image_for_upload",
            side_effect=_passthrough_prepare,
        ), patch(
            "app.workers.tasks.image_tasks._resolve_requires_white_bg",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(
                side_effect=[[b"v1", b"v2"], [b"v3", b"v4"]]  # 2 chamadas (1 por foto bruta), 2 imagens cada
            )
            mock_ml_cls.return_value.upload = AsyncMock(
                side_effect=["pic1", "pic2", "pic3", "pic4"]
            )
            result = await _try_i2i_generation(mock_db, _make_listing(), MagicMock(), "token")

        assert result == 4
        assert mock_engine_cls.return_value.edit.await_count == 2  # uma chamada por foto bruta
        assert mock_ml_cls.return_value.upload.await_count == 4

    @pytest.mark.asyncio
    async def test_generates_cover_plus_individuals_for_kit_with_two_skus(self):
        from app.workers.tasks.image_tasks import _try_i2i_generation

        mock_config = MagicMock()
        mock_config.raw_base_url = "https://pub-xxx.r2.dev/sku"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock()

        raw_photos = {
            "SKU0001": [b"sku1-raw1", b"sku1-raw2"],
            "SKU0002": [b"sku2-raw1", b"sku2-raw2"],
        }

        listing = _make_listing()

        with patch(
            "app.services.seller_image_source_service.resolve_listing_skus",
            new_callable=AsyncMock,
            return_value=["SKU0001", "SKU0002"],
        ), patch(
            "app.services.seller_image_source_service.fetch_all_raw_photos",
            new_callable=AsyncMock,
            return_value=raw_photos,
        ), patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as mock_engine_cls, patch(
            "app.workers.tasks.image_tasks._prepare_image_for_upload",
            side_effect=_passthrough_prepare,
        ), patch(
            "app.workers.tasks.image_tasks._resolve_requires_white_bg",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(
                side_effect=[
                    [b"cover"],                # 1a chamada: composicao da capa (n=1)
                    [b"v1", b"v2"],             # SKU0001 foto 1
                    [b"v3", b"v4"],             # SKU0001 foto 2
                    [b"v5", b"v6"],             # SKU0002 foto 1
                    [b"v7", b"v8"],             # SKU0002 foto 2
                ]
            )
            mock_ml_cls.return_value.upload = AsyncMock(
                side_effect=[f"pic{i}" for i in range(1, 10)]
            )
            result = await _try_i2i_generation(mock_db, listing, MagicMock(), "token")

        # 1 capa + (2 fotos x 2 variacoes x 2 SKUs) = 9
        assert result == 9
        assert mock_engine_cls.return_value.edit.await_count == 5

        added_images = [
            call.args[0] for call in mock_db.add.call_args_list
            if type(call.args[0]).__name__ == "ListingImage"
        ]
        assert added_images[0].kind == "cover_composed"
        assert added_images[0].source_sku is None
        assert all(img.kind == "individual" for img in added_images[1:])

    @pytest.mark.asyncio
    async def test_cover_composition_failure_falls_back_to_individual_only(self):
        from app.workers.tasks.image_tasks import _try_i2i_generation

        mock_config = MagicMock()
        mock_config.raw_base_url = "https://pub-xxx.r2.dev/sku"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock()

        raw_photos = {
            "SKU0001": [b"sku1-raw1", b"sku1-raw2"],
            "SKU0002": [b"sku2-raw1", b"sku2-raw2"],
        }

        with patch(
            "app.services.seller_image_source_service.resolve_listing_skus",
            new_callable=AsyncMock,
            return_value=["SKU0001", "SKU0002"],
        ), patch(
            "app.services.seller_image_source_service.fetch_all_raw_photos",
            new_callable=AsyncMock,
            return_value=raw_photos,
        ), patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as mock_engine_cls, patch(
            "app.workers.tasks.image_tasks._prepare_image_for_upload",
            side_effect=_passthrough_prepare,
        ), patch(
            "app.workers.tasks.image_tasks._resolve_requires_white_bg",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(
                side_effect=[
                    RuntimeError("composicao falhou"),  # capa falha
                    [b"v1", b"v2"], [b"v3", b"v4"], [b"v5", b"v6"], [b"v7", b"v8"],
                ]
            )
            mock_ml_cls.return_value.upload = AsyncMock(
                side_effect=[f"pic{i}" for i in range(1, 9)]
            )
            result = await _try_i2i_generation(mock_db, _make_listing(), MagicMock(), "token")

        # sem capa: 2 fotos x 2 variacoes x 2 SKUs = 8
        assert result == 8
        added_images = [
            call.args[0] for call in mock_db.add.call_args_list
            if type(call.args[0]).__name__ == "ListingImage"
        ]
        assert all(img.kind == "individual" for img in added_images)
        assert added_images[0].sort_order == 0  # 1a imagem individual assume a posicao de capa
