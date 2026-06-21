import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.listing import Listing
from app.models.listing_attribute import ListingAttribute
from app.models.seller import Seller
from app.core.security import decrypt_value

_ML_API = "https://api.mercadolibre.com"

# Atributos que o sistema pré-preenche automaticamente
_PREFILL_KEYS = {"BRAND", "ITEM_CONDITION"}


class CategoryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def predict_and_save(self, listing: Listing) -> None:
        result = await self.db.execute(select(Seller).where(Seller.id == listing.seller_id))
        seller = result.scalar_one()
        token = decrypt_value(seller.access_token_enc)

        category_id = await self._predict_category(listing.selected_title, token)
        listing.ml_category_id = category_id

        raw_attrs = await self._get_attributes(category_id, token)
        await self._save_attributes(listing, raw_attrs)

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

    async def _save_attributes(self, listing: Listing, raw_attrs: list[dict]) -> None:
        prefill = {
            "BRAND": listing.sku_brand,
            "ITEM_CONDITION": "Novo" if listing.condition == "new" else "Usado",
        }

        has_unfilled_required = False

        for attr in raw_attrs:
            attr_id: str = attr["id"]
            is_required: bool = bool(attr.get("tags", {}).get("required", False))
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
                source="ai",
                allowed_values=allowed,
            ))

        listing.status = "pending_seller_attributes" if has_unfilled_required else "pending_description"
