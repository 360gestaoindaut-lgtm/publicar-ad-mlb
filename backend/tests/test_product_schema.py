from app.schemas.product import ProductCreate, ProductOut
from decimal import Decimal
import uuid


def test_product_create_new_fields_optional():
    p = ProductCreate(sku="SKU-001", description="Rolamento 6203 DDU C3 NSK")
    assert p.product_group is None
    assert p.technical_reference is None


def test_product_create_new_fields_accepted():
    p = ProductCreate(
        sku="SKU-001",
        description="Rolamento 6203 DDU C3 NSK",
        product_group="rolamentos",
        technical_reference="6203 DDU C3",
        vehicle_application="Honda CG 125",
        color=None,
    )
    assert p.product_group == "rolamentos"
    assert p.technical_reference == "6203 DDU C3"


def test_product_group_stripped():
    p = ProductCreate(sku="S", description="D", product_group="  rolamentos  ")
    assert p.product_group == "rolamentos"


def test_product_group_empty_string_becomes_none():
    p = ProductCreate(sku="S", description="D", product_group="   ")
    assert p.product_group is None


def test_product_update_exclude_unset():
    """Test that ProductUpdate.model_dump(exclude_unset=True) only includes set fields."""
    from app.schemas.product import ProductUpdate

    # Create ProductUpdate with only technical_reference set
    p = ProductUpdate(technical_reference="REF-001")
    dumped = p.model_dump(exclude_unset=True)

    # technical_reference should be present
    assert "technical_reference" in dumped
    assert dumped["technical_reference"] == "REF-001"

    # Other unset fields should NOT be present
    assert "description" not in dumped
    assert "brand" not in dumped
    assert "model" not in dumped
    assert "ean" not in dumped
    assert "color" not in dumped
    assert "material" not in dumped
