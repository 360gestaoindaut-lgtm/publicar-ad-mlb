import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestGetImageEngineEndpointLogic:
    @pytest.mark.asyncio
    async def test_builds_response_from_state_and_pending_listings(self):
        """Testa a função do endpoint diretamente (sem subir o app FastAPI completo),
        garantindo que ela monta o schema corretamente a partir do estado e da
        contagem de listings pendentes."""
        from app.api.v1.endpoints.system import get_image_engine

        mock_engine_state = MagicMock()
        mock_engine_state.current_engine = "openai"
        mock_engine_state.last_openai_error = "boom"
        mock_engine_state.last_switch_to_openai_at = None

        mock_db = AsyncMock()
        execute_calls = [0]

        async def execute_side(stmt):
            execute_calls[0] += 1
            r = MagicMock()
            if execute_calls[0] == 1:   # SELECT ImageEngineState
                r.scalar_one = MagicMock(return_value=mock_engine_state)
            else:                        # SELECT Listing.id WHERE pending...
                r.all = MagicMock(return_value=[("lid-1",), ("lid-2",)])
            return r

        mock_db.execute = execute_side

        result = await get_image_engine(current_user=MagicMock(), db=mock_db)

        assert result.current_engine == "openai"
        assert result.pending_confirmation_count == 2
        assert result.pending_listing_ids == ["lid-1", "lid-2"]
        assert result.last_openai_error == "boom"
        assert "OpenAI" in result.engine_label
