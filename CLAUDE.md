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

---

## Estado das fases

| Fase | Status | Descrição |
|---|---|---|
| Fase 0 | ✅ Concluída | Planejamento, SPECs (SPEC-000 a SPEC-009), scaffolding, docker-compose |
| Fase 1 | ✅ Concluída | Auth JWT, ML OAuth, modelos SQLAlchemy, migration inicial, admin criado |
| Fase 2 | ✅ Concluída | Serviço de IA, category service, listing service, endpoints REST, workers Celery reais |
| Fase 3 | ✅ Concluída | Pipeline de imagens: Gemini Imagen 4 → ML CDN (R2 bypassed: ISP bloqueia r2.cloudflarestorage.com) |
| Fase 4 | ✅ Concluída | Geração de descrição (IA) + publicação no ML via API |
| Fase 5 | ✅ Concluída | Frontend Next.js 14: login, kanban board, criar anúncio, seleção de título, atributos, imagens, preview/publicar, settings ML OAuth |
| Fase 6 | 🔲 Futura | Deploy produção (Railway + Vercel) + rotação de credenciais |

---

## Portas locais (Docker)

| Serviço | Porta host | Porta container |
|---|---|---|
| backend (FastAPI) | **8001** | 8000 |
| postgres | 5433 | 5432 |
| redis | 6379 | 6379 |
| pgadmin | 5050 | 80 |

> A porta do backend é 8001 (não 8000) — conflito resolvido na Fase 1.

---

## Comandos essenciais

```bash
# Subir todo o ambiente
docker compose up -d

# Ver logs
docker compose logs -f backend
docker compose logs -f celery_worker

# Aplicar migrations
docker compose exec backend alembic upgrade head

# Criar nova migration
docker compose exec backend alembic revision --autogenerate -m "descricao"

# Rebuild após mudança de código
docker compose build backend celery_worker
docker compose up -d backend celery_worker celery_beat

# Rodar testes
docker compose exec backend pytest -v
```

---

## Variáveis de ambiente

Copie `.env.example` para `.env`. NUNCA commite `.env`.

Chaves relevantes:
- `ML_APP_ID`, `ML_CLIENT_SECRET`, `ML_REDIRECT_URI` — app Mercado Livre
- `SECRET_KEY` — JWT (hex 64 chars)
- `FERNET_KEY` — criptografia de tokens ML (base64 Fernet)
- `POSTGRES_PASSWORD`, `REDIS_PASSWORD`
- `AI_PROVIDER` — `gemini` (padrão) ou `claude`
- `GEMINI_API_KEY`, `GEMINI_MODEL`
- `ANTHROPIC_API_KEY` (se usar Claude como provider)
- `FREEPIK_API_KEY` — necessário para Fase 3
- `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, `R2_PUBLIC_URL` — necessário para Fase 3

---

## Convenções de código

- **API**: REST, sempre versionada em `/api/v1/`
- **Auth**: JWT Bearer em todos os endpoints, exceto `/health` e `/api/v1/auth/ml/callback`
- **Erros**: sempre retornar `{"detail": "mensagem"}` com o status HTTP correto
- **Segurança**: tokens ML criptografados no banco (Fernet); chaves de API nunca em código
- **Branches**: `feature/nome`, `fix/nome`, `chore/nome`
- **Commits**: Conventional Commits — `feat:`, `fix:`, `chore:`, `docs:`, `test:`

---

## Padrões de código estabelecidos

### Services
```python
class XService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
```
Instanciados nos endpoints com `XService(db)`.

### Workers Celery (tasks assíncronas)
```python
@celery_app.task(bind=True, max_retries=3)
def my_task(self, listing_id: str) -> dict:
    try:
        return asyncio.run(_my_task_async(listing_id))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries * 5)

async def _my_task_async(listing_id: str) -> dict:
    from app.database import AsyncSessionLocal  # import aqui, não no topo
    async with AsyncSessionLocal() as db:
        ...
