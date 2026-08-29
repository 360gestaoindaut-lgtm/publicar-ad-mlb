"""Frente B: ficha tecnica renderizada por IA sob demanda + review_seconds.

Testes de `generate_specs_variant` no mesmo estilo de `test_cover_variant.py`
— db mockado com AsyncMock, engine e copy patchados na origem (imports
locais dentro da funcao, entao o patch precisa mirar o modulo que define o
nome, nao `specs_variant_service`).

Os testes de `review_seconds` chamam `ListingService.approve_images` de
verdade (nao um mock do metodo) e leem o valor de volta direto do objeto ORM
`ListingImage` — nao basta provar que um mock foi chamado com um numero.
"""
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.listing_image import ListingImage
from app.services.image_card_copy_service import CardCopy
from app.services.image_service import ImageValidationResult


def _make_listing():
    listing = MagicMock()
    listing.id = uuid4()
    return listing


def _make_cover(listing_id, image_bytes, source_sku="SKU0001"):
    return ListingImage(
        id=uuid4(),
        listing_id=listing_id,
        kind="cover_deterministic",
        approved=True,
        sort_order=0,
        status="uploaded",
        source_sku=source_sku,
        image_bytes=image_bytes,
    )


def _make_db(cover_image, attributes=None):
    """AsyncMock de sessao cujas duas queries (capa determinística, depois
    atributos) devolvem `cover_image` e `attributes`, nessa ordem — mesma
    ordem em que `generate_specs_variant` as executa."""
    mock_db = AsyncMock()
    cover_result = MagicMock()
    cover_result.scalar_one_or_none.return_value = cover_image
    attrs_result = MagicMock()
    attrs_result.scalars.return_value.all.return_value = list(attributes or [])
    mock_db.execute = AsyncMock(side_effect=[cover_result, attrs_result])
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    return mock_db


