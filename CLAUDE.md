# Publicar AD MLB

Sistema web para automação de criação e publicação de anúncios no Mercado Livre.

## Stack

| Camada | Tecnologia |
|---|---|
| Backend API | Python 3.12 + FastAPI + SQLAlchemy 2.0 (async) |
| Workers | Celery 5 + Redis 7 |
| Banco de dados | PostgreSQL 16 |
| Frontend | Next.js 14 (App Router) + TypeScript + Tailwind + shadcn/ui |
| Storage de imagens | Cloudflare R2 (URL pública funciona; API S3 bloqueada pelo ISP) |
| Infra local | Docker Compose |
| Infra produção | Railway (backend) + Vercel (frontend) — ainda não deployado |

---

## Estado das fases

| Fase / Sprint | Status | Descrição |
|---|---|---|
| Fase 0 | ✅ | Planejamento, SPECs (SPEC-000 a SPEC-009), scaffolding, docker-compose |
| Fase 1 | ✅ | Auth JWT, ML OAuth, modelos SQLAlchemy, migration inicial, admin criado |
| Fase 2 | ✅ | Serviço de IA, category service, listing service, endpoints REST, workers Celery reais |
| Fase 3 | ✅ | Pipeline de imagens: Gemini Imagen 4 → ML CDN direto (R2 bypassed: ISP bloqueia r2.cloudflarestorage.com) |
| Fase 4 | ✅ | Geração de descrição (IA) + publicação no ML via API |
| Fase 5 | ✅ | Frontend Next.js 14 completo |
| Sprint 1 | ✅ | Multi-account N:N: tabela `user_seller_access`, header `X-Seller-ID`, seletor de seller na sidebar |
| Sprint 2 | ✅ | Batch import: upload de planilha de anúncios → pipeline automático sem aprovação humana |
| SPEC-010 | ✅ | Catálogo de Produtos: tabela `products`, ProductService multi-tenant, CRUD via UI e planilha |
| SPEC-011 | ✅ | Listing upload refatorado: planilha de anúncios só tem campos de publicação; dados do produto vêm do catálogo |
| Quick fixes F-1..F-4 | ✅ | Resiliência do pipeline de imagens: ensure_dimensions seguro, _mark_failed robusto, ImageRateLimitError + backoff 429 |
| SPEC-012 | ✅ | Resiliência estrutural do pipeline de imagens (token refresh, idempotência, Celery chain, lock otimista) |
| Trilha 2 · Fase 3 | ✅ | Cards de benefício: 3 imagens extras por anúncio (benefícios / modo de uso / especificações) montadas com Pillow sobre foto já gerada, texto por LLM, sem motor de IA de imagem |
| Fase 6 | 🔲 | Deploy produção (Railway + Vercel) + rotação de credenciais |

> **Atenção à numeração:** "Fase 3" aparece duas vezes. A da linha de cima
> (pipeline de imagens) é da trilha original; a **Trilha 2** é a de qualidade
> de imagem, iniciada depois (`qa-imagens-fase1` → `capa-deterministica-fase2`
> → `cards-beneficio-fase3`). Ao falar de "Fase 3", diga de qual trilha.

---

## Portas locais (Docker)

| Serviço | Porta host | Porta container |
|---|---|---|
| backend (FastAPI) | **8001** | 8000 |
| postgres | 5433 | 5432 |
| redis | 6379 | 6379 |
| pgadmin | 5050 | 80 |
| frontend (Next.js) | 3000 | 3000 |

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

