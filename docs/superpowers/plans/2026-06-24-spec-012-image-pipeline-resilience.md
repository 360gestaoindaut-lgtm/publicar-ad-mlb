# SPEC-012 — Resiliência Estrutural do Pipeline de Imagens

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminar quatro falhas estruturais no pipeline de imagens do batch: token expirado no upload, execução dupla em retries, dispatch perdido entre DB commit e enfileiramento Redis, e race condition entre workers.

**Architecture:** Quatro mudanças independentes no backend, todas em `backend/app/workers/` e `backend/app/services/listing_service.py`. Task 1 e Task 2 operam apenas em `image_tasks.py`. Task 3 adiciona dispatch via Celery `chain` com UPDATE atômico nos dois gatilhos do pipeline. Task 4 remove os `.delay()` internos das tasks que a chain agora gerencia — deve ser implantada após Task 3.

**Tech Stack:** Python 3.12, Celery 5 (`celery.chain`, `.si()`), SQLAlchemy 2.0 async (`update().execution_options(synchronize_session=False)`), pytest + pytest-asyncio.

## Global Constraints

- Nunca alterar caminhos de sucesso do fluxo manual (endpoints chamados pelo usuário via UI).
- Sem dependências novas — `celery`, `sqlalchemy`, `httpx` já estão em `requirements.txt`.
- Todos os imports dentro de workers devem permanecer **lazy** (dentro do corpo das funções), não no topo do arquivo — restrição do startup do Celery.
- A exceção ao lazy import é `from celery import chain` que pode ser feito lazy dentro da função de dispatch.
- `celery.chain` deve usar `.si()` (não `.s()`) — os tasks não passam resultado para o próximo.
- Tasks em queues diferentes (`images`, `ai`, `publish`) — o chain respeita as rotas configuradas em `celery_app.py`.
- UPDATE atômico usa `.execution_options(synchronize_session=False)` no SQLAlchemy async.
- Commits em Conventional Commits: `fix: <descrição>`.
- Testes rodam dentro do Docker: `docker compose exec backend python -m pytest <path> -v`.

---

## Mapa de arquivos

| Arquivo | Tasks que o tocam | Papel |
|---|---|---|
| `backend/app/workers/tasks/image_tasks.py` | 1, 2, 4 | Token refresh, idempotência, remoção de .delay() internos |
| `backend/app/workers/tasks/ai_tasks.py` | 4 | Remoção de `publish_listing.delay()` interno |
| `backend/app/workers/tasks/category_tasks.py` | 3 | Atomic UPDATE + chain dispatch |
| `backend/app/services/listing_service.py` | 3 | Atomic UPDATE + chain dispatch em submit_attributes |
| `backend/tests/test_image_tasks.py` | 1, 2 | Testes das Tasks 1 e 2 (adicionar classes) |
| `backend/tests/test_batch_chain.py` | 3, 4 | Criado: testes das Tasks 3 e 4 |

---

## Task 1 — Token refresh automático antes do upload ML

**Files:**
- Modify: `backend/app/workers/tasks/image_tasks.py` (função `_generate_images_async`, ≈ linhas 9 e 58-62)
- Test: `backend/tests/test_image_tasks.py` (adicionar classe `TestFetchUploadToken`)

**Interfaces:**
- Produces: `async def _fetch_upload_token(seller, db) -> str` — helper interno que chama `get_valid_access_token(seller, db)` de `publish_service`; garante refresh se o token estiver expirado.

**Context — o que existe hoje:**
```python
# image_tasks.py linha 9 (dentro de _generate_images_async, bloco lazy imports):
from app.core.security import decrypt_value
...
# linha 62:
access_token = decrypt_value(seller.access_token_enc)
```
`decrypt_value` apenas descriptografa o valor armazenado. Se o token ML estiver expirado, o upload falha com 401 sem possibilidade de recuperação. A função `get_valid_access_token(seller, db)` em `publish_service.py` já verifica a expiração e faz refresh se necessário — ela é usada em `publish_tasks.py` com o mesmo padrão.

---

- [ ] **Step 1: Escrever o teste (falha esperada — função não existe ainda)**

Adicionar ao final de `backend/tests/test_image_tasks.py`:

