"""
Script para criar o primeiro usuário administrador do sistema.

Como usar (dentro do container ou com venv local):
    python scripts/create_first_user.py

Ou via Docker:
    docker compose exec backend python scripts/create_first_user.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.config import get_settings
from app.core.security import hash_password
from app.models.seller import Seller
from app.models.user import User
from datetime import datetime, timezone

settings = get_settings()

engine = create_async_engine(settings.database_url)
Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def main() -> None:
    print("=== Criação do primeiro usuário ===")
    full_name = input("Nome completo: ").strip()
    email = input("Email: ").strip()
    password = input("Senha (mínimo 8 caracteres): ").strip()

    if len(password) < 8:
        print("Senha muito curta. Abortando.")
        sys.exit(1)

    async with Session() as db:
        # Cria um seller placeholder para o primeiro usuário
        # (será substituído quando conectar a conta ML real)
        seller = Seller(
            ml_user_id=0,
            ml_nickname="pending_ml_connect",
            access_token_enc="pending",
            refresh_token_enc="pending",
            token_expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
            is_active=False,
        )
        db.add(seller)
        await db.flush()

        user = User(
            seller_id=seller.id,
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            role="admin",
        )
        db.add(user)
        await db.commit()

    print(f"\nUsuário '{full_name}' ({email}) criado com sucesso.")
    print("Agora conecte a conta ML em Settings > Conectar Mercado Livre.")


if __name__ == "__main__":
    asyncio.run(main())
