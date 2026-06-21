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
from app.models.user import User

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
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            role="admin",
        )
        db.add(user)
        await db.commit()

    print(f"\nUsuário '{full_name}' ({email}) criado com sucesso.")
    print("Faça login e acesse Configurações > Conectar Mercado Livre para adicionar contas ML.")


if __name__ == "__main__":
    asyncio.run(main())