```python
class TestFetchUploadToken:
    @pytest.mark.asyncio
    async def test_calls_get_valid_access_token(self):
        from app.workers.tasks.image_tasks import _fetch_upload_token

        mock_seller = MagicMock()
        mock_db = AsyncMock()

        with patch(
            "app.services.publish_service.get_valid_access_token",
            new_callable=AsyncMock,
            return_value="refreshed-token",
        ) as mock_fn:
            result = await _fetch_upload_token(mock_seller, mock_db)

        assert result == "refreshed-token"
        mock_fn.assert_called_once_with(mock_seller, mock_db)

    @pytest.mark.asyncio
    async def test_does_not_call_decrypt_value_directly(self):
        from app.workers.tasks.image_tasks import _fetch_upload_token

        with patch("app.core.security.decrypt_value") as mock_decrypt, \
             patch(
                 "app.services.publish_service.get_valid_access_token",
                 new_callable=AsyncMock,
                 return_value="tok",
             ):
            await _fetch_upload_token(MagicMock(), AsyncMock())

        mock_decrypt.assert_not_called()
```

- [ ] **Step 2: Rodar — confirmar falha**

```bash
docker compose exec backend python -m pytest tests/test_image_tasks.py::TestFetchUploadToken -v
```

Saída esperada: `FAILED` com `ImportError: cannot import name '_fetch_upload_token'`.

- [ ] **Step 3: Implementar `_fetch_upload_token` e substituir `decrypt_value`**

Em `backend/app/workers/tasks/image_tasks.py`, adicionar a função após os imports de módulo (antes de `_generate_images_async`):

```python
async def _fetch_upload_token(seller, db) -> str:
    from app.services.publish_service import get_valid_access_token
    return await get_valid_access_token(seller, db)
```

Dentro de `_generate_images_async`, localizar o bloco de lazy imports (≈ linha 9) e remover a linha:
```python
from app.core.security import decrypt_value
```

Localizar a linha de uso (≈ linha 62) e substituir:
```python
# ANTES:
access_token = decrypt_value(seller.access_token_enc)

# DEPOIS:
access_token = await _fetch_upload_token(seller, db)
```

- [ ] **Step 4: Rodar — confirmar que passa**

```bash
docker compose exec backend python -m pytest tests/test_image_tasks.py::TestFetchUploadToken -v
```

Saída esperada: 2 passed.

- [ ] **Step 5: Confirmar que o módulo carrega sem erros**

```bash
docker compose exec backend python -c "from app.workers.tasks.image_tasks import generate_images; print('ok')"
```

Saída esperada: `ok`

- [ ] **Step 6: Rodar suite completa para checar regressões**

```bash
docker compose exec backend python -m pytest tests/test_image_tasks.py -v
```

Saída esperada: todos os testes anteriores ainda passam + 2 novos.

- [ ] **Step 7: Commit**

```bash
git add backend/app/workers/tasks/image_tasks.py backend/tests/test_image_tasks.py
git commit -m "fix: use get_valid_access_token instead of decrypt_value in image upload"
```

---

## Task 2 — Guard de idempotência por status em `generate_images`

**Files:**
- Modify: `backend/app/workers/tasks/image_tasks.py` (início de `_generate_images_async`)
- Test: `backend/tests/test_image_tasks.py` (adicionar classe `TestGenerateImagesIdempotency`)

**Interfaces:**
- Consumes: `listing.status` — lido do banco logo após carregar o objeto.
- Produces: retorno antecipado `{"listing_id": listing_id, "skipped": True}` quando `listing.status != "generating_images"`.

**Context — o problema:**
Se `generate_images` for enfileirada duas vezes para o mesmo listing (bug de retry ou dispatch duplo), a segunda execução lê o listing já no status `pending_image_approval` ou `generating_description` (definido pela primeira execução) e deve abortar sem gerar novas imagens ou duplicar entradas no banco.

---

- [ ] **Step 1: Escrever o teste (falha esperada)**

Adicionar ao final de `backend/tests/test_image_tasks.py`:

