from uuid import UUID
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from app.models.product import Product
from app.schemas.product import ProductOut, ProductPage, ProductCreate, ProductUpdate


class ProductService:
    def __init__(self, db: AsyncSession, seller_id: UUID) -> None:
        self.db = db
        self.seller_id = seller_id  # sempre do JWT — nunca do request body

    def _base_query(self):
        """Toda query de produto inclui seller_id — isolamento multi-tenant garantido."""
        return select(Product).where(Product.seller_id == self.seller_id)

    async def get_or_404(self, sku: str) -> Product:
        result = await self.db.execute(
            self._base_query().where(Product.sku == sku)
        )
        product = result.scalar_one_or_none()
        if not product:
            raise HTTPException(404, f"Produto '{sku}' não encontrado")
        return product

    async def get_by_sku(self, sku: str) -> Product | None:
        result = await self.db.execute(
            self._base_query().where(Product.sku == sku)
        )
        return result.scalar_one_or_none()

    async def list_products(
        self,
        search: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> ProductPage:
        query = self._base_query()
        if search:
            term = f"%{search}%"
            query = query.where(
                or_(
                    Product.sku.ilike(term),
                    Product.description.ilike(term),
                    Product.brand.ilike(term),
                    Product.ean.ilike(term),
                )
            )

        count_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_q)).scalar_one()

        query = query.order_by(Product.sku.asc()).offset((page - 1) * page_size).limit(page_size)
        items = (await self.db.execute(query)).scalars().all()

        return ProductPage(
            items=[ProductOut.model_validate(p) for p in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def create(self, data: ProductCreate) -> Product:
        existing = await self.get_by_sku(data.sku)
        if existing:
            raise HTTPException(409, f"Produto com SKU '{data.sku}' já existe. Use a edição para atualizar.")
        product = Product(seller_id=self.seller_id, **data.model_dump())
        self.db.add(product)
        await self.db.commit()
        await self.db.refresh(product)
        return product

    async def update(self, sku: str, data: ProductUpdate) -> Product:
        product = await self.get_or_404(sku)
        for key, value in data.model_dump(exclude_unset=False).items():
            setattr(product, key, value)
        await self.db.commit()
        await self.db.refresh(product)
        return product

    async def upsert(self, data: dict) -> tuple[Product, bool]:
        """Cria ou atualiza produto por SKU. Retorna (product, created)."""
        product = await self.get_by_sku(data["sku"])
        if product:
            for key, value in data.items():
                if key != "sku" and value is not None:
                    setattr(product, key, value)
            await self.db.commit()
            await self.db.refresh(product)
            return product, False

        product = Product(seller_id=self.seller_id, **data)
        self.db.add(product)
        await self.db.commit()
        await self.db.refresh(product)
        return product, True
