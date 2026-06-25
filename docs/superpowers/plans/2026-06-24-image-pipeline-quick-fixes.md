# Image Pipeline Quick Fixes (F-1 a F-4) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corrigir quatro falhas de resiliência pontuais no pipeline de geração de imagens sem alterar comportamento externo visível.

**Architecture:** Todas as mudanças são cirúrgicas e estão confinadas a dois arquivos de backend. F-1 muda a assinatura de `ensure_dimensions` para `bytes | None` e atualiza o único call site. F-2 e F-3 reforçam `_mark_failed`. F-4 introduz `ImageRateLimitError` para que o Celery use backoff maior em 429.

**Tech Stack:** Python 3.12, Celery 5, Pillow 11, httpx 0.28, pytest, pytest-asyncio.

## Global Constraints

- Nunca alterar o comportamento em caminhos de sucesso — só os caminhos de erro mudam.
- Sem dependências novas em `requirements.txt` (todas as libs usadas já estão instaladas).
- Commits em Conventional Commits: `fix: <descrição em inglês técnico>`.
- Todos os testes rodam dentro do container Docker: `docker compose exec backend pytest <path> -v`.
- Python `logging` padrão — não introduzir bibliotecas de log externas.

---

## Mapa de arquivos

| Arquivo | Papel neste PR |
|---|---|
| `backend/app/services/image_service.py` | F-1: tipo de retorno de `ensure_dimensions`; F-4: `ImageRateLimitError` + detecção de 429 |
| `backend/app/workers/tasks/image_tasks.py` | F-1: call site; F-2: remover `hasattr`; F-3: try/except em `_mark_failed`; F-4: catch separado para `ImageRateLimitError` |
| `backend/tests/test_image_service.py` | Criado: testes unitários de `ensure_dimensions` e `GeminiImageService` |
| `backend/tests/test_image_tasks.py` | Criado: testes unitários de `_mark_failed` |

---

## Task 1 — F-1: `ensure_dimensions` retorna `None` em bytes corrompidos

**Files:**
- Modify: `backend/app/services/image_service.py:88-97`
- Modify: `backend/app/workers/tasks/image_tasks.py:75-99` (call site do loop)
- Create: `backend/tests/test_image_service.py`

**Interfaces:**
- Produces: `ensure_dimensions(image_bytes: bytes, target: int = 1024) -> bytes | None` — retorna `None` quando PIL não consegue abrir/converter os bytes; retorna JPEG bytes em caso de sucesso. Todos os callers devem tratar `None` como "descartar imagem".

---

- [ ] **Step 1: Verificar que pytest está disponível no container**

```bash
docker compose exec backend python -m pytest --version
```

Saída esperada: `pytest 7.x.x` ou superior. Se falhar com `No module named pytest`:

```bash
docker compose exec backend pip install pytest pytest-asyncio
```

---

- [ ] **Step 2: Escrever o arquivo de testes (falha esperada nos steps 3-4)**

Criar `backend/tests/test_image_service.py`:

```python
import io
import pytest
from PIL import Image

from app.services.image_service import ensure_dimensions, validate_image


def _make_jpeg(width: int, height: int) -> bytes:
    img = Image.new("RGB", (width, height), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class TestEnsureDimensions:
    def test_corrupted_bytes_returns_none(self):
        result = ensure_dimensions(b"this-is-not-an-image")
        assert result is None

    def test_empty_bytes_returns_none(self):
        result = ensure_dimensions(b"")
        assert result is None

    def test_small_image_is_upscaled(self):
        small = _make_jpeg(200, 200)
        result = ensure_dimensions(small, target=1024)
        assert result is not None
        img = Image.open(io.BytesIO(result))
        assert min(img.size) >= 1024

    def test_large_image_is_not_downscaled(self):
        large = _make_jpeg(1500, 1500)
        result = ensure_dimensions(large, target=1024)
        assert result is not None
        img = Image.open(io.BytesIO(result))
        assert min(img.size) >= 1024

    def test_returns_jpeg_bytes(self):
        source = _make_jpeg(800, 800)
        result = ensure_dimensions(source, target=1024)
        assert result is not None
        img = Image.open(io.BytesIO(result))
        assert img.format == "JPEG"
```

---

- [ ] **Step 3: Rodar testes — confirmar falha em `test_corrupted_bytes_returns_none` e `test_empty_bytes_returns_none`**

```bash
docker compose exec backend pytest tests/test_image_service.py::TestEnsureDimensions -v
```

Saída esperada: `test_corrupted_bytes_returns_none` FAILED com `PIL.UnidentifiedImageError` ou similar; os demais passam.

---

- [ ] **Step 4: Implementar a correção em `image_service.py`**