```python
class TestGenerateImagesIdempotency:
    @pytest.mark.asyncio
    async def test_skips_when_status_not_generating_images(self):
        from app.workers.tasks.image_tasks import _generate_images_async

        mock_listing = MagicMock()
        mock_listing.status = "pending_image_approval"  # já avançou

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_listing
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.database.worker_session", lambda: _mock_session(mock_db)), \
             patch("app.services.image_service.GeminiImageService") as mock_gemini:
            result = await _generate_images_async("listing-id")

        assert result == {"listing_id": "listing-id", "skipped": True}
        mock_gemini.assert_not_called()

    @pytest.mark.asyncio
    async def test_proceeds_when_status_is_generating_images(self):
        """Verificação negativa: guard NÃO aborta quando status está correto."""
        from app.workers.tasks.image_tasks import _generate_images_async

        mock_listing = MagicMock()
        mock_listing.status = "generating_images"
        mock_listing.sku_external_id = None
        mock_listing.seller_id = "sid"
        mock_listing.created_via = "manual"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_listing
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Com status correto, a função avança — mas vai falhar em algum ponto
        # sem o restante dos mocks. Basta confirmar que GeminiImageService foi instanciado.
        with patch("app.database.worker_session", lambda: _mock_session(mock_db)), \
             patch("app.services.ai.service.get_ai_provider", return_value=AsyncMock(
                 generate_image_prompt=AsyncMock(return_value="prompt")
             )), \
             patch("app.services.image_service.GeminiImageService") as mock_gemini_cls, \
             patch("app.workers.tasks.image_tasks._fetch_upload_token", new_callable=AsyncMock, return_value="tok"):
            mock_gemini_cls.return_value.generate = AsyncMock(return_value=[])
            try:
                await _generate_images_async("listing-id")
            except Exception:
                pass  # pode falhar após o guard — o que importa é que chegou aqui

        mock_gemini_cls.assert_called_once()
```

- [ ] **Step 2: Rodar — confirmar falha**

```bash
docker compose exec backend python -m pytest tests/test_image_tasks.py::TestGenerateImagesIdempotency -v
```

Saída esperada: `test_skips_when_status_not_generating_images` FAILED (função não retorna `{"skipped": True}`).

- [ ] **Step 3: Implementar o guard no início de `_generate_images_async`**

Dentro de `_generate_images_async`, após carregar o `listing` do banco (imediatamente após o `scalar_one()`), inserir:

```python
        # Guard de idempotência: se o status já avançou (retry ou dispatch duplo), abortar.
        if listing.status != "generating_images":
            return {"listing_id": listing_id, "skipped": True}
```

O bloco deve ficar assim (o `sku = ...` vem depois):

```python
    async with worker_session() as db:
        listing = (
            await db.execute(select(Listing).where(Listing.id == listing_id))
        ).scalar_one()

        if listing.status != "generating_images":
            return {"listing_id": listing_id, "skipped": True}

        sku = listing.sku_external_id or ""
        ...
```

- [ ] **Step 4: Rodar — confirmar que passa**

```bash
docker compose exec backend python -m pytest tests/test_image_tasks.py::TestGenerateImagesIdempotency -v
```

Saída esperada: 2 passed.

- [ ] **Step 5: Rodar suite completa**

```bash
docker compose exec backend python -m pytest tests/test_image_tasks.py -v
```

Saída esperada: todos passam.

- [ ] **Step 6: Commit**

```bash
git add backend/app/workers/tasks/image_tasks.py backend/tests/test_image_tasks.py
git commit -m "fix: skip generate_images if listing status already advanced (idempotency guard)"
```

---

## Task 3 — Atomic UPDATE + Celery chain nos gatilhos do batch

**Files:**
- Modify: `backend/app/workers/tasks/category_tasks.py` (função `_predict_category_async`, ≈ linhas 19-24)
- Modify: `backend/app/services/listing_service.py` (método `submit_attributes`, ≈ linhas 170-181)
- Create: `backend/tests/test_batch_chain.py`

**Interfaces:**
- Produces: em ambos os gatilhos, a transição `pending_description → generating_images` passa a ser feita por um `UPDATE ... WHERE status = 'pending_description'` atômico. Se `rowcount == 1`, o gatilho despacha `chain(generate_images.si | generate_description.si | publish_listing.si)`. Se `rowcount == 0`, outro worker ganhou a corrida — nenhuma ação.
- A chain usa `.si(listing_id)` em todos os steps para não passar o valor de retorno adiante.

