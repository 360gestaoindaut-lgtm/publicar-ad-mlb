"""Frente B: promover a ficha tecnica — troca quem ocupa o slot de specs.

Espelha `test_cover_promote.py`, com UMA diferenca estrutural deliberada: a
capa tem posicao FIXA (`COVER_SORT_ORDER = 0`, invariante do dominio), a
ficha tecnica NAO tem.

Os cards recebem `start_sort_order + saved` em `image_tasks.py`, onde o
inicio e a contagem corrente de imagens ja salvas. O `card_specs` do SKU 37
esta em 7 porque aquele anuncio tem 1 capa + 4 individuais + 3 cards; um
anuncio com 2 individuais poe a ficha em 5. Inventar um slot fixo mudaria a
numeracao da galeria de TODO anuncio, inclusive os ja publicados.

Por isso `promote_specs` faz troca NO LUGAR: o alvo assume o `sort_order` que
a ficha atual ocupa, seja ele qual for. Sem convençao nova, sem tocar em
`approve_images`.

Como em `test_cover_promote.py`, os `ListingImage` sao instancias REAIS do
model — as assercoes olham o estado dos objetos depois da chamada, nao
contagem de mock.
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
    result = MagicMock()
    result.scalar_one_or_none.return_value = obj
    return result


def _rows_result(objs):
    result = MagicMock()
    result.scalars.return_value.all.return_value = list(objs)
    return result


def _make_db(*execute_results):
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=list(execute_results))
    db.commit = AsyncMock()
    return db


class TestPromoteSpecsSwapsInPlace:
    @pytest.mark.asyncio
    async def test_ai_variant_takes_the_slot_the_pillow_card_occupied(self):
        from app.services.specs_variant_service import promote_specs

        listing = _make_listing()
        pillow = _make_image(listing.id, "card_specs", True, 7, "pic-pillow")
        ia = _make_image(listing.id, "specs_ai", False, 91, "pic-ia")
        db = _make_db(_target_result(ia), _rows_result([pillow]))

        await promote_specs(db, listing, ia.id)

        assert ia.approved is True
        assert ia.sort_order == 7, "assume o slot que a ficha antiga ocupava"
        assert pillow.approved is False
        assert pillow.sort_order == 91
        assert pillow.ml_picture_id == "pic-pillow", "rebaixada, nunca apagada"
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_slot_is_read_from_the_data_not_hardcoded(self):
        """O mesmo caso com a ficha em 5 em vez de 7. Se a funcao tivesse um
        numero cravado, este teste pegaria — e e justamente o que difere da
        capa, cujo 0 e invariante."""
        from app.services.specs_variant_service import promote_specs

        listing = _make_listing()
        pillow = _make_image(listing.id, "card_specs", True, 5, "pic-pillow")
        ia = _make_image(listing.id, "specs_ai", False, 91, "pic-ia")
        db = _make_db(_target_result(ia), _rows_result([pillow]))

        await promote_specs(db, listing, ia.id)

        assert ia.sort_order == 5

    @pytest.mark.asyncio
    async def test_promoting_the_pillow_card_back_reverses_the_swap(self):
        from app.services.specs_variant_service import promote_specs

        listing = _make_listing()
        pillow = _make_image(listing.id, "card_specs", False, 91, "pic-pillow")
        ia = _make_image(listing.id, "specs_ai", True, 7, "pic-ia")
        db = _make_db(_target_result(pillow), _rows_result([ia]))

        await promote_specs(db, listing, pillow.id)

        assert pillow.approved is True
        assert pillow.sort_order == 7
        assert ia.approved is False
        assert ia.sort_order == 91


class TestPromoteSpecsWithoutAnExistingCard:
    @pytest.mark.asyncio
    async def test_goes_to_the_end_of_the_gallery(self):
        """Anuncio sem ficha tecnica: nao ha slot a herdar, entao a ficha
        entra DEPOIS da ultima imagem da galeria — nunca em cima de uma foto
        que ja esta publicada."""
        from app.services.specs_variant_service import promote_specs

        listing = _make_listing()
        ia = _make_image(listing.id, "specs_ai", False, 91, "pic-ia")
        db = _make_db(
            _target_result(ia),
            _rows_result([]),      # nenhuma ficha existente
            _rows_result([4]),     # maior sort_order da galeria
        )

        await promote_specs(db, listing, ia.id)

        assert ia.approved is True
        assert ia.sort_order == 5

    @pytest.mark.asyncio
    async def test_empty_gallery_puts_specs_after_the_reserved_cover_slot(self):
        """Galeria vazia nao pode mandar a ficha para o 0: aquela posicao e
        reservada a kind de capa (`PROMOTABLE_COVER_KINDS`)."""
        from app.models.listing_image import COVER_SORT_ORDER
        from app.services.specs_variant_service import promote_specs

        listing = _make_listing()
        ia = _make_image(listing.id, "specs_ai", False, 91, "pic-ia")
        db = _make_db(_target_result(ia), _rows_result([]), _rows_result([None]))

        await promote_specs(db, listing, ia.id)

        assert ia.sort_order > COVER_SORT_ORDER


class TestPromoteSpecsValidation:
    @pytest.mark.asyncio
    async def test_promoting_an_individual_photo_raises_422(self):
        from app.services.specs_variant_service import promote_specs

        listing = _make_listing()
        foto = _make_image(listing.id, "individual", True, 2, "pic-ind")
        db = _make_db(_target_result(foto))

        with pytest.raises(HTTPException) as exc:
            await promote_specs(db, listing, foto.id)

        assert exc.value.status_code == 422
        assert foto.sort_order == 2, "alvo invalido nao pode ser alterado"
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_promoting_a_cover_raises_422(self):
        """Capa tem o proprio endpoint. Aceitar capa aqui poria uma imagem de
        capa no meio da galeria, e o 0 ficaria vago."""
        from app.services.specs_variant_service import promote_specs

        listing = _make_listing()
        capa = _make_image(listing.id, "cover_deterministic", True, 0, "pic-capa")
        db = _make_db(_target_result(capa))

        with pytest.raises(HTTPException) as exc:
            await promote_specs(db, listing, capa.id)

        assert exc.value.status_code == 422
        assert capa.sort_order == 0

    @pytest.mark.asyncio
    async def test_image_from_another_listing_raises_404(self):
        from app.services.specs_variant_service import promote_specs

        listing = _make_listing()
        db = _make_db(_target_result(None))

        with pytest.raises(HTTPException) as exc:
            await promote_specs(db, listing, uuid4())

        assert exc.value.status_code == 404
        db.commit.assert_not_awaited()


class TestPromoteSpecsGalleryUntouched:
    @pytest.mark.asyncio
    async def test_individuals_and_other_cards_are_not_demoted(self):
        """O rebaixamento so pode alcancar kind de ficha. Sem esse filtro,
        promover a ficha despublicaria silenciosamente uma foto aprovada —
        mesmo defeito que `promote_cover` ja evita."""
        from app.services.specs_variant_service import promote_specs

        listing = _make_listing()
        individual = _make_image(listing.id, "individual", True, 3, "pic-ind")
        beneficios = _make_image(listing.id, "card_benefits", True, 5, "pic-ben")
        pillow = _make_image(listing.id, "card_specs", True, 7, "pic-pillow")
        ia = _make_image(listing.id, "specs_ai", False, 91, "pic-ia")

        # A sessao entrega TAMBEM linhas que nao sao ficha: se a funcao
        # confiasse so no filtro SQL, ela as rebaixaria.
        db = _make_db(_target_result(ia), _rows_result([pillow, individual, beneficios]))

        await promote_specs(db, listing, ia.id)

        assert individual.approved is True and individual.sort_order == 3
        assert beneficios.approved is True and beneficios.sort_order == 5
        assert pillow.approved is False

    @pytest.mark.asyncio
    async def test_demotion_query_filters_by_kind_in_sql(self):
        from app.services.specs_variant_service import promote_specs

        listing = _make_listing()
        pillow = _make_image(listing.id, "card_specs", True, 7, "pic-pillow")
        ia = _make_image(listing.id, "specs_ai", False, 91, "pic-ia")
        db = _make_db(_target_result(ia), _rows_result([pillow]))

        await promote_specs(db, listing, ia.id)

        sql = str(db.execute.await_args_list[1].args[0])
        assert "listing_images.kind IN" in sql, sql
        assert "FOR UPDATE" in sql, sql


class TestPromoteSpecsIdempotency:
    @pytest.mark.asyncio
    async def test_promoting_the_current_specs_again_is_a_no_op(self):
        from app.services.specs_variant_service import promote_specs

        listing = _make_listing()
        ia = _make_image(listing.id, "specs_ai", True, 7, "pic-ia")
        db = _make_db(_target_result(ia), _rows_result([]))

        await promote_specs(db, listing, ia.id)

        assert ia.approved is True
        assert ia.sort_order == 7
        db.commit.assert_not_awaited(), "nada mudou: nao escreve no banco"


class TestPromoteSpecsSelfHeals:
    @pytest.mark.asyncio
    async def test_two_specs_rows_tied_in_the_same_slot_are_both_demoted(self):
        """Estado corrompido por promocoes concorrentes: duas fichas no mesmo
        slot. `publish_service` ordena por `sort_order` sem desempate, entao o
        empate faz a ficha publicada virar sorteio. Rebaixar a lista inteira
        faz a proxima promocao consertar em vez de quebrar."""
        from app.services.specs_variant_service import promote_specs

        listing = _make_listing()
        empatada_a = _make_image(listing.id, "card_specs", True, 7, "pic-a")
        empatada_b = _make_image(listing.id, "specs_ai", True, 7, "pic-b")
        alvo = _make_image(listing.id, "specs_ai", False, 91, "pic-c")
        db = _make_db(_target_result(alvo), _rows_result([empatada_a, empatada_b]))

        await promote_specs(db, listing, alvo.id)

        assert alvo.approved is True and alvo.sort_order == 7
        assert empatada_a.approved is False and empatada_a.sort_order == 91
        assert empatada_b.approved is False and empatada_b.sort_order == 91