```

### Sessão de banco nos workers
`AsyncSessionLocal` está em `app.database` (não em `app.db.session`).
Nos endpoints, usa-se `Depends(get_db)` de `app.core.dependencies`.

### Lazy loading de relacionamentos
Nunca passar um objeto ORM com relacionamentos lazy direto para `Model.model_validate()` — causa `MissingGreenlet`. Sempre carregar os relacionamentos com queries separadas e passar os objetos já carregados.

### Bcrypt
Usa `bcrypt` diretamente, sem `passlib` (incompatível com bcrypt 4.x).
Ver `app/core/security.py`: `hash_password()` e `verify_password()`.

---

## Arquivos implementados

### backend/app/models/
- `base.py` — Base, TimestampMixin
- `user.py` — User (id, email, hashed_password, seller_id, is_active, is_superuser)
- `seller.py` — Seller (ml_user_id, ml_nickname, access_token_enc, refresh_token_enc, token_expires_at)
- `listing.py` — Listing (todos os campos + status + relacionamentos)
- `listing_title.py` — ListingTitle (title_text, ai_score, selected)
- `listing_attribute.py` — ListingAttribute (attribute_id, value_id, value_name, allowed_values JSONB, is_required, source)
- `listing_image.py` — ListingImage (url_r2, url_ml, position)
- `listing_description.py` — ListingDescription (description_html)
- `listing_job.py` — ListingJob (job_type, celery_task_id, status, payload_in, payload_out, attempts)

### backend/app/services/
- `auth_service.py` — login, refresh token
- `ml_oauth_service.py` — OAuth ML, troca code→token, refresh token ML
- `ai/base.py` — AIProvider (ABC)
- `ai/gemini.py` — GeminiProvider (httpx direto, sem SDK)
- `ai/claude.py` — ClaudeProvider (httpx direto, sem SDK)
- `ai/prompts.py` — `build_title_prompt()`, `build_description_prompt()`
- `ai/service.py` — `get_ai_provider()` factory
- `category_service.py` — CategoryService: prediz categoria ML + salva atributos com allowed_values
- `listing_service.py` — ListingService: CRUD + pipeline (start, retry, select_title, submit_attributes)

### backend/app/api/v1/endpoints/
- `health.py` — GET /health
- `auth.py` — login, refresh, ml/connect, ml/callback, ml/status
- `listings.py` — CRUD + pipeline endpoints

### backend/app/workers/tasks/
- `ai_tasks.py` — `generate_title`, `generate_description` (real, asyncio.run)
- `category_tasks.py` — `predict_category` (real, asyncio.run)
- `image_tasks.py` — stub (Fase 3)
- `publish_tasks.py` — implementado na Fase 4 (real, asyncio.run, MLValidationError sem retry)

### Migrations aplicadas
- `a7519acf4e00` — schema inicial (8 tabelas)
- `08c6a96e1502` — coluna `allowed_values JSONB` em `listing_attributes`

---

## State machine do Listing

```
draft
  └─(pipeline/start)──► generating_title
                           └─(worker OK)──► pending_title_approval
                                              └─(titles/{id}/select)──► predicting_category
                                                                           └─(worker OK)──► pending_seller_attributes
                                                                                              └─(attributes PUT)──► pending_description
                                                                           └─(worker OK, sem atribs required)──► pending_description
                                                                                                                    └─(pipeline/generate_images)──► generating_images
                                                                                                                                                      └─(worker OK)──► pending_image_approval
                                                                                                                                                                          └─(images/approve)──► generating_description
                                                                                                                                                                                                   └─(worker OK)──► ready_to_publish
                                                                                                                                                                                                                      └─(pipeline/publish)──► publishing
                                                                                                                                                                                                                                               └─(worker OK)──► published
Em qualquer estado: falha ──► failed ──(retry)──► generating_title
MLValidationError (400 do ML) ──► failed (sem retry automático)
```

---

## Endpoints implementados

```
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
GET    /api/v1/auth/ml/connect
GET    /api/v1/auth/ml/callback
GET    /api/v1/auth/ml/status

