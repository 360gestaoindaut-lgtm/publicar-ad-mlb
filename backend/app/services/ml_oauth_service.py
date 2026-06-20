import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, status
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import get_settings
from app.core.security import encrypt_value
from app.models.seller import Seller

settings = get_settings()

ML_AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
ML_TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
ML_USER_URL = "https://api.mercadolibre.com/users/me"

# Estado anti-CSRF em memória — substituir por Redis na Fase 1 final
_pending_states: dict[str, bool] = {}


class MLOAuthService:

    def get_authorization_url(self) -> str:
        state = str(uuid.uuid4())
        _pending_states[state] = True
        return (
            f"{ML_AUTH_URL}"
            f"?response_type=code"
            f"&client_id={settings.ml_app_id}"
            f"&redirect_uri={settings.ml_redirect_uri}"
            f"&state={state}"
        )

    async def handle_callback(self, code: str, state: str, db: AsyncSession) -> None:
        if state not in _pending_states:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="State inválido ou expirado",
            )
        del _pending_states[state]

        token_data = await self._exchange_code(code)
        user_data = await self._get_ml_user(token_data["access_token"])

        expires_at = datetime.fromtimestamp(
            datetime.now(timezone.utc).timestamp() + token_data["expires_in"],
            tz=timezone.utc,
        )

        result = await db.execute(
            select(Seller).where(Seller.ml_user_id == user_data["id"])
        )
        seller = result.scalar_one_or_none()

        if seller:
            seller.access_token_enc = encrypt_value(token_data["access_token"])
            seller.refresh_token_enc = encrypt_value(token_data["refresh_token"])
            seller.token_expires_at = expires_at
            seller.ml_nickname = user_data["nickname"]
            seller.is_active = True
        else:
            seller = Seller(
                ml_user_id=user_data["id"],
                ml_nickname=user_data["nickname"],
                access_token_enc=encrypt_value(token_data["access_token"]),
                refresh_token_enc=encrypt_value(token_data["refresh_token"]),
                token_expires_at=expires_at,
            )
            db.add(seller)

        await db.commit()

    async def _exchange_code(self, code: str) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                ML_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.ml_app_id,
                    "client_secret": settings.ml_client_secret,
                    "code": code,
                    "redirect_uri": settings.ml_redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15.0,
            )
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Erro ao obter token ML: {response.text}",
            )
        return response.json()

    async def _get_ml_user(self, access_token: str) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                ML_USER_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10.0,
            )
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Erro ao consultar usuário ML",
            )
        return response.json()
