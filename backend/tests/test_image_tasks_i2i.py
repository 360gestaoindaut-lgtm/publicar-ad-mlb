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
            "app.workers.tasks.image_tasks._append_benefit_cards",
            new_callable=AsyncMock,
            return_value=0,
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
            "app.workers.tasks.image_tasks._append_benefit_cards",
            new_callable=AsyncMock,
            return_value=0,
        ), patch(
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
            "app.workers.tasks.image_tasks._append_benefit_cards",
            new_callable=AsyncMock,
            return_value=0,
        ), patch(
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


# --------------------------------------------------------------------------
# Fase 2: capa deterministica (sem custo de IA) antes do loop pago
# --------------------------------------------------------------------------


def _make_i2i_db():
    mock_config = MagicMock()
    mock_config.raw_base_url = "https://pub-xxx.r2.dev/sku"

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_config
    mock_db.execute = AsyncMock(return_value=mock_result)
    added = []
    mock_db.add = MagicMock(side_effect=added.append)
    return mock_db, added


class TestDeterministicCoverIntegration:
    @pytest.mark.asyncio
    async def test_successful_cover_takes_sort_order_zero_without_extra_ai_call(self):
        """A capa sai do recorte; o engine pago segue sendo chamado 2x (1 por foto bruta)."""
        from app.workers.tasks.image_tasks import _try_i2i_generation

        mock_db, added = _make_i2i_db()

        with patch(
            "app.workers.tasks.image_tasks._append_benefit_cards",
            new_callable=AsyncMock,
            return_value=0,
        ), patch(
            "app.services.seller_image_source_service.fetch_all_raw_photos",
            new_callable=AsyncMock,
            return_value={"SKU0001": [b"raw1", b"raw2"]},
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
            return_value=b"cover-deterministica",
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(
                side_effect=[[b"v1", b"v2"], [b"v3", b"v4"]]
            )
            mock_ml_cls.return_value.upload = AsyncMock(
                side_effect=["cover", "pic1", "pic2", "pic3", "pic4"]
            )
            saved = await _try_i2i_generation(mock_db, _make_listing(), MagicMock(), "token")

        assert saved == 5, "1 capa deterministica + 4 imagens de IA"
        assert mock_engine_cls.return_value.edit.await_count == 2, (
            "a capa nao pode gerar chamada extra ao engine pago"
        )

        covers = [o for o in added if getattr(o, "kind", None) == "cover_deterministic"]
        assert len(covers) == 1
        assert covers[0].sort_order == 0
        assert covers[0].source_sku == "SKU0001"
        assert covers[0].status == "uploaded"

    @pytest.mark.asyncio
    async def test_ai_images_start_at_sort_order_one_when_cover_succeeds(self):
        from app.workers.tasks.image_tasks import _try_i2i_generation

        mock_db, added = _make_i2i_db()

        with patch(
            "app.workers.tasks.image_tasks._append_benefit_cards",
            new_callable=AsyncMock,
            return_value=0,
        ), patch(
            "app.services.seller_image_source_service.fetch_all_raw_photos",
            new_callable=AsyncMock,
            return_value={"SKU0001": [b"raw1", b"raw2"]},
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
            return_value=b"cover-deterministica",
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(
                side_effect=[[b"v1", b"v2"], [b"v3", b"v4"]]
            )
            mock_ml_cls.return_value.upload = AsyncMock(
                side_effect=["cover", "pic1", "pic2", "pic3", "pic4"]
            )
            await _try_i2i_generation(mock_db, _make_listing(), MagicMock(), "token")

        individuais = [o for o in added if getattr(o, "kind", None) == "individual"]
        assert [o.sort_order for o in individuais] == [1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_failed_cover_keeps_previous_behaviour(self):
        """Capa deterministica falhou: resultado identico ao de antes da Fase 2."""
        from app.workers.tasks.image_tasks import _try_i2i_generation

        mock_db, added = _make_i2i_db()

        with patch(
            "app.workers.tasks.image_tasks._append_benefit_cards",
            new_callable=AsyncMock,
            return_value=0,
        ), patch(
            "app.services.seller_image_source_service.fetch_all_raw_photos",
            new_callable=AsyncMock,
            return_value={"SKU0001": [b"raw1", b"raw2"]},
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
            return_value=None,
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(
                side_effect=[[b"v1", b"v2"], [b"v3", b"v4"]]
            )
            mock_ml_cls.return_value.upload = AsyncMock(
                side_effect=["pic1", "pic2", "pic3", "pic4"]
            )
            saved = await _try_i2i_generation(mock_db, _make_listing(), MagicMock(), "token")

        assert saved == 4, "mesmo total de antes da Fase 2"
        assert mock_engine_cls.return_value.edit.await_count == 2
        assert [o for o in added if getattr(o, "kind", None) == "cover_deterministic"] == []
        individuais = [o for o in added if getattr(o, "kind", None) == "individual"]
        assert [o.sort_order for o in individuais] == [0, 1, 2, 3], "IA volta a ocupar sort_order 0"

    @pytest.mark.asyncio
    async def test_cover_is_skipped_for_kits_with_more_than_one_sku(self):
        """Kit (N>1) segue fora de escopo, igual ao resto do i2i."""
        from app.workers.tasks.image_tasks import _try_i2i_generation

        mock_db, added = _make_i2i_db()
        listing = _make_listing()

        with patch(
            "app.workers.tasks.image_tasks._append_benefit_cards",
            new_callable=AsyncMock,
            return_value=0,
        ), patch(
            "app.services.seller_image_source_service.resolve_listing_skus",
            new_callable=AsyncMock,
            return_value=["SKU0001", "SKU0002"],
        ), patch(
            "app.services.seller_image_source_service.fetch_all_raw_photos",
            new_callable=AsyncMock,
            return_value={"SKU0001": [b"a1", b"a2"], "SKU0002": [b"b1", b"b2"]},
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
            return_value=b"nao-deveria-ser-usada",
        ) as mock_cover, patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(
                return_value=[b"v1", b"v2"]
            )
            mock_ml_cls.return_value.upload = AsyncMock(
                side_effect=[f"pic{i}" for i in range(20)]
            )
            await _try_i2i_generation(mock_db, listing, MagicMock(), "token")

        mock_cover.assert_not_called()
        assert [o for o in added if getattr(o, "kind", None) == "cover_deterministic"] == []

    @pytest.mark.asyncio
    async def test_cover_uses_the_first_raw_photo(self):
        from app.workers.tasks.image_tasks import _try_i2i_generation

        mock_db, _ = _make_i2i_db()

        with patch(
            "app.workers.tasks.image_tasks._append_benefit_cards",
            new_callable=AsyncMock,
            return_value=0,
        ), patch(
            "app.services.seller_image_source_service.fetch_all_raw_photos",
            new_callable=AsyncMock,
            return_value={"SKU0001": [b"primeira", b"segunda"]},
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
            return_value=b"cover",
        ) as mock_cover, patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(
                side_effect=[[b"v1"], [b"v2"]]
            )
            mock_ml_cls.return_value.upload = AsyncMock(
                side_effect=["cover", "pic1", "pic2"]
            )
            await _try_i2i_generation(mock_db, _make_listing(), MagicMock(), "token")

        mock_cover.assert_called_once_with(b"primeira")


# --------------------------------------------------------------------------
# Fase 3: cards de beneficio/uso/especificacoes depois das imagens individuais
# --------------------------------------------------------------------------


def _make_cards_db(attributes=None):
    """Como `_make_i2i_db`, mas respondendo tambem a query de atributos.

    O `_append_benefit_cards` carrega os ListingAttribute por query propria
    (nunca pelo relacionamento lazy), entao o mock de db precisa cobrir esse
    caminho.
    """
    mock_db, added = _make_i2i_db()
    mock_db.execute.return_value.scalars.return_value.all.return_value = (
        attributes if attributes is not None else []
    )
    return mock_db, added


def _card_copies(*kinds):
    from app.services.image_card_copy_service import CardCopy

    return [
        CardCopy(kind=kind, title=f"Titulo {kind}", bullets=["bullet 1", "bullet 2"])
        for kind in kinds
    ]


def _uploaded_kinds(added):
    return [
        o.kind for o in added
        if type(o).__name__ == "ListingImage" and getattr(o, "status", None) == "uploaded"
    ]


def _cards_of(added):
    return [o for o in added if str(getattr(o, "kind", "")).startswith("card_")]


class TestBenefitCardsIntegration:
    @pytest.mark.asyncio
    async def test_three_cards_are_appended_after_the_individual_images(self):
        """Cards entram depois das individuais, na ordem de CARD_KINDS."""
        from app.services.image_card_copy_service import CARD_KINDS
        from app.workers.tasks.image_tasks import _try_i2i_generation

        attributes = [MagicMock()]
        mock_db, added = _make_cards_db(attributes)
        listing = _make_listing()

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
            return_value=None,
        ), patch(
            "app.services.image_card_copy_service.generate_card_copy",
            new_callable=AsyncMock,
            return_value=_card_copies(*CARD_KINDS),
        ) as mock_copy, patch(
            "app.services.image_benefit_card_service.render_benefit_card",
            side_effect=[b"card-a", b"card-b", b"card-c"],
        ) as mock_render, patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(return_value=[b"v1", b"v2"])
            mock_ml_cls.return_value.upload = AsyncMock(
                side_effect=["pic1", "pic2", "card1", "card2", "card3"]
            )
            saved = await _try_i2i_generation(mock_db, listing, MagicMock(), "token")

        assert saved == 5, "2 individuais + 3 cards"
        assert _uploaded_kinds(added) == [
            "individual", "individual", "card_benefits", "card_usage", "card_specs",
        ]

        cards = _cards_of(added)
        assert [o.sort_order for o in cards] == [2, 3, 4], "contiguo apos as individuais"
        assert all(o.source_sku == "SKU0001" for o in cards)
        assert [o.ml_picture_id for o in cards] == ["card1", "card2", "card3"]

        # Atributos vem da query propria, nunca do relacionamento lazy.
        mock_copy.assert_awaited_once_with(listing, attributes)
        # A foto-base dos 3 cards e a 1a individual aprovada.
        assert [c.args[0] for c in mock_render.call_args_list] == [b"v1", b"v1", b"v1"]

    @pytest.mark.asyncio
    async def test_one_failing_card_does_not_take_down_the_others(self):
        """Render explode no 2o card: sobram 2 cards e as individuais intactas."""
        from app.services.image_benefit_card_service import CardRenderError
        from app.services.image_card_copy_service import CARD_KINDS
        from app.workers.tasks.image_tasks import _try_i2i_generation

        mock_db, added = _make_cards_db()

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
            return_value=None,
        ), patch(
            "app.services.image_card_copy_service.generate_card_copy",
            new_callable=AsyncMock,
            return_value=_card_copies(*CARD_KINDS),
        ), patch(
            "app.services.image_benefit_card_service.render_benefit_card",
            side_effect=[b"card-a", CardRenderError("foto base ilegivel"), b"card-c"],
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(return_value=[b"v1", b"v2"])
            mock_ml_cls.return_value.upload = AsyncMock(
                side_effect=["pic1", "pic2", "card1", "card3"]
            )
            saved = await _try_i2i_generation(mock_db, _make_listing(), MagicMock(), "token")

        assert saved == 4, "2 individuais + os 2 cards que sobraram"
        assert _uploaded_kinds(added) == [
            "individual", "individual", "card_benefits", "card_specs",
        ]

        cards = _cards_of(added)
        assert [o.sort_order for o in cards] == [2, 3], "sort_order segue contiguo apos a falha"
        assert [o.source_sku for o in cards] == ["SKU0001", "SKU0001"]

    @pytest.mark.asyncio
    async def test_no_cards_when_no_individual_image_was_saved(self):
        """Sem foto-base nao ha card — e o LLM nem chega a ser chamado."""
        from app.workers.tasks.image_tasks import _try_i2i_generation

        mock_db, added = _make_cards_db()

        def _reject_all(image_bytes, requires_white_bg):
            return None, ImageValidationResult(is_valid=False, errors=["reprovada no QA"])

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
            side_effect=_reject_all,
        ), patch(
            "app.services.image_deterministic_service.try_deterministic_cover",
            return_value=None,
        ), patch(
            "app.services.image_card_copy_service.generate_card_copy",
            new_callable=AsyncMock,
            return_value=_card_copies("card_benefits"),
        ) as mock_copy, patch(
            "app.services.image_benefit_card_service.render_benefit_card"
        ) as mock_render, patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(return_value=[b"v1", b"v2"])
            mock_ml_cls.return_value.upload = AsyncMock(return_value="nunca")
            saved = await _try_i2i_generation(mock_db, _make_listing(), MagicMock(), "token")

        assert saved == 0
        mock_copy.assert_not_awaited()
        mock_render.assert_not_called()
        assert _cards_of(added) == []

    @pytest.mark.asyncio
    async def test_kit_with_two_skus_gets_no_cards(self):
        """Kit (N>1) segue fora de escopo, igual as demais features de 1 SKU."""
        from app.workers.tasks.image_tasks import _try_i2i_generation

        mock_db, added = _make_cards_db()

        with patch(
            "app.services.seller_image_source_service.resolve_listing_skus",
            new_callable=AsyncMock,
            return_value=["SKU0001", "SKU0002"],
        ), patch(
            "app.services.seller_image_source_service.fetch_all_raw_photos",
            new_callable=AsyncMock,
            return_value={"SKU0001": [b"a1"], "SKU0002": [b"b1"]},
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
            "app.services.image_card_copy_service.generate_card_copy",
            new_callable=AsyncMock,
            return_value=_card_copies("card_benefits"),
        ) as mock_copy, patch(
            "app.services.image_benefit_card_service.render_benefit_card"
        ) as mock_render, patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(return_value=[b"v1"])
            mock_ml_cls.return_value.upload = AsyncMock(
                side_effect=[f"pic{i}" for i in range(20)]
            )
            saved = await _try_i2i_generation(mock_db, _make_listing(), MagicMock(), "token")

        # 1 capa composta + 1 individual por SKU = 3, e nenhum card.
        assert saved == 3
        mock_copy.assert_not_awaited()
        mock_render.assert_not_called()
        assert _cards_of(added) == []

    @pytest.mark.asyncio
    async def test_empty_copy_leaves_the_product_images_untouched(self):
        """Copy vazia (LLM fora do ar): zero cards, imagens de produto intactas."""
        from app.workers.tasks.image_tasks import _try_i2i_generation

        mock_db, added = _make_cards_db()

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
            return_value=None,
        ), patch(
            "app.services.image_card_copy_service.generate_card_copy",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "app.services.image_benefit_card_service.render_benefit_card"
        ) as mock_render, patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(return_value=[b"v1", b"v2"])
            mock_ml_cls.return_value.upload = AsyncMock(side_effect=["pic1", "pic2"])
            saved = await _try_i2i_generation(mock_db, _make_listing(), MagicMock(), "token")

        assert saved == 2, "so as individuais"
        mock_render.assert_not_called()
        assert _uploaded_kinds(added) == ["individual", "individual"]


class TestBenefitCardsLogging:
    """Os cards sao engolidos de proposito (nunca derrubam o anuncio), entao
    estes logs sao o UNICO sinal de producao de que pararam de sair. Sem
    traceback nao da pra separar falha de render, de QA, de upload ou de db —
    por isso o `exc_info` e testado, nao so a mensagem."""

    @pytest.mark.asyncio
    async def test_falha_global_loga_com_traceback(self, caplog):
        import logging

        from app.workers.tasks.image_tasks import _append_benefit_cards

        mock_db, _added = _make_cards_db()

        with caplog.at_level(logging.WARNING, logger="app.workers.tasks.image_tasks"), patch(
            "app.services.image_card_copy_service.generate_card_copy",
            new_callable=AsyncMock,
            side_effect=RuntimeError("provider caiu"),
        ):
            saved = await _append_benefit_cards(
                mock_db, _make_listing(), "token",
                base_photo=b"foto", source_sku="SKU0001", start_sort_order=2,
            )

        assert saved == 0
        rec = next(r for r in caplog.records if "result=failed" in r.getMessage())
        assert rec.exc_info is not None
        assert rec.exc_info[0] is RuntimeError

    @pytest.mark.asyncio
    async def test_falha_de_um_card_loga_com_traceback(self, caplog):
        import logging

        from app.workers.tasks.image_tasks import _append_benefit_cards

        mock_db, _added = _make_cards_db()

        with caplog.at_level(logging.WARNING, logger="app.workers.tasks.image_tasks"), patch(
            "app.services.image_card_copy_service.generate_card_copy",
            new_callable=AsyncMock,
            return_value=_card_copies("card_benefits"),
        ), patch(
            "app.services.image_benefit_card_service.render_benefit_card",
            side_effect=ValueError("render quebrou"),
        ), patch(
            "app.services.image_service.MLPictureService"
        ):
            saved = await _append_benefit_cards(
                mock_db, _make_listing(), "token",
                base_photo=b"foto", source_sku="SKU0001", start_sort_order=2,
            )

        assert saved == 0
        rec = next(r for r in caplog.records if "kind=card_benefits" in r.getMessage())
        assert rec.exc_info is not None
        assert rec.exc_info[0] is ValueError


class TestCardsUsamCapaDeterministicaComoBase:
    """A base dos cards e a capa deterministica quando ela existe.

    Motivo: o motor i2i altera texto impresso no rotulo de forma estocastica.
    Num teste real o frasco de 100ml virou "160ml" nas individuais, e os 3
    cards herdaram o erro por usarem a primeira individual como base. A capa
    deterministica e recorte do pixel original, sem IA — o rotulo nela e fiel.
    """

    @pytest.mark.asyncio
    async def test_com_capa_deterministica_os_cards_usam_a_capa(self):
        from app.services.image_card_copy_service import CARD_KINDS
        from app.workers.tasks.image_tasks import _try_i2i_generation

        mock_db, added = _make_cards_db([MagicMock()])

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
            return_value=b"capa-deterministica",
        ), patch(
            "app.services.image_card_copy_service.generate_card_copy",
            new_callable=AsyncMock,
            return_value=_card_copies(*CARD_KINDS),
        ), patch(
            "app.services.image_benefit_card_service.render_benefit_card",
            side_effect=[b"card-a", b"card-b", b"card-c"],
        ) as mock_render, patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(return_value=[b"ind-1", b"ind-2"])
            mock_ml_cls.return_value.upload = AsyncMock(
                side_effect=["capa", "pic1", "pic2", "c1", "c2", "c3"]
            )
            saved = await _try_i2i_generation(mock_db, _make_listing(), MagicMock(), "token")

        assert saved == 6, "1 capa + 2 individuais + 3 cards"
        assert _uploaded_kinds(added) == [
            "cover_deterministic", "individual", "individual",
            "card_benefits", "card_usage", "card_specs",
        ]

        # O ponto do teste: os 3 renders receberam a CAPA, nao a individual.
        bases = [c.args[0] for c in mock_render.call_args_list]
        assert bases == [b"capa-deterministica"] * 3, (
            "os cards precisam sair da capa deterministica, nao de uma imagem "
            "de IA que ninguem verificou"
        )
        assert b"ind-1" not in bases and b"ind-2" not in bases

    @pytest.mark.asyncio
    async def test_sem_capa_deterministica_cai_para_a_primeira_individual(self):
        """Fallback preservado: foto bruta com fundo texturizado nao gera capa."""
        from app.services.image_card_copy_service import CARD_KINDS
        from app.workers.tasks.image_tasks import _try_i2i_generation

        mock_db, added = _make_cards_db([MagicMock()])

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
            return_value=None,
        ), patch(
            "app.services.image_card_copy_service.generate_card_copy",
            new_callable=AsyncMock,
            return_value=_card_copies(*CARD_KINDS),
        ), patch(
            "app.services.image_benefit_card_service.render_benefit_card",
            side_effect=[b"card-a", b"card-b", b"card-c"],
        ) as mock_render, patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(return_value=[b"ind-1", b"ind-2"])
            mock_ml_cls.return_value.upload = AsyncMock(
                side_effect=["pic1", "pic2", "c1", "c2", "c3"]
            )
            saved = await _try_i2i_generation(mock_db, _make_listing(), MagicMock(), "token")

        assert saved == 5, "2 individuais + 3 cards, sem capa"
        assert "cover_deterministic" not in _uploaded_kinds(added)
        bases = [c.args[0] for c in mock_render.call_args_list]
        assert bases == [b"ind-1"] * 3, "sem capa, a base volta a ser a 1a individual"


