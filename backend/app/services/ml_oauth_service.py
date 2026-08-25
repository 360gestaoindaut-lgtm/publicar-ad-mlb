import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, status
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.config import get_settings
from app.core.security import encrypt_value
from app.models.seller import Seller
from app.models.user import User
from app.models.user_seller_access import UserSellerAccess

settings = get_settings()

ML_AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
ML_TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
ML_USER_URL = "https://api.mercadolibre.com/users/me"

# state → user_id: vincula o callback OAuth ao usuário que iniciou o fluxo.
#
# Vive no Redis, não em memória do processo. Em produção a API roda com
# `uvicorn --workers 2`: o GET /ml/connect cai num worker e o callback do
# Mercado Livre volta em OUTRO, que não teria o state no dict local — o fluxo
# falharia com "State inválido" em cerca de metade das tentativas, de forma
# intermitente e sem erro no log. O Redis já está disponível (é o broker do
# Celery) e é compartilhado por todos os workers.
_STATE_PREFIX = "ml_oauth_state:"

# 10 minutos: tempo de sobra para autorizar no ML sem deixar state pendurado.
# O TTL também resolve o vazamento do dict antigo, que nunca limpava state de
# fluxo abandonado.
_STATE_TTL_SECONDS = 600


def _redis_client():
    """Cliente Redis novo por chamada.

    O fluxo OAuth é raro (uma vez por conexão de conta), então o custo de abrir
    conexão é irrelevante perto do risco de um cliente de módulo ficar preso ao
    event loop de um worker específico.
    """
    from redis.asyncio import from_url
    return from_url(settings.redis_url, decode_responses=True)


async def _store_state(state: str, user_id: str) -> None:
    client = _redis_client()
    try:
        await client.setex(f"{_STATE_PREFIX}{state}", _STATE_TTL_SECONDS, user_id)
    finally:
        await client.aclose()


async def _pop_state(state: str) -> str | None:
    """Lê e apaga o state numa operação só.

    GETDEL é atômico: dois callbacks com o mesmo state (replay, ou duplo clique)
    não conseguem os dois resgatar o usuário.
    """
    client = _redis_client()
    try:
        return await client.getdel(f"{_STATE_PREFIX}{state}")
    finally:
        await client.aclose()


class MLOAuthService:

    async def get_authorization_url(self, user_id: str) -> str:
        state = str(uuid.uuid4())
        await _store_state(state, user_id)
        return (
            f"{ML_AUTH_URL}"
            f"?response_type=code"
            f"&client_id={settings.ml_app_id}"
            f"&redirect_uri={settings.ml_redirect_uri}"
            f"&state={state}"
        )

    async def handle_callback(self, code: str, state: str, db: AsyncSession) -> None:
        user_id = await _pop_state(state)
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="State inválido ou expirado",
            )

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
            await db.flush()  # obtém o seller.id antes do commit

        # Concede acesso a todos os admins ativos (ON CONFLICT DO NOTHING evita duplicatas)
        admin_ids_result = await db.execute(
            select(User.id).where(User.role == "admin", User.is_active.is_(True))
        )
        admin_ids = admin_ids_result.scalars().all()
        if admin_ids:
            await db.execute(
                pg_insert(UserSellerAccess)
                .values([{"user_id": uid, "seller_id": seller.id, "role": "admin"} for uid in admin_ids])
                .on_conflict_do_nothing()
            )

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
