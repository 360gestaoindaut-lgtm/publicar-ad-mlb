import asyncio
import re
import logging
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import decrypt_value, encrypt_value

logger = logging.getLogger(__name__)

ML_ITEMS_URL = "https://api.mercadolibre.com/items"
ML_TOKEN_URL = "https://api.mercadolibre.com/oauth/token"


class MLValidationError(Exception):
    """Erro de validação retornado pela API do ML (HTTP 400). Não deve ser retentado."""


async def get_valid_access_token(seller, db) -> str:
    now = datetime.now(timezone.utc)
    expires_at = seller.token_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at > now:
        return decrypt_value(seller.access_token_enc)

    settings = get_settings()
    refresh_token = decrypt_value(seller.refresh_token_enc)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            ML_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": settings.ml_app_id,
                "client_secret": settings.ml_client_secret,
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Falha ao renovar token ML: {resp.text[:300]}")

    data = resp.json()
    from datetime import timedelta
    seller.access_token_enc = encrypt_value(data["access_token"])
    seller.refresh_token_enc = encrypt_value(data["refresh_token"])
    seller.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=data["expires_in"])
    await db.commit()
    return data["access_token"]


class PublishService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def activate_listing(self, listing, seller) -> None:
        token = await get_valid_access_token(seller, self.db)
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"https://api.mercadolibre.com/items/{listing.mlb_id}",
                json={"status": "active"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=15.0,
            )
        if response.status_code not in (200, 204):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Erro ao ativar anúncio no ML: {response.text}",
            )
        listing.status = "published"
        await self.db.commit()

    async def publish(
        self,
        listing,
        attributes: list,
        images: list,
        description_html: str | None,
        access_token: str,
    ) -> str:
        attrs_payload = [
            {"id": a.attribute_id, "value_id": a.value_id, "value_name": a.value_name}
            if a.value_id
            else {"id": a.attribute_id, "value_name": a.value_name}
            for a in attributes
            if a.value_name
        ]

        pics_payload = [
            {"id": img.ml_picture_id}
            for img in sorted(images, key=lambda x: x.sort_order)
            if img.approved and img.ml_picture_id
        ]
        if not pics_payload:
            raise RuntimeError("Nenhuma imagem aprovada encontrada para publicação")

        body = {
            "title": listing.selected_title,
            "category_id": listing.ml_category_id,
            "price": float(listing.price),
            "currency_id": "BRL",
            "available_quantity": listing.stock_quantity,
            "buying_mode": "buy_it_now",
            "condition": listing.condition,
            "listing_type_id": listing.listing_type_id,
            "pictures": pics_payload,
            "attributes": attrs_payload,
            "status": "paused",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                ML_ITEMS_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                json=body,
            )

        if resp.status_code == 400:
            error_text = resp.text[:1200]
            try:
                err_data = resp.json()
                causes = err_data.get("cause", [])
                msgs = [c["message"] for c in causes if c.get("message")]
                if msgs:
                    error_text = "ML rejeitou o anúncio: " + " | ".join(msgs)
            except Exception:
                pass
            raise MLValidationError(error_text)
        if resp.status_code >= 400:
            raise RuntimeError(f"ML criar item {resp.status_code}: {resp.text[:600]}")

        item_data = resp.json()
        item_id = item_data["id"]

        await self._ensure_paused(item_id, item_data, access_token)

        if description_html:
            await self._post_description(item_id, description_html, access_token)

        return item_id

    async def _ensure_paused(self, item_id: str, item_data: dict, access_token: str) -> None:
        """O ML reativa o item sozinho ao concluir a validação assíncrona das fotos
        (sub_status picture_download_pending), ignorando o status enviado na criação.
        Aguarda a validação terminar e força status=paused de novo no final."""
        status_value = item_data.get("status")
        sub_status = item_data.get("sub_status") or []

        for _ in range(5):
            if "picture_download_pending" not in sub_status:
                break
            await asyncio.sleep(2)
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{ML_ITEMS_URL}/{item_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            if resp.status_code != 200:
                logger.warning("Falha ao checar status do item %s: %s", item_id, resp.text[:200])
                break
            item_data = resp.json()
            status_value = item_data.get("status")
            sub_status = item_data.get("sub_status") or []

        if status_value != "paused":
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.put(
                    f"{ML_ITEMS_URL}/{item_id}",
                    json={"status": "paused"},
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            if resp.status_code >= 400:
                logger.warning("Falha ao forçar pausa do item %s: %s", item_id, resp.text[:300])

    async def _post_description(self, item_id: str, html: str, access_token: str) -> None:
        plain = re.sub(r"<[^>]+>", " ", html)
        plain = re.sub(r" {2,}", " ", plain).strip()

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{ML_ITEMS_URL}/{item_id}/description",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"plain_text": plain},
            )
        if resp.status_code >= 400:
            logger.warning("Falha ao postar descrição para %s: %s", item_id, resp.text[:200])