**Context — o problema atual:**
```python
# category_tasks.py (padrão atual):
if listing.created_via == "batch" and listing.status == "pending_description":
    listing.status = "generating_images"
    await db.commit()                    # ← 1. status gravado no banco
    generate_images.delay(listing_id)   # ← 2. dispatch (se Redis falhar aqui, listing fica preso)
```
Entre o commit (1) e o dispatch (2) há uma janela de falha. Além disso, se dois workers chegarem simultâneamente, ambos podem passar pela checagem de status e despachar duas vezes. O UPDATE atômico elimina as duas vulnerabilidades: o banco decide quem ganha, e o broker recebe a chain inteira de uma vez.

---

- [ ] **Step 1: Criar `backend/tests/test_batch_chain.py` com testes (falha esperada)**

```python
import pytest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch, call


@asynccontextmanager
async def _mock_session(mock_db):
    yield mock_db


class TestCategoryTaskChainDispatch:
    @pytest.mark.asyncio
    async def test_dispatches_chain_when_update_succeeds(self):
        """Quando o UPDATE atômico altera 1 linha, a chain é despachada."""
        from app.workers.tasks.category_tasks import _predict_category_async

        mock_listing = MagicMock()
        mock_listing.created_via = "batch"
        mock_listing.status = "pending_description"
        mock_listing.ml_category_id = "MLB1055"

        # UPDATE retorna rowcount=1 (ganhou a corrida)
        mock_update_result = MagicMock()
        mock_update_result.rowcount = 1

        mock_db = AsyncMock()
        execute_calls = [0]

        async def execute_side(stmt):
            execute_calls[0] += 1
            if execute_calls[0] == 1:  # SELECT Listing
                r = MagicMock()
                r.scalar_one = MagicMock(return_value=mock_listing)
                return r
            else:  # UPDATE atômico
                return mock_update_result

        mock_db.execute = execute_side

        mock_chain_instance = MagicMock()

        with patch("app.database.worker_session", lambda: _mock_session(mock_db)), \
             patch("app.services.category_service.CategoryService") as mock_cat_cls, \
             patch("celery.chain", return_value=mock_chain_instance) as mock_chain_fn:
            mock_cat = AsyncMock()
            mock_cat.predict_and_save = AsyncMock()
            mock_cat_cls.return_value = mock_cat
            await _predict_category_async("listing-id")

        mock_chain_fn.assert_called_once()
        mock_chain_instance.delay.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_dispatch_when_update_returns_zero(self):
        """Quando rowcount=0 (outro worker ganhou), não despacha nada."""
        from app.workers.tasks.category_tasks import _predict_category_async

        mock_listing = MagicMock()
        mock_listing.created_via = "batch"
        mock_listing.status = "pending_description"
        mock_listing.ml_category_id = "MLB1055"

        mock_update_result = MagicMock()
        mock_update_result.rowcount = 0  # outro worker ganhou

        mock_db = AsyncMock()
        execute_calls = [0]

        async def execute_side(stmt):
            execute_calls[0] += 1
            if execute_calls[0] == 1:
                r = MagicMock()
                r.scalar_one = MagicMock(return_value=mock_listing)
                return r
            else:
                return mock_update_result

        mock_db.execute = execute_side

        with patch("app.database.worker_session", lambda: _mock_session(mock_db)), \
             patch("app.services.category_service.CategoryService") as mock_cat_cls, \
             patch("celery.chain") as mock_chain_fn:
            mock_cat = AsyncMock()
            mock_cat.predict_and_save = AsyncMock()
            mock_cat_cls.return_value = mock_cat
            await _predict_category_async("listing-id")

        mock_chain_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_dispatch_when_not_batch(self):
        """Flow manual (created_via != 'batch') não despacha chain."""
        from app.workers.tasks.category_tasks import _predict_category_async

        mock_listing = MagicMock()
        mock_listing.created_via = "manual"
        mock_listing.status = "pending_description"
        mock_listing.ml_category_id = "MLB1055"

        mock_db = AsyncMock()

        async def execute_side(stmt):
            r = MagicMock()
            r.scalar_one = MagicMock(return_value=mock_listing)
            return r

        mock_db.execute = execute_side

        with patch("app.database.worker_session", lambda: _mock_session(mock_db)), \
             patch("app.services.category_service.CategoryService") as mock_cat_cls, \
             patch("celery.chain") as mock_chain_fn:
            mock_cat = AsyncMock()
            mock_cat.predict_and_save = AsyncMock()
            mock_cat_cls.return_value = mock_cat
            await _predict_category_async("listing-id")

        mock_chain_fn.assert_not_called()


class TestSubmitAttributesChainDispatch:
    @pytest.mark.asyncio
    async def test_dispatches_chain_when_batch_and_pending_description(self):
        """submit_attributes em modo batch com pending_description despacha chain."""
        from app.services.listing_service import ListingService
        from app.models.listing import Listing as ListingModel

        mock_listing = MagicMock(spec=ListingModel)
        mock_listing.id = "lid"
        mock_listing.seller_id = "sid"
        mock_listing.status = "pending_seller_attributes"
        mock_listing.created_via = "batch"

        mock_db = AsyncMock()
        execute_calls = [0]

        # Simula: sem imagem aprovada, sem descrição (new_status = pending_description)
        # depois: UPDATE atômico com rowcount=1
        async def execute_side(stmt):
            execute_calls[0] += 1
            r = MagicMock()
            if execute_calls[0] <= 2:    # select ListingAttribute (para submitted vazio)
                r.scalar_one_or_none = MagicMock(return_value=None)
                return r
            if execute_calls[0] == 3:    # select ListingImage (approved)
                r.scalars = MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))
                return r
            if execute_calls[0] == 4:    # select ListingDescription
                r.scalar_one_or_none = MagicMock(return_value=None)
                return r
            # UPDATE atômico
            r.rowcount = 1
            return r

        mock_db.execute = execute_side
        mock_db.commit = AsyncMock()

        mock_chain_instance = MagicMock()

        with patch("celery.chain", return_value=mock_chain_instance) as mock_chain_fn:
            svc = ListingService(mock_db)
            await svc.submit_attributes(mock_listing, [])

        mock_chain_fn.assert_called_once()
        mock_chain_instance.delay.assert_called_once()
```

