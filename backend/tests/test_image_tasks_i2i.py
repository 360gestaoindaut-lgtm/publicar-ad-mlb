import pytest
from unittest.mock import AsyncMock, MagicMock, patch


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
            "app.services.image_service.validate_image", return_value=True
        ), patch(
            "app.services.image_service.ensure_dimensions", side_effect=lambda b: b
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
