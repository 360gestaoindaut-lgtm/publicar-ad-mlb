# SPEC-000 — Visão Geral e Arquitetura

**Versão**: 1.0 | **Status**: Aprovado | **Autor**: Tech Lead

---

## 1. Objetivo do sistema

Automatizar a criação e publicação de anúncios no Mercado Livre, reduzindo o trabalho
manual do seller a apenas: fornecer o SKU (descrição + marca + preço + estoque + condição)
e preencher os atributos específicos que a IA não consegue inferir.

Todo o resto — título, categoria, imagens, descrição rica, publicação — é feito pelo sistema.

---

## 2. Módulos

| ID | Nome | Responsabilidade |
|---|---|---|
| M01 | Auth | Autenticação de usuários do sistema + OAuth ML |
| M02 | Listing | CRUD e máquina de estados dos anúncios |
| M03 | AI Service | Geração de títulos e descrições (Gemini / Claude) |
| M04 | Category | Predição de categoria ML + gestão de atributos |
| M05 | Image Pipeline | Geração FreePik → R2 → upload ML CDN |
| M06 | Job Queue | Orquestração assíncrona de workers Celery |
| M07 | Notification | Alertas por e-mail ao seller |
| M08 | ERP Connector | Importação de SKUs via CSV (MVP) |

---

## 3. Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND  (Next.js 14)                    │
│                                                                  │
│  /dashboard   /listings/[id]   /listings/[id]/attributes         │
│  /settings/connect-ml          /listings/[id]/preview            │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTPS · REST + SSE
┌──────────────────────────▼──────────────────────────────────────┐
│                      BACKEND  (FastAPI)                          │
│                                                                  │
│  /api/v1/auth         /api/v1/listings    /api/v1/jobs           │
│  /api/v1/attributes   /api/v1/images      /health                │
│                                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │
│  │  Auth    │ │ Listing  │ │   AI     │ │  Image Pipeline  │   │
│  │ Service  │ │ Service  │ │ Service  │ │     Service      │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘   │
│                        │                                         │
│  ┌─────────────────────▼──────────────────────────────────┐     │
│  │                Job Queue  (Celery + Redis)              │     │
│  │                                                        │     │
│  │  [ai]     task_generate_title                          │     │
│  │  [ai]     task_generate_description                    │     │
│  │  [default] task_predict_category                       │     │
│  │  [images] task_generate_images                         │     │
│  │  [images] task_upload_images_to_ml                     │     │
│  │  [publish] task_publish_listing                        │     │
│  └────────────────────────────────────────────────────────┘     │
└────────────┬──────────────┬──────────────┬────────────────────┘
             │              │              │
       ┌─────▼────┐  ┌──────▼────┐  ┌────▼────────────────────┐
       │ PostgreSQL│  │   Redis   │  │ APIs Externas           │
       │   (dados) │  │  (queue)  │  │ • ML API                │
       └──────────┘  └───────────┘  │ • Gemini / Claude API   │
                                    │ • FreePik API            │
                                    │ • Cloudflare R2          │
                                    └─────────────────────────┘
```

---

## 4. Máquina de estados do anúncio

```
DRAFT
  └─▶ GENERATING_TITLE
        └─▶ PENDING_TITLE_APPROVAL       (seller escolhe título)
              └─▶ PREDICTING_CATEGORY
                    └─▶ PENDING_SELLER_ATTRIBUTES   ◀─┐
                          │                            │ (em paralelo)
                          │         GENERATING_IMAGES ─┘
                          │
                          └─▶ GENERATING_DESCRIPTION
                                └─▶ READY_TO_PUBLISH   (seller revisa preview)
                                      └─▶ PUBLISHING
                                            ├─▶ PUBLISHED  (MLB_ID salvo)
                                            └─▶ FAILED     (retry disponível)
```

Qualquer estado pode ir para `FAILED`. Seller pode retentar a partir do dashboard.

---

## 5. Decisões técnicas e justificativas

| Decisão | Escolha | Motivo |
|---|---|---|
| Linguagem backend | Python 3.12 | Ecossistema rico para IA, FastAPI é o mais performático |
| ORM | SQLAlchemy 2.0 async | Suporte a async nativo, melhor para I/O bound |
| Queue | Celery + Redis | Maduro, confiável, fácil de escalar workers |
| Frontend | Next.js 14 App Router | Server Components reduzem JS no cliente |
| Storage imagens | Cloudflare R2 | Sem custo de egress, S3-compatible |
| Criptografia tokens | Fernet (AES-128-CBC + HMAC-SHA256) | Biblioteca padrão Python, tokens revogáveis |
| AI provider | Abstração com adapter | Permite trocar Gemini ↔ Claude sem mudar código |

---

## 6. Requisitos não-funcionais do MVP

| Requisito | Meta |
|---|---|
| Tempo de resposta API (p95) | < 300ms (exceto workers) |
| Jobs de IA | Timeout de 30s, máximo 3 tentativas |
| Tokens ML no banco | Sempre criptografados, nunca em texto plano |
| Secrets | Apenas em variáveis de ambiente, nunca em código |
| Logs | Estruturados (JSON), sem dados sensíveis |
| CORS | Whitelist explícita (não `*`) |

---

## 7. O que está FORA do MVP

- Multi-tenant (múltiplos usuários com contas ML diferentes por tenant)
- Integração automática com ERP (MVP usa CSV ou formulário manual)
- Notificação por WhatsApp
- A/B testing de títulos
- Analytics de performance pós-publicação
- Renovação automática de anúncios
