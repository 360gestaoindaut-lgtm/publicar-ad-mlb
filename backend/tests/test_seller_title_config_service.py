import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.seller_title_config_service import SellerTitleConfigService
from app.models.seller_title_config import SellerTitleConfig


def make_config(product_group: str, structure: str, is_default: bool = False, rules: str | None = None):
    c = MagicMock(spec=SellerTitleConfig)
    c.id = uuid.uuid4()
    c.product_group = product_group
    c.title_structure = structure
    c.title_rules = rules
    c.is_default = is_default
    return c


@pytest.mark.asyncio
async def test_resolve_returns_matching_group():
    db = AsyncMock()
    seller_id = uuid.uuid4()
    configs = [
        make_config("rolamentos", "{referencia_tecnica} {marca}", is_default=False),
        make_config("geral", "{descricao_erp} {marca}", is_default=True),
    ]
    db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=configs)))))

    svc = SellerTitleConfigService(db, seller_id)
    result = await svc.resolve("rolamentos")

    assert result is not None
    assert result["structure"] == "{referencia_tecnica} {marca}"


@pytest.mark.asyncio
async def test_resolve_falls_back_to_default():
    db = AsyncMock()
    seller_id = uuid.uuid4()
    configs = [
        make_config("geral", "{descricao_erp} {marca}", is_default=True),
    ]
    db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=configs)))))

    svc = SellerTitleConfigService(db, seller_id)
    result = await svc.resolve("rolamentos")

    assert result is not None
    assert result["structure"] == "{descricao_erp} {marca}"


@pytest.mark.asyncio
async def test_resolve_returns_none_when_no_configs():
    db = AsyncMock()
    seller_id = uuid.uuid4()
    db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))

    svc = SellerTitleConfigService(db, seller_id)
    result = await svc.resolve("rolamentos")

    assert result is None


@pytest.mark.asyncio
async def test_resolve_returns_none_when_no_match_and_no_default():
    db = AsyncMock()
    seller_id = uuid.uuid4()
    configs = [
        make_config("pastilhas", "{descricao_erp} {marca}", is_default=False),
    ]
    db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=configs)))))

    svc = SellerTitleConfigService(db, seller_id)
    result = await svc.resolve("rolamentos")

    assert result is None
