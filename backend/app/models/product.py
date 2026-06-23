from decimal import Decimal
from typing import Optional
from uuid import uuid4
from sqlalchemy import ForeignKey, Integer, Numeric, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    seller_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sellers.id"), nullable=False, index=True
    )
    sku: Mapped[str] = mapped_column(String(100), nullable=False)

    # Identificação
    description: Mapped[str] = mapped_column(Text, nullable=False)
    brand: Mapped[Optional[str]] = mapped_column(String(200))
    model: Mapped[Optional[str]] = mapped_column(String(200))
    ean: Mapped[Optional[str]] = mapped_column(String(20))
    ncm: Mapped[Optional[str]] = mapped_column(String(10))

    # Fiscal
    fiscal_origin: Mapped[Optional[int]] = mapped_column(SmallInteger)
    icms_cst: Mapped[Optional[str]] = mapped_column(String(4))
    icms_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    pis_cst: Mapped[Optional[str]] = mapped_column(String(4))
    cofins_cst: Mapped[Optional[str]] = mapped_column(String(4))

    # Físico (embalagem)
    weight_kg: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 3))
    length_cm: Mapped[Optional[int]] = mapped_column(Integer)
    width_cm: Mapped[Optional[int]] = mapped_column(Integer)
    height_cm: Mapped[Optional[int]] = mapped_column(Integer)

    # Custo
    acquisition_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))

    seller: Mapped["Seller"] = relationship("Seller", back_populates="products")
    listings: Mapped[list["Listing"]] = relationship("Listing", back_populates="product")

    __table_args__ = (
        UniqueConstraint("seller_id", "sku", name="uq_products_seller_sku"),
    )
