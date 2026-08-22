import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.r2_write_service import write_back_images


def _make_listing_image(ml_picture_id: str):
    img = MagicMock()
    img.ml_picture_id = ml_picture_id
    img.approved = True
    img.url_r2 = None
    img.r2_write_status = None
    return img


def _make_listing():
    listing = MagicMock()
    listing.id = "lid"
    listing.mlb_id = "MLB123456789"
    return listing


class TestWriteBackImages:
    @pytest.mark.asyncio
    async def test_skips_when_no_config(self):
        img = _make_listing_image("pic1")
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [img]
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        await write_back_images(mock_db, _make_listing(), None, "token")

        assert img.r2_write_status == "skipped_no_config"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_when_write_credentials_incomplete(self):
        img = _make_listing_image("pic1")
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [img]
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        config = MagicMock()
        config.write_bucket_name = "bucket"
        config.write_endpoint_url = None  # incompleto
        config.write_access_key_id_enc = "enc-key"
        config.write_secret_access_key_enc = "enc-secret"

        await write_back_images(mock_db, _make_listing(), config, "token")

        assert img.r2_write_status == "skipped_no_config"

    @pytest.mark.asyncio
    async def test_writes_successfully_and_updates_status(self):
        img = _make_listing_image("pic1")
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [img]
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        config = MagicMock()
        config.write_bucket_name = "bucket"
        config.write_endpoint_url = "https://account.r2.cloudflarestorage.com"
        config.write_access_key_id_enc = "enc-key"
        config.write_secret_access_key_enc = "enc-secret"

        ml_item_response = MagicMock()
        ml_item_response.status_code = 200
        ml_item_response.json.return_value = {
            "pictures": [{"id": "pic1", "secure_url": "https://http2.mlstatic.com/pic1.jpg"}]
        }
        photo_response = MagicMock()
        photo_response.content = b"photo-bytes"
        photo_response.raise_for_status = MagicMock()

        mock_get = AsyncMock(side_effect=[ml_item_response, photo_response])

        with patch("httpx.AsyncClient") as mock_client_cls, \
             patch("app.services.r2_write_service.decrypt_value", side_effect=["access-key", "secret-key"]), \
             patch("boto3.client") as mock_boto_client:
            mock_client_cls.return_value.__aenter__.return_value.get = mock_get
            mock_s3 = MagicMock()
            mock_boto_client.return_value = mock_s3

            await write_back_images(mock_db, _make_listing(), config, "token")

        assert img.r2_write_status == "success"
        assert img.url_r2 == "anuncios/MLB123456789-1.jpg"
        mock_s3.put_object.assert_called_once()
        call_kwargs = mock_s3.put_object.call_args.kwargs
        assert call_kwargs["Bucket"] == "bucket"
        assert call_kwargs["Key"] == "anuncios/MLB123456789-1.jpg"
        assert call_kwargs["Body"] == b"photo-bytes"

    @pytest.mark.asyncio
    async def test_ml_item_fetch_failure_marks_all_as_failed(self):
        img = _make_listing_image("pic1")
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [img]
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        config = MagicMock()
        config.write_bucket_name = "bucket"
        config.write_endpoint_url = "https://account.r2.cloudflarestorage.com"
        config.write_access_key_id_enc = "enc-key"
        config.write_secret_access_key_enc = "enc-secret"

        ml_item_response = MagicMock()
        ml_item_response.status_code = 404

        mock_get = AsyncMock(return_value=ml_item_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.get = mock_get
            await write_back_images(mock_db, _make_listing(), config, "token")

        assert img.r2_write_status == "failed"

    @pytest.mark.asyncio
    async def test_missing_picture_in_ml_response_marks_that_image_failed(self):
        img = _make_listing_image("pic-not-found")
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [img]
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        config = MagicMock()
        config.write_bucket_name = "bucket"
        config.write_endpoint_url = "https://account.r2.cloudflarestorage.com"
        config.write_access_key_id_enc = "enc-key"
        config.write_secret_access_key_enc = "enc-secret"

        ml_item_response = MagicMock()
        ml_item_response.status_code = 200
        ml_item_response.json.return_value = {"pictures": []}  # pic-not-found nao esta la

        mock_get = AsyncMock(return_value=ml_item_response)

        with patch("httpx.AsyncClient") as mock_client_cls, \
             patch("app.services.r2_write_service.decrypt_value", side_effect=["access-key", "secret-key"]), \
             patch("boto3.client"):
            mock_client_cls.return_value.__aenter__.return_value.get = mock_get
            await write_back_images(mock_db, _make_listing(), config, "token")

        assert img.r2_write_status == "failed"
