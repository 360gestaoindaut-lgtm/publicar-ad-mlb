"""`values` do ML: enumeracao fechada ou sugestao? O `value_type` decide.

O guard que consertou o PERFUME_TYPE do SKU 37 tratava QUALQUER lista de
valores como enumeracao fechada. So que o ML usa `values` de dois jeitos:

- `value_type == "list"` (PERFUME_TYPE): enumeracao real. "Colonia" e
  recusado, "Agua de colonia" e aceito. Foi o defeito original.
- `value_type == "string"` (BRAND): lista de SUGESTOES. O ML aceita texto
  livre e resolve o id sozinho.

Prova empirica de que a segunda linha existe: o anuncio MLB5145387291, ativo
em MLB6284, tem `BRAND value_id='13065330' value_name='Wepink'` — e "Wepink"
NAO esta entre as 24 sugestoes que a mesma categoria devolve. O ML resolveu
por conta propria.

Sem essa distincao, o cadastro do SKU 38 travava: marca real do produto
recusada com 422 e nenhum caminho pela API para grava-la.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _attr_ml(attr_id, name, value_type, values=None, required=False):
    a = {"id": attr_id, "name": name, "value_type": value_type}
    if values is not None:
        a["values"] = values
    if required:
        a["tags"] = {"required": True}
    return a


_MARCAS = [
    {"id": "498493", "name": "47 Street"},
    {"id": "23688", "name": "Benetton"},
    {"id": "350205", "name": "Axis"},
]
_TIPOS = [
    {"id": "111075", "name": "Água de colônia"},
    {"id": "111076", "name": "Eau de parfum"},
]


def _listing():
    listing = MagicMock()
    listing.id = "lid"
    listing.ml_category_id = "MLB6284"
    listing.condition = "new"
    listing.sku_brand = "Wepink"
    listing.sku_model = None
    listing.sku_external_id = "38"
    listing.package_weight_kg = None
    listing.package_length_cm = None
    listing.package_width_cm = None
    listing.package_height_cm = None
    return listing


def _db():
    db = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


def _salvos(db):
    return {c.args[0].attribute_id: c.args[0] for c in db.add.call_args_list}


class TestPrefillDeStringComSugestoes:
    @pytest.mark.asyncio
    async def test_marca_fora_das_sugestoes_e_preservada(self):
        """O caso que travou o SKU 38: BRAND e `string`, entao a lista e
        sugestao. Descartar a marca real do produto nao ajuda ninguem — o ML
        aceita e resolve o id sozinho."""
        from app.services.category_service import CategoryService

        db = _db()
        svc = CategoryService(db)
        attrs = [_attr_ml("BRAND", "Marca", "string", _MARCAS, required=True)]

        await svc._save_attributes(_listing(), attrs)

        brand = _salvos(db)["BRAND"]
        assert brand.value_name == "Wepink"
        assert brand.value_id is None, "sem id: o ML resolve na publicacao"

    @pytest.mark.asyncio
    async def test_marca_que_casa_ganha_o_value_id(self):
        """Casar continua valendo: se a marca ESTA na lista, aproveitamos o id
        e o nome exato do ML em vez de mandar so texto."""
        from app.services.category_service import CategoryService

        db = _db()
        listing = _listing()
        listing.sku_brand = "benetton"  # minusculo de proposito
        attrs = [_attr_ml("BRAND", "Marca", "string", _MARCAS, required=True)]

        await CategoryService(db)._save_attributes(listing, attrs)

        brand = _salvos(db)["BRAND"]
        assert brand.value_id == "23688"
        assert brand.value_name == "Benetton", "normaliza para o nome exato do ML"


class TestPrefillDeListaContinuaEstrito:
    """Exercitado por `ITEM_CONDITION`, que e `value_type == "list"` E e
    prefilled de verdade ("Novo"/"Usado"). Nao ha parametro de teste no codigo
    de producao: e o mesmo caminho que roda em `predict_and_save`."""

    @pytest.mark.asyncio
    async def test_valor_fora_da_lista_ainda_e_descartado(self):
        """A protecao original nao pode afrouxar: em `list`, valor fora da
        enumeracao vira `Attribute [X] is not valid` na publicacao."""
        from app.services.category_service import CategoryService

        db = _db()
        # Categoria cuja lista de condicao NAO contem "Novo" — analogo exato do
        # "Colônia" que existe em MLB178938 e nao em MLB6284.
        outra_lista = [{"id": "999", "name": "Recondicionado"}]
        attrs = [_attr_ml("ITEM_CONDITION", "Condição", "list", outra_lista, required=True)]

        await CategoryService(db)._save_attributes(_listing(), attrs)

        cond = _salvos(db)["ITEM_CONDITION"]
        assert cond.value_name is None, "fora da enumeracao: descartado"
        assert cond.value_id is None

    @pytest.mark.asyncio
    async def test_valor_de_lista_que_casa_e_gravado_com_id(self):
        from app.services.category_service import CategoryService

        db = _db()
        lista = [{"id": "2230284", "name": "Novo"}, {"id": "2230581", "name": "Usado"}]
        attrs = [_attr_ml("ITEM_CONDITION", "Condição", "list", lista)]

        await CategoryService(db)._save_attributes(_listing(), attrs)

        cond = _salvos(db)["ITEM_CONDITION"]
        assert cond.value_id == "2230284"
        assert cond.value_name == "Novo"


class TestSubmitAttributesSegueAMesmaRegra:
    def _attr(self, attribute_id, attribute_type, allowed):
        a = MagicMock()
        a.attribute_id = attribute_id
        a.attribute_name = attribute_id
        a.attribute_type = attribute_type
        a.allowed_values = allowed
        return a

    def test_string_com_sugestoes_aceita_valor_livre(self):
        from app.services.listing_service import ListingService

        attr = self._attr("BRAND", "string", _MARCAS)
        value_id, value_name = ListingService._validar_valor(
            attr, {"value_name": "Wepink"}
        )
        assert value_name == "Wepink"
        assert value_id is None

    def test_string_com_sugestoes_ainda_resolve_o_id_quando_casa(self):
        from app.services.listing_service import ListingService

        attr = self._attr("BRAND", "string", _MARCAS)
        value_id, value_name = ListingService._validar_valor(
            attr, {"value_name": "axis"}
        )
        assert (value_id, value_name) == ("350205", "Axis")

    def test_lista_continua_recusando_com_422(self):
        from app.services.listing_service import ListingService

        attr = self._attr("PERFUME_TYPE", "list", _TIPOS)
        with pytest.raises(HTTPException) as exc:
            ListingService._validar_valor(attr, {"value_name": "Colônia"})

        assert exc.value.status_code == 422
        assert "Água de colônia" in exc.value.detail

    def test_lista_aceita_valor_valido(self):
        from app.services.listing_service import ListingService

        attr = self._attr("PERFUME_TYPE", "list", _TIPOS)
        assert ListingService._validar_valor(attr, {"value_name": "Eau de parfum"}) == (
            "111076",
            "Eau de parfum",
        )


class TestEanChegaAoGtin:
    @pytest.mark.asyncio
    async def test_predict_category_le_o_ean_do_produto(self):
        """O EAN esta em `products.ean` desde o cadastro, mas
        `predict_category.delay(listing_id)` nao passava nada e o parametro
        `ean` tinha default None — o GTIN nunca era pre-preenchido."""
        from app.workers.tasks import category_tasks

        listing = MagicMock()
        listing.id = "lid"
        listing.product_id = "pid"
        listing.created_via = "manual"
        listing.status = "pending_seller_attributes"

        product = MagicMock()
        product.ean = "7908647604106"

        db = AsyncMock()
        db.commit = AsyncMock()
        r_listing = MagicMock()
        r_listing.scalar_one.return_value = listing
        r_product = MagicMock()
        r_product.scalar_one_or_none.return_value = product
        db.execute = AsyncMock(side_effect=[r_listing, r_product])

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=db)
        ctx.__aexit__ = AsyncMock(return_value=False)

        svc = MagicMock()
        svc.predict_and_save = AsyncMock()

        with patch("app.database.worker_session", return_value=ctx), patch(
            "app.services.category_service.CategoryService", return_value=svc
        ):
            await category_tasks._predict_category_async("lid")

        assert svc.predict_and_save.await_args.kwargs["ean"] == "7908647604106"

    @pytest.mark.asyncio
    async def test_ean_explicito_tem_precedencia(self):
        """Quem chama informando o EAN continua mandando — a leitura do produto
        e fallback, nao sobrescrita."""
        from app.workers.tasks import category_tasks

        listing = MagicMock()
        listing.id = "lid"
        listing.product_id = "pid"
        listing.created_via = "manual"
        listing.status = "pending_seller_attributes"

        db = AsyncMock()
        db.commit = AsyncMock()
        r_listing = MagicMock()
        r_listing.scalar_one.return_value = listing
        db.execute = AsyncMock(side_effect=[r_listing])

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=db)
        ctx.__aexit__ = AsyncMock(return_value=False)

        svc = MagicMock()
        svc.predict_and_save = AsyncMock()

        with patch("app.database.worker_session", return_value=ctx), patch(
            "app.services.category_service.CategoryService", return_value=svc
        ):
            await category_tasks._predict_category_async("lid", ean="1111111111116")

        assert svc.predict_and_save.await_args.kwargs["ean"] == "1111111111116"
