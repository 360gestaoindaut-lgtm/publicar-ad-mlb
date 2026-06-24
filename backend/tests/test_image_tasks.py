import logging
import pytest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch


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
        # Make execute() return a mock with scalar_one_or_none method
        # that returns a coroutine when awaited
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


import asyncio
from unittest.mock import patch, MagicMock

from app.services.image_service import ImageRateLimitError


class TestGenerateImagesRateLimit:
    def test_rate_limit_error_uses_longer_countdown(self):
        from app.workers.tasks.image_tasks import generate_images

        retry_calls = []

        def fake_retry(exc, countdown):
            retry_calls.append(countdown)
            raise exc  # simula o raise que o Celery faz internamente

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
