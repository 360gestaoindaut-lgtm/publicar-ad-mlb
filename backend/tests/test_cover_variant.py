"""Frente A: variante ambientada da capa, gerada sob demanda.

Testes de `generate_cover_variant` no mesmo estilo dos testes de
`_try_i2i_generation` em test_image_tasks.py — db mockado com AsyncMock,
engine e MLPictureService patchados na origem (import é feito dentro da
função, então o patch precisa mirar o módulo que define a classe).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.image_service import ImageValidationResult


def _make_db(cover_image):
    """AsyncMock de sessão cuja primeira (e única) query devolve `cover_image`."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = cover_image
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    return mock_db


def _make_listing():
    listing = MagicMock()
    listing.id = "lid"
    listing.ml_category_id = "MLB1055"
    return listing


def _make_cover(image_bytes, source_sku="SKU0001"):
    cover = MagicMock()
    cover.image_bytes = image_bytes
    cover.source_sku = source_sku
    return cover


class TestGenerateCoverVariantSuccess:
    @pytest.mark.asyncio
    async def test_engine_receives_exactly_the_saved_cover_bytes(self):
        from app.services.cover_variant_service import generate_cover_variant

        cover = _make_cover(image_bytes=b"exact-saved-cover-bytes")
        listing = _make_listing()
        mock_db = _make_db(cover)

        prepared = b"prepared-1200x1200"
        verdict = ImageValidationResult(is_valid=True)

        with patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as mock_engine_cls, patch(
            "app.workers.tasks.image_tasks._resolve_requires_white_bg",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "app.workers.tasks.image_tasks._prepare_image_for_upload",
            return_value=(prepared, verdict),
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(return_value=[b"variant-bytes"])
            mock_ml_cls.return_value.upload = AsyncMock(return_value="pic-ai-1")

            await generate_cover_variant(mock_db, listing, "token-xyz")

        mock_engine_cls.return_value.edit.assert_awaited_once()
        call_kwargs = mock_engine_cls.return_value.edit.await_args.kwargs
        assert call_kwargs["images"] == [b"exact-saved-cover-bytes"]
        assert call_kwargs["n"] == 1

    @pytest.mark.asyncio
    async def test_candidate_is_born_unapproved_with_cover_ai_kind_and_sort_order(self):
        from app.services.cover_variant_service import (
            COVER_AI_KIND,
            COVER_AI_SORT_ORDER,
            generate_cover_variant,
        )

        cover = _make_cover(image_bytes=b"cover-bytes")
        listing = _make_listing()
        mock_db = _make_db(cover)

        prepared = b"prepared-bytes"
        verdict = ImageValidationResult(is_valid=True)

        with patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as mock_engine_cls, patch(
            "app.workers.tasks.image_tasks._resolve_requires_white_bg",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "app.workers.tasks.image_tasks._prepare_image_for_upload",
            return_value=(prepared, verdict),
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(return_value=[b"variant-bytes"])
            mock_ml_cls.return_value.upload = AsyncMock(return_value="pic-ai-1")

            candidate = await generate_cover_variant(mock_db, listing, "token-xyz")

        assert candidate.kind == COVER_AI_KIND == "cover_ai"
        assert candidate.approved is False
        assert candidate.sort_order == COVER_AI_SORT_ORDER == 90
        assert candidate.status == "uploaded"
        assert candidate.ml_picture_id == "pic-ai-1"
        mock_db.commit.assert_awaited()


class TestGenerateCoverVariantMissingCover:
    @pytest.mark.asyncio
    async def test_no_deterministic_cover_raises(self):
        from app.services.cover_variant_service import (
            CoverVariantError,
            generate_cover_variant,
        )

        listing = _make_listing()
        mock_db = _make_db(cover_image=None)

        with pytest.raises(CoverVariantError):
            await generate_cover_variant(mock_db, listing, "token-xyz")

    @pytest.mark.asyncio
    async def test_cover_without_saved_bytes_raises_and_never_calls_engine(self):
        """Capa existe (registro pré-Task 1), mas image_bytes é NULL: nunca
        chamar o motor pago — o request não pode ter sucesso de jeito nenhum."""
        from app.services.cover_variant_service import (
            CoverVariantError,
            generate_cover_variant,
        )

        cover = _make_cover(image_bytes=None)
        listing = _make_listing()
        mock_db = _make_db(cover)

        with patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as mock_engine_cls:
            with pytest.raises(CoverVariantError):
                await generate_cover_variant(mock_db, listing, "token-xyz")

        mock_engine_cls.assert_not_called()


class TestGenerateCoverVariantQaRejection:
    @pytest.mark.asyncio
    async def test_rejected_by_qa_records_validation_failed_and_does_not_upload(self):
        from app.services.cover_variant_service import (
            COVER_AI_KIND,
            COVER_AI_SORT_ORDER,
            generate_cover_variant,
        )

        cover = _make_cover(image_bytes=b"cover-bytes")
        listing = _make_listing()
        mock_db = _make_db(cover)

        verdict = ImageValidationResult(is_valid=False, errors=["fundo não é branco puro"])

        with patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as mock_engine_cls, patch(
            "app.workers.tasks.image_tasks._resolve_requires_white_bg",
            new_callable=AsyncMock,
            return_value=True,
        ), patch(
            "app.workers.tasks.image_tasks._prepare_image_for_upload",
            return_value=(None, verdict),
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(return_value=[b"variant-bytes"])
            mock_ml_cls.return_value.upload = AsyncMock(return_value="pic-ai-1")

            candidate = await generate_cover_variant(mock_db, listing, "token-xyz")

        assert candidate.status == "validation_failed"
        assert candidate.validation_error == verdict.reason
        assert candidate.kind == COVER_AI_KIND
        assert candidate.sort_order == COVER_AI_SORT_ORDER
        assert candidate.approved is False
        assert candidate.ml_picture_id is None
        mock_ml_cls.return_value.upload.assert_not_awaited()


class TestGenerateCoverVariantPrompt:
    @pytest.mark.asyncio
    async def test_prompt_carries_the_critical_and_pixel_faithful_clauses(self):
        from app.services.cover_variant_service import generate_cover_variant

        cover = _make_cover(image_bytes=b"cover-bytes")
        listing = _make_listing()
        mock_db = _make_db(cover)

        prepared = b"prepared-bytes"
        verdict = ImageValidationResult(is_valid=True)

        with patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as mock_engine_cls, patch(
            "app.workers.tasks.image_tasks._resolve_requires_white_bg",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "app.workers.tasks.image_tasks._prepare_image_for_upload",
            return_value=(prepared, verdict),
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(return_value=[b"variant-bytes"])
            mock_ml_cls.return_value.upload = AsyncMock(return_value="pic-ai-1")

            await generate_cover_variant(mock_db, listing, "token-xyz")

        prompt = mock_engine_cls.return_value.edit.await_args.kwargs["prompt"]
        assert "CRITICAL" in prompt
        assert "pixel-faithful" in prompt
