from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_db, get_current_user
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse
from app.services.auth_service import AuthService
from app.services.ml_oauth_service import MLOAuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    return await AuthService(db).login(request.email, request.password)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshRequest, db: AsyncSession = Depends(get_db)):
    return await AuthService(db).refresh(request.refresh_token)


@router.get("/ml/connect")
async def ml_connect(current_user=Depends(get_current_user)):
    auth_url = MLOAuthService().get_authorization_url(user_id=str(current_user.id))
    return {"auth_url": auth_url}


@router.get("/ml/callback")
async def ml_callback(code: str, state: str, db: AsyncSession = Depends(get_db)):
    await MLOAuthService().handle_callback(code, state, db)
    return RedirectResponse(url="http://localhost:3000/settings?ml_connected=true")