Substituir a função `ensure_dimensions` atual (linhas 88-97) por:

```python
def ensure_dimensions(image_bytes: bytes, target: int = _RECOMMENDED_DIM) -> bytes | None:
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return None
    w, h = img.size
    if w < target or h < target:
        scale = target / min(w, h)
        img = img.resize((max(int(w * scale), target), max(int(h * scale), target)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()
```

---

- [ ] **Step 5: Rodar testes — confirmar que todos passam**

```bash
docker compose exec backend pytest tests/test_image_service.py::TestEnsureDimensions -v
```

Saída esperada: 5 passed.

---

- [ ] **Step 6: Atualizar o call site em `image_tasks.py`**

No loop `_generate_images_async`, localizar o bloco (linhas 75-99):

```python
        for img_bytes in raw_images:
            if not validate_image(img_bytes):
                continue

            img_bytes = ensure_dimensions(img_bytes)
            ml_picture_id = await ml_pic.upload(img_bytes, access_token)
```

Substituir por:

```python
        for img_bytes in raw_images:
            if not validate_image(img_bytes):
                continue

            img_bytes = ensure_dimensions(img_bytes)
            if img_bytes is None:
                continue
            ml_picture_id = await ml_pic.upload(img_bytes, access_token)
```

---

- [ ] **Step 7: Confirmar que o backend ainda sobe sem erros de importação**

```bash
docker compose exec backend python -c "from app.services.image_service import ensure_dimensions; print('ok')"
```

Saída esperada: `ok`

---

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/image_service.py backend/app/workers/tasks/image_tasks.py backend/tests/test_image_service.py
git commit -m "fix: ensure_dimensions returns None on corrupt bytes instead of raising"
```

---

## Task 2 — F-2 + F-3: `_mark_failed` preserva mensagem de erro e tolera falha de banco

**Files:**
- Modify: `backend/app/workers/tasks/image_tasks.py:131-140`
- Create: `backend/tests/test_image_tasks.py`

**Interfaces:**
- Consumes: `_mark_failed(listing_id: str, error: str) -> None` — assinatura inalterada.
- Produces: mesma assinatura; agora: (a) sempre grava `error_message` sem checar `hasattr`; (b) se qualquer exceção ocorrer internamente, loga com `logging.error` e retorna sem propagar.

---

- [ ] **Step 1: Escrever arquivo de testes**

Criar `backend/tests/test_image_tasks.py`:

```python
import logging
import pytest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch


@asynccontextmanager
async def _mock_session(mock_db):
    yield mock_db


def _make_mock_listing():
    listing = MagicMock()
    listing.status = "generating_images"
    listing.error_message = None
    return listing


class TestMarkFailed:
    @pytest.mark.asyncio
    async def test_sets_status_and_error_message(self):
        from app.workers.tasks.image_tasks import _mark_failed

        listing = _make_mock_listing()
        mock_db = AsyncMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = listing

        with patch("app.database.worker_session", lambda: _mock_session(mock_db)):
            await _mark_failed("abc-123", "something went wrong")

        assert listing.status == "failed"
        assert listing.error_message == "something went wrong"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_truncates_long_error_to_500_chars(self):
        from app.workers.tasks.image_tasks import _mark_failed

        listing = _make_mock_listing()
        mock_db = AsyncMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = listing

        long_error = "x" * 1000
        with patch("app.database.worker_session", lambda: _mock_session(mock_db)):
            await _mark_failed("abc-123", long_error)

        assert len(listing.error_message) == 500

    @pytest.mark.asyncio
    async def test_db_failure_logs_and_does_not_propagate(self, caplog):
        from app.workers.tasks.image_tasks import _mark_failed

        @asynccontextmanager
        async def _exploding_session():
            raise RuntimeError("DB connection lost")
            yield  # noqa: unreachable — satisfies contextmanager protocol

        with patch("app.database.worker_session", _exploding_session):
            with caplog.at_level(logging.ERROR):
                await _mark_failed("abc-123", "original error")  # must not raise

        assert "abc-123" in caplog.text
        assert "original error" in caplog.text

    @pytest.mark.asyncio
    async def test_listing_not_found_does_not_raise(self):
        from app.workers.tasks.image_tasks import _mark_failed

        mock_db = AsyncMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        with patch("app.database.worker_session", lambda: _mock_session(mock_db)):
            await _mark_failed("abc-123", "error")  # must not raise
