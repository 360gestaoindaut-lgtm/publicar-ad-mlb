import asyncio
import logging
import pytest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.image_service import ImageRateLimitError


@asynccontextmanager
async def _mock_session(mock_db):
    yield mock_db


def _make_mock_listing():
    listing = MagicMock()
    listing.status = "generating_images"
    listing.error_message = None
    return listing


class TestMarkFailed:
    @pytest.mark.asyncio
    async def test_sets_status_and_error_message(self):
        from app.workers.tasks.image_tasks import _mark_failed

        listing = _make_mock_listing()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = listing

        async def async_execute(*args, **kwargs):
            return mock_result

        mock_db.execute = async_execute

        with patch("app.database.worker_session", lambda: _mock_session(mock_db)):
            await _mark_failed("abc-123", "something went wrong")

        assert listing.status == "failed"
        assert listing.error_message == "something went wrong"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_truncates_long_error_to_500_chars(self):
        from app.workers.tasks.image_tasks import _mark_failed

        listing = _make_mock_listing()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = listing

        async def async_execute(*args, **kwargs):
            return mock_result

        mock_db.execute = async_execute

        long_error = "x" * 1000
        with patch("app.database.worker_session", lambda: _mock_session(mock_db)):
            await _mark_failed("abc-123", long_error)

        assert len(listing.error_message) == 500

    @pytest.mark.asyncio
    async def test_db_failure_logs_and_does_not_propagate(self, caplog):
        from app.workers.tasks.image_tasks import _mark_failed

        @asynccontextmanager
        async def _exploding_session():
            raise RuntimeError("DB connection lost")
            yield  # noqa: unreachable — satisfies contextmanager protocol

        with patch("app.database.worker_session", _exploding_session):
            with caplog.at_level(logging.ERROR):
                await _mark_failed("abc-123", "original error")  # must not raise

        assert "abc-123" in caplog.text
        assert "original error" in caplog.text
        assert "DB connection lost" in caplog.text

    @pytest.mark.asyncio
    async def test_listing_not_found_does_not_raise(self):
        from app.workers.tasks.image_tasks import _mark_failed

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        async def async_execute(*args, **kwargs):
            return mock_result

        mock_db.execute = async_execute

        with patch("app.database.worker_session", lambda: _mock_session(mock_db)):
            await _mark_failed("abc-123", "error")  # must not raise


class TestGenerateImagesRateLimit:
    def test_rate_limit_error_uses_longer_countdown(self):
        from app.workers.tasks.image_tasks import generate_images

        retry_calls = []

        def fake_retry(exc, countdown):
            retry_calls.append(countdown)
            raise exc

        mock_self = MagicMock()
        mock_self.request.retries = 0
        mock_self.max_retries = 2
        mock_self.retry = fake_retry

        with patch(
            "app.workers.tasks.image_tasks.asyncio.run",
            side_effect=ImageRateLimitError("quota hit"),
        ):
            with pytest.raises(ImageRateLimitError):
                generate_images.run.__func__(mock_self, "listing-abc")

        assert retry_calls == [60], f"Expected countdown=60, got {retry_calls}"

    def test_generic_error_uses_short_countdown(self):
        from app.workers.tasks.image_tasks import generate_images

        retry_calls = []

        def fake_retry(exc, countdown):
            retry_calls.append(countdown)
            raise exc

        mock_self = MagicMock()
        mock_self.request.retries = 0
        mock_self.max_retries = 2
        mock_self.retry = fake_retry

        with patch(
            "app.workers.tasks.image_tasks.asyncio.run",
            side_effect=RuntimeError("network error"),
        ):
            with pytest.raises(RuntimeError):
                generate_images.run.__func__(mock_self, "listing-abc")

        assert retry_calls == [5], f"Expected countdown=5, got {retry_calls}"


class TestFetchUploadToken:
    @pytest.mark.asyncio
    async def test_calls_get_valid_access_token(self):
        from app.workers.tasks.image_tasks import _fetch_upload_token

        mock_seller = MagicMock()
        mock_db = AsyncMock()

        with patch(
            "app.services.publish_service.get_valid_access_token",
            new_callable=AsyncMock,
            return_value="refreshed-token",
        ) as mock_fn:
            result = await _fetch_upload_token(mock_seller, mock_db)

        assert result == "refreshed-token"
        mock_fn.assert_called_once_with(mock_seller, mock_db)

    @pytest.mark.asyncio
    async def test_does_not_call_decrypt_value_directly(self):
        from app.workers.tasks.image_tasks import _fetch_upload_token

        with patch("app.core.security.decrypt_value") as mock_decrypt, \
             patch(
                 "app.services.publish_service.get_valid_access_token",
                 new_callable=AsyncMock,
                 return_value="tok",
             ):
            await _fetch_upload_token(MagicMock(), AsyncMock())

        mock_decrypt.assert_not_called()


class TestGenerateImagesIdempotency:
    @pytest.mark.asyncio
    async def test_skips_when_status_not_generating_images(self):
        from app.workers.tasks.image_tasks import _generate_images_async

        mock_listing = MagicMock()
        mock_listing.status = "pending_image_approval"  # já avançou

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_listing
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.database.worker_session", lambda: _mock_session(mock_db)), \
             patch("app.services.image_service.GeminiImageService") as mock_gemini:
            result = await _generate_images_async("listing-id")

        assert result == {"listing_id": "listing-id", "skipped": True}
        mock_gemini.assert_not_called()

    @pytest.mark.asyncio
    async def test_proceeds_when_status_is_generating_images(self):
        """Verificação negativa: guard NÃO aborta quando status está correto."""
        from app.workers.tasks.image_tasks import _generate_images_async

        mock_listing = MagicMock()
        mock_listing.status = "generating_images"
        mock_listing.sku_external_id = None
        mock_listing.seller_id = "sid"
        mock_listing.created_via = "manual"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_listing
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Com status correto, a função avança — mas vai falhar em algum ponto
        # sem o restante dos mocks. Basta confirmar que GeminiImageService foi instanciado.
        with patch("app.database.worker_session", lambda: _mock_session(mock_db)), \
             patch("app.services.ai.service.get_ai_provider", return_value=AsyncMock(
                 generate_image_prompt=AsyncMock(return_value="prompt")
             )), \
             patch("app.services.image_service.GeminiImageService") as mock_gemini_cls, \
             patch("app.workers.tasks.image_tasks._fetch_upload_token", new_callable=AsyncMock, return_value="tok"):
            mock_gemini_cls.return_value.generate = AsyncMock(return_value=[])
            try:
                await _generate_images_async("listing-id")
            except Exception:
                pass  # pode falhar após o guard — o que importa é que chegou aqui

        mock_gemini_cls.assert_called_once()
