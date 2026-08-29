"""Frente A: promover a capa — troca qual imagem ocupa sort_order=0.

`promote_cover` (backend/app/services/cover_variant_service.py) é a única
peça de decisão: dado um `image_id`, decide se ele vira a capa publicada
(`approved=True, sort_order=0`) e rebaixa toda linha que hoje ocupa
sort_order=0 e não é o alvo, devolvendo cada uma ao papel de candidata
(`approved=False, sort_order=COVER_AI_SORT_ORDER`) — sem apagar nada e sem
tocar no resto da galeria.

Os objetos `ListingImage` usados aqui são instâncias REAIS do model (não
`MagicMock`) — as asserções são sobre o estado desses objetos depois da
chamada, não sobre quantas vezes um mock foi invocado. Só a sessão (`db`) é
mockada, no mesmo estilo já usado em `test_bulk_service.py`: uma lista de
resultados por chamada de `db.execute`, via `side_effect`. `promote_cover`
faz até duas queries por chamada — alvo (`scalar_one_or_none`) e "quem mais
está em sort_order=0" (`scalars().all()`) — então cada teste monta os
resultados na ordem certa.
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


def _target_result(obj):
    """Resultado de `db.execute` para a query do alvo (`scalar_one_or_none`)."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = obj
    return result


def _others_result(objs):
    """Resultado de `db.execute` para a query de 'quem mais está em
    sort_order=0' (`scalars().all()`)."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = list(objs)
    return result


def _make_db(*execute_results):
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=list(execute_results))
    db.commit = AsyncMock()
    return db


class TestPromoteCoverSwapsPlaces:
    @pytest.mark.asyncio
    async def test_promoting_the_ai_variant_swaps_it_with_the_deterministic_cover(self):
        from app.services.cover_variant_service import promote_cover

        listing = _make_listing()
        cover_det = _make_image(listing.id, "cover_deterministic", True, 0, "pic-det")
        cover_ai = _make_image(listing.id, "cover_ai", False, 90, "pic-ai")
        db = _make_db(_target_result(cover_ai), _others_result([cover_det]))

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
        db = _make_db(_target_result(cover_det), _others_result([cover_ai]))

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
        db = _make_db(_target_result(cover_ai), _others_result([cover_det]))

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
        db = _make_db(_target_result(individual))

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
        db = _make_db(_target_result(None))  # nenhuma linha bate id + listing_id

        with pytest.raises(HTTPException) as exc_info:
            await promote_cover(db, listing, uuid4())

        assert exc_info.value.status_code == 404
        db.commit.assert_not_awaited()


class TestPromoteCoverGalleryUntouched:
    @pytest.mark.asyncio
    async def test_individuals_and_cards_keep_their_sort_order_and_approval(self):
        """A garantia "nada mais se move" era estrutural (a função nunca
        consulta além de alvo e duplicatas em sort_order=0), não testada.
        Este teste põe individuais e cards na galeria com valores que não
        colidem com nenhuma query de `promote_cover` e confere que nenhum
        atributo deles muda."""
        from app.services.cover_variant_service import promote_cover

        listing = _make_listing()
        cover_det = _make_image(listing.id, "cover_deterministic", True, 0, "pic-det")
        cover_ai = _make_image(listing.id, "cover_ai", False, 90, "pic-ai")
        individual_1 = _make_image(listing.id, "individual", True, 1, "pic-1")
        individual_2 = _make_image(listing.id, "individual", True, 2, "pic-2")
        card = _make_image(listing.id, "card_specs", True, 50, "pic-card")

        before = [
            (img.id, img.approved, img.sort_order) for img in (individual_1, individual_2, card)
        ]

        db = _make_db(_target_result(cover_ai), _others_result([cover_det]))

        await promote_cover(db, listing, cover_ai.id)

        after = [
            (img.id, img.approved, img.sort_order) for img in (individual_1, individual_2, card)
        ]
        assert before == after


class TestPromoteCoverIdempotency:
    @pytest.mark.asyncio
    async def test_promoting_twice_in_a_row_keeps_the_same_state(self):
        """Chama `promote_cover` duas vezes seguidas para o mesmo alvo. Na
        1ª chamada o alvo muda de lugar com a capa atual; na 2ª, o alvo já
        está em sort_order=0 e não há mais ninguém em 0 pra rebaixar, então
        nada muda e não há um segundo `commit`."""
        from app.services.cover_variant_service import promote_cover

        listing = _make_listing()
        cover_det = _make_image(listing.id, "cover_deterministic", True, 0, "pic-det")
        cover_ai = _make_image(listing.id, "cover_ai", False, 90, "pic-ai")
        db = _make_db(
            _target_result(cover_ai),
            _others_result([cover_det]),  # chamada 1: cover_det ainda em 0
            _target_result(cover_ai),
            _others_result([]),  # chamada 2: ninguém além do alvo em 0
        )

        await promote_cover(db, listing, cover_ai.id)
        await promote_cover(db, listing, cover_ai.id)

        assert cover_ai.approved is True
        assert cover_ai.sort_order == 0
        assert cover_det.approved is False
        assert cover_det.sort_order == 90
        assert db.commit.await_count == 1
        assert db.execute.await_count == 4


class TestPromoteCoverSelfHeals:
    @pytest.mark.asyncio
    async def test_promoting_a_third_image_fixes_a_pre_existing_duplicate_cover(self):
        """Prova da autocura pedida na revisão: o estado já chega corrompido
        com DUAS imagens em sort_order=0 (uma corrida anterior a este guard,
        por exemplo). Promover uma terceira imagem precisa deixar exatamente
        uma em 0 e rebaixar as outras duas — sem estourar
        `MultipleResultsFound` nem nenhuma outra exceção."""
        from app.services.cover_variant_service import promote_cover

        listing = _make_listing()
        dup_det = _make_image(listing.id, "cover_deterministic", True, 0, "pic-det")
        dup_ai_old = _make_image(listing.id, "cover_ai", True, 0, "pic-ai-old")
        target = _make_image(listing.id, "cover_ai", False, 90, "pic-ai-new")

        db = _make_db(_target_result(target), _others_result([dup_det, dup_ai_old]))

        await promote_cover(db, listing, target.id)

        assert target.approved is True
        assert target.sort_order == 0
        assert dup_det.approved is False
        assert dup_det.sort_order == 90
        assert dup_ai_old.approved is False
        assert dup_ai_old.sort_order == 90

        all_images = [dup_det, dup_ai_old, target]
        at_cover = [img for img in all_images if img.sort_order == 0]
        assert len(at_cover) == 1
        assert at_cover[0] is target
        db.commit.assert_awaited()