- [ ] **Step 2: Rodar — confirmar falha**

```bash
docker compose exec backend python -m pytest tests/test_batch_chain.py -v
```

Saída esperada: múltiplos FAILED — `celery.chain` não é chamado ainda.

- [ ] **Step 3: Implementar em `category_tasks.py`**

Substituir o bloco final de `_predict_category_async` (≈ linhas 19-24):

```python
        # ANTES:
        if listing.created_via == "batch" and listing.status == "pending_description":
            listing.status = "generating_images"
            await db.commit()
            from app.workers.tasks.image_tasks import generate_images
            generate_images.delay(listing_id)
```

Por:

```python
        if listing.created_via == "batch" and listing.status == "pending_description":
            from sqlalchemy import update as sa_update
            result = await db.execute(
                sa_update(Listing)
                .where(
                    Listing.id == listing_id,
                    Listing.status == "pending_description",
                    Listing.created_via == "batch",
                )
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

Também adicionar `from app.models.listing import Listing` ao bloco de imports lazy no topo de `_predict_category_async` (ele já importa `Listing` — confirmar que está lá; se não, adicionar).

- [ ] **Step 4: Implementar em `listing_service.py` — método `submit_attributes`**

Substituir o bloco batch (≈ linhas 170-181):

```python
        # ANTES:
        if listing.created_via == "batch":
            if new_status == "pending_description":
                listing.status = "generating_images"
                await self.db.commit()
                from app.workers.tasks.image_tasks import generate_images
                generate_images.delay(str(listing.id))
            elif new_status == "ready_to_publish":
                listing.status = "publishing"
                await self.db.commit()
                from app.workers.tasks.publish_tasks import publish_listing
                publish_listing.delay(str(listing.id))
```

Por:

```python
        if listing.created_via == "batch":
            if new_status == "pending_description":
                from sqlalchemy import update as sa_update
                from app.models.listing import Listing as ListingModel
                result = await self.db.execute(
                    sa_update(ListingModel)
                    .where(
                        ListingModel.id == listing.id,
                        ListingModel.status == "pending_description",
                    )
                    .values(status="generating_images")
                    .execution_options(synchronize_session=False)
                )
                await self.db.commit()
                if result.rowcount == 1:
                    listing.status = "generating_images"
                    from celery import chain as celery_chain
                    from app.workers.tasks.image_tasks import generate_images
                    from app.workers.tasks.ai_tasks import generate_description
                    from app.workers.tasks.publish_tasks import publish_listing
                    celery_chain(
                        generate_images.si(str(listing.id)),
                        generate_description.si(str(listing.id)),
                        publish_listing.si(str(listing.id)),
                    ).delay()
            elif new_status == "ready_to_publish":
                listing.status = "publishing"
                await self.db.commit()
                from app.workers.tasks.publish_tasks import publish_listing
                publish_listing.delay(str(listing.id))