# Frontend
cd frontend && npm run dev    # desenvolvimento
cd frontend && npm run build  # checar erros TS
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
- `GEMINI_API_KEY` — usado para Gemini Flash (texto) e Gemini Imagen 4 (imagens)
- `GEMINI_MODEL` — modelo de texto (ex: `gemini-2.0-flash`)
- `ANTHROPIC_API_KEY` (se usar Claude como provider)
- `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, `R2_PUBLIC_URL` — Cloudflare R2 (configurado mas não usado no pipeline de imagens atualmente)

> `FREEPIK_API_KEY` não é mais necessário — FreePik foi descartado; imagens geradas pelo Gemini Imagen 4.

---

## Uso do Subagent-Driven Development (SDD)

Antes de qualquer implementação, Claude deve avaliar a complexidade e **anunciar a decisão** antes de começar, aguardando confirmação do usuário.

### Quando usar SDD
- 5 ou mais tasks independentes
- Múltiplos arquivos com integração entre si (ex: migration + service + endpoint + frontend)
- Risco real de regressão em funcionalidades existentes
- Features estruturais (auth, pipeline, multi-tenant, workers Celery)

### Quando implementar direto (sem SDD)
- Até 4 arquivos modificados
- Spec clara com código já definido
- Baixo risco de regressão
- Bug fixes, ajustes de UI, novos campos simples, endpoints CRUD isolados

### Anúncio obrigatório antes de implementar
Claude deve sempre declarar, antes de começar qualquer implementação:

> "Esta feature é **[simples/complexa]** — vou implementar **[diretamente/via SDD]** porque **[razão em uma linha]**."

Aguardar confirmação do usuário antes de prosseguir.

---

## Convenções de código

- **API**: REST, sempre versionada em `/api/v1/`
- **Auth**: JWT Bearer em todos os endpoints, exceto `/health` e `/api/v1/auth/ml/callback`
- **Multi-tenant**: header `X-Seller-ID` identifica o seller ativo; validado contra `user_seller_access` no middleware
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
    from app.database import worker_session  # import aqui, não no topo
    async with worker_session() as db:
        ...
```

### Batch dispatch atômico (SPEC-012)
Nos gatilhos batch (`category_tasks.py`, `listing_service.submit_attributes`), a transição de status e o dispatch são feitos atomicamente:
```python
from sqlalchemy import update as sa_update
result = await db.execute(
    sa_update(Listing)
    .where(Listing.id == listing_id, Listing.status == "pending_description")
    .values(status="generating_images")
    .execution_options(synchronize_session=False)
)
await db.commit()
if result.rowcount == 1:
    from celery import chain as celery_chain
    from app.workers.tasks.image_tasks import generate_images
    from app.workers.tasks.ai_tasks import generate_description
    from app.workers.tasks.publish_tasks import publish_listing
    celery_chain(
        generate_images.si(listing_id),
        generate_description.si(listing_id),
        publish_listing.si(listing_id),
    ).delay()
```
- `rowcount == 0` → outro worker ganhou a race condition, não despacha nada
- `.si()` (não `.s()`) — tasks não passam resultado para o próximo step
- `execution_options(synchronize_session=False)` obrigatório no async SQLAlchemy

### Idempotência em workers batch
No início de `_generate_images_async`, antes de qualquer processamento:
```python
if listing.status != "generating_images":
    return {"listing_id": listing_id, "skipped": True}
```
Protege contra double-dispatch (retry ou bug de enfileiramento duplo).

### Sessão de banco nos workers
`worker_session()` está em `app.database` — usar como context manager async.
Nos endpoints, usa-se `Depends(get_db)` de `app.core.dependencies`.

### Lazy loading de relacionamentos
Nunca passar um objeto ORM com relacionamentos lazy direto para `Model.model_validate()` — causa `MissingGreenlet`. Sempre carregar os relacionamentos com queries separadas.

### Provider de IA — 4 métodos abstratos
`AIProvider` (`ai/base.py`) declara `generate_titles`, `generate_description`,
`generate_image_prompt` e `generate_card_copy`. **Provider novo tem que
implementar os 4** — faltar um faz a classe estourar `TypeError` na
instanciação. Os prompts ficam centralizados em `ai/prompts.py` como
`build_*_prompt()`; `gemini.py` e `claude.py` compartilham a mesma assinatura
`_call(prompt, max_tokens, temperature)`, e `claude.py` reusa `_extract_json`
de `gemini.py` em vez de duplicar.

### Bcrypt
Usa `bcrypt` diretamente, sem `passlib` (incompatível com bcrypt 4.x).
Ver `app/core/security.py`: `hash_password()` e `verify_password()`.

### Models no Alembic
**Todo model novo deve ser importado em `app/models/__init__.py`** para que o Alembic detecte as tabelas e resolva as FKs. Omitir causa `NoReferencedTableError` na geração de migrations.

---

## Arquitetura de duas planilhas

