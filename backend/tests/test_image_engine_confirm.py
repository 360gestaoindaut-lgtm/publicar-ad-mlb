import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestConfirmImageEngine:
    @pytest.mark.asyncio
    async def test_use_gemini_switches_state_and_reenqueues_all_pending(self):
        from app.services.listing_service import ListingService

        triggering_listing = MagicMock()
        triggering_listing.id = "lid-1"
        triggering_listing.status = "pending_image_engine_confirmation"
        triggering_listing.created_via = "manual"

        other_pending = MagicMock()
        other_pending.id = "lid-2"
        other_pending.status = "pending_image_engine_confirmation"
        other_pending.created_via = "manual"

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

        # Parent tracker to verify temporal ordering between db.commit() and
        # generate_images.delay(): the production code must commit the
        # status change BEFORE dispatching any Celery task (never interleave
        # mutate-status/dispatch inside the same loop).
        call_order = MagicMock()

        with patch("app.workers.tasks.image_tasks.generate_images") as mock_task:
            call_order.attach_mock(mock_db.commit, "commit")
            call_order.attach_mock(mock_task.delay, "delay")

            svc = ListingService(mock_db)
            await svc.confirm_image_engine(triggering_listing, "use_gemini")

        assert mock_engine_state.current_engine == "gemini"
        assert triggering_listing.status == "generating_images"
        assert other_pending.status == "generating_images"
        assert mock_task.delay.call_count == 2
        mock_task.delay.assert_any_call("lid-1")
        mock_task.delay.assert_any_call("lid-2")

        call_names = [c[0] for c in call_order.mock_calls]
        commit_indices = [i for i, name in enumerate(call_names) if name == "commit"]
        delay_indices = [i for i, name in enumerate(call_names) if name == "delay"]
        assert commit_indices, "db.commit() was never called"
        assert delay_indices, "generate_images.delay() was never called"
        assert max(commit_indices) < min(delay_indices), (
            "generate_images.delay() must not be called before db.commit() "
            f"(call order: {call_names})"
        )

    @pytest.mark.asyncio
    async def test_retry_openai_only_reenqueues_this_listing(self):
        from app.services.listing_service import ListingService

        listing = MagicMock()
        listing.id = "lid-1"
        listing.status = "pending_image_engine_confirmation"
        listing.created_via = "manual"

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


class TestConfirmImageEngineBatchAwareRedispatch:
    """Batch listings need the full chain re-dispatched on retry/resume, or
    the pipeline dead-ends in 'generating_description' forever (no chain
    left to enqueue generate_description/publish_listing). Manual listings
    keep the bare .delay() since their pipeline pauses at each step anyway.
    """

    @pytest.mark.asyncio
    async def test_use_gemini_mixed_batch_and_manual_dispatch_correctly(self):
        from app.services.listing_service import ListingService

        batch_listing = MagicMock()
        batch_listing.id = "lid-batch"
        batch_listing.status = "pending_image_engine_confirmation"
        batch_listing.created_via = "batch"

        manual_listing = MagicMock()
        manual_listing.id = "lid-manual"
        manual_listing.status = "pending_image_engine_confirmation"
        manual_listing.created_via = "manual"

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
                    all=MagicMock(return_value=[batch_listing, manual_listing])
                ))
            return r

        mock_db.execute = execute_side
        mock_db.commit = AsyncMock()

        mock_chain_instance = MagicMock()

        with patch("app.workers.tasks.image_tasks.generate_images") as mock_gi, \
             patch("app.workers.tasks.ai_tasks.generate_description") as mock_gd, \
             patch("app.workers.tasks.publish_tasks.publish_listing") as mock_pl, \
             patch("celery.chain", return_value=mock_chain_instance) as mock_chain_fn:
            svc = ListingService(mock_db)
            await svc.confirm_image_engine(batch_listing, "use_gemini")

        assert mock_engine_state.current_engine == "gemini"
        assert batch_listing.status == "generating_images"
        assert manual_listing.status == "generating_images"

        # Batch listing: full chain re-dispatched.
        mock_gi.si.assert_called_once_with("lid-batch")
        mock_gd.si.assert_called_once_with("lid-batch")
        mock_pl.si.assert_called_once_with("lid-batch")
        mock_chain_fn.assert_called_once_with(
            mock_gi.si.return_value, mock_gd.si.return_value, mock_pl.si.return_value
        )
        mock_chain_instance.delay.assert_called_once()

        # Manual listing: bare .delay(), no chain/si involvement (only 1 total
        # .si() call for generate_description/publish_listing — from the batch
        # listing above; the manual listing never touches them at all).
        mock_gi.delay.assert_called_once_with("lid-manual")
        mock_gd.si.assert_called_once()
        mock_gd.delay.assert_not_called()
        mock_pl.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_retry_openai_batch_listing_dispatches_chain(self):
        from app.services.listing_service import ListingService

        listing = MagicMock()
        listing.id = "lid-1"
        listing.status = "pending_image_engine_confirmation"
        listing.created_via = "batch"

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_chain_instance = MagicMock()

        with patch("app.workers.tasks.image_tasks.generate_images") as mock_gi, \
             patch("app.workers.tasks.ai_tasks.generate_description") as mock_gd, \
             patch("app.workers.tasks.publish_tasks.publish_listing") as mock_pl, \
             patch("celery.chain", return_value=mock_chain_instance) as mock_chain_fn:
            svc = ListingService(mock_db)
            await svc.confirm_image_engine(listing, "retry_openai")

        assert listing.status == "generating_images"
        mock_gi.si.assert_called_once_with("lid-1")
        mock_gd.si.assert_called_once_with("lid-1")
        mock_pl.si.assert_called_once_with("lid-1")
        mock_chain_fn.assert_called_once_with(
            mock_gi.si.return_value, mock_gd.si.return_value, mock_pl.si.return_value
        )
        mock_chain_instance.delay.assert_called_once()
        mock_gi.delay.assert_not_called()
