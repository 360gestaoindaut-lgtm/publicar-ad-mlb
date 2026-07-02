import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestConfirmImageEngine:
    @pytest.mark.asyncio
    async def test_use_gemini_switches_state_and_reenqueues_all_pending(self):
        from app.services.listing_service import ListingService

        triggering_listing = MagicMock()
        triggering_listing.id = "lid-1"
        triggering_listing.status = "pending_image_engine_confirmation"

        other_pending = MagicMock()
        other_pending.id = "lid-2"
        other_pending.status = "pending_image_engine_confirmation"

        mock_engine_state = MagicMock()
        mock_engine_state.current_engine = "openai"

        mock_db = AsyncMock()
        execute_calls = [0]

        async def execute_side(stmt):
            execute_calls[0] += 1
            r = MagicMock()
            if execute_calls[0] == 1:      # SELECT ImageEngineState
                r.scalar_one = MagicMock(return_value=mock_engine_state)
            else:                          # SELECT Listing WHERE status = pending_...
                r.scalars = MagicMock(return_value=MagicMock(
                    all=MagicMock(return_value=[triggering_listing, other_pending])
                ))
            return r

        mock_db.execute = execute_side
        mock_db.commit = AsyncMock()

        with patch("app.workers.tasks.image_tasks.generate_images") as mock_task:
            svc = ListingService(mock_db)
            await svc.confirm_image_engine(triggering_listing, "use_gemini")

        assert mock_engine_state.current_engine == "gemini"
        assert triggering_listing.status == "generating_images"
        assert other_pending.status == "generating_images"
        assert mock_task.delay.call_count == 2
        mock_task.delay.assert_any_call("lid-1")
        mock_task.delay.assert_any_call("lid-2")

    @pytest.mark.asyncio
    async def test_retry_openai_only_reenqueues_this_listing(self):
        from app.services.listing_service import ListingService

        listing = MagicMock()
        listing.id = "lid-1"
        listing.status = "pending_image_engine_confirmation"

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        with patch("app.workers.tasks.image_tasks.generate_images") as mock_task:
            svc = ListingService(mock_db)
            await svc.confirm_image_engine(listing, "retry_openai")

        assert listing.status == "generating_images"
        mock_task.delay.assert_called_once_with("lid-1")

    @pytest.mark.asyncio
    async def test_wrong_status_raises_409(self):
        from fastapi import HTTPException
        from app.services.listing_service import ListingService

        listing = MagicMock()
        listing.status = "failed"
        mock_db = AsyncMock()

        svc = ListingService(mock_db)
        with pytest.raises(HTTPException) as exc_info:
            await svc.confirm_image_engine(listing, "use_gemini")
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_invalid_action_raises_422(self):
        from fastapi import HTTPException
        from app.services.listing_service import ListingService

        listing = MagicMock()
        listing.status = "pending_image_engine_confirmation"
        mock_db = AsyncMock()

        svc = ListingService(mock_db)
        with pytest.raises(HTTPException) as exc_info:
            await svc.confirm_image_engine(listing, "not_a_real_action")
        assert exc_info.value.status_code == 422