**TGFPRO (catálogo de produtos):** sku, descricao, marca, modelo, ean, ncm, origemfiscal, icmscst, icmsrate, piscst, cofinscst, pesokg, comprimentocm, larguracm, alturacm, custo
- Upload via `POST /api/v1/products/upload` ou formulário `/products/new` / `/products/{sku}/edit`
- Multi-tenant: `seller_id` em todas as queries via `ProductService._base_query()`

**TGFMLB (anúncios):** sku, preco, estoque, tipo, condicao, seo
- Upload via `POST /api/v1/import` → batch pipeline automático
- Valida existência do produto por `(seller_id, sku)` antes de criar listing
- Denormaliza campos do produto no listing no momento da criação

**Modelos XLSX disponíveis para download:** gerados client-side com ExcelJS (Calibri 11pt, cabeçalho negrito fundo cinza `#E2E8F0`). EAN e NCM pré-formatados como texto (`numFmt: "@"`). Suporta `;` e `,` como separador CSV (auto-detect no backend). Suporta `,` e `.` como decimal.

---

## Arquivos implementados

### backend/app/models/
- `base.py` — Base, TimestampMixin
- `user.py` — User
- `seller.py` — Seller (access_token_enc, refresh_token_enc, token_expires_at)
- `user_seller_access.py` — UserSellerAccess (user_id, seller_id, role) — tabela N:N
- `product.py` — Product (sku, description, brand, **model**, ean, ncm, fiscal, físico, custo)
- `listing.py` — Listing (sku_external_id, sku_description, sku_brand, **sku_model**, price, status, ...)
- `listing_title.py` — ListingTitle
- `listing_attribute.py` — ListingAttribute (allowed_values JSONB, is_required, source)
- `listing_image.py` — ListingImage (ml_picture_id, approved, sort_order)
- `listing_description.py` — ListingDescription
- `listing_job.py` — ListingJob
- `product_image.py` — ProductImage (seller_id, sku, ml_picture_id, is_approved) — índice SKU→imagem
- `batch_import.py` — BatchImport + BatchImportRow

### backend/app/assets/fonts/
- `Inter-Regular.ttf` (peso 400), `Inter-Bold.ttf` (peso 700), `OFL.txt` — fonte do renderizador de cards. Versionadas no repo de propósito: a imagem `python:3.12-slim` **não traz nenhuma TTF** e o Pillow só embarca fonte bitmap, então sem isso `ImageFont.truetype()` não tem o que carregar. Licença SIL OFL, uso comercial livre.

### backend/app/services/
- `auth_service.py` — login, refresh token
- `ml_oauth_service.py` — OAuth ML, troca code→token, refresh token ML
- `ai/base.py`, `ai/gemini.py`, `ai/claude.py`, `ai/prompts.py`, `ai/service.py` — providers de IA
- `category_service.py` — CategoryService: prediz categoria ML + salva atributos; pré-preenche BRAND, MODEL, GTIN, SELLER_SKU, dimensões, peso com unidades corretas
- `listing_service.py` — ListingService: CRUD + pipeline
- `image_service.py` — GeminiImageService (Imagen 4 fast) + MLPictureService + `validate_image()` + `ensure_dimensions()` (upscale para 1024px antes do upload) + `ImageRateLimitError` (HTTP 429 → backoff 60s×2^retries)
- `publish_service.py` — PublishService + `get_valid_access_token()` + MLValidationError
- `product_service.py` — ProductService (multi-tenant via `_base_query()`): list, get, create, update, upsert
- `product_import_service.py` — parser CSV/XLSX de produtos (auto-detect delimitador)
- `batch_import_service.py` — parser CSV/XLSX de anúncios (auto-detect delimitador)
- `image_card_copy_service.py` — copy dos cards via LLM: `CARD_KINDS`, `CardCopy`, `generate_card_copy()`. **Nunca levanta exceção** — devolve `[]` em falha e descarta ângulo inutilizável. Sanitiza sem confiar no LLM: trunca título em 40 e bullets em 50 chars, exige 2–3 bullets, e roda uma **denylist de conteúdo proibido pelo ML** (preço, URL, telefone, frete grátis, superlativo) no texto **cru, antes de truncar** — truncar o preço para fora não pode servir de lavagem
- `image_benefit_card_service.py` — renderizador Pillow: `render_benefit_card()` → JPEG 1200×1200, `CardRenderError`. Foto em contain-fit na faixa y=0..640, bloco de texto centralizado em y=700..1110 com clamp que impede desenho fora do canvas (descarta o último bullet se não couber)

