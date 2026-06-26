import pytest
from app.services.product_import_service import (
    normalize_product_row,
    _build_header_map,
)


class TestNormalizeProductRow:
    def test_new_structured_fields_passthrough(self):
        """Test that new SPEC-013 structured fields pass through correctly."""
        raw = {
            "sku": "SKU001",
            "descricao": "Produto A",
            "marca": "MarcaX",
            "product_group": "Eletrônicos",
            "technical_reference": "REF-001",
            "vehicle_application": "Honda Civic 2020",
            "color": "Preto",
            "size": "M",
            "capacity": "500ml",
            "material": "Plástico",
            "gender": "Unissex",
        }
        result = normalize_product_row(raw)
        assert result["product_group"] == "Eletrônicos"
        assert result["technical_reference"] == "REF-001"
        assert result["vehicle_application"] == "Honda Civic 2020"
        assert result["color"] == "Preto"
        assert result["size"] == "M"
        assert result["capacity"] == "500ml"
        assert result["material"] == "Plástico"
        assert result["gender"] == "Unissex"

    def test_empty_string_structured_fields_become_none(self):
        """Test that empty strings in structured fields become None."""
        raw = {
            "sku": "SKU002",
            "descricao": "Produto B",
            "marca": "MarcaY",
            "product_group": "",
            "technical_reference": "",
            "color": "",
        }
        result = normalize_product_row(raw)
        assert result["product_group"] is None
        assert result["technical_reference"] is None
        assert result["color"] is None

    def test_build_header_map_recognizes_new_column_headers(self):
        """Test that _build_header_map correctly normalizes new SPEC-013 headers."""
        headers = [
            "sku", "descricao", "marca",
            "grupo_produto", "referencia_tecnica", "aplicacao_veiculo",
            "cor", "tamanho", "capacidade", "material", "genero",
        ]
        header_map = _build_header_map(headers)

        # Verify that headers were recognized and mapped to normalized field names
        # The header map is {column_index: field_name}
        # We expect to find the new fields in the values
        mapped_values = set(header_map.values())
        assert "product_group" in mapped_values
        assert "technical_reference" in mapped_values
        assert "vehicle_application" in mapped_values
        assert "color" in mapped_values
        assert "size" in mapped_values
        assert "capacity" in mapped_values
        assert "material" in mapped_values
        assert "gender" in mapped_values

    def test_normalize_only_returns_present_fields(self):
        """Test that normalize_product_row only returns fields that were in raw dict."""
        raw = {
            "sku": "SKU003",
            "descricao": "Produto C",
            "product_group": "Acessórios",
        }
        result = normalize_product_row(raw)

        # Present fields
        assert "sku" in result
        assert "description" in result
        assert "product_group" in result

        # Not present in raw, so should not be in result
        assert "technical_reference" not in result
        assert "color" not in result
        assert "material" not in result
