import uuid as _uuid
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.seller_title_config import SellerTitleConfig
from app.schemas.seller_title_config import SellerTitleConfigCreate, SellerTitleConfigUpdate


class SellerTitleConfigService:
    def __init__(self, db: AsyncSession, seller_id: _uuid.UUID) -> None:
        self.db = db
        self.seller_id = seller_id

    def _base_query(self):
        return select(SellerTitleConfig).where(SellerTitleConfig.seller_id == self.seller_id)

    async def list(self) -> list[SellerTitleConfig]:
        result = await self.db.execute(self._base_query().order_by(SellerTitleConfig.product_group))
        return list(result.scalars().all())

    async def get_or_404(self, config_id: _uuid.UUID) -> SellerTitleConfig:
        result = await self.db.execute(
            self._base_query().where(SellerTitleConfig.id == config_id)
        )
        cfg = result.scalar_one_or_none()
        if not cfg:
            raise HTTPException(404, "Configuração de título não encontrada")
        return cfg

    async def resolve(self, product_group: str | None) -> dict | None:
        """Returns {"structure": str, "rules": str | None} for the best matching config, or None."""
        result = await self.db.execute(self._base_query())
        configs: list[SellerTitleConfig] = list(result.scalars().all())
        if not configs:
            return None
        # Exact group match first
        if product_group:
            for cfg in configs:
                if cfg.product_group == product_group.strip().lower():
                    return {"structure": cfg.title_structure, "rules": cfg.title_rules}
        # Fall back to default
        for cfg in configs:
            if cfg.is_default:
                return {"structure": cfg.title_structure, "rules": cfg.title_rules}
        return None

    async def create(self, payload: SellerTitleConfigCreate) -> SellerTitleConfig:
        if payload.is_default:
            # Clear existing default
            existing = await self.list()
            for cfg in existing:
                if cfg.is_default:
                    cfg.is_default = False
        cfg = SellerTitleConfig(
            seller_id=self.seller_id,
            product_group=payload.product_group,
            title_structure=payload.title_structure,
            title_rules=payload.title_rules,
            is_default=payload.is_default,
        )
        self.db.add(cfg)
        await self.db.commit()
        await self.db.refresh(cfg)
        return cfg

    async def update(self, config_id: _uuid.UUID, payload: SellerTitleConfigUpdate) -> SellerTitleConfig:
        cfg = await self.get_or_404(config_id)
        if payload.is_default is True:
            existing = await self.list()
            for other in existing:
                if other.id != config_id and other.is_default:
                    other.is_default = False
        if payload.title_structure is not None:
            cfg.title_structure = payload.title_structure
        if payload.title_rules is not None:
            cfg.title_rules = payload.title_rules
        if payload.is_default is not None:
            cfg.is_default = payload.is_default
        await self.db.commit()
        await self.db.refresh(cfg)
        return cfg

    async def delete(self, config_id: _uuid.UUID) -> None:
        cfg = await self.get_or_404(config_id)
        self.db.delete(cfg)
        await self.db.commit()