### backend/app/api/v1/endpoints/
- `health.py`, `auth.py`, `listings.py`
- `products.py` — CRUD de produtos + upload de planilha
- `import.py` — batch import de anúncios + histórico

### backend/app/workers/tasks/
- `ai_tasks.py` — `generate_title`, `generate_description`
- `category_tasks.py` — `predict_category` (batch: atomic UPDATE + Celery chain se sem attrs pendentes)
- `image_tasks.py` — `generate_images` (`_fetch_upload_token` para refresh automático de token ML; guard de idempotência; reutiliza imagens via ProductImage; `ensure_dimensions` antes do upload) + `_append_benefit_cards` (3 cards depois das individuais; só para 1 SKU e só se ao menos 1 individual foi salva; nunca levanta — falha vira log e zero cards)
- `publish_tasks.py` — `publish_listing` (MLValidationError → failed sem retry)
- `batch_tasks.py` — `process_batch` (lê planilha, cria listings, dispara pipeline)

### backend/tests/
> **`conftest.py` bloqueia a rede em toda a suíte.** Fixture autouse que faz
> qualquer egresso HTTP real levantar `NetworkAccessAttempted` nomeando a URL.
> O patch é na camada de **transporte** do httpx (`AsyncHTTPTransport.handle_async_request`
> / `HTTPTransport.handle_request`) e no `botocore`, **não** no `AsyncClient` —
> por isso `ASGITransport` (usado em `test_health.py`) e `MockTransport` seguem
> funcionando. Escape hatch: `@pytest.mark.allow_network`. Se um teste novo
> esquecer de mockar o provider de IA, ele falha em alto e bom som em vez de
> gastar chamada paga.

- `test_image_service.py` — `TestEnsureDimensions` (5 casos), `TestGeminiImageService429` (2 casos)
- `test_image_tasks.py` — `TestMarkFailed` (4), `TestGenerateImagesRateLimit` (2), `TestFetchUploadToken` (2), `TestGenerateImagesIdempotency` (2)
- `test_batch_chain.py` — `TestCategoryTaskChainDispatch` (3), `TestSubmitAttributesChainDispatch` (1), `TestRemovedInternalDispatch` (2)
- `test_image_card_copy_service.py` — saneamento da copy, denylist de conteúdo (true positives + **13 casos de falso positivo**: `12V`, `3,5cm`, `500ml`, `12,50 m`, `99,9%`, `5000mAh`…)
- `test_image_benefit_card_service.py` — geometria do card. Os testes de layout aferem a geometria **calculada de forma independente** das constantes, mais um caso pixel-level que garante que nada é desenhado abaixo de y=1112
- `test_image_tasks_i2i.py` — `TestBenefitCardsIntegration`: ordem dos 3 cards, `sort_order` contíguo, falha de 1 card não derruba os outros, nenhum card sem individual salva, kit não gera card

> Suíte completa: **248 passed**. Os 2 warnings (`coroutine '_generate_images_async'
> was never awaited`) são pré-existentes em `test_image_tasks.py`.

### Migrations aplicadas (ordem cronológica)
- `a7519acf4e00` — schema inicial (8 tabelas)
- `08c6a96e1502` — coluna `allowed_values JSONB` em `listing_attributes`
- *(várias)* — multi-account, batch_import, product_images, products
- `d3aa35ba6d71` — `products.model` + `listings.sku_model` + fix índices

---

## State machine do Listing