```

---

- [ ] **Step 2: Rodar testes — confirmar falhas**

```bash
docker compose exec backend pytest tests/test_image_tasks.py::TestMarkFailed -v
```

Saída esperada: múltiplos FAILED — `test_sets_status_and_error_message` falhará porque `hasattr` retorna `None` em vez do erro; `test_db_failure_logs_and_does_not_propagate` falhará porque a exceção propaga.

---

- [ ] **Step 3: Implementar a correção em `image_tasks.py`**

Substituir a função `_mark_failed` atual (linhas 131-140) integralmente por:

```python
async def _mark_failed(listing_id: str, error: str) -> None:
    import logging
    logger = logging.getLogger(__name__)
    try:
        from app.database import worker_session
        from app.models.listing import Listing
        from sqlalchemy import select
        async with worker_session() as db:
            listing = (
                await db.execute(select(Listing).where(Listing.id == listing_id))
            ).scalar_one_or_none()
            if listing:
                listing.status = "failed"
                listing.error_message = error[:500]
                await db.commit()
    except Exception as mark_exc:
        logger.error(
            "Could not mark listing %s as failed (original error: %s): %s",
            listing_id,
            error,
            mark_exc,
        )
```

---

- [ ] **Step 4: Rodar testes — confirmar que todos passam**

```bash
docker compose exec backend pytest tests/test_image_tasks.py::TestMarkFailed -v
```

Saída esperada: 4 passed.

---

- [ ] **Step 5: Confirmar importação limpa**

```bash
docker compose exec backend python -c "from app.workers.tasks.image_tasks import _mark_failed; print('ok')"
```

Saída esperada: `ok`

---

- [ ] **Step 6: Commit**

```bash
git add backend/app/workers/tasks/image_tasks.py backend/tests/test_image_tasks.py
git commit -m "fix: _mark_failed always saves error_message and tolerates DB failure"
```

---

## Task 3 — F-4: HTTP 429 do Imagen recebe backoff maior no Celery

**Files:**
- Modify: `backend/app/services/image_service.py` (adicionar `ImageRateLimitError`; detecção de 429)
- Modify: `backend/app/workers/tasks/image_tasks.py` (catch separado com countdown 60s/120s)
- Modify: `backend/tests/test_image_service.py` (nova classe `TestGeminiImageService429`)
- Modify: `backend/tests/test_image_tasks.py` (nova classe `TestGenerateImagesRateLimit`)

**Interfaces:**
- Produces: `class ImageRateLimitError(Exception)` exportada de `app.services.image_service`. Raised por `GeminiImageService.generate()` quando a Imagen API retorna HTTP 429. O Celery task captura essa exceção antes do `except Exception` genérico e usa `countdown=60 * (2 ** retries)`.

---

- [ ] **Step 1: Escrever testes para `ImageRateLimitError` e detecção de 429**

Adicionar ao final de `backend/tests/test_image_service.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.image_service import GeminiImageService, ImageRateLimitError


class TestGeminiImageService429:
    @pytest.mark.asyncio
    async def test_raises_rate_limit_error_on_429(self):
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.is_success = False
        mock_response.text = "Quota exceeded"
        mock_response.request = MagicMock()

        mock_post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            service = GeminiImageService()
            with pytest.raises(ImageRateLimitError):
                await service.generate("test prompt")

    @pytest.mark.asyncio
    async def test_other_errors_raise_http_status_error(self):
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.is_success = False
        mock_response.text = "Internal Server Error"
        mock_response.request = MagicMock()

        mock_post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            service = GeminiImageService()
            with pytest.raises(httpx.HTTPStatusError):
                await service.generate("test prompt")
```

---

- [ ] **Step 2: Rodar testes — confirmar falha**

```bash
docker compose exec backend pytest tests/test_image_service.py::TestGeminiImageService429 -v
```

Saída esperada: `test_raises_rate_limit_error_on_429` FAILED com `ImportError: cannot import name 'ImageRateLimitError'`.

---

- [ ] **Step 3: Implementar `ImageRateLimitError` e detecção de 429 em `image_service.py`**

Logo após os imports e constantes (antes da classe `GeminiImageService`), adicionar:

```python
class ImageRateLimitError(Exception):
    """Raised when Imagen API returns HTTP 429 — signals Celery to use longer backoff."""
```

Substituir o bloco de verificação de erro no método `generate` (linhas 44-49) por:

```python
        if not resp.is_success:
            if resp.status_code == 429:
                raise ImageRateLimitError(
                    f"Imagen API rate limit (429): {resp.text[:300]}"
                )
            raise httpx.HTTPStatusError(
                f"Imagen API {resp.status_code}: {resp.text[:600]}",
                request=resp.request,
                response=resp,
            )