```

- [ ] **Step 5: Rodar — confirmar que passa**

```bash
docker compose exec backend python -m pytest tests/test_batch_chain.py -v
```

Saída esperada: todos os testes do arquivo passam.

- [ ] **Step 6: Confirmar que módulos carregam**

```bash
docker compose exec backend python -c "
from app.workers.tasks.category_tasks import predict_category
from app.services.listing_service import ListingService
print('ok')
"
```

Saída esperada: `ok`

- [ ] **Step 7: Rodar suite completa**

```bash
docker compose exec backend python -m pytest tests/ -v
```

Saída esperada: todos os testes passam (o `test_health_returns_ok` pré-existente é a única exceção conhecida, fora do escopo desta SPEC).

- [ ] **Step 8: Commit**

```bash
git add backend/app/workers/tasks/category_tasks.py backend/app/services/listing_service.py backend/tests/test_batch_chain.py
git commit -m "fix: atomic UPDATE + celery chain dispatch in batch image pipeline triggers"
```

---

## Task 4 — Remover `.delay()` internos das tasks gerenciadas pela chain

**Files:**
- Modify: `backend/app/workers/tasks/image_tasks.py` (remover 2 blocos de `generate_description.delay()`)
- Modify: `backend/app/workers/tasks/ai_tasks.py` (remover `publish_listing.delay()`)
- Test: `backend/tests/test_batch_chain.py` (adicionar classe `TestRemovedInternalDispatch`)

**Interfaces:**
- Consumes: chain despachada na Task 3 — garante que `generate_description` e `publish_listing` serão executados pelo broker após `generate_images` completar.
- Produces: `generate_images` e `generate_description` não mais despacham tasks subsequentes internamente no batch path.

**Context — ATENÇÃO À ORDEM DE DEPLOY:**
Esta task remove os `.delay()` internos que hoje mantêm o pipeline funcionando. Ela DEVE ser deployada junto ou após a Task 3 (que adiciona a chain). Em produção (Fase 6), aguardar que não haja tasks `generate_images` em voo antes de deployar esta task.

**O que muda em `image_tasks.py`:**

*Path de reutilização de imagens (≈ linhas 48-52):*
```python
# REMOVER estas linhas no bloco batch do reuse path:
from app.workers.tasks.ai_tasks import generate_description
generate_description.delay(listing_id)
```
O status `listing.status = "generating_description"` e o `db.commit()` **permanecem** — apenas o `.delay()` é removido.

*Path de geração nova (≈ linhas 122-125):*
```python
# REMOVER estas linhas no bloco batch do generation path:
from app.workers.tasks.ai_tasks import generate_description
generate_description.delay(listing_id)
```
Idem — status e commit permanecem.

**O que muda em `ai_tasks.py`:**

*`_generate_description_async` (≈ linhas 94-98):*
```python
# REMOVER estas linhas no bloco batch:
from app.workers.tasks.publish_tasks import publish_listing
publish_listing.delay(listing_id)
```
O status `listing.status = "publishing"` e o `db.commit()` **permanecem**.

---

- [ ] **Step 1: Escrever testes que verificam a ausência dos `.delay()` internos**

Adicionar ao final de `backend/tests/test_batch_chain.py`:

```python
class TestRemovedInternalDispatch:
    """Garante que tasks no batch path não mais chamam .delay() internamente.
    A chain (Task 3) é responsável por despachar os próximos steps.
    """

    @pytest.mark.asyncio
    async def test_generate_images_reuse_does_not_call_generate_description_delay(self):
        """Reuse path: imagens copiadas do índice, mas generate_description NÃO é chamado."""
        from app.workers.tasks.image_tasks import _generate_images_async

        # Imagem existente no índice SKU→imagem
        mock_product_image = MagicMock()
        mock_product_image.ml_picture_id = "pic-123"

        mock_listing = MagicMock()
        mock_listing.id = "lid"
        mock_listing.status = "generating_images"
        mock_listing.sku_external_id = "SKU-001"
        mock_listing.seller_id = "sid"
        mock_listing.created_via = "batch"

        mock_db = AsyncMock()
        execute_calls = [0]

        async def execute_side(stmt):
            execute_calls[0] += 1
            r = MagicMock()
            if execute_calls[0] == 1:   # SELECT Listing
                r.scalar_one = MagicMock(return_value=mock_listing)
            else:                        # SELECT ProductImage (imagens existentes)
                r.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_product_image])))
            return r

        mock_db.execute = execute_side
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        with patch("app.database.worker_session", lambda: _mock_session(mock_db)), \
             patch("app.workers.tasks.ai_tasks.generate_description") as mock_gd:
            await _generate_images_async("lid")

        mock_gd.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_description_batch_does_not_call_publish_listing_delay(self):
        """generate_description em batch seta status 'publishing' mas NÃO despacha publish_listing."""
        from app.workers.tasks.ai_tasks import _generate_description_async

        mock_listing = MagicMock()
        mock_listing.id = "lid"
        mock_listing.created_via = "batch"
        mock_listing.selected_title = "Title"
        mock_listing.sku_brand = "Brand"
        mock_listing.sku_description = "Desc"
        mock_listing.condition = "new"

        mock_db = AsyncMock()
        execute_calls = [0]

        async def execute_side(stmt):
            execute_calls[0] += 1
            r = MagicMock()
            if execute_calls[0] == 1:   # SELECT Listing
                r.scalar_one = MagicMock(return_value=mock_listing)
            elif execute_calls[0] == 2: # SELECT ListingAttribute
                r.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            else:                        # SELECT ListingDescription
                r.scalar_one_or_none = MagicMock(return_value=None)
            return r

        mock_db.execute = execute_side
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        with patch("app.database.worker_session", lambda: _mock_session(mock_db)), \
             patch("app.services.ai.service.get_ai_provider") as mock_provider_fn, \
             patch("app.workers.tasks.publish_tasks.publish_listing") as mock_pl:
            mock_ai = AsyncMock()
            mock_ai.generate_description = AsyncMock(return_value="<p>desc</p>")
            mock_provider_fn.return_value = mock_ai
            await _generate_description_async("lid")

        mock_pl.delay.assert_not_called()
        assert mock_listing.status == "publishing"
