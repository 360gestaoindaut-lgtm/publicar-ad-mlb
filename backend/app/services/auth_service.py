from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User
from app.core.security import verify_password, create_access_token, create_refresh_token, decode_token
from app.schemas.auth import TokenResponse


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def login(self, email: str, password: str) -> TokenResponse:
        result = await self.db.execute(
            select(User).where(User.email == email, User.is_active == True)
        )
        user = result.scalar_one_or_none()

        if not user or not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email ou senha incorretos",
            )

        return TokenResponse(
            access_token=create_access_token({"sub": str(user.id)}),
            refresh_token=create_refresh_token({"sub": str(user.id)}),
            expires_in=1800,
        )

    async def refresh(self, refresh_token: str) -> TokenResponse:
        invalid = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido ou expirado",
        )
        try:
            payload = decode_token(refresh_token)
            if payload.get("type") != "refresh":
                raise invalid
            user_id: str = payload.get("sub")
            if not user_id:
                raise invalid
        except JWTError:
            raise invalid

        result = await self.db.execute(
            select(User).where(User.id == user_id, User.is_active == True)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise invalid

        return TokenResponse(
            access_token=create_access_token({"sub": str(user.id)}),
            refresh_token=create_refresh_token({"sub": str(user.id)}),
            expires_in=1800,
        )
