import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.models.listing import Listing
from app.models.listing_attribute import ListingAttribute
from app.models.seller import Seller

_ML_API = "https://api.mercadolibre.com"

# Atributos que o sistema pré-preenche automaticamente
_PREFILL_KEYS = {"BRAND", "ITEM_CONDITION"}


class CategoryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def predict_and_save(self, listing: Listing, ean: str | None = None) -> None:
        from app.services.publish_service import get_valid_access_token
        result = await self.db.execute(select(Seller).where(Seller.id == listing.seller_id))
        seller = result.scalar_one()
        token = await get_valid_access_token(seller, self.db)

        category_id = await self._predict_category(listing.selected_title, token)
        listing.ml_category_id = category_id

        raw_attrs = await self._get_attributes(category_id, token)
        await self._save_attributes(listing, raw_attrs, ean=ean)

    async def _predict_category(self, title: str, token: str) -> str:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_ML_API}/sites/MLB/domain_discovery/search",
                params={"q": title},
                headers={"Authorization": f"Bearer {token}"},
            )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            raise ValueError(f"Nenhuma categoria ML encontrada para: {title!r}")
        return results[0]["category_id"]

    async def _get_attributes(self, category_id: str, token: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_ML_API}/categories/{category_id}/attributes",
                headers={"Authorization": f"Bearer {token}"},
            )
        resp.raise_for_status()
        return resp.json()

    async def _save_attributes(self, listing: Listing, raw_attrs: list[dict], ean: str | None = None) -> None:
        # Remove atributos de tentativas anteriores — garante idempotência em retries
        await self.db.execute(
            delete(ListingAttribute).where(ListingAttribute.listing_id == listing.id)
        )

        prefill: dict[str, str | None] = {
            "BRAND": listing.sku_brand,
            "ITEM_CONDITION": "Novo" if listing.condition == "new" else "Usado",
        }
        if ean:
            prefill["GTIN"] = ean
        if listing.sku_external_id:
            prefill["SELLER_SKU"] = listing.sku_external_id
        if listing.package_weight_kg is not None:
            from decimal import Decimal as _D
            # Planilha: kg → ML espera gramas; format 'f' evita notação científica (ex: 1.2E+2)
            weight_g = _D(str(listing.package_weight_kg)) * _D("1000")
            prefill["SELLER_PACKAGE_WEIGHT"] = format(weight_g, 'f').rstrip("0").rstrip(".")
        if listing.package_length_cm is not None:
            prefill["SELLER_PACKAGE_LENGTH"] = str(listing.package_length_cm)
        if listing.package_width_cm is not None:
            prefill["SELLER_PACKAGE_WIDTH"] = str(listing.package_width_cm)
        if listing.package_height_cm is not None:
            prefill["SELLER_PACKAGE_HEIGHT"] = str(listing.package_height_cm)

        has_unfilled_required = False

        for attr in raw_attrs:
            attr_id: str = attr["id"]
            tags = attr.get("tags", {})
            is_required: bool = bool(tags.get("required", False) or tags.get("conditional_required", False))
            attr_type: str = attr.get("value_type", "string")
            allowed: list | None = attr.get("values") or None

            value_name: str | None = prefill.get(attr_id)
            value_id: str | None = None

            # Tenta casar value_id na lista de valores permitidos
            if value_name and allowed:
                for v in allowed:
                    if v["name"].lower() == value_name.lower():
                        value_id = v["id"]
                        value_name = v["name"]
                        break

            if not value_name and is_required:
                has_unfilled_required = True

            self.db.add(ListingAttribute(
                listing_id=listing.id,
                attribute_id=attr_id,
                attribute_name=attr["name"],
                attribute_type=attr_type,
                is_required=is_required,
                value_id=value_id,
                value_name=value_name,
                source="seller" if attr_id in prefill and prefill.get(attr_id) else "ai",
                allowed_values=allowed,
            ))

        listing.status = "pending_seller_attributes" if has_unfilled_required else "pending_description"