```

---

- [ ] **Step 4: Rodar testes — confirmar que passam**

```bash
docker compose exec backend pytest tests/test_image_service.py::TestGeminiImageService429 -v
```

Saída esperada: 2 passed.

---

- [ ] **Step 5: Atualizar o Celery task em `image_tasks.py`**

No topo do arquivo, adicionar o import (junto aos outros imports do módulo):

```python
from app.services.image_service import GeminiImageService, MLPictureService, validate_image, ensure_dimensions
```

> **Atenção:** esse import já existe dentro de `_generate_images_async` (lazy). Não mova os imports lazy — adicione apenas o import de `ImageRateLimitError` na task wrapper, lazy também, para evitar circular import no startup do Celery.

Substituir a task `generate_images` (linhas 143-151) por:

```python
@celery_app.task(name="app.workers.tasks.image_tasks.generate_images", bind=True, max_retries=2)
def generate_images(self, listing_id: str) -> dict:
    try:
        return asyncio.run(_generate_images_async(listing_id))
    except Exception as exc:
        from app.services.image_service import ImageRateLimitError
        countdown = (
            60 * (2 ** self.request.retries)   # 60s, 120s — muito mais longo para 429
            if isinstance(exc, ImageRateLimitError)
            else 2 ** self.request.retries * 5  # 5s, 10s — erros comuns
        )
        if self.request.retries >= self.max_retries:
            asyncio.run(_mark_failed(listing_id, str(exc)))
            raise
        raise self.retry(exc=exc, countdown=countdown)
```

---

- [ ] **Step 6: Escrever teste comportamental para o countdown maior**

Adicionar ao final de `backend/tests/test_image_tasks.py`:

```python
import asyncio
from unittest.mock import patch, MagicMock

from app.services.image_service import ImageRateLimitError


class TestGenerateImagesRateLimit:
    def test_rate_limit_error_uses_longer_countdown(self):
        from app.workers.tasks.image_tasks import generate_images

        retry_calls = []

        def fake_retry(exc, countdown):
            retry_calls.append(countdown)
            raise exc  # simula o raise que o Celery faz internamente

        mock_self = MagicMock()
        mock_self.request.retries = 0
        mock_self.max_retries = 2
        mock_self.retry = fake_retry

        with patch(
            "app.workers.tasks.image_tasks.asyncio.run",
            side_effect=ImageRateLimitError("quota hit"),
        ):
            with pytest.raises(ImageRateLimitError):
                generate_images(mock_self, "listing-abc")

        assert retry_calls == [60], f"Expected countdown=60, got {retry_calls}"

    def test_generic_error_uses_short_countdown(self):
        from app.workers.tasks.image_tasks import generate_images

        retry_calls = []

        def fake_retry(exc, countdown):
            retry_calls.append(countdown)
            raise exc

        mock_self = MagicMock()
        mock_self.request.retries = 0
        mock_self.max_retries = 2
        mock_self.retry = fake_retry

        with patch(
            "app.workers.tasks.image_tasks.asyncio.run",
            side_effect=RuntimeError("network error"),
        ):
            with pytest.raises(RuntimeError):
                generate_images(mock_self, "listing-abc")

        assert retry_calls == [5], f"Expected countdown=5, got {retry_calls}"
```

---

- [ ] **Step 7: Rodar todos os testes**

```bash
docker compose exec backend pytest tests/test_image_service.py tests/test_image_tasks.py -v
```

Saída esperada: todos os testes passam (sem nenhum FAILED ou ERROR).

---

- [ ] **Step 8: Rodar o suite completo para confirmar ausência de regressões**

```bash
docker compose exec backend pytest tests/ -v
```

Saída esperada: todos os testes passam (incluindo `test_health.py`).

---

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/image_service.py backend/app/workers/tasks/image_tasks.py backend/tests/test_image_service.py backend/tests/test_image_tasks.py
git commit -m "fix: raise ImageRateLimitError on 429 and use 60s backoff in Celery retry"
```

---

## Self-Review

**Cobertura dos requisitos:**

| Fix | Tarefa | Coberto? |
|---|---|---|
| F-1: ensure_dimensions sem try/except | Task 1 | ✅ |
| F-1: call site atualizado | Task 1, Step 6 | ✅ |
| F-2: remover hasattr de error_message | Task 2 | ✅ |
| F-3: _mark_failed tolera falha de banco | Task 2 | ✅ |
| F-4: 429 → ImageRateLimitError | Task 3 | ✅ |
| F-4: Celery backoff 60s/120s para 429 | Task 3 | ✅ |

**Placeholder scan:** Nenhum TBD, TODO, "similar to", ou "add handling" encontrado.

**Consistência de tipos:**
- `ensure_dimensions` retorna `bytes | None` — call site em Task 1 Step 6 verifica `if img_bytes is None`.
- `ImageRateLimitError` definida em Task 3 Step 3 — importada lazy em Task 3 Step 5 e em test em Step 6.
- `_mark_failed(listing_id: str, error: str)` — assinatura idêntica nas Tasks 2 e 3.