class TestGenerateSpecsVariantSuccess:
    @pytest.mark.asyncio
    async def test_candidate_is_born_unapproved_with_specs_ai_kind_and_sort_order(self):
        from app.services.specs_variant_service import (
            SPECS_AI_KIND,
            SPECS_AI_SORT_ORDER,
            generate_specs_variant,
        )

        listing = _make_listing()
        cover = _make_cover(listing.id, image_bytes=b"exact-saved-cover-bytes")
        mock_db = _make_db(cover)

        specs_copy = CardCopy(
            kind="card_specs", title="Ficha tecnica", bullets=["Bullet 1", "Bullet 2"]
        )
        prepared = b"prepared-1200x1200"
        verdict = ImageValidationResult(is_valid=True)

        with patch(
            "app.services.image_card_copy_service.generate_card_copy",
            new_callable=AsyncMock,
            return_value=[specs_copy],
        ), patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as mock_engine_cls, patch(
            "app.workers.tasks.image_tasks._prepare_image_for_upload",
            return_value=(prepared, verdict),
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(return_value=[b"variant-bytes"])
            mock_ml_cls.return_value.upload = AsyncMock(return_value="pic-specs-1")

            candidate = await generate_specs_variant(mock_db, listing, "token-xyz")

        assert candidate.kind == SPECS_AI_KIND == "specs_ai"
        assert candidate.approved is False
        assert candidate.sort_order == SPECS_AI_SORT_ORDER == 91
        assert candidate.status == "uploaded"
        assert candidate.ml_picture_id == "pic-specs-1"
        mock_db.commit.assert_awaited()

        engine_kwargs = mock_engine_cls.return_value.edit.await_args.kwargs
        assert engine_kwargs["images"] == [b"exact-saved-cover-bytes"]
        assert engine_kwargs["n"] == 1
        prompt = engine_kwargs["prompt"]
        assert "Ficha tecnica" in prompt
        assert "Bullet 1" in prompt
        assert "Bullet 2" in prompt


class TestGenerateSpecsVariantPreservesPillowCard:
    @pytest.mark.asyncio
    async def test_existing_card_specs_row_stays_untouched(self):
        """O `card_specs` (Pillow) ja existente no anuncio nunca aparece em
        nenhum resultado configurado para `mock_db.execute` — a unica forma
        dele ser alterado seria o servico fazer uma consulta extra (nao
        configurada aqui) que o devolvesse, o que estouraria o `side_effect`
        de 2 resultados. A asserção confere o ESTADO real do objeto depois da
        chamada, não so que ele "ainda existe"."""
        from app.services.specs_variant_service import generate_specs_variant

        listing = _make_listing()
        cover = _make_cover(listing.id, image_bytes=b"cover-bytes")
        mock_db = _make_db(cover)

        pillow_card = ListingImage(
            id=uuid4(),
            listing_id=listing.id,
            kind="card_specs",
            approved=True,
            sort_order=52,
            status="approved",
        )

        specs_copy = CardCopy(
            kind="card_specs", title="Ficha tecnica", bullets=["Bullet 1", "Bullet 2"]
        )
        prepared = b"prepared-bytes"
        verdict = ImageValidationResult(is_valid=True)

        with patch(
            "app.services.image_card_copy_service.generate_card_copy",
            new_callable=AsyncMock,
            return_value=[specs_copy],
        ), patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as mock_engine_cls, patch(
            "app.workers.tasks.image_tasks._prepare_image_for_upload",
            return_value=(prepared, verdict),
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(return_value=[b"variant-bytes"])
            mock_ml_cls.return_value.upload = AsyncMock(return_value="pic-specs-1")

            await generate_specs_variant(mock_db, listing, "token-xyz")

        assert pillow_card.approved is True
        assert pillow_card.sort_order == 52
        assert pillow_card.kind == "card_specs"
        assert mock_db.execute.await_count == 2


class TestGenerateSpecsVariantMissingCopyAngle:
    @pytest.mark.asyncio
    async def test_missing_card_specs_angle_raises_and_writes_nothing(self):
        from app.services.specs_variant_service import (
            SpecsVariantError,
            generate_specs_variant,
        )

        listing = _make_listing()
        cover = _make_cover(listing.id, image_bytes=b"cover-bytes")
        mock_db = _make_db(cover)

        # Copy trouxe outro angulo, mas o sanitizador descartou card_specs.
        other_angle = CardCopy(kind="card_benefits", title="Beneficios", bullets=["A", "B"])

        with patch(
            "app.services.image_card_copy_service.generate_card_copy",
            new_callable=AsyncMock,
            return_value=[other_angle],
        ), patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as mock_engine_cls:
            with pytest.raises(SpecsVariantError):
                await generate_specs_variant(mock_db, listing, "token-xyz")

        mock_engine_cls.assert_not_called()
        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_awaited()


def _make_approval_listing(status="pending_image_approval"):
    listing = MagicMock()
    listing.id = uuid4()
    listing.seller_id = uuid4()
    listing.status = status
    listing.sku_external_id = None  # evita a atualizacao de ProductImage
    return listing


def _make_approve_db(images):
    """AsyncMock de sessao cuja unica query devolve a lista `images` — sem
    `ml_picture_id`/`sku_external_id` casados, o branch de ProductImage no
    fim de `approve_images` nao dispara uma 2a query."""
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = images
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


class TestApproveImagesReviewSeconds:
    @pytest.mark.asyncio
    async def test_review_seconds_recorded_on_approved_images_when_provided(self):
        """Chama `ListingService.approve_images` de verdade e le
        `review_seconds` de volta do objeto ORM — nao mocka o metodo nem
        confere so a chamada."""
        from app.services.listing_service import ListingService

        listing = _make_approval_listing()
        approved_img = ListingImage(
            id=uuid4(), listing_id=listing.id, kind="specs_ai",
            approved=False, sort_order=91, status="uploaded",
        )
        rejected_img = ListingImage(
            id=uuid4(), listing_id=listing.id, kind="card_specs",
            approved=True, sort_order=3, status="approved",
        )
        db = _make_approve_db([approved_img, rejected_img])
        svc = ListingService(db)

        await svc.approve_images(listing, [approved_img.id], review_seconds=42)

        assert approved_img.review_seconds == 42
        assert approved_img.approved is True
        # Imagem nao aprovada nesta chamada nao ganha o tempo de revisao.
        assert rejected_img.review_seconds is None
        assert rejected_img.approved is False
        assert listing.status == "generating_description"
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_review_seconds_absent_stays_null_and_approval_still_works(self):
        from app.services.listing_service import ListingService

        listing = _make_approval_listing()
        approved_img = ListingImage(
            id=uuid4(), listing_id=listing.id, kind="specs_ai",
            approved=False, sort_order=91, status="uploaded",
        )
        db = _make_approve_db([approved_img])
        svc = ListingService(db)

        await svc.approve_images(listing, [approved_img.id])

        assert approved_img.review_seconds is None
        assert approved_img.approved is True
        assert approved_img.status == "approved"
        assert listing.status == "generating_description"
        db.commit.assert_awaited()
