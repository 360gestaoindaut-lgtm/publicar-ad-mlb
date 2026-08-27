"""Valor de atributo de lista tem que casar com os allowed_values da categoria.

O caso real que originou estes testes: "Colônia" e valor valido em MLB178938
(perfume pet) e NAO existe em MLB6284 (perfumes), onde o equivalente chama
"Água de colônia". O valor migrou de uma categoria para a outra, foi gravado
com value_id nulo, atravessou geracao de imagem e de descricao, e so foi
recusado la no fim pelo Mercado Livre:

    Attribute [PERFUME_TYPE] is not valid, item values [(null:Colônia)]

Estes testes travam os DOIS caminhos por onde um valor invalido pode entrar,
em qualquer categoria e qualquer atributo — nao so PERFUME_TYPE.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.models.listing_attribute import ListingAttribute
from app.services.listing_service import ListingService


def _attr(attribute_id, allowed, nome="Tipo de perfume"):
    a = ListingAttribute(
        listing_id=None,
        attribute_id=attribute_id,
        attribute_name=nome,
        attribute_type="list",
        is_required=False,
        source="ai",
        allowed_values=allowed,
    )
    return a


class TestSubmitAttributesValidaContraAllowedValues:
    def test_valor_fora_da_lista_e_recusado_com_422(self):
        attr = _attr("PERFUME_TYPE", [
            {"id": "111075", "name": "Água de colônia"},
            {"id": "110465", "name": "Eau de parfum"},
        ])

        with pytest.raises(HTTPException) as exc:
            ListingService._validar_valor(attr, {"value_name": "Colônia"})

        assert exc.value.status_code == 422
        # A mensagem tem que dizer o que E aceito — senao o cliente fica
        # adivinhando, que era o problema da resposta crua do ML.
        assert "Água de colônia" in exc.value.detail
        assert "PERFUME_TYPE" in exc.value.detail

    def test_valor_valido_passa_e_resolve_o_id_sozinho(self):
        """Cliente que manda so o nome nao precisa conhecer o id do ML."""
        attr = _attr("PERFUME_TYPE", [
            {"id": "111075", "name": "Água de colônia"},
            {"id": "110465", "name": "Eau de parfum"},
        ])

        vid, vname = ListingService._validar_valor(attr, {"value_name": "Água de colônia"})

        assert vid == "111075", "o id tem que vir resolvido, nao nulo"
        assert vname == "Água de colônia"

    def test_diferenca_de_caixa_nao_derruba_valor_legitimo(self):
        attr = _attr("PERFUME_TYPE", [{"id": "111075", "name": "Água de colônia"}])
        vid, vname = ListingService._validar_valor(attr, {"value_name": "ÁGUA DE COLÔNIA"})
        assert vid == "111075"
        assert vname == "Água de colônia", "normaliza para a grafia exata do ML"

    def test_texto_livre_sem_lista_passa_intacto(self):
        """GTIN, MODEL, dimensoes: nao tem allowed_values, nada a validar."""
        attr = _attr("GTIN", None, nome="Código universal de produto")
        vid, vname = ListingService._validar_valor(attr, {"value_name": "7908981505459"})
        assert vname == "7908981505459"
        assert vid is None

    def test_lista_vazia_e_tratada_como_texto_livre(self):
        attr = _attr("MODEL", [], nome="Modelo")
        vid, vname = ListingService._validar_valor(attr, {"value_name": "Martin"})
        assert vname == "Martin"

    def test_value_id_valido_e_aceito_mesmo_com_nome_diferente(self):
        """Se o id casa, vale o id — o nome e normalizado pelo do ML."""
        attr = _attr("PERFUME_TYPE", [{"id": "111075", "name": "Água de colônia"}])
        vid, vname = ListingService._validar_valor(
            attr, {"value_id": "111075", "value_name": "agua de colonia"}
        )
        assert (vid, vname) == ("111075", "Água de colônia")

    def test_valor_nulo_nao_e_validado(self):
        """Limpar um atributo (mandar None) continua permitido."""
        attr = _attr("PERFUME_TYPE", [{"id": "111075", "name": "Água de colônia"}])
        assert ListingService._validar_valor(attr, {"value_name": None}) == (None, None)

    def test_o_caso_real_que_originou_o_bug(self):
        """Migracao de categoria: valor da categoria pet aplicado na de perfumes."""
        pet = _attr("PERFUME_TYPE", [
            {"id": "194472", "name": "Colônia"},
            {"id": "194473", "name": "Parfum"},
        ])
        # Na pet, "Colônia" e legitimo.
        assert ListingService._validar_valor(pet, {"value_name": "Colônia"}) == ("194472", "Colônia")

        # Na de perfumes humanos, o mesmo valor tem que ser recusado.
        humano = _attr("PERFUME_TYPE", [
            {"id": "111075", "name": "Água de colônia"},
            {"id": "209441", "name": "Parfum"},
        ])
        with pytest.raises(HTTPException) as exc:
            ListingService._validar_valor(humano, {"value_name": "Colônia"})
        assert exc.value.status_code == 422


class TestPrefillDescartaValorForaDaCategoria:
    """O prefill do category_service nao pode gravar nome sem id correspondente."""

    @pytest.mark.asyncio
    async def test_prefill_que_nao_casa_e_descartado_em_vez_de_gravado(self):
        from app.services.category_service import CategoryService

        listing = MagicMock()
        listing.id = "lid"
        listing.condition = "new"
        listing.sku_brand = "Wepink"
        listing.sku_external_id = "37"
        listing.sku_model = None
        listing.ml_category_id = "MLB6284"
        listing.package_weight_kg = None
        listing.package_length_cm = None
        listing.package_width_cm = None
        listing.package_height_cm = None

        adicionados = []
        db = AsyncMock()
        db.add = MagicMock(side_effect=adicionados.append)
        db.execute = AsyncMock()

        # ITEM_CONDITION e o unico prefill de lista hoje. Categoria que nomeie
        # a condicao de outro jeito nao pode receber "Novo" com id nulo.
        raw = [{
            "id": "ITEM_CONDITION",
            "name": "Condição do item",
            "value_type": "list",
            "tags": {},
            "values": [{"id": "2230284", "name": "Nuevo"}, {"id": "2230581", "name": "Usado"}],
        }]

        await CategoryService(db)._save_attributes(listing, raw)

        cond = next(a for a in adicionados if a.attribute_id == "ITEM_CONDITION")
        assert cond.value_name is None, (
            "prefill fora dos allowed_values tem que ser descartado, nao gravado "
            "com value_id nulo — e isso que o ML recusa na publicacao"
        )
        assert cond.value_id is None

    @pytest.mark.asyncio
    async def test_prefill_que_casa_resolve_o_id(self):
        from app.services.category_service import CategoryService

        listing = MagicMock()
        listing.id = "lid"
        listing.condition = "new"
        listing.sku_brand = ""
        listing.sku_external_id = None
        listing.sku_model = None
        listing.ml_category_id = "MLB6284"
        listing.package_weight_kg = None
        listing.package_length_cm = None
        listing.package_width_cm = None
        listing.package_height_cm = None

        adicionados = []
        db = AsyncMock()
        db.add = MagicMock(side_effect=adicionados.append)
        db.execute = AsyncMock()

        raw = [{
            "id": "ITEM_CONDITION",
            "name": "Condição do item",
            "value_type": "list",
            "tags": {},
            "values": [{"id": "2230284", "name": "Novo"}, {"id": "2230581", "name": "Usado"}],
        }]

        await CategoryService(db)._save_attributes(listing, raw)

        cond = next(a for a in adicionados if a.attribute_id == "ITEM_CONDITION")
        assert (cond.value_id, cond.value_name) == ("2230284", "Novo")