```
draft
  └─(pipeline/start)──► generating_title
                           └─(worker OK)──► pending_title_approval         [manual]
                                              └─(titles/{id}/select)──► predicting_category
                           └─(batch_mode)──► (auto-seleciona) ──► predicting_category
                                                                     └─(worker OK, attrs preenchidos)──► pending_description
                                                                     └─(worker OK, attrs pendentes)──► pending_seller_attributes
                                                                                                          └─(attributes PUT)──► pending_description
                                                                                                          └─(batch: pausa — SKU aguarda ação manual)
                                                                                       └─(pending_description)──► [manual: pipeline/generate_images]
                                                                                                                    └─(batch: auto)──► generating_images
                                                                                                                                         └─(worker OK)──► pending_image_approval [manual]
                                                                                                                                                             └─(images/approve)──► generating_description
                                                                                                                                         └─(batch: auto-aprova)──► generating_description
                                                                                                                                                                      └─(worker OK)──► ready_to_publish [manual]
                                                                                                                                                                      └─(batch)──► publishing
                                                                                                                                                                                     └─(worker OK)──► published
Em qualquer estado: falha ──► failed ──(retry)──► generating_title
MLValidationError (400 do ML) ──► failed (sem retry automático)
```

---

## Ordem das imagens do anúncio

`sort_order` no caminho image-to-image, 1 SKU:

| # | `kind` | Origem |
|---|---|---|
| 0 | `cover_deterministic` | recorte por distância de cor, sem custo de IA — só quando a foto bruta tem fundo uniforme |
| 1..n | `individual` | edição i2i da foto bruta do seller (2 variantes por foto) |
| n+1 | `card_benefits` | Pillow + copy LLM |
| n+2 | `card_usage` | Pillow + copy LLM |
| n+3 | `card_specs` | Pillow + copy LLM |

Se a capa determinística falhar, tudo desloca uma posição para trás e a 1ª
individual assume o `sort_order` 0. **Cards nunca ocupam a posição 0** — o ML
não aceita texto/infográfico na capa, só da 2ª imagem em diante.

> **Gap conhecido:** cards **não** gravam linha em `ProductImage`, porque a copy
> é derivada do `selected_title` e dos atributos *daquele* anúncio — reusar em
> outro anúncio do mesmo SKU publicaria texto errado. Consequência: um segundo
> anúncio do mesmo SKU que caia no caminho de reuso por `ProductImage` recebe
> as fotos reusadas e **nenhum card**. É o comportamento padrão para SKU
> repetido, não um caso raro. Decisão de produto em aberto.

---

## Endpoints implementados

```
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
GET    /api/v1/auth/ml/connect
GET    /api/v1/auth/ml/callback
GET    /api/v1/auth/ml/status

POST   /api/v1/products                    criar produto (409 se SKU já existe)
PUT    /api/v1/products/{sku}              atualizar produto (todos os campos)
GET    /api/v1/products                    listar com paginação e busca
GET    /api/v1/products/{sku}              detalhe de produto
POST   /api/v1/products/upload             importar planilha de produtos (XLSX/CSV)

POST   /api/v1/import                      importar planilha de anúncios (batch)
GET    /api/v1/import                      listar imports recentes
GET    /api/v1/import/{id}                 detalhe de import com status por linha

POST   /api/v1/listings                    criar anúncio (status: draft)
GET    /api/v1/listings                    listar com paginação/filtro
GET    /api/v1/listings/{id}               detalhe (com títulos, atributos, imagens, jobs)
DELETE /api/v1/listings/{id}               excluir (só draft ou failed)
POST   /api/v1/listings/{id}/pipeline/start
POST   /api/v1/listings/{id}/pipeline/retry
POST   /api/v1/listings/{id}/titles/{tid}/select
PUT    /api/v1/listings/{id}/attributes
POST   /api/v1/listings/{id}/pipeline/generate_images
POST   /api/v1/listings/{id}/images/approve
POST   /api/v1/listings/{id}/pipeline/publish
```

---

## Frontend — páginas implementadas

Rodar com `npm run dev` dentro de `frontend/`. Porta: `http://localhost:3000`

| Rota | Página |
|---|---|
| `/` | Anúncios (kanban, polling 8s, botão Novo anúncio) |
| `/products` | Catálogo de produtos (tabela com zebra striping, expansão fiscal, editar por linha) |
| `/products/new` | Novo produto (formulário: identificação / fiscal / embalagem) |
| `/products/[sku]/edit` | Editar produto (mesmo formulário, SKU readonly, staleTime: 0) |
| `/products/upload` | Importar planilha de produtos (+ botão Baixar modelo) |
| `/import` | Importar anúncios batch (+ botão Baixar modelo, histórico de imports) |
| `/listings/new` | Novo anúncio manual |
| `/listings/[id]` | Detalhe adaptativo por status |
| `/listings/[id]/titles` | Seleção de título gerado pela IA |
| `/listings/[id]/attributes` | Form dinâmico de atributos ML |
| `/listings/[id]/images` | Galeria de imagens com aprovação |
| `/listings/[id]/preview` | Preview + botão publicar |
| `/settings` | OAuth ML + lista de contas conectadas |

