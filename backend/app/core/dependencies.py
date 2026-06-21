from typing import AsyncGenerator
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.core.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    from app.models.user import User

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise credentials_exception
        user_id: str = payload.get("sub")
        if not user_id:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(
        select(User).where(User.id == user_id, User.is_active == True)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user


async def get_active_seller(
    x_seller_id: str | None = Header(default=None, alias="X-Seller-ID"),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Resolve e valida a conta ML ativa para o request atual.

    O frontend envia X-Seller-ID com o seller selecionado no seletor de conta.
    Validamos que o user autenticado tem acesso a esse seller antes de prosseguir.
    """
    from app.models.seller import Seller
    from app.models.user_seller_access import UserSellerAccess

    if not x_seller_id:
        # Se não passou o header, retorna o primeiro seller disponível para o usuário
        result = await db.execute(
            select(Seller)
            .join(UserSellerAccess, UserSellerAccess.seller_id == Seller.id)
            .where(UserSellerAccess.user_id == current_user.id, Seller.is_active == True)
            .order_by(UserSellerAccess.granted_at.asc())
            .limit(1)
        )
        seller = result.scalar_one_or_none()
        if not seller:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Nenhuma conta do Mercado Livre conectada. Acesse Configurações para conectar.",
            )
        return seller

    # Valida que o user tem acesso ao seller solicitado
    result = await db.execute(
        select(Seller)
        .join(UserSellerAccess, UserSellerAccess.seller_id == Seller.id)
        .where(
            UserSellerAccess.user_id == current_user.id,
            Seller.id == x_seller_id,
            Seller.is_active == True,
        )
    )
    seller = result.scalar_one_or_none()
    if not seller:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado a esta conta do Mercado Livre.",
        )
    return seller