class TestPromptProibeAlterarTexto:
    """A regra anti-alteracao de texto tem que estar nos dois prompts do i2i.

    Nao da para testar o COMPORTAMENTO do modelo com fixture sintetica — isso
    e do modelo, nao da nossa logica. O que da para travar e que a instrucao
    nao suma do prompt numa refatoracao futura.
    """

    @pytest.mark.asyncio
    async def test_prompt_das_individuais_proibe_alterar_texto(self):
        from app.workers.tasks.image_tasks import _try_i2i_generation

        mock_db, _ = _make_cards_db([])

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
            return_value=None,
        ), patch(
            "app.workers.tasks.image_tasks._append_benefit_cards",
            new_callable=AsyncMock,
            return_value=0,
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(return_value=[b"v1"])
            mock_ml_cls.return_value.upload = AsyncMock(return_value="pic1")
            await _try_i2i_generation(mock_db, _make_listing(), MagicMock(), "token")

        prompt = mock_engine_cls.return_value.edit.await_args.kwargs["prompt"]
        assert "CRITICAL" in prompt
        for termo in ("do not alter", "volumes", "measurement units", "character for character"):
            assert termo in prompt, f"prompt perdeu a instrucao: {termo}"
        # A contradicao antiga: "no text" pedia remover texto enquanto o resto
        # pedia preservar o produto. Agora e "no text overlay".
        assert "no text overlay" in prompt


class TestComposedCoverRespectsTheRawPhotoCut:
    """Finding 5: o corte `[:RAW_PHOTOS_MIN]` faltava SO no ramo da capa
    composta.

    `fetch_all_raw_photos` descobre todas as fotos brutas disponiveis do SKU
    (a descoberta foi justamente a Frente que abriu este branch), e cada foto
    extra entregue ao motor de edicao e custo de IA. O laco das individuais ja
    corta no minimo obrigatorio; a comprehension da capa composta nao cortava,
    entao um kit de 5 SKUs com 6 fotos cada mandaria 30 fotos numa unica
    chamada paga em vez de 10.

    Dormente hoje (`resolve_listing_skus` sempre devolve 1 SKU), mas o teste
    fixa a regra antes do projeto de kits acordar o ramo.
    """

    @pytest.mark.asyncio
    async def test_only_the_first_raw_photos_of_each_sku_reach_the_paid_engine(self):
        from app.services.seller_image_source_service import RAW_PHOTOS_MIN
        from app.workers.tasks.image_tasks import _try_i2i_generation

        mock_config = MagicMock()
        mock_config.raw_base_url = "https://pub-xxx.r2.dev/sku"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock()

        # 5 fotos por SKU: bem mais que o minimo obrigatorio (2).
        raw_photos = {
            "SKU0001": [f"sku1-raw{i}".encode() for i in range(1, 6)],
            "SKU0002": [f"sku2-raw{i}".encode() for i in range(1, 6)],
        }

        listing = _make_listing()

        with patch(
            "app.workers.tasks.image_tasks._append_benefit_cards",
            new_callable=AsyncMock,
            return_value=0,
        ), patch(
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
                side_effect=[[b"cover"]] + [[b"v1", b"v2"] for _ in range(4)]
            )
            mock_ml_cls.return_value.upload = AsyncMock(
                side_effect=[f"pic{i}" for i in range(1, 20)]
            )
            await _try_i2i_generation(mock_db, listing, MagicMock(), "token")

        cover_call = mock_engine_cls.return_value.edit.await_args_list[0]
        enviadas = cover_call.kwargs["images"]

        assert len(enviadas) == RAW_PHOTOS_MIN * 2, enviadas
        assert enviadas == [b"sku1-raw1", b"sku1-raw2", b"sku2-raw1", b"sku2-raw2"]

        # E o laco das individuais continua cortando no mesmo minimo:
        # 1 chamada da capa + 2 fotos x 2 SKUs = 5 chamadas pagas ao todo.
        assert mock_engine_cls.return_value.edit.await_count == 1 + RAW_PHOTOS_MIN * 2