**UX:**
- Topbar removida; título em cada página; seletor de seller no rodapé da sidebar
- Transição suave entre páginas: `key={pathname}` com `animate-in fade-in duration-200`
- Títulos em PT-BR sentence case

**Arquivos frontend críticos:**
- `src/components/layout/Sidebar.tsx` — sidebar com SellerSelector embutido
- `src/components/products/ProductForm.tsx` — formulário compartilhado criar/editar produto
- `src/lib/api/client.ts` — fetch wrapper (Bearer, redirect 401)
- `src/lib/api/products.ts`, `listings.ts`, `auth.ts`, `sellers.ts`, `import.ts`
- `src/lib/download-template.ts` — ExcelJS: `downloadProductTemplate()`, `downloadListingTemplate()`
- `src/lib/utils.ts` — `formatPrice()`, `formatQuantity()` (usam `Number()` antes de `toLocaleString`)
- `src/types/product.ts`, `types/listing.ts`

> **Atenção:** `frontend/src/lib/` é capturado pelo padrão `lib/` no `.gitignore` (artefato Python). Novos arquivos neste diretório precisam de `git add -f`.

---

## Atributos ML pré-preenchidos automaticamente

O `category_service.py` pré-preenche estes atributos a partir dos dados do produto/listing:

| Atributo ML | Fonte | Regra |
|---|---|---|
| `ITEM_CONDITION` | `listing.condition` | "new" → "Novo", "used" → "Usado" |
| `BRAND` | `listing.sku_brand` | Skip se vazio ou "Sem marca" (case-insensitive) |
| `MODEL` | `listing.sku_model` | Skip se vazio; vem de `product.model` |
| `GTIN` | EAN do produto | Só preenche se numérico e len in (8, 12, 13, 14) |
| `SELLER_SKU` | `listing.sku_external_id` | — |
| `SELLER_PACKAGE_WEIGHT` | `package_weight_kg × 1000` | Formato: `"120 g"` (com unidade) |
| `SELLER_PACKAGE_LENGTH/WIDTH/HEIGHT` | dimensões em cm | Formato: `"16 cm"` (com unidade) |

---

## Erros ML resolvidos (commit ecf8978, 2026-06-22)

| Erro ML | Causa | Fix |
|---|---|---|
| GTIN com formato inválido | EAN "NA" ou não-numérico passava `if ean:` | `.isdigit()` + length check |
| Dimensão omitida (unidade inválida) | Enviava `"16"` sem unidade | f-string `f"{val} cm"` |
| Peso omitido (unidade inválida) | Enviava `"120"` sem unidade | `format(val,'f') + " g"` |
| Marca obrigatória não adicionada | "Sem marca" enviado ao ML | Skip se empty ou == "sem marca" |
| Modelo obrigatório não adicionado | Campo inexistente no sistema | Campo `model` adicionado ao catálogo |
| Fotos com menos de 500 pixels | Gemini Imagen fast pode gerar < 500px | `ensure_dimensions()` upscale para 1024px |

---

## Requisitos para smartphones (categoria MLB1055)

Atributos obrigatórios que o ML valida contra bases externas:
- **GTIN**: EAN-13 numérico da embalagem
- **Nº Anatel**: número de homologação (12 dígitos sem hífens) — validado contra banco Anatel
- **MODEL**: modelo do produto (ex: "Galaxy A54 128GB") — agora vem de `product.model`
- **BRAND**: marca real (não placeholder)

Esses dados devem estar no catálogo de produtos antes do pipeline de batch.

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
| specs/SPEC-006-image-pipeline.md | Pipeline de imagens |
| specs/SPEC-007-job-queue.md | Fila de jobs Celery + state machine |
| specs/SPEC-008-frontend.md | Arquitetura do frontend |
| specs/SPEC-009-security.md | Modelo de segurança |
