# SPEC-008 — Arquitetura do Frontend

**Versão**: 1.0 | **Status**: Aprovado | **Framework**: Next.js 14 (App Router)

---

## Estrutura de pastas

```
frontend/src/
├── app/
│   ├── (auth)/
│   │   └── login/page.tsx
│   ├── (dashboard)/
│   │   ├── layout.tsx               sidebar + topbar
│   │   ├── page.tsx                 → redirect para /listings
│   │   ├── listings/
│   │   │   ├── page.tsx             pipeline board (kanban)
│   │   │   ├── new/page.tsx         criar novo listing
│   │   │   └── [id]/
│   │   │       ├── page.tsx         detalhe + ações por status
│   │   │       ├── titles/page.tsx  selecionar título
│   │   │       ├── attributes/page.tsx  preencher atributos
│   │   │       ├── images/page.tsx  aprovar imagens
│   │   │       └── preview/page.tsx revisar + publicar
│   │   └── settings/
│   │       └── page.tsx             conectar conta ML
│   └── layout.tsx                   root layout (providers)
│
├── components/
│   ├── ui/                          shadcn/ui (gerado, não editar)
│   ├── layout/
│   │   ├── Sidebar.tsx
│   │   ├── Topbar.tsx
│   │   └── PageHeader.tsx
│   ├── listings/
│   │   ├── PipelineBoard.tsx        kanban principal
│   │   ├── ListingCard.tsx          card no kanban
│   │   ├── ListingStatusBadge.tsx
│   │   ├── TitleSelector.tsx        3 opções de título
│   │   ├── AttributeForm.tsx        formulário dinâmico
│   │   ├── ImageGallery.tsx         grade de imagens + aprovação
│   │   └── ListingPreview.tsx       preview final
│   └── common/
│       ├── StatusPoll.tsx           polling de status via SSE
│       └── EmptyState.tsx
│
├── lib/
│   ├── api/
│   │   ├── client.ts                fetch wrapper com auth
│   │   ├── auth.ts                  endpoints de auth
│   │   └── listings.ts              endpoints de listings
│   ├── auth.ts                      next-auth config
│   └── utils.ts
│
└── types/
    ├── listing.ts
    ├── attribute.ts
    └── job.ts
```

---

## Páginas e responsabilidades

### `/login`
- Formulário email + senha
- Chama `POST /api/v1/auth/login`
- Armazena JWT no cookie httpOnly via Next.js Route Handler
- Redirect para `/listings`

---

### `/listings` — Pipeline Board
Estado principal do sistema. Exibe cards em colunas por status.

**Colunas do Kanban:**
| Coluna | Status agrupados |
|---|---|
| Em processamento | generating_title, predicting_category, generating_images, generating_description |
| Aguardando você | pending_title_approval, pending_seller_attributes |
| Pronto para publicar | ready_to_publish |
| Publicado | published |
| Com erro | failed |

Atualização: polling a cada 10 segundos (ou SSE quando implementado).

---

### `/listings/new`
Formulário para criar listing:
- SKU ID (opcional)
- Descrição do produto
- Marca
- Preço
- Quantidade em estoque
- Condição (novo/usado)

Submit → `POST /api/v1/listings` → redirect para `/listings/{id}`

---

### `/listings/[id]` — Detalhe
Página adaptativa: o conteúdo muda conforme o `status` do listing.

| Status | O que mostrar |
|---|---|
| `generating_*` | Spinner + mensagem do que está sendo processado |
| `pending_title_approval` | Botão "Escolher título" → `/listings/{id}/titles` |
| `pending_seller_attributes` | Botão "Preencher atributos" → `/listings/{id}/attributes` |
| `ready_to_publish` | Botão "Revisar e publicar" → `/listings/{id}/preview` |
| `published` | MLB_ID linkado + data |
| `failed` | Mensagem de erro + botão "Tentar novamente" |

Sempre exibir: linha do tempo de jobs (GET /listings/{id}/jobs).

---

### `/listings/[id]/titles`
- Exibe 3 cards com título, score e justificativa
- Seller clica em um → `POST /titles/{tid}/select`
- Redirect automático para `/listings/{id}`

---

### `/listings/[id]/attributes`
Formulário dinâmico gerado pelos dados de `GET /listings/{id}/attributes`.

- Campos required marcados com `*`
- Tipos renderizados conforme SPEC-005
- Validação no frontend (campos required não podem ficar vazios)
- Submit → `PUT /listings/{id}/attributes`

---

### `/listings/[id]/images`
- Grade 2x2 das imagens geradas
- Cada imagem: botão aprovar ✓ / rejeitar ✗
- Drag-and-drop para reordenar (apenas entre aprovadas)
- Mínimo 1 aprovada para prosseguir

---

### `/listings/[id]/preview`
Simulação visual do anúncio:
- Título (grande)
- Imagens em carrossel
- Preço
- Descrição HTML (renderizada)
- Atributos em lista

Botão: "Confirmar e Publicar" → `POST /listings/{id}/publish`

---

### `/settings`
- Status da conexão ML (conectado/desconectado, nickname, validade do token)
- Botão "Conectar conta ML" → chama `GET /auth/ml/connect` → redirect OAuth
- Botão "Desconectar"

---

## Gerenciamento de estado

MVP usa **React Query (TanStack Query)** para:
- Cache de dados do servidor
- Revalidação automática
- Estados de loading/error prontos

Sem Redux ou Zustand no MVP — o estado do servidor é a fonte da verdade.

---

## Autenticação no frontend

- JWT armazenado em **cookie httpOnly** (não localStorage — evita XSS)
- Next.js Route Handler `/api/auth/[...nextauth]` gerencia os cookies
- Middleware Next.js protege todas as rotas `(dashboard)` — redirect para `/login` se não autenticado
- Axios interceptor adiciona `Authorization: Bearer` em todas as chamadas

---

## Tecnologias

| Pacote | Uso |
|---|---|
| `@tanstack/react-query` | Fetch, cache, revalidação |
| `shadcn/ui` | Componentes base (Button, Card, Form, etc.) |
| `react-hook-form` + `zod` | Formulários com validação tipada |
| `@dnd-kit/core` | Drag-and-drop nas imagens |
| `sonner` | Toast notifications |
| `lucide-react` | Ícones |
