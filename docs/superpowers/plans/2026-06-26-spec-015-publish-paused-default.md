# SPEC-015: Publicação pausada por padrão

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Alterar o pipeline para que anúncios sejam publicados no ML com status `paused` por padrão, exigindo ativação manual pelo usuário.

**Architecture:** Mudança no payload do `POST /items` para incluir `"status": "paused"`. Novo status interno `published_paused` no state machine. Novo endpoint e método de serviço para ativar o anúncio via `PUT /items/{mlb_id}`. Botão "Ativar" no `ListingCard` quando status `published_paused`.

**Tech Stack:** Python/FastAPI, SQLAlchemy async, Next.js 14, TypeScript, Mercado Livre API

## Global Constraints

- `status` é coluna `VARCHAR` — nenhuma migration necessária
- ML API: `POST /items` aceita `"status": "paused"` no payload
- ML API: ativar anúncio = `PUT https://api.mercadolibre.com/items/{mlb_id}` com `{"status": "active"}`
- Token ML deve ser obtido via `get_valid_access_token(seller, db)` (já existe em `publish_service.py`)
- Padrão atual `published` permanece como estado final após ativação manual
- Conventional Commits: `feat:`, `fix:`, etc.

---

### Task 1: Backend — publicar como pausado + novo status

**Files:**
- Modify: `backend/app/services/publish_service.py`
- Modify: `backend/app/workers/tasks/publish_tasks.py`

**Interfaces:**
- Produz: status `published_paused` no listing após publicação bem-sucedida
- `publish_service.py` já tem `PublishService.publish_listing(listing, seller, db)` e `get_valid_access_token()`

- [ ] **Step 1: Em `publish_service.py`, adicionar `"status": "paused"` no payload do POST /items**

Localizar o dict de payload enviado ao ML (algo como `payload = { "title": ..., "category_id": ..., ... }`).
Adicionar a chave:

```python
"status": "paused",
```

- [ ] **Step 2: Em `publish_tasks.py`, alterar o status final de `published` para `published_paused`**

Localizar a linha que seta `listing.status = "published"` após publicação bem-sucedida e alterar para:

```python
listing.status = "published_paused"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/publish_service.py backend/app/workers/tasks/publish_tasks.py
git commit -m "feat: publicar anúncios ML como pausado por padrão (published_paused)"
```

---

### Task 2: Backend — endpoint de ativação

**Files:**
- Modify: `backend/app/services/publish_service.py`
- Modify: `backend/app/api/v1/endpoints/listings.py`

**Interfaces:**
- Consome: `listing.mlb_id`, `listing.status == "published_paused"`
- Produz: `POST /api/v1/listings/{id}/activate` → 200 `{"status": "published"}`

- [ ] **Step 1: Adicionar método `activate_listing` em `PublishService`**

```python
async def activate_listing(self, listing: Listing, seller: Seller) -> None:
    token = await get_valid_access_token(seller, self.db)
    async with httpx.AsyncClient() as client:
        response = await client.put(
            f"https://api.mercadolibre.com/items/{listing.mlb_id}",
            json={"status": "active"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15.0,
        )
    if response.status_code not in (200, 204):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Erro ao ativar anúncio no ML: {response.text}",
        )
    listing.status = "published"
    await self.db.commit()
```

- [ ] **Step 2: Adicionar endpoint em `listings.py`**

```python
@router.post("/{listing_id}/activate")
async def activate_listing(
    listing_id: UUID,
    active_seller=Depends(get_active_seller),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Listing).where(
            Listing.id == listing_id,
            Listing.seller_id == active_seller.id,
        )
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Anúncio não encontrado")
    if listing.status != "published_paused":
        raise HTTPException(status_code=422, detail="Anúncio não está pausado")

    seller_result = await db.execute(select(Seller).where(Seller.id == active_seller.id))
    seller = seller_result.scalar_one()

    await PublishService(db).activate_listing(listing, seller)
    return {"status": "published"}
```

Verificar imports necessários no topo do arquivo (`Seller`, `PublishService`).

- [ ] **Step 3: Verificar no OpenAPI que o endpoint aparece**

```bash
curl -s http://localhost:8001/openapi.json | python -m json.tool | grep "activate"
```

Esperado: aparece `/api/v1/listings/{listing_id}/activate`

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/publish_service.py backend/app/api/v1/endpoints/listings.py
git commit -m "feat: endpoint POST /listings/{id}/activate para ativar anúncio pausado"
```

---

### Task 3: Frontend — tipos, API client e ListingCard

**Files:**
- Modify: `frontend/src/types/listing.ts`
- Modify: `frontend/src/lib/api/listings.ts`
- Modify: `frontend/src/components/listings/PipelineBoard.tsx`
- Modify: `frontend/src/components/listings/ListingCard.tsx`

**Interfaces:**
- Consome: `activateListing(id: string): Promise<{status: string}>` (a criar)
- `ListingStatus` deve incluir `"published_paused"`
- `PipelineBoard` coluna "Publicados" deve incluir `published_paused` nos `statuses`

- [ ] **Step 1: Adicionar `"published_paused"` ao tipo `ListingStatus` em `types/listing.ts`**

Localizar o union type `ListingStatus` e adicionar `"published_paused"`.

- [ ] **Step 2: Adicionar função `activateListing` em `lib/api/listings.ts`**

```typescript
export async function activateListing(id: string): Promise<{ status: string }> {
  return apiFetch(`/listings/${id}/activate`, { method: "POST" })
}
```

- [ ] **Step 3: Em `PipelineBoard.tsx`, incluir `"published_paused"` na coluna "Publicados"**

Localizar o objeto da coluna com `id: "publicados"` e adicionar `"published_paused"` ao array `statuses`:

```typescript
statuses: ["published", "published_paused"],
```

- [ ] **Step 4: Em `ListingCard.tsx`, adicionar botão "Ativar anúncio" para status `published_paused`**

Após o bloco de título/status existente, adicionar:

```tsx
{listing.status === "published_paused" && (
  <button
    onClick={async (e) => {
      e.stopPropagation()
      await activateListing(listing.id)
      // O polling de 8s atualiza o card automaticamente
    }}
    className="mt-2 w-full text-xs font-medium bg-green-600 hover:bg-green-700 text-white rounded px-2 py-1"
  >
    Ativar anúncio
  </button>
)}
```

Importar `activateListing` de `@/lib/api/listings`.

- [ ] **Step 5: Verificar no browser que card `published_paused` exibe o botão e que ao clicar o status muda para `published` após o próximo polling (8s)**

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/listing.ts frontend/src/lib/api/listings.ts frontend/src/components/listings/PipelineBoard.tsx frontend/src/components/listings/ListingCard.tsx
git commit -m "feat: UI para ativar anúncio pausado no kanban"
```
