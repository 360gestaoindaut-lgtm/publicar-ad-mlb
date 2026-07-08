import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.publish_service import PublishService


def _listing():
    listing = MagicMock()
    listing.selected_title = "Produto teste"
    listing.ml_category_id = "MLB1055"
    listing.price = 1299.90
    listing.stock_quantity = 1
    listing.condition = "new"
    listing.listing_type_id = "gold_special"
    return listing


def _image():
    img = MagicMock()
    img.approved = True
    img.ml_picture_id = "123456-PIC"
    img.sort_order = 0
    return img


class TestPublishEnsuresPaused:
    @pytest.mark.asyncio
    async def test_forces_pause_when_ml_activates_immediately(self):
        """ML pode ignorar status=paused e devolver o item já 'active' na
        própria resposta de criação — o publish() deve corrigir com um PUT."""
        create_response = MagicMock()
        create_response.status_code = 201
        create_response.json.return_value = {"id": "MLB999", "status": "active", "sub_status": []}

        put_response = MagicMock()
        put_response.status_code = 200

        mock_post = AsyncMock(return_value=create_response)
        mock_put = AsyncMock(return_value=put_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            client = mock_client_cls.return_value.__aenter__.return_value
            client.post = mock_post
            client.put = mock_put

            service = PublishService(db=MagicMock())
            item_id = await service.publish(
                listing=_listing(),
                attributes=[],
                images=[_image()],
                description_html=None,
                access_token="token",
            )

        assert item_id == "MLB999"
        mock_put.assert_awaited_once()
        put_call = mock_put.await_args
        assert put_call.kwargs["json"] == {"status": "paused"}

    @pytest.mark.asyncio
    async def test_does_not_force_pause_when_already_paused(self):
        create_response = MagicMock()
        create_response.status_code = 201
        create_response.json.return_value = {"id": "MLB999", "status": "paused", "sub_status": []}

        mock_post = AsyncMock(return_value=create_response)
        mock_put = AsyncMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            client = mock_client_cls.return_value.__aenter__.return_value
            client.post = mock_post
            client.put = mock_put

            service = PublishService(db=MagicMock())
            await service.publish(
                listing=_listing(),
                attributes=[],
                images=[_image()],
                description_html=None,
                access_token="token",
            )

        mock_put.assert_not_called()

    @pytest.mark.asyncio
    async def test_waits_for_picture_processing_then_forces_pause(self):
        """Enquanto sub_status tem picture_download_pending, o publish() deve
        aguardar (polling via GET) e só então reforçar o pause quando a
        validação da imagem termina e o ML já tiver ativado o item sozinho."""
        create_response = MagicMock()
        create_response.status_code = 201
        create_response.json.return_value = {
            "id": "MLB999", "status": "paused", "sub_status": ["picture_download_pending"],
        }

        get_response = MagicMock()
        get_response.status_code = 200
        get_response.json.return_value = {"id": "MLB999", "status": "active", "sub_status": []}

        put_response = MagicMock()
        put_response.status_code = 200

        mock_post = AsyncMock(return_value=create_response)
        mock_get = AsyncMock(return_value=get_response)
        mock_put = AsyncMock(return_value=put_response)

        with patch("httpx.AsyncClient") as mock_client_cls, \
             patch("app.services.publish_service.asyncio.sleep", new_callable=AsyncMock):
            client = mock_client_cls.return_value.__aenter__.return_value
            client.post = mock_post
            client.get = mock_get
            client.put = mock_put

            service = PublishService(db=MagicMock())
            await service.publish(
                listing=_listing(),
                attributes=[],
                images=[_image()],
                description_html=None,
                access_token="token",
            )

        mock_get.assert_awaited_once()
        mock_put.assert_awaited_once()
        assert mock_put.await_args.kwargs["json"] == {"status": "paused"}