```

- [ ] **Step 2: Rodar — confirmar falha**

```bash
docker compose exec backend python -m pytest tests/test_batch_chain.py::TestRemovedInternalDispatch -v
```

Saída esperada: ambos FAILED — os `.delay()` internos ainda existem.

- [ ] **Step 3: Remover `.delay()` internos de `image_tasks.py`**

**Reuse path** — localizar o bloco (≈ linhas 48-56) e remover as duas linhas marcadas:

```python
            if existing:
                for i, pi in enumerate(existing):
                    db.add(ListingImage(
                        listing_id=listing.id,
                        ml_picture_id=pi.ml_picture_id,
                        status="uploaded",
                        approved=True,
                        sort_order=i,
                    ))
                if listing.created_via == "batch":
                    listing.status = "generating_description"
                    await db.commit()
                    # REMOVER as duas linhas abaixo:
                    from app.workers.tasks.ai_tasks import generate_description
                    generate_description.delay(listing_id)
                else:
                    listing.status = "pending_image_approval"
                    await db.commit()
                return {"listing_id": listing_id, "images_reused": len(existing)}
```

Resultado após remoção:

```python
            if existing:
                for i, pi in enumerate(existing):
                    db.add(ListingImage(
                        listing_id=listing.id,
                        ml_picture_id=pi.ml_picture_id,
                        status="uploaded",
                        approved=True,
                        sort_order=i,
                    ))
                if listing.created_via == "batch":
                    listing.status = "generating_description"
                    await db.commit()
                else:
                    listing.status = "pending_image_approval"
                    await db.commit()
                return {"listing_id": listing_id, "images_reused": len(existing)}