POST   /api/v1/listings                               criar anúncio (status: draft)
GET    /api/v1/listings?status=&page=&page_size=      listar com paginação
GET    /api/v1/listings/{id}                          detalhe (com títulos, atributos, imagens, jobs)
DELETE /api/v1/listings/{id}                          excluir (só draft ou failed)
POST   /api/v1/listings/{id}/pipeline/start           iniciar pipeline (draft → generating_title)
POST   /api/v1/listings/{id}/pipeline/retry           retry após falha
POST   /api/v1/listings/{id}/titles/{tid}/select      selecionar título gerado pela IA
PUT    /api/v1/listings/{id}/attributes               submeter atributos preenchidos pelo vendedor
POST   /api/v1/listings/{id}/pipeline/generate_images gerar imagens (pending_description → generating_images)
POST   /api/v1/listings/{id}/images/approve           aprovar imagens → generating_description (dispara IA)
POST   /api/v1/listings/{id}/pipeline/publish         publicar no ML (ready_to_publish → publishing → published)
```

---

## Fase 3 — Pipeline de Imagens (✅ Implementado)

**Arquivos criados/modificados:**
- `backend/app/services/image_service.py` — GeminiImageService (Imagen 4) + MLPictureService + validate_image
  - **Nota:** R2 removido do pipeline — ISP bloqueia `r2.cloudflarestorage.com`. URL pública r2.dev funciona.
  - Upload de imagens agora vai direto: Gemini Imagen → multipart POST → ML CDN
- `backend/app/workers/tasks/image_tasks.py` — worker `generate_images` (real, asyncio.run)
- `backend/app/services/listing_service.py` — `trigger_image_generation()` + `approve_images()`
- `backend/app/schemas/listing.py` — ImageOut + ImageApproveRequest; ListingDetail inclui `images`
- `backend/app/api/v1/endpoints/listings.py` — endpoints generate_images e approve_images
- `backend/requirements.txt` — Pillow adicionado (boto3 mantido mas não usado no pipeline)

---

## Fase 4 — Geração de Descrição + Publicação ML (✅ Implementado)

**Arquivos criados/modificados:**
- `backend/app/services/publish_service.py` (novo) — PublishService + get_valid_access_token (refresh automático) + MLValidationError
- `backend/app/workers/tasks/publish_tasks.py` — worker `publish_listing` implementado (asyncio.run)
  - MLValidationError (400 do ML) → status=failed, sem retry automático
  - Outros erros → retry exponencial (max 2x)
- `backend/app/services/listing_service.py` — `trigger_publish()` + approve_images agora dispara `generate_description` e usa status `generating_description`
- `backend/app/workers/tasks/ai_tasks.py` — `_generate_description_async` corrigido (carrega atributos, chaves corretas, status generating_description → ready_to_publish)
- `backend/app/schemas/listing.py` — `description_html` adicionado a ListingDetail
- `backend/app/api/v1/endpoints/listings.py` — endpoint `POST /pipeline/publish` + descrição no `_load_detail()`

**Fluxo de publicação ML:**
1. `POST /items` com title, category_id, price, condition, listing_type_id, pictures, attributes
2. `POST /items/{id}/description` com descrição convertida para plain_text (strip HTML)
3. Salva mlb_id + status = published

**Requisitos de dados reais para smartphones (MLB1055):**
- **GTIN**: código de barras EAN-13 da embalagem do produto (obrigatório no ML)
- **Nº Anatel**: número de homologação Anatel da caixa (ex: "10645-23-XXXXX" → 12 dígitos sem hífens). ML valida contra o banco da Anatel.
- Esses dados devem ser informados pelo vendedor durante a etapa `pending_seller_attributes`

**Provedor de imagens:** Gemini Imagen 3 (`imagen-3.0-generate-001`) — usa a mesma `GEMINI_API_KEY` já configurada. FreePik foi descartado.

**Variáveis necessárias no .env:**
- `GEMINI_API_KEY` (já existia — reaproveitada)
- `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, `R2_PUBLIC_URL`

---

## Fase 5 — Frontend Next.js (✅ Implementado)

**Porta:** `http://localhost:3000` — rodar com `npm run dev` dentro de `frontend/`

**Arquivos em `frontend/src/`:**
- `app/(auth)/login/page.tsx` — tela de login (JWT salvo em localStorage)
- `app/(dashboard)/layout.tsx` — layout com sidebar + topbar
- `app/(dashboard)/listings/page.tsx` — kanban board (5 colunas, polling 8s)
- `app/(dashboard)/listings/new/page.tsx` — criar anúncio + iniciar pipeline
- `app/(dashboard)/listings/[id]/page.tsx` — detalhe adaptativo por status
- `app/(dashboard)/listings/[id]/titles/page.tsx` — seleção de título gerado pela IA
- `app/(dashboard)/listings/[id]/attributes/page.tsx` — form dinâmico de atributos ML
- `app/(dashboard)/listings/[id]/images/page.tsx` — galeria de imagens com aprovação
- `app/(dashboard)/listings/[id]/preview/page.tsx` — preview + botão publicar
- `app/(dashboard)/settings/page.tsx` — status OAuth ML + botão conectar
- `lib/api/client.ts` — fetch wrapper com auth (Bearer) e redirect 401
- `lib/api/listings.ts` + `lib/api/auth.ts` — chamadas à API
- `types/listing.ts` — tipos TypeScript completos

**Fluxo do usuário:**
1. Login → `/listings` (kanban)
2. "+ Novo" → `/listings/new` → preenche dados → pipeline começa automaticamente
3. Card em "Aguardando você" → clica → detalhe → botão de ação contextual
4. Cada etapa (títulos / atributos / imagens / preview) tem página dedicada
5. "Confirmar e Publicar" → chama `POST /pipeline/publish` → aguarda status published

**Comandos:**
```bash
cd frontend
npm run dev    # desenvolvimento
npm run build  # checar erros TS antes de deploy
```

---

## SPECs de referência

| SPEC | Assunto |
|---|---|
| specs/SPEC-000-overview.md | Arquitetura geral e módulos |
| specs/SPEC-001-database.md | Schema do banco de dados |
| specs/SPEC-002-api-contract.md | Contrato da API REST |
| specs/SPEC-003-ml-oauth.md | OAuth com Mercado Livre |
| specs/SPEC-004-ai-service.md | Serviço de IA (títulos e descrições) |
| specs/SPEC-005-category-attributes.md | Predição de categoria + atributos ML |
| specs/SPEC-006-image-pipeline.md | Pipeline de imagens FreePik → ML |
| specs/SPEC-007-job-queue.md | Fila de jobs Celery + state machine |
| specs/SPEC-008-frontend.md | Arquitetura do frontend |
| specs/SPEC-009-security.md | Modelo de segurança |
