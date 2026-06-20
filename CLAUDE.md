# Publicar AD MLB

Sistema web para automação de criação e publicação de anúncios no Mercado Livre.

## Stack

| Camada | Tecnologia |
|---|---|
| Backend API | Python 3.12 + FastAPI + SQLAlchemy 2.0 (async) |
| Workers | Celery 5 + Redis 7 |
| Banco de dados | PostgreSQL 16 |
| Frontend | Next.js 14 (App Router) + TypeScript + Tailwind + shadcn/ui |
| Storage de imagens | Cloudflare R2 |
| Infra local | Docker Compose |
| Infra produção | Railway (backend) + Vercel (frontend) |

## Estrutura de pastas

```
backend/
  app/
    api/v1/        rotas FastAPI
    models/        modelos SQLAlchemy
    schemas/       Pydantic schemas (request/response)
    services/      lógica de negócio
    workers/       tasks Celery
    core/          config, segurança, dependências
  alembic/         migrations
  tests/
frontend/
  src/
    app/           rotas Next.js (App Router)
    components/    componentes React
    lib/           utilitários, clientes de API
    types/         types TypeScript
specs/             documentação de design (SPECs)
docker-compose.yml ambiente de desenvolvimento
```

## Comandos essenciais

```bash
# Subir todo o ambiente
docker compose up -d

# Ver logs de um serviço
docker compose logs -f backend
docker compose logs -f celery_worker

# Aplicar migrations
docker compose exec backend alembic upgrade head

# Criar nova migration
docker compose exec backend alembic revision --autogenerate -m "descricao"

# Rodar testes do backend
docker compose exec backend pytest -v

# Instalar dep nova no backend (dentro do container ou no venv local)
pip install <pacote> && pip freeze > requirements.txt

# Frontend dev (se rodar local, fora do Docker)
cd frontend && npm run dev
```

## Variáveis de ambiente

Copie `.env.example` para `.env` e preencha. NUNCA commite `.env`.
Frontend usa `frontend/.env.local` (copie de `frontend/.env.local.example`).

## Convenções de código

- **Branches**: `feature/nome`, `fix/nome`, `chore/nome`
- **Commits**: Conventional Commits — `feat:`, `fix:`, `chore:`, `docs:`, `test:`
- **API**: REST, sempre versionada em `/api/v1/`
- **Auth**: JWT Bearer em todos os endpoints, exceto `/health` e `/api/v1/auth/ml/callback`
- **Erros**: sempre retornar `{"detail": "mensagem"}` com o status HTTP correto
- **Segurança**: tokens ML criptografados no banco (Fernet); chaves de API nunca em código

## SPECs de referência

| SPEC | Assunto |
|---|---|
| specs/SPEC-000-overview.md | Arquitetura geral e módulos |
| specs/SPEC-001-database.md | Schema do banco de dados |
| specs/SPEC-002-api-contract.md | Contrato da API REST |
| specs/SPEC-003-ml-oauth.md | OAuth PKCE com Mercado Livre |
| specs/SPEC-004-ai-service.md | Serviço de IA (títulos e descrições) |
| specs/SPEC-005-category-attributes.md | Predição de categoria + atributos ML |
| specs/SPEC-006-image-pipeline.md | Pipeline de imagens FreePik → ML |
| specs/SPEC-007-job-queue.md | Fila de jobs Celery + state machine |
| specs/SPEC-008-frontend.md | Arquitetura do frontend |
| specs/SPEC-009-security.md | Modelo de segurança |