```

**Generation path** — localizar o bloco batch (≈ linhas 106-125) e remover as duas linhas marcadas:

```python
        if listing.created_via == "batch":
            images = (await db.execute(
                select(ListingImage).where(ListingImage.listing_id == listing.id)
            )).scalars().all()
            for img in images:
                img.approved = True
            if sku:
                prod_imgs = (await db.execute(
                    select(ProductImage).where(
                        ProductImage.seller_id == listing.seller_id,
                        ProductImage.sku == sku,
                    )
                )).scalars().all()
                for pi in prod_imgs:
                    pi.is_approved = True
            listing.status = "generating_description"
            await db.commit()
            # REMOVER as duas linhas abaixo:
            from app.workers.tasks.ai_tasks import generate_description
            generate_description.delay(listing_id)
        else:
            listing.status = "pending_image_approval"
            await db.commit()
```

Resultado após remoção (o bloco `if listing.created_via == "batch":` perde apenas as 2 últimas linhas):

```python
        if listing.created_via == "batch":
            ...
            listing.status = "generating_description"
            await db.commit()
        else:
            listing.status = "pending_image_approval"
            await db.commit()
```

- [ ] **Step 4: Remover `.delay()` interno de `ai_tasks.py`**

Localizar o bloco batch em `_generate_description_async` (≈ linhas 94-98):

```python
        if listing.created_via == "batch":
            listing.status = "publishing"
            await db.commit()
            # REMOVER as duas linhas abaixo:
            from app.workers.tasks.publish_tasks import publish_listing
            publish_listing.delay(listing_id)
        else:
            listing.status = "ready_to_publish"
            await db.commit()
```

Resultado após remoção:

```python
        if listing.created_via == "batch":
            listing.status = "publishing"
            await db.commit()
        else:
            listing.status = "ready_to_publish"
            await db.commit()
```

- [ ] **Step 5: Rodar — confirmar que os novos testes passam**

```bash
docker compose exec backend python -m pytest tests/test_batch_chain.py::TestRemovedInternalDispatch -v
```

Saída esperada: 2 passed.

- [ ] **Step 6: Rodar suite completa**

```bash
docker compose exec backend python -m pytest tests/ -v
```

Saída esperada: todos os testes passam.

- [ ] **Step 7: Confirmar que os módulos carregam**

```bash
docker compose exec backend python -c "
from app.workers.tasks.image_tasks import generate_images
from app.workers.tasks.ai_tasks import generate_description
print('ok')
"
```

Saída esperada: `ok`

- [ ] **Step 8: Commit**

```bash
git add backend/app/workers/tasks/image_tasks.py backend/app/workers/tasks/ai_tasks.py backend/tests/test_batch_chain.py
git commit -m "fix: remove internal .delay() calls managed by celery chain"
```

---

## Self-Review

**Cobertura dos requisitos SPEC-012:**

| Requisito | Task | Coberto? |
|---|---|---|
| Token refresh automático | 1 | ✅ |
| Idempotência em generate_images | 2 | ✅ |
| Dispatch atômico via Celery chain | 3 | ✅ |
| Lock otimista / race condition | 3 (atomic UPDATE) | ✅ |
| .delay() internos removidos após chain | 4 | ✅ |

**Placeholder scan:** Nenhum TBD, TODO ou "similar to" encontrado.

**Consistência de tipos e nomes:**
- `_fetch_upload_token(seller, db) -> str` — definido em Task 1, usado em Task 1 somente.
- `celery_chain(generate_images.si(...), generate_description.si(...), publish_listing.si(...))` — mesmo padrão em category_tasks e listing_service (Task 3).
- Testes de Task 4 referenciam `_generate_images_async` e `_generate_description_async` — funções existentes, não modificadas em assinatura.

**Caminhos manuais (não-batch) intactos:**
- `listing_service.trigger_image_generation()` mantém `generate_images.delay()` standalone — não tocado.
- `listing_service.approve_images()` mantém `generate_description.delay()` standalone — não tocado.
- `listing_service.trigger_publish()` mantém `publish_listing.delay()` standalone — não tocado.

**Nota de deploy (Fase 6):** Tasks 3 e 4 devem ser deployadas juntas ou em sequência rápida. Task 3 sozinha é segura (adiciona chain, mantém .delay() internos como fallback redundante). Task 4 sozinha em produção quebraria o pipeline de batch — não deployar separadamente.
