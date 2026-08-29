"""Frente B: promover a capa — troca qual imagem ocupa sort_order=0.

`promote_cover` (backend/app/services/cover_variant_service.py) é a única
peça de decisão: dado um `image_id`, decide se ele vira a capa publicada
(`approved=True, sort_order=0`) e devolve a capa anterior ao papel de
candidata (`approved=False, sort_order=COVER_AI_SORT_ORDER`), sem apagar
nada e sem tocar no resto da galeria.

Os objetos `ListingImage` usados aqui são instâncias REAIS do model (não
`MagicMock`) — as asserções são sobre o estado desses objetos depois da
chamada, não sobre quantas vezes um mock foi invocado. Só a sessão (`db`) é
mockada, no mesmo estilo já usado em `test_bulk_service.py`: uma lista de
resultados por chamada de `db.execute`, via `side_effect`.
"""
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.listing_image import ListingImage


def _make_listing():
    listing = MagicMock()
    listing.id = uuid4()
    return listing


def _make_image(listing_id, kind, approved, sort_order, ml_picture_id):
    return ListingImage(
        id=uuid4(),
        listing_id=listing_id,
        kind=kind,
        approved=approved,
        sort_order=sort_order,
        ml_picture_id=ml_picture_id,
        status="uploaded",
    )


def _execute_result(obj):
    """MagicMock cujo `scalar_one_or_none()` devolve `obj` — uma linha de
    `side_effect` de `db.execute`."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = obj
    return result


def _make_db(*execute_results):
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_execute_result(r) for r in execute_results])
    db.commit = AsyncMock()
    return db


class TestPromoteCoverSwapsPlaces:
    @pytest.mark.asyncio
    async def test_promoting_the_ai_variant_swaps_it_with_the_deterministic_cover(self):
        from app.services.cover_variant_service import promote_cover

        listing = _make_listing()
        cover_det = _make_image(listing.id, "cover_deterministic", True, 0, "pic-det")
        cover_ai = _make_image(listing.id, "cover_ai", False, 90, "pic-ai")
        db = _make_db(cover_ai, cover_det)  # 1ª query = alvo, 2ª = capa atual

        await promote_cover(db, listing, cover_ai.id)

        assert cover_ai.approved is True
        assert cover_ai.sort_order == 0
        assert cover_det.approved is False
        assert cover_det.sort_order == 90
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_promoting_the_deterministic_cover_back_reverses_the_swap(self):
        """Sentido inverso do teste anterior: a variante IA está em 0/aprovada
        e a determinística em 90/candidata; promover a determinística de
        volta troca os dois outra vez."""
        from app.services.cover_variant_service import promote_cover

        listing = _make_listing()
        cover_det = _make_image(listing.id, "cover_deterministic", False, 90, "pic-det")
        cover_ai = _make_image(listing.id, "cover_ai", True, 0, "pic-ai")
        db = _make_db(cover_det, cover_ai)

        await promote_cover(db, listing, cover_det.id)

        assert cover_det.approved is True
        assert cover_det.sort_order == 0
        assert cover_ai.approved is False
        assert cover_ai.sort_order == 90
        db.commit.assert_awaited()


class TestPromoteCoverPublishPayload:
    @pytest.mark.asyncio
    async def test_demoted_image_never_reaches_the_upload_payload(self):
        """Reproduz o filtro que `publish_service.publish` usa pra montar o
        payload de fotos (approved + ml_picture_id, ordenado por sort_order)
        e confere que só a imagem promovida sobra — sem chamar publish() de
        verdade, o que bateria na rede bloqueada pelo conftest."""
        from app.services.cover_variant_service import promote_cover

        listing = _make_listing()
        cover_det = _make_image(listing.id, "cover_deterministic", True, 0, "pic-det")
        cover_ai = _make_image(listing.id, "cover_ai", False, 90, "pic-ai")
        db = _make_db(cover_ai, cover_det)

        await promote_cover(db, listing, cover_ai.id)

        images = [cover_det, cover_ai]
        pics_payload = [
            {"id": img.ml_picture_id}
            for img in sorted(images, key=lambda x: x.sort_order)
            if img.approved and img.ml_picture_id
        ]

        assert pics_payload == [{"id": "pic-ai"}]


class TestPromoteCoverValidation:
    @pytest.mark.asyncio
    async def test_promoting_an_individual_photo_raises_422(self):
        from app.services.cover_variant_service import promote_cover

        listing = _make_listing()
        individual = _make_image(listing.id, "individual", False, 3, "pic-3")
        db = _make_db(individual)

        with pytest.raises(HTTPException) as exc_info:
            await promote_cover(db, listing, individual.id)

        assert exc_info.value.status_code == 422
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_promoting_an_image_from_another_listing_raises_404(self):
        """A query já filtra por `listing_id`, então uma imagem de outro
        anúncio simplesmente não aparece — mesmo comportamento de
        `ListingService.get_or_404`."""
        from app.services.cover_variant_service import promote_cover

        listing = _make_listing()
        db = _make_db(None)  # nenhuma linha bate id + listing_id

        with pytest.raises(HTTPException) as exc_info:
            await promote_cover(db, listing, uuid4())

        assert exc_info.value.status_code == 404
        db.commit.assert_not_awaited()


class TestPromoteCoverIdempotency:
    @pytest.mark.asyncio
    async def test_promoting_twice_in_a_row_keeps_the_same_state(self):
        """Chama `promote_cover` duas vezes seguidas para o mesmo alvo. Se o
        guard `sort_order == 0` for removido, a segunda chamada buscaria 'a
        capa atual', encontraria a própria imagem alvo e a rebaixaria pra 90
        — este teste pega exatamente essa regressão, e também confirma que a
        segunda chamada não faz um segundo `commit`."""
        from app.services.cover_variant_service import promote_cover

        listing = _make_listing()
        cover_det = _make_image(listing.id, "cover_deterministic", True, 0, "pic-det")
        cover_ai = _make_image(listing.id, "cover_ai", False, 90, "pic-ai")
        # chamada 1: alvo (cover_ai) + capa atual (cover_det).
        # chamada 2: alvo já em sort_order=0 -> retorno antecipado, sem 2ª query.
        db = _make_db(cover_ai, cover_det, cover_ai)

        await promote_cover(db, listing, cover_ai.id)
        await promote_cover(db, listing, cover_ai.id)

        assert cover_ai.approved is True
        assert cover_ai.sort_order == 0
        assert cover_det.approved is False
        assert cover_det.sort_order == 90
        assert db.commit.await_count == 1
        assert db.execute.await_count == 3
