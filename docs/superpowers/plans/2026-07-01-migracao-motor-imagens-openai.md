# Migração do Motor de Imagens (Gemini → OpenAI) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trocar o motor de geração de pixels das imagens de anúncio de Gemini Imagen 4 para OpenAI gpt-image-1, mantendo o Gemini como motor de contingência acionável manualmente, com failover assimétrico (OpenAI→Gemini exige confirmação do usuário; Gemini→OpenAI é automático, só notifica).

**Architecture:** Nova abstração `ImageEngineProvider` (análoga ao `AIProvider` já existente para texto) com duas implementações (`GeminiImageEngine`, `OpenAIImageEngine`), um estado global singleton em `image_engine_state` (tabela nova) que guarda o motor ativo, um novo status de listing (`pending_image_engine_confirmation`) para pausar anúncios que precisam de decisão do usuário, e um endpoint de confirmação que reenfileira 1 ou N anúncios. O frontend expõe isso via um banner global (polling 8s) e um badge nos cards de imagem.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Celery 5, httpx (chamadas REST diretas à OpenAI e Gemini — sem SDK novo), pytest + pytest-asyncio. Frontend: Next.js 14, TanStack Query, shadcn/ui (`Badge`, `Button`), `sonner` (toast).

**Spec de referência:** `docs/superpowers/specs/2026-07-01-migracao-motor-imagens-openai-design.md`

## Global Constraints

- **Sem SDK novo da OpenAI** — usar `httpx` diretamente (mesmo padrão do `GeminiImageService` atual), evitando adicionar `openai` ao `requirements.txt`.
- **Imports lazy dentro de workers** — todo import usado dentro de `_generate_images_async` deve ficar dentro do corpo da função (padrão já usado em `image_tasks.py`), não no topo do arquivo.
- **`celery.chain` usa `.si()`**, nunca `.s()` — não se aplica diretamente a este plano (não criamos chains novas), mas o dispatch de `generate_images.delay()` deve seguir o padrão existente.
- **UPDATE atômico via `execution_options(synchronize_session=False)`** é reservado para dispatch entre workers Celery concorrentes (padrão documentado no `CLAUDE.md`) — o endpoint de confirmação criado aqui é acionado por uma requisição HTTP de usuário, não por workers concorrentes, então usa leitura+escrita simples (mesmo padrão de `trigger_image_generation` já existente em `listing_service.py`).
- **Gemini não muda de comportamento** — `GeminiImageEngine` deve continuar levantando exatamente as mesmas exceções que `GeminiImageService` levanta hoje (`ImageRateLimitError` em 429, `httpx.HTTPStatusError` em outros erros). Isso é só reorganização de arquivo, não reescrita de lógica.
- **Etapa 1 (prompt de imagem) não muda** — `AIProvider.generate_image_prompt` continua exatamente como está.
- **Commits em Conventional Commits**: `feat:`, `fix:`, `test:`, `docs:`.
- **Testes backend rodam via**: `docker compose exec backend python -m pytest <path> -v`.
- **Migrations aplicam via**: `docker compose exec backend alembic upgrade head`.

---

## Mapa de arquivos

| Arquivo | Tasks | Papel |
|---|---|---|
| `backend/app/models/image_engine_state.py` | 1 | Model novo — singleton de estado do motor |
| `backend/app/models/__init__.py` | 1 | Registrar novo model p/ Alembic |
| `backend/alembic/versions/b7e4a1c92f83_*.py` | 1 | Migration — cria tabela + seed |
| `backend/app/services/image_engines/base.py` | 2 | Interface `ImageEngineProvider` + exceções + prompt suffix compartilhado |
| `backend/app/services/image_engines/gemini_engine.py` | 3 | `GeminiImageEngine` (motor atual, reorganizado) |
| `backend/app/services/image_service.py` | 3 | Remove `GeminiImageService`/`ImageRateLimitError` (movidos) |
| `backend/app/config.py` | 4 | Settings `openai_api_key`, `openai_image_model` |
| `.env.example` | 4 | Novas variáveis de ambiente |
| `backend/app/services/image_engines/openai_engine.py` | 4 | `OpenAIImageEngine` + `check_openai_health()` |
| `backend/app/services/image_engines/service.py` | 5 | Factory `get_engine_instance`, `get_engine_state`, `get_engine_label` |
| `backend/app/workers/tasks/image_tasks.py` | 6 | Fluxo de decisão de motor dentro de `_generate_images_async` |
| `backend/app/services/listing_service.py` | 7 | `confirm_image_engine()` |
| `backend/app/schemas/listing.py` | 7 | `ImageEngineConfirmRequest` |
| `backend/app/api/v1/endpoints/listings.py` | 7 | Endpoint `POST .../confirm_image_engine` |
| `backend/app/schemas/system.py` | 8 | `ImageEngineStateOut` (novo arquivo) |
| `backend/app/api/v1/endpoints/system.py` | 8 | Endpoint `GET /system/image-engine` (novo arquivo) |
| `backend/app/api/v1/router.py` | 8 | Registrar router `system` |
| `frontend/src/types/listing.ts` | 9 | Novo status no enum/labels |
| `frontend/src/components/listings/ListingStatusBadge.tsx` | 9 | Cor/variant do novo status |
| `frontend/src/components/listings/PipelineBoard.tsx` | 9 | Novo status na coluna "Imagens" |
| `frontend/src/types/system.ts` | 10 | Tipo `ImageEngineState` (novo arquivo) |
| `frontend/src/lib/api/system.ts` | 10 | `getImageEngineState()` (novo arquivo) |
| `frontend/src/lib/api/listings.ts` | 10 | `confirmImageEngine()` |
| `frontend/src/components/system/ImageEngineBanner.tsx` | 11 | Banner global (novo arquivo) |
| `frontend/src/app/(dashboard)/layout.tsx` | 11 | Monta o banner |
| `frontend/src/app/(dashboard)/listings/[id]/page.tsx` | 12 | Badge de motor + card de confirmação |

---

## Task 1: Model + migration `image_engine_state`

**Files:**
- Create: `backend/app/models/image_engine_state.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/b7e4a1c92f83_add_image_engine_state.py`

**Interfaces:**
- Produces: `ImageEngineState` (SQLAlchemy model) com colunas `id`, `current_engine`, `last_openai_error`, `last_switch_to_openai_at`, `updated_at`. Consumido pelas Tasks 5, 6, 7, 8.

- [ ] **Step 1: Criar o model**

Criar `backend/app/models/image_engine_state.py`:

```python
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4
from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ImageEngineState(Base):
    """Linha única (singleton) que guarda qual motor de geração de imagem está ativo."""
    __tablename__ = "image_engine_state"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    current_engine: Mapped[str] = mapped_column(String(20), nullable=False, default="openai")
    last_openai_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    last_switch_to_openai_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
```

- [ ] **Step 2: Registrar o model em `app/models/__init__.py`**

Editar `backend/app/models/__init__.py` — adicionar o import e a entrada em `__all__`:

```python
from app.models.seller import Seller
from app.models.user import User
from app.models.user_seller_access import UserSellerAccess
from app.models.product import Product
from app.models.listing import Listing
from app.models.listing_job import ListingJob
from app.models.listing_title import ListingTitle
from app.models.listing_attribute import ListingAttribute
from app.models.listing_image import ListingImage
from app.models.listing_description import ListingDescription
from app.models.product_image import ProductImage
from app.models.batch_import import BatchImport, BatchImportRow
from app.models.seller_title_config import SellerTitleConfig  # noqa: F401
from app.models.image_engine_state import ImageEngineState

__all__ = [
    "Seller", "User", "UserSellerAccess", "Product", "Listing", "ListingJob",
    "ListingTitle", "ListingAttribute", "ListingImage", "ListingDescription",
    "ProductImage", "BatchImport", "BatchImportRow", "SellerTitleConfig",
    "ImageEngineState",
]
```

- [ ] **Step 3: Criar a migration**

Criar `backend/alembic/versions/b7e4a1c92f83_add_image_engine_state.py`:

```python
"""add_image_engine_state

Revision ID: b7e4a1c92f83
Revises: fbf3f83bf9e4
Create Date: 2026-07-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'b7e4a1c92f83'
down_revision = 'fbf3f83bf9e4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'image_engine_state',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('current_engine', sa.String(length=20), nullable=False, server_default='openai'),
        sa.Column('last_openai_error', sa.String(length=500), nullable=True),
        sa.Column('last_switch_to_openai_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.execute(
        "INSERT INTO image_engine_state (id, current_engine, updated_at) "
        "VALUES (gen_random_uuid(), 'openai', now())"
    )


def downgrade() -> None:
    op.drop_table('image_engine_state')
```

- [ ] **Step 4: Aplicar a migration e verificar**

Run: `docker compose exec backend alembic upgrade head`
Expected: saída termina em `Running upgrade fbf3f83bf9e4 -> b7e4a1c92f83, add_image_engine_state` sem erro.

Run: `docker compose exec postgres psql -U mlb_user -d publicar_ad_mlb -c "SELECT current_engine FROM image_engine_state;"`
Expected: uma linha, `current_engine = openai`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/image_engine_state.py backend/app/models/__init__.py backend/alembic/versions/b7e4a1c92f83_add_image_engine_state.py
git commit -m "feat: adiciona tabela image_engine_state (motor de imagem ativo)"
```

---

## Task 2: Interface `ImageEngineProvider` + exceções compartilhadas

**Files:**
- Create: `backend/app/services/image_engines/__init__.py`
- Create: `backend/app/services/image_engines/base.py`

**Interfaces:**
- Consumes: nada (arquivo base, sem dependências do projeto).
- Produces: `ImageEngineProvider` (ABC, método `async def generate(self, prompt: str) -> list[bytes]`), `ImageRateLimitError`, `ImageEngineUnavailableError`, `PROMPT_SUFFIX: str`. Consumidos pelas Tasks 3, 4, 5, 6.

- [ ] **Step 1: Criar o pacote e a interface**

Criar `backend/app/services/image_engines/__init__.py` (vazio):

```python
```

Criar `backend/app/services/image_engines/base.py`:

```python
from abc import ABC, abstractmethod


class ImageRateLimitError(Exception):
    """Erro de rate limit (HTTP 429) do motor de imagem — sinaliza ao Celery
    para usar um backoff mais longo (usado hoje só pelo Gemini)."""


class ImageEngineUnavailableError(Exception):
    """Erro de infraestrutura (timeout, HTTP 5xx ou 429) do motor de imagem
    atualmente ativo. Só é levantado pelo OpenAIImageEngine — sinaliza ao
    pipeline que a troca de motor deve ser oferecida ao usuário (RF4/RF5)."""


# Sufixo adicionado ao prompt positivo em todos os motores — reforça as regras
# de fundo branco/produto isolado que os prompts de texto nem sempre respeitam.
PROMPT_SUFFIX = (
    " Strict requirements: pure white (#FFFFFF) background only, product isolated and centered, "
    "no people, no hands, no text, no watermarks, no banners, no plants, no leaves, "
    "no furniture, no rooms, no shadows, no lifestyle elements, no extra products."
)


class ImageEngineProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str) -> list[bytes]:
        """Gera imagens a partir do prompt. Retorna lista de bytes (JPEG/PNG)."""
```

- [ ] **Step 2: Verificar que importa sem erro**

Run: `docker compose exec backend python -c "from app.services.image_engines.base import ImageEngineProvider, ImageRateLimitError, ImageEngineUnavailableError, PROMPT_SUFFIX; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/image_engines/__init__.py backend/app/services/image_engines/base.py
git commit -m "feat: adiciona interface ImageEngineProvider e exceções compartilhadas"
```

---

## Task 3: Mover Gemini para `GeminiImageEngine`

**Files:**
- Create: `backend/app/services/image_engines/gemini_engine.py`
- Modify: `backend/app/services/image_service.py` (remover `GeminiImageService` e `ImageRateLimitError`)
- Create: `backend/tests/test_image_engines_gemini.py`
- Modify: `backend/tests/test_image_service.py` (remover `TestGeminiImageService429` — migrado)
- Modify: `backend/tests/test_image_tasks.py` (atualizar import de `ImageRateLimitError`)

**Interfaces:**
- Consumes: `ImageEngineProvider`, `ImageRateLimitError`, `PROMPT_SUFFIX` de `app.services.image_engines.base` (Task 2).
- Produces: `GeminiImageEngine` (classe) em `app.services.image_engines.gemini_engine`. Consumido pelas Tasks 5, 6.

- [ ] **Step 1: Escrever o teste (vai falhar — módulo não existe ainda)**

Criar `backend/tests/test_image_engines_gemini.py`:

```python
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.image_engines.base import ImageRateLimitError
from app.services.image_engines.gemini_engine import GeminiImageEngine


class TestGeminiImageEngine429:
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
            engine = GeminiImageEngine()
            with pytest.raises(ImageRateLimitError):
                await engine.generate("test prompt")

    @pytest.mark.asyncio
    async def test_other_errors_raise_http_status_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.is_success = False
        mock_response.text = "Internal Server Error"
        mock_response.request = MagicMock()

        mock_post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            engine = GeminiImageEngine()
            with pytest.raises(httpx.HTTPStatusError):
                await engine.generate("test prompt")
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

Run: `docker compose exec backend python -m pytest tests/test_image_engines_gemini.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.image_engines.gemini_engine'`

- [ ] **Step 3: Criar `gemini_engine.py` (mesma lógica de hoje, só reorganizada)**

Criar `backend/app/services/image_engines/gemini_engine.py`:

```python
import base64
import httpx

from app.config import get_settings
from app.services.image_engines.base import (
    ImageEngineProvider,
    ImageRateLimitError,
    PROMPT_SUFFIX,
)

_IMAGEN_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "imagen-4.0-fast-generate-001:predict"
)


class GeminiImageEngine(ImageEngineProvider):
    def __init__(self) -> None:
        self.settings = get_settings()

    async def generate(self, prompt: str) -> list[bytes]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                _IMAGEN_URL,
                headers={"X-goog-api-key": self.settings.gemini_api_key},
                json={
                    "instances": [{"prompt": prompt + PROMPT_SUFFIX}],
                    "parameters": {
                        "sampleCount": 4,
                        "aspectRatio": "1:1",
                        "personGeneration": "DONT_ALLOW",
                    },
                },
            )
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
        predictions = resp.json().get("predictions", [])
        return [base64.b64decode(p["bytesBase64Encoded"]) for p in predictions]
```

- [ ] **Step 4: Rodar o teste de novo e confirmar que passa**

Run: `docker compose exec backend python -m pytest tests/test_image_engines_gemini.py -v`
Expected: `2 passed`

- [ ] **Step 5: Remover `GeminiImageService`/`ImageRateLimitError` de `image_service.py`**

Editar `backend/app/services/image_service.py` — remover as linhas 10-13 (`_IMAGEN_URL`, `_PROMPT_SUFFIX`), a classe `ImageRateLimitError` (linhas 27-28) e a classe `GeminiImageService` (linhas 31-60). O arquivo final deve conter só `MLPictureService`, `validate_image`, `ensure_dimensions` e as constantes `ML_PICTURES_URL`, `_MIN_DIMENSION`, `_RECOMMENDED_DIM`, `_MAX_BYTES`:

```python
import asyncio
import io

import httpx
from PIL import Image

ML_PICTURES_URL = "https://api.mercadolibre.com/pictures/items/upload"
_MIN_DIMENSION = 500       # ML minimum accepted
_RECOMMENDED_DIM = 1024    # tamanho alvo após upscale (aceitável para ML, abaixo do ideal 1200)
_MAX_BYTES = 10 * 1024 * 1024


class MLPictureService:
    async def upload(self, image_bytes: bytes, access_token: str) -> str:
        last_exc: Exception = RuntimeError("ML CDN upload failed")
        async with httpx.AsyncClient(timeout=60.0) as client:
            for attempt in range(3):
                if attempt > 0:
                    await asyncio.sleep(5 * (2 ** (attempt - 1)))
                try:
                    resp = await client.post(
                        ML_PICTURES_URL,
                        headers={"Authorization": f"Bearer {access_token}"},
                        files={"file": ("image.jpg", image_bytes, "image/jpeg")},
                    )
                    if resp.status_code < 500:
                        resp.raise_for_status()
                        return resp.json()["id"]
                    last_exc = RuntimeError(f"ML CDN {resp.status_code}: {resp.text}")
                except Exception as exc:
                    last_exc = exc
        raise last_exc


def validate_image(image_bytes: bytes) -> bool:
    if len(image_bytes) > _MAX_BYTES:
        return False
    try:
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        return min(w, h) > 0
    except Exception:
        return False


def ensure_dimensions(image_bytes: bytes, target: int = _RECOMMENDED_DIM) -> bytes | None:
    """Upscale to target×target if smaller; always returns JPEG bytes. Returns None if bytes are corrupted."""
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

- [ ] **Step 6: Remover a classe migrada de `test_image_service.py`**

Editar `backend/tests/test_image_service.py` — remover a classe `TestGeminiImageService429` (linhas 48-79) e o import de `GeminiImageService`/`ImageRateLimitError`/`httpx` que não são mais usados nesse arquivo. Arquivo final:

```python
import io
from PIL import Image

from app.services.image_service import ensure_dimensions


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

- [ ] **Step 7: Atualizar o import de `ImageRateLimitError` em `test_image_tasks.py`**

Editar `backend/tests/test_image_tasks.py` linha 7:

```python
from app.services.image_engines.base import ImageRateLimitError
```

- [ ] **Step 8: Rodar toda a suíte de imagens e confirmar que passa**

Run: `docker compose exec backend python -m pytest tests/test_image_service.py tests/test_image_engines_gemini.py tests/test_image_tasks.py -v`
Expected: todos os testes de `test_image_service.py` e `test_image_engines_gemini.py` passam. `test_image_tasks.py` pode ter falhas nesse ponto (será corrigido na Task 6) — se `TestGenerateImagesRateLimit` já passar sozinho, ótimo; se `TestGenerateImagesIdempotency::test_proceeds_when_status_is_generating_images` falhar por ainda referenciar `app.services.image_service.GeminiImageService`, está esperado — será corrigido na Task 6.

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/image_engines/gemini_engine.py backend/app/services/image_service.py backend/tests/test_image_engines_gemini.py backend/tests/test_image_service.py backend/tests/test_image_tasks.py
git commit -m "refactor: move GeminiImageService para GeminiImageEngine (image_engines/)"
```

---

## Task 4: `OpenAIImageEngine` + `check_openai_health()`

**Files:**
- Modify: `backend/app/config.py`
- Modify: `.env.example`
- Create: `backend/app/services/image_engines/openai_engine.py`
- Create: `backend/tests/test_image_engines_openai.py`

**Interfaces:**
- Consumes: `ImageEngineProvider`, `ImageEngineUnavailableError`, `PROMPT_SUFFIX` de `app.services.image_engines.base` (Task 2). `get_settings()` de `app.config`.
- Produces: `OpenAIImageEngine` (classe) e `async def check_openai_health() -> bool`, ambos em `app.services.image_engines.openai_engine`. Consumidos pelas Tasks 5, 6.

- [ ] **Step 1: Adicionar as settings**

Editar `backend/app/config.py` — adicionar após o bloco `# IA` (linha 33, após `claude_model`):

```python
    # OpenAI (motor de imagem alternativo — gpt-image-1)
    openai_api_key: str = ""
    openai_image_model: str = "gpt-image-1"
```

- [ ] **Step 2: Adicionar as variáveis em `.env.example`**

Editar `.env.example` — adicionar após o bloco `# Anthropic Claude (alternativa)`:

```
# --- OpenAI (motor de geração de imagens) ---
OPENAI_API_KEY=
OPENAI_IMAGE_MODEL=gpt-image-1
```

- [ ] **Step 3: Escrever os testes (vão falhar — módulo não existe ainda)**

Criar `backend/tests/test_image_engines_openai.py`:

```python
import base64
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.image_engines.base import ImageEngineUnavailableError
from app.services.image_engines.openai_engine import OpenAIImageEngine, check_openai_health


def _b64_image() -> str:
    return base64.b64encode(b"fake-image-bytes").decode()


class TestOpenAIImageEngineGenerate:
    @pytest.mark.asyncio
    async def test_success_returns_decoded_images(self):
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {"data": [{"b64_json": _b64_image()}]}

        mock_post = AsyncMock(return_value=mock_response)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            engine = OpenAIImageEngine()
            result = await engine.generate("a product photo")

        assert result == [b"fake-image-bytes"]

    @pytest.mark.asyncio
    async def test_429_raises_unavailable_error(self):
        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 429
        mock_response.text = "Rate limited"
        mock_response.request = MagicMock()

        mock_post = AsyncMock(return_value=mock_response)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            engine = OpenAIImageEngine()
            with pytest.raises(ImageEngineUnavailableError):
                await engine.generate("prompt")

    @pytest.mark.asyncio
    async def test_500_raises_unavailable_error(self):
        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.request = MagicMock()

        mock_post = AsyncMock(return_value=mock_response)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            engine = OpenAIImageEngine()
            with pytest.raises(ImageEngineUnavailableError):
                await engine.generate("prompt")

    @pytest.mark.asyncio
    async def test_timeout_raises_unavailable_error(self):
        mock_post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            engine = OpenAIImageEngine()
            with pytest.raises(ImageEngineUnavailableError):
                await engine.generate("prompt")

    @pytest.mark.asyncio
    async def test_content_policy_400_raises_http_status_error_not_unavailable(self):
        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 400
        mock_response.text = "Your request was rejected by content policy"
        mock_response.request = MagicMock()

        mock_post = AsyncMock(return_value=mock_response)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            engine = OpenAIImageEngine()
            with pytest.raises(httpx.HTTPStatusError):
                await engine.generate("prompt")


class TestCheckOpenAIHealth:
    @pytest.mark.asyncio
    async def test_returns_true_on_200(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get = AsyncMock(return_value=mock_response)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.get = mock_get
            assert await check_openai_health() is True

    @pytest.mark.asyncio
    async def test_returns_false_on_error_status(self):
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_get = AsyncMock(return_value=mock_response)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.get = mock_get
            assert await check_openai_health() is False

    @pytest.mark.asyncio
    async def test_returns_false_on_network_exception(self):
        mock_get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.get = mock_get
            assert await check_openai_health() is False
```

- [ ] **Step 4: Rodar os testes e confirmar que falham**

Run: `docker compose exec backend python -m pytest tests/test_image_engines_openai.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.image_engines.openai_engine'`

- [ ] **Step 5: Implementar `openai_engine.py`**

Criar `backend/app/services/image_engines/openai_engine.py`:

```python
import base64
import httpx

from app.config import get_settings
from app.services.image_engines.base import (
    ImageEngineProvider,
    ImageEngineUnavailableError,
    PROMPT_SUFFIX,
)

_OPENAI_IMAGES_URL = "https://api.openai.com/v1/images/generations"
_OPENAI_MODELS_URL = "https://api.openai.com/v1/models"


class OpenAIImageEngine(ImageEngineProvider):
    def __init__(self) -> None:
        self.settings = get_settings()

    async def generate(self, prompt: str) -> list[bytes]:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    _OPENAI_IMAGES_URL,
                    headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
                    json={
                        "model": self.settings.openai_image_model,
                        "prompt": prompt + PROMPT_SUFFIX,
                        "n": 4,
                        "size": "1024x1024",
                        "quality": "medium",
                        "background": "opaque",
                    },
                )
        except httpx.TimeoutException as exc:
            raise ImageEngineUnavailableError(f"Timeout ao chamar a OpenAI: {exc}") from exc

        if not resp.is_success:
            if resp.status_code == 429 or resp.status_code >= 500:
                raise ImageEngineUnavailableError(
                    f"OpenAI API {resp.status_code}: {resp.text[:600]}"
                )
            raise httpx.HTTPStatusError(
                f"OpenAI API {resp.status_code}: {resp.text[:600]}",
                request=resp.request,
                response=resp,
            )
        data = resp.json().get("data", [])
        return [base64.b64decode(item["b64_json"]) for item in data]


async def check_openai_health() -> bool:
    """Checagem leve de conectividade — usada quando o motor atual é Gemini,
    para decidir se já pode voltar a usar a OpenAI automaticamente (RF4)."""
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                _OPENAI_MODELS_URL,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            )
        return resp.status_code == 200
    except httpx.HTTPError:
        return False
```

- [ ] **Step 6: Rodar os testes e confirmar que passam**

Run: `docker compose exec backend python -m pytest tests/test_image_engines_openai.py -v`
Expected: `8 passed`

- [ ] **Step 7: Commit**

```bash
git add backend/app/config.py .env.example backend/app/services/image_engines/openai_engine.py backend/tests/test_image_engines_openai.py
git commit -m "feat: adiciona OpenAIImageEngine (gpt-image-1) e checagem de saúde da API"
```

---

## Task 5: Factory `get_engine_instance` / `get_engine_state` / `get_engine_label`

**Files:**
- Create: `backend/app/services/image_engines/service.py`
- Create: `backend/tests/test_image_engines_service.py`

**Interfaces:**
- Consumes: `ImageEngineState` (Task 1), `ImageEngineProvider`/`GeminiImageEngine`/`OpenAIImageEngine` (Tasks 2-4).
- Produces: `async def get_engine_state(db: AsyncSession) -> ImageEngineState`, `def get_engine_instance(name: str) -> ImageEngineProvider`, `def get_engine_label(name: str) -> str` em `app.services.image_engines.service`. Consumidos pela Task 6 (`image_tasks.py`) e Task 8 (endpoint `system`).

- [ ] **Step 1: Escrever os testes (vão falhar — módulo não existe ainda)**

Criar `backend/tests/test_image_engines_service.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.image_engines.gemini_engine import GeminiImageEngine
from app.services.image_engines.openai_engine import OpenAIImageEngine


class TestGetEngineState:
    @pytest.mark.asyncio
    async def test_returns_the_single_row(self):
        from app.services.image_engines.service import get_engine_state

        mock_state = MagicMock()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_state
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_engine_state(mock_db)

        assert result is mock_state


class TestGetEngineInstance:
    def test_returns_openai_engine(self):
        from app.services.image_engines.service import get_engine_instance

        assert isinstance(get_engine_instance("openai"), OpenAIImageEngine)

    def test_returns_gemini_engine(self):
        from app.services.image_engines.service import get_engine_instance

        assert isinstance(get_engine_instance("gemini"), GeminiImageEngine)


class TestGetEngineLabel:
    def test_openai_label_includes_configured_model(self):
        from app.services.image_engines.service import get_engine_label

        label = get_engine_label("openai")
        assert "OpenAI" in label
        assert "gpt-image-1" in label

    def test_gemini_label(self):
        from app.services.image_engines.service import get_engine_label

        assert get_engine_label("gemini") == "Gemini · imagen-4.0-fast"
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `docker compose exec backend python -m pytest tests/test_image_engines_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.image_engines.service'`

- [ ] **Step 3: Implementar `service.py`**

Criar `backend/app/services/image_engines/service.py`:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.image_engine_state import ImageEngineState
from app.services.image_engines.base import ImageEngineProvider


async def get_engine_state(db: AsyncSession) -> ImageEngineState:
    result = await db.execute(select(ImageEngineState))
    return result.scalar_one()


def get_engine_instance(name: str) -> ImageEngineProvider:
    if name == "openai":
        from app.services.image_engines.openai_engine import OpenAIImageEngine
        return OpenAIImageEngine()
    from app.services.image_engines.gemini_engine import GeminiImageEngine
    return GeminiImageEngine()


def get_engine_label(name: str) -> str:
    if name == "openai":
        from app.config import get_settings
        return f"OpenAI · {get_settings().openai_image_model}"
    return "Gemini · imagen-4.0-fast"
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `docker compose exec backend python -m pytest tests/test_image_engines_service.py -v`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/image_engines/service.py backend/tests/test_image_engines_service.py
git commit -m "feat: adiciona factory get_engine_instance/get_engine_state/get_engine_label"
```

---

## Task 6: Fluxo de decisão em `_generate_images_async`

**Files:**
- Modify: `backend/app/workers/tasks/image_tasks.py`
- Modify: `backend/tests/test_image_tasks.py`

**Interfaces:**
- Consumes: `get_engine_state`, `get_engine_instance` (Task 5); `check_openai_health` (Task 4); `ImageEngineUnavailableError`, `ImageRateLimitError` (Task 2).
- Produces: `_generate_images_async` passa a decidir motor dinamicamente e a colocar o listing em `pending_image_engine_confirmation` quando a OpenAI falha por infraestrutura.

**Contexto — o que existe hoje** (`backend/app/workers/tasks/image_tasks.py:1-134`): a função `_generate_images_async` sempre usa `GeminiImageService().generate(prompt)` direto, sem checar motor nenhum. Vamos substituir esse trecho.

- [ ] **Step 1: Atualizar o import no topo da função (linha 20)**

Trocar:
```python
    from app.services.image_service import GeminiImageService, MLPictureService, validate_image, ensure_dimensions
```
Por:
```python
    from app.services.image_service import MLPictureService, validate_image, ensure_dimensions
```

- [ ] **Step 2: Substituir o trecho de geração (linhas 64-105 do arquivo atual)**

Localizar, dentro de `_generate_images_async`, o bloco que começa em `# Sem imagens existentes — gera com IA` e vai até o fim do `for img_bytes in raw_images:` (incluindo a criação de `ProductImage` com `source="gemini"` fixo). Substituir por:

```python
        # Sem imagens existentes — gera com IA
        from datetime import datetime, timezone
        from app.services.image_engines.base import ImageEngineUnavailableError
        from app.services.image_engines.openai_engine import check_openai_health
        from app.services.image_engines.service import get_engine_instance, get_engine_state

        seller = (
            await db.execute(select(Seller).where(Seller.id == listing.seller_id))
        ).scalar_one()
        access_token = await _fetch_upload_token(seller, db)

        engine_state = await get_engine_state(db)

        if engine_state.current_engine == "gemini" and await check_openai_health():
            engine_state.current_engine = "openai"
            engine_state.last_openai_error = None
            engine_state.last_switch_to_openai_at = datetime.now(timezone.utc)
            await db.commit()

        ai = get_ai_provider()
        prompt = await ai.generate_image_prompt(
            brand=listing.sku_brand,
            title=listing.selected_title or "",
            description=listing.sku_description,
        )

        engine = get_engine_instance(engine_state.current_engine)
        source_label = engine_state.current_engine

        try:
            raw_images = await engine.generate(prompt)
        except ImageEngineUnavailableError as exc:
            engine_state.last_openai_error = str(exc)[:500]
            await db.commit()
            listing.failed_step = listing.status
            listing.status = "pending_image_engine_confirmation"
            listing.error_message = str(exc)[:500]
            await db.commit()
            return {"listing_id": listing_id, "pending_image_engine_confirmation": True}

        ml_pic = MLPictureService()
        saved = 0

        for img_bytes in raw_images:
            if not validate_image(img_bytes):
                continue

            img_bytes = ensure_dimensions(img_bytes)
            if img_bytes is None:
                continue
            ml_picture_id = await ml_pic.upload(img_bytes, access_token)

            db.add(ListingImage(
                listing_id=listing.id,
                ml_picture_id=ml_picture_id,
                status="uploaded",
                sort_order=saved,
            ))

            # Registra no índice SKU→imagem (não aprovada ainda)
            if sku:
                db.add(ProductImage(
                    seller_id=listing.seller_id,
                    sku=sku,
                    ml_picture_id=ml_picture_id,
                    source=source_label,
                    is_approved=False,
                ))

            saved += 1

        if saved == 0:
            raise RuntimeError(f"Nenhuma imagem válida foi gerada pelo motor '{source_label}'")
```

- [ ] **Step 3: Atualizar o import de `ImageRateLimitError` na task Celery (linha 167)**

No corpo de `generate_images` (o `@celery_app.task`), trocar:
```python
        from app.services.image_service import ImageRateLimitError
```
Por:
```python
        from app.services.image_engines.base import ImageRateLimitError
```

- [ ] **Step 4: Corrigir o teste `TestGenerateImagesIdempotency::test_proceeds_when_status_is_generating_images` (quebrado desde a Task 3)**

Esse teste patcheava `app.services.image_service.GeminiImageService` para verificar que o guard de idempotência não bloqueia o fluxo. Agora precisa mockar `Seller` e `ImageEngineState` também, e verificar `OpenAIImageEngine` (motor padrão). Substituir o teste em `backend/tests/test_image_tasks.py`:

```python
    @pytest.mark.asyncio
    async def test_proceeds_when_status_is_generating_images(self):
        """Verificação negativa: guard NÃO aborta quando status está correto."""
        from app.workers.tasks.image_tasks import _generate_images_async

        mock_listing = MagicMock()
        mock_listing.status = "generating_images"
        mock_listing.sku_external_id = None
        mock_listing.seller_id = "sid"
        mock_listing.created_via = "manual"

        mock_engine_state = MagicMock()
        mock_engine_state.current_engine = "openai"

        mock_db = AsyncMock()
        execute_calls = [0]

        async def execute_side(stmt):
            execute_calls[0] += 1
            r = MagicMock()
            if execute_calls[0] == 1:      # SELECT Listing
                r.scalar_one = MagicMock(return_value=mock_listing)
            elif execute_calls[0] == 2:    # SELECT Seller
                r.scalar_one = MagicMock(return_value=MagicMock())
            else:                          # SELECT ImageEngineState
                r.scalar_one = MagicMock(return_value=mock_engine_state)
            return r

        mock_db.execute = execute_side
        mock_db.commit = AsyncMock()

        with patch("app.database.worker_session", lambda: _mock_session(mock_db)), \
             patch("app.workers.tasks.image_tasks._fetch_upload_token", new_callable=AsyncMock, return_value="tok"), \
             patch("app.services.ai.service.get_ai_provider", return_value=AsyncMock(
                 generate_image_prompt=AsyncMock(return_value="prompt")
             )), \
             patch("app.services.image_engines.openai_engine.OpenAIImageEngine") as mock_openai_cls:
            mock_openai_cls.return_value.generate = AsyncMock(return_value=[])
            try:
                await _generate_images_async("listing-id")
            except Exception:
                pass  # pode falhar após o guard — o que importa é que chegou aqui

        mock_openai_cls.assert_called_once()
```

Remover o `patch("app.services.image_service.GeminiImageService")` desse teste (não existe mais nesse módulo).

- [ ] **Step 5: Adicionar os 3 testes de fluxo de decisão**

Adicionar ao final de `backend/tests/test_image_tasks.py`:

```python
class TestImageEngineDecisionFlow:
    @pytest.mark.asyncio
    async def test_openai_infra_failure_sets_pending_confirmation(self):
        from app.workers.tasks.image_tasks import _generate_images_async
        from app.services.image_engines.base import ImageEngineUnavailableError

        mock_listing = MagicMock()
        mock_listing.id = "lid"
        mock_listing.status = "generating_images"
        mock_listing.sku_external_id = None
        mock_listing.seller_id = "sid"
        mock_listing.created_via = "manual"

        mock_engine_state = MagicMock()
        mock_engine_state.current_engine = "openai"

        mock_db = AsyncMock()
        execute_calls = [0]

        async def execute_side(stmt):
            execute_calls[0] += 1
            r = MagicMock()
            if execute_calls[0] == 1:
                r.scalar_one = MagicMock(return_value=mock_listing)
            elif execute_calls[0] == 2:
                r.scalar_one = MagicMock(return_value=MagicMock())
            else:
                r.scalar_one = MagicMock(return_value=mock_engine_state)
            return r

        mock_db.execute = execute_side
        mock_db.commit = AsyncMock()

        with patch("app.database.worker_session", lambda: _mock_session(mock_db)), \
             patch("app.workers.tasks.image_tasks._fetch_upload_token", new_callable=AsyncMock, return_value="tok"), \
             patch("app.services.ai.service.get_ai_provider", return_value=AsyncMock(
                 generate_image_prompt=AsyncMock(return_value="prompt")
             )), \
             patch("app.services.image_engines.openai_engine.OpenAIImageEngine") as mock_openai_cls:
            mock_openai_cls.return_value.generate = AsyncMock(
                side_effect=ImageEngineUnavailableError("timeout")
            )
            result = await _generate_images_async("lid")

        assert result == {"listing_id": "lid", "pending_image_engine_confirmation": True}
        assert mock_listing.status == "pending_image_engine_confirmation"
        assert mock_engine_state.last_openai_error == "timeout"

    @pytest.mark.asyncio
    async def test_gemini_auto_switches_back_when_openai_healthy(self):
        from app.workers.tasks.image_tasks import _generate_images_async

        mock_listing = MagicMock()
        mock_listing.id = "lid"
        mock_listing.status = "generating_images"
        mock_listing.sku_external_id = None
        mock_listing.seller_id = "sid"
        mock_listing.created_via = "manual"

        mock_engine_state = MagicMock()
        mock_engine_state.current_engine = "gemini"

        mock_db = AsyncMock()
        execute_calls = [0]

        async def execute_side(stmt):
            execute_calls[0] += 1
            r = MagicMock()
            if execute_calls[0] == 1:
                r.scalar_one = MagicMock(return_value=mock_listing)
            elif execute_calls[0] == 2:
                r.scalar_one = MagicMock(return_value=MagicMock())
            else:
                r.scalar_one = MagicMock(return_value=mock_engine_state)
            return r

        mock_db.execute = execute_side
        mock_db.commit = AsyncMock()

        with patch("app.database.worker_session", lambda: _mock_session(mock_db)), \
             patch("app.workers.tasks.image_tasks._fetch_upload_token", new_callable=AsyncMock, return_value="tok"), \
             patch("app.services.ai.service.get_ai_provider", return_value=AsyncMock(
                 generate_image_prompt=AsyncMock(return_value="prompt")
             )), \
             patch("app.services.image_engines.openai_engine.check_openai_health", new_callable=AsyncMock, return_value=True), \
             patch("app.services.image_engines.openai_engine.OpenAIImageEngine") as mock_openai_cls:
            mock_openai_cls.return_value.generate = AsyncMock(return_value=[])
            try:
                await _generate_images_async("lid")
            except RuntimeError:
                pass  # "Nenhuma imagem válida" — irrelevante para este teste

        assert mock_engine_state.current_engine == "openai"
        assert mock_engine_state.last_openai_error is None
        assert mock_engine_state.last_switch_to_openai_at is not None
        mock_openai_cls.return_value.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_gemini_stays_when_openai_still_unhealthy(self):
        from app.workers.tasks.image_tasks import _generate_images_async

        mock_listing = MagicMock()
        mock_listing.id = "lid"
        mock_listing.status = "generating_images"
        mock_listing.sku_external_id = None
        mock_listing.seller_id = "sid"
        mock_listing.created_via = "manual"

        mock_engine_state = MagicMock()
        mock_engine_state.current_engine = "gemini"

        mock_db = AsyncMock()
        execute_calls = [0]

        async def execute_side(stmt):
            execute_calls[0] += 1
            r = MagicMock()
            if execute_calls[0] == 1:
                r.scalar_one = MagicMock(return_value=mock_listing)
            elif execute_calls[0] == 2:
                r.scalar_one = MagicMock(return_value=MagicMock())
            else:
                r.scalar_one = MagicMock(return_value=mock_engine_state)
            return r

        mock_db.execute = execute_side
        mock_db.commit = AsyncMock()

        with patch("app.database.worker_session", lambda: _mock_session(mock_db)), \
             patch("app.workers.tasks.image_tasks._fetch_upload_token", new_callable=AsyncMock, return_value="tok"), \
             patch("app.services.ai.service.get_ai_provider", return_value=AsyncMock(
                 generate_image_prompt=AsyncMock(return_value="prompt")
             )), \
             patch("app.services.image_engines.openai_engine.check_openai_health", new_callable=AsyncMock, return_value=False), \
             patch("app.services.image_engines.gemini_engine.GeminiImageEngine") as mock_gemini_cls:
            mock_gemini_cls.return_value.generate = AsyncMock(return_value=[])
            try:
                await _generate_images_async("lid")
            except RuntimeError:
                pass

        assert mock_engine_state.current_engine == "gemini"
        mock_gemini_cls.return_value.generate.assert_called_once()
```

- [ ] **Step 6: Rodar toda a suíte de imagens e confirmar que passa**

Run: `docker compose exec backend python -m pytest tests/test_image_service.py tests/test_image_engines_gemini.py tests/test_image_engines_openai.py tests/test_image_engines_service.py tests/test_image_tasks.py tests/test_batch_chain.py -v`
Expected: todos passam (a suíte completa relacionada a imagens/batch, incluindo `TestRemovedInternalDispatch` que não foi tocada).

- [ ] **Step 7: Commit**

```bash
git add backend/app/workers/tasks/image_tasks.py backend/tests/test_image_tasks.py
git commit -m "feat: integra fluxo de decisão de motor (OpenAI/Gemini) em generate_images"
```

---

## Task 7: `confirm_image_engine` (service + endpoint)

**Files:**
- Modify: `backend/app/services/listing_service.py`
- Modify: `backend/app/schemas/listing.py`
- Modify: `backend/app/api/v1/endpoints/listings.py`
- Create: `backend/tests/test_image_engine_confirm.py`

**Interfaces:**
- Consumes: `ImageEngineState` (Task 1), `generate_images` (task Celery já existente).
- Produces: `ListingService.confirm_image_engine(listing, action) -> None`; endpoint `POST /api/v1/listings/{listing_id}/pipeline/confirm_image_engine`.

- [ ] **Step 1: Escrever os testes (vão falhar — método não existe ainda)**

Criar `backend/tests/test_image_engine_confirm.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestConfirmImageEngine:
    @pytest.mark.asyncio
    async def test_use_gemini_switches_state_and_reenqueues_all_pending(self):
        from app.services.listing_service import ListingService

        triggering_listing = MagicMock()
        triggering_listing.id = "lid-1"
        triggering_listing.status = "pending_image_engine_confirmation"

        other_pending = MagicMock()
        other_pending.id = "lid-2"
        other_pending.status = "pending_image_engine_confirmation"

        mock_engine_state = MagicMock()
        mock_engine_state.current_engine = "openai"

        mock_db = AsyncMock()
        execute_calls = [0]

        async def execute_side(stmt):
            execute_calls[0] += 1
            r = MagicMock()
            if execute_calls[0] == 1:      # SELECT ImageEngineState
                r.scalar_one = MagicMock(return_value=mock_engine_state)
            else:                          # SELECT Listing WHERE status = pending_...
                r.scalars = MagicMock(return_value=MagicMock(
                    all=MagicMock(return_value=[triggering_listing, other_pending])
                ))
            return r

        mock_db.execute = execute_side
        mock_db.commit = AsyncMock()

        with patch("app.workers.tasks.image_tasks.generate_images") as mock_task:
            svc = ListingService(mock_db)
            await svc.confirm_image_engine(triggering_listing, "use_gemini")

        assert mock_engine_state.current_engine == "gemini"
        assert triggering_listing.status == "generating_images"
        assert other_pending.status == "generating_images"
        assert mock_task.delay.call_count == 2
        mock_task.delay.assert_any_call("lid-1")
        mock_task.delay.assert_any_call("lid-2")

    @pytest.mark.asyncio
    async def test_retry_openai_only_reenqueues_this_listing(self):
        from app.services.listing_service import ListingService

        listing = MagicMock()
        listing.id = "lid-1"
        listing.status = "pending_image_engine_confirmation"

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        with patch("app.workers.tasks.image_tasks.generate_images") as mock_task:
            svc = ListingService(mock_db)
            await svc.confirm_image_engine(listing, "retry_openai")

        assert listing.status == "generating_images"
        mock_task.delay.assert_called_once_with("lid-1")

    @pytest.mark.asyncio
    async def test_wrong_status_raises_409(self):
        from fastapi import HTTPException
        from app.services.listing_service import ListingService

        listing = MagicMock()
        listing.status = "failed"
        mock_db = AsyncMock()

        svc = ListingService(mock_db)
        with pytest.raises(HTTPException) as exc_info:
            await svc.confirm_image_engine(listing, "use_gemini")
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_invalid_action_raises_422(self):
        from fastapi import HTTPException
        from app.services.listing_service import ListingService

        listing = MagicMock()
        listing.status = "pending_image_engine_confirmation"
        mock_db = AsyncMock()

        svc = ListingService(mock_db)
        with pytest.raises(HTTPException) as exc_info:
            await svc.confirm_image_engine(listing, "not_a_real_action")
        assert exc_info.value.status_code == 422
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `docker compose exec backend python -m pytest tests/test_image_engine_confirm.py -v`
Expected: FAIL — `AttributeError: 'ListingService' object has no attribute 'confirm_image_engine'`

- [ ] **Step 3: Implementar `ListingService.confirm_image_engine`**

Adicionar em `backend/app/services/listing_service.py`, logo após o método `trigger_image_generation` (linha ~212):

```python
    async def confirm_image_engine(self, listing: Listing, action: str) -> None:
        if listing.status != "pending_image_engine_confirmation":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Confirmação de motor de imagem indisponível no status '{listing.status}'",
            )
        if action not in ("use_gemini", "retry_openai"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="action deve ser 'use_gemini' ou 'retry_openai'",
            )

        from app.workers.tasks.image_tasks import generate_images

        if action == "use_gemini":
            from app.models.image_engine_state import ImageEngineState
            engine_state = (await self.db.execute(select(ImageEngineState))).scalar_one()
            engine_state.current_engine = "gemini"

            pending = (await self.db.execute(
                select(Listing).where(Listing.status == "pending_image_engine_confirmation")
            )).scalars().all()
            for pending_listing in pending:
                pending_listing.status = "generating_images"
                pending_listing.error_message = None
            await self.db.commit()
            for pending_listing in pending:
                generate_images.delay(str(pending_listing.id))
        else:
            listing.status = "generating_images"
            listing.error_message = None
            await self.db.commit()
            generate_images.delay(str(listing.id))
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `docker compose exec backend python -m pytest tests/test_image_engine_confirm.py -v`
Expected: `4 passed`

- [ ] **Step 5: Adicionar o schema da requisição**

Editar `backend/app/schemas/listing.py` linha 2 (import), trocar:
```python
from typing import Optional, Any
```
Por:
```python
from typing import Optional, Any, Literal
```

Adicionar, logo após a classe `ImageApproveRequest` (linha ~119):

```python
class ImageEngineConfirmRequest(BaseModel):
    action: Literal["use_gemini", "retry_openai"]
```

- [ ] **Step 6: Adicionar o endpoint**

Editar `backend/app/api/v1/endpoints/listings.py` — adicionar o import do novo schema na linha 14-21 (bloco `from app.schemas.listing import (...)`, adicionar `ImageEngineConfirmRequest`), e adicionar o endpoint logo após `generate_images` (linha ~180):

```python
@router.post("/{listing_id}/pipeline/confirm_image_engine", response_model=ListingSummary)
async def confirm_image_engine(
    listing_id: UUID,
    body: ImageEngineConfirmRequest,
    active_seller=Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    svc = ListingService(db)
    listing = await svc.get_or_404(listing_id, active_seller.id)
    await svc.confirm_image_engine(listing, body.action)
    return ListingSummary.model_validate(listing)
```

- [ ] **Step 7: Rodar a suíte completa de backend**

Run: `docker compose exec backend python -m pytest tests/ -v`
Expected: todos os testes passam (nenhuma quebra em outros endpoints).

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/listing_service.py backend/app/schemas/listing.py backend/app/api/v1/endpoints/listings.py backend/tests/test_image_engine_confirm.py
git commit -m "feat: adiciona endpoint de confirmação de troca de motor de imagem"
```

---

## Task 8: Endpoint `GET /api/v1/system/image-engine`

**Files:**
- Create: `backend/app/schemas/system.py`
- Create: `backend/app/api/v1/endpoints/system.py`
- Modify: `backend/app/api/v1/router.py`
- Create: `backend/tests/test_system_image_engine_endpoint.py`

**Interfaces:**
- Consumes: `ImageEngineState` (Task 1), `get_engine_label` (Task 5).
- Produces: `GET /api/v1/system/image-engine` → `ImageEngineStateOut`. Consumido pelo frontend (Tasks 10, 11, 12).

- [ ] **Step 1: Criar o schema**

Criar `backend/app/schemas/system.py`:

```python
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ImageEngineStateOut(BaseModel):
    current_engine: str
    engine_label: str
    pending_confirmation_count: int
    pending_listing_ids: list[str]
    last_openai_error: Optional[str]
    last_switch_to_openai_at: Optional[datetime]
```

- [ ] **Step 2: Escrever o teste do endpoint (vai falhar — endpoint não existe ainda)**

Criar `backend/tests/test_system_image_engine_endpoint.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestGetImageEngineEndpointLogic:
    @pytest.mark.asyncio
    async def test_builds_response_from_state_and_pending_listings(self):
        """Testa a função do endpoint diretamente (sem subir o app FastAPI completo),
        garantindo que ela monta o schema corretamente a partir do estado e da
        contagem de listings pendentes."""
        from app.api.v1.endpoints.system import get_image_engine

        mock_engine_state = MagicMock()
        mock_engine_state.current_engine = "openai"
        mock_engine_state.last_openai_error = "boom"
        mock_engine_state.last_switch_to_openai_at = None

        mock_db = AsyncMock()
        execute_calls = [0]

        async def execute_side(stmt):
            execute_calls[0] += 1
            r = MagicMock()
            if execute_calls[0] == 1:   # SELECT ImageEngineState
                r.scalar_one = MagicMock(return_value=mock_engine_state)
            else:                        # SELECT Listing.id WHERE pending...
                r.all = MagicMock(return_value=[("lid-1",), ("lid-2",)])
            return r

        mock_db.execute = execute_side

        result = await get_image_engine(current_user=MagicMock(), db=mock_db)

        assert result.current_engine == "openai"
        assert result.pending_confirmation_count == 2
        assert result.pending_listing_ids == ["lid-1", "lid-2"]
        assert result.last_openai_error == "boom"
        assert "OpenAI" in result.engine_label
```

- [ ] **Step 3: Rodar o teste e confirmar que falha**

Run: `docker compose exec backend python -m pytest tests/test_system_image_engine_endpoint.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.api.v1.endpoints.system'`

- [ ] **Step 4: Implementar o endpoint**

Criar `backend/app/api/v1/endpoints/system.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.dependencies import get_db, get_current_user
from app.models.image_engine_state import ImageEngineState
from app.models.listing import Listing
from app.schemas.system import ImageEngineStateOut
from app.services.image_engines.service import get_engine_label

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/image-engine", response_model=ImageEngineStateOut)
async def get_image_engine(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    engine_state = (await db.execute(select(ImageEngineState))).scalar_one()

    pending_result = await db.execute(
        select(Listing.id).where(Listing.status == "pending_image_engine_confirmation")
    )
    pending_ids = [str(row[0]) for row in pending_result.all()]

    return ImageEngineStateOut(
        current_engine=engine_state.current_engine,
        engine_label=get_engine_label(engine_state.current_engine),
        pending_confirmation_count=len(pending_ids),
        pending_listing_ids=pending_ids,
        last_openai_error=engine_state.last_openai_error,
        last_switch_to_openai_at=engine_state.last_switch_to_openai_at,
    )
```

- [ ] **Step 5: Registrar o router**

Editar `backend/app/api/v1/router.py`:

```python
from fastapi import APIRouter
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.listings import router as listings_router
from app.api.v1.endpoints.sellers import router as sellers_router
from app.api.v1.endpoints.import_listings import router as import_router
from app.api.v1.endpoints.products import router as products_router
from app.api.v1.endpoints.seller_title_configs import router as title_configs_router
from app.api.v1.endpoints.listings_bulk import router as listings_bulk_router
from app.api.v1.endpoints.system import router as system_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(health_router)
router.include_router(listings_router)
router.include_router(sellers_router)
router.include_router(import_router)
router.include_router(products_router)
router.include_router(title_configs_router)
router.include_router(listings_bulk_router, prefix="/listings")
router.include_router(system_router)
```

- [ ] **Step 6: Rodar o teste e confirmar que passa**

Run: `docker compose exec backend python -m pytest tests/test_system_image_engine_endpoint.py -v`
Expected: `1 passed`

- [ ] **Step 7: Smoke test manual via curl (backend precisa estar rodando)**

Run: `docker compose up -d backend && docker compose exec backend alembic upgrade head`
Run (com um token JWT válido, ex. do usuário admin): `curl -H "Authorization: Bearer <token>" http://localhost:8001/api/v1/system/image-engine`
Expected: JSON `{"current_engine":"openai","engine_label":"OpenAI · gpt-image-1","pending_confirmation_count":0,"pending_listing_ids":[],"last_openai_error":null,"last_switch_to_openai_at":null}`

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/system.py backend/app/api/v1/endpoints/system.py backend/app/api/v1/router.py backend/tests/test_system_image_engine_endpoint.py
git commit -m "feat: adiciona endpoint GET /system/image-engine"
```

---

## Task 9: Frontend — novo status (tipos, badge, coluna do kanban)

**Files:**
- Modify: `frontend/src/types/listing.ts`
- Modify: `frontend/src/components/listings/ListingStatusBadge.tsx`
- Modify: `frontend/src/components/listings/PipelineBoard.tsx`

**Interfaces:**
- Produces: `ListingStatus` inclui `"pending_image_engine_confirmation"`, com label, cor de badge e presença na coluna "Imagens" do kanban.

- [ ] **Step 1: Adicionar o status ao tipo e aos labels**

Editar `frontend/src/types/listing.ts` — adicionar `"pending_image_engine_confirmation"` ao union `ListingStatus` (logo após `"generating_images"`):

```typescript
export type ListingStatus =
  | "draft"
  | "generating_title"
  | "pending_title_approval"
  | "predicting_category"
  | "pending_seller_attributes"
  | "pending_description"
  | "generating_images"
  | "pending_image_engine_confirmation"
  | "pending_image_approval"
  | "generating_description"
  | "ready_to_publish"
  | "publishing"
  | "published"
  | "published_paused"
  | "failed"
```

Adicionar ao `STATUS_LABELS` (logo após `generating_images: "Gerando imagens",`):

```typescript
  pending_image_engine_confirmation: "Aguardando confirmação de motor de imagem",
```

Adicionar `"pending_image_engine_confirmation"` ao array `WAITING_STATUSES`:

```typescript
export const WAITING_STATUSES: ListingStatus[] = [
  "pending_title_approval",
  "pending_seller_attributes",
  "pending_image_approval",
  "pending_image_engine_confirmation",
  "ready_to_publish",
]
```

- [ ] **Step 2: Verificar que o TypeScript compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: erros apontando `ListingStatusBadge.tsx` (Record incompleto) — esperado, corrigido no próximo passo.

- [ ] **Step 3: Atualizar `ListingStatusBadge.tsx`**

Editar `frontend/src/components/listings/ListingStatusBadge.tsx` — adicionar ao `STATUS_VARIANTS` (logo após `pending_image_approval: "default",`):

```typescript
  pending_image_engine_confirmation: "default",
```

Adicionar ao `STATUS_COLORS` (logo após `pending_image_approval: C.yellow,`):

```typescript
  pending_image_engine_confirmation: C.yellow,
```

- [ ] **Step 4: Adicionar o status à coluna "Imagens" do kanban**

Editar `frontend/src/components/listings/PipelineBoard.tsx` — no objeto da coluna `imagens` (linha ~44-50):

```typescript
  {
    id: "imagens",
    title: "Imagens",
    statuses: ["generating_images", "pending_image_engine_confirmation", "pending_image_approval"],
    failedSteps: ["generating_images", "pending_image_approval"],
    colorClass: "border-t-orange-400",
  },
```

- [ ] **Step 5: Rodar o build de TypeScript e confirmar que passa**

Run: `cd frontend && npx tsc --noEmit`
Expected: sem erros.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/listing.ts frontend/src/components/listings/ListingStatusBadge.tsx frontend/src/components/listings/PipelineBoard.tsx
git commit -m "feat: adiciona status pending_image_engine_confirmation ao frontend"
```

---

## Task 10: Frontend — API client (leitura de estado + confirmação)

**Files:**
- Create: `frontend/src/types/system.ts`
- Create: `frontend/src/lib/api/system.ts`
- Modify: `frontend/src/lib/api/listings.ts`

**Interfaces:**
- Produces: `ImageEngineState` (tipo), `getImageEngineState(): Promise<ImageEngineState>`, `confirmImageEngine(id, action): Promise<ListingSummary>`. Consumidos pelas Tasks 11 e 12.

- [ ] **Step 1: Criar o tipo**

Criar `frontend/src/types/system.ts`:

```typescript
export interface ImageEngineState {
  current_engine: "openai" | "gemini"
  engine_label: string
  pending_confirmation_count: number
  pending_listing_ids: string[]
  last_openai_error: string | null
  last_switch_to_openai_at: string | null
}
```

- [ ] **Step 2: Criar o client de leitura**

Criar `frontend/src/lib/api/system.ts`:

```typescript
import { apiFetch } from "./client"
import type { ImageEngineState } from "@/types/system"

export async function getImageEngineState(): Promise<ImageEngineState> {
  return apiFetch<ImageEngineState>("/api/v1/system/image-engine")
}
```

- [ ] **Step 3: Adicionar `confirmImageEngine` em `listings.ts`**

Editar `frontend/src/lib/api/listings.ts` — adicionar, logo após `generateImages`:

```typescript
export async function confirmImageEngine(
  id: string,
  action: "use_gemini" | "retry_openai"
): Promise<ListingSummary> {
  return apiFetch<ListingSummary>(
    `/api/v1/listings/${id}/pipeline/confirm_image_engine`,
    { method: "POST", body: JSON.stringify({ action }) }
  )
}
```

- [ ] **Step 4: Rodar o build de TypeScript**

Run: `cd frontend && npx tsc --noEmit`
Expected: sem erros.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/system.ts frontend/src/lib/api/system.ts frontend/src/lib/api/listings.ts
git commit -m "feat: adiciona client de API para estado e confirmação de motor de imagem"
```

---

## Task 11: Frontend — banner global

**Files:**
- Create: `frontend/src/components/system/ImageEngineBanner.tsx`
- Modify: `frontend/src/app/(dashboard)/layout.tsx`

**Interfaces:**
- Consumes: `getImageEngineState`, `confirmImageEngine` (Task 10).
- Produces: componente `<ImageEngineBanner />`, montado no layout do dashboard, visível em qualquer página.

- [ ] **Step 1: Criar o componente**

Criar `frontend/src/components/system/ImageEngineBanner.tsx`:

```tsx
"use client"

import { useRef } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { AlertTriangle, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { getImageEngineState } from "@/lib/api/system"
import { confirmImageEngine } from "@/lib/api/listings"

export function ImageEngineBanner() {
  const lastSwitchSeen = useRef<string | null>(null)
  const queryClient = useQueryClient()

  const { data } = useQuery({
    queryKey: ["image-engine-state"],
    queryFn: getImageEngineState,
    refetchInterval: 8_000,
  })

  const mutation = useMutation({
    mutationFn: (action: "use_gemini" | "retry_openai") => {
      const targetId = data?.pending_listing_ids[0]
      if (!targetId) throw new Error("Nenhum anúncio pendente")
      return confirmImageEngine(targetId, action)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["image-engine-state"] })
      queryClient.invalidateQueries({ queryKey: ["listings"] })
    },
    onError: (err: Error) => {
      toast.error(err.message || "Erro ao trocar motor de imagem")
    },
  })

  if (data) {
    const seen = lastSwitchSeen.current
    if (data.last_switch_to_openai_at && seen !== null && seen !== data.last_switch_to_openai_at) {
      toast.success("Geração de imagens voltou a usar a OpenAI")
    }
    lastSwitchSeen.current = data.last_switch_to_openai_at
  }

  if (!data || data.pending_confirmation_count === 0) return null

  return (
    <div className="mb-4 flex items-center justify-between gap-4 rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-amber-900">
      <div className="flex items-center gap-2 text-sm">
        <AlertTriangle className="h-4 w-4 shrink-0" />
        <span>
          A geração de imagens via OpenAI apresentou falha
          {data.last_openai_error ? `: ${data.last_openai_error}` : ""}.{" "}
          {data.pending_confirmation_count} anúncio(s) aguardando decisão.
        </span>
      </div>
      <div className="flex gap-2 shrink-0">
        <Button
          size="sm"
          variant="outline"
          disabled={mutation.isPending}
          onClick={() => mutation.mutate("retry_openai")}
        >
          {mutation.isPending && mutation.variables === "retry_openai" ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            "Tentar novamente com OpenAI"
          )}
        </Button>
        <Button
          size="sm"
          disabled={mutation.isPending}
          onClick={() => mutation.mutate("use_gemini")}
        >
          {mutation.isPending && mutation.variables === "use_gemini" ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            "Usar Gemini nestes anúncios"
          )}
        </Button>
      </div>
    </div>
  )
}
```

> Nota: o botão "Tentar novamente com OpenAI" do banner global reenfileira só o primeiro anúncio pendente (`pending_listing_ids[0]`), por design — `retry_openai` sempre age sobre um único listing (spec RF/Endpoint de confirmação). Se houver vários anúncios pendentes, os demais precisam ser retentados individualmente na página de cada anúncio (Task 12) ou resolvidos de uma vez com "Usar Gemini nestes anúncios".

- [ ] **Step 2: Montar o banner no layout do dashboard**

Editar `frontend/src/app/(dashboard)/layout.tsx` — adicionar o import e o componente:

```tsx
"use client"

import { useEffect, useState } from "react"
import { useRouter, usePathname } from "next/navigation"
import { Sidebar } from "@/components/layout/Sidebar"
import { SellerProvider } from "@/contexts/SellerContext"
import { ImageEngineBanner } from "@/components/system/ImageEngineBanner"

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const router = useRouter()
  const pathname = usePathname()
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const token = localStorage.getItem("access_token")
    if (!token) {
      router.replace("/login")
    } else {
      setReady(true)
    }
  }, [router])

  if (!ready) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-600" />
      </div>
    )
  }

  return (
    <SellerProvider>
      <div className="flex h-screen overflow-hidden bg-background">
        <Sidebar />
        <main className="flex-1 min-w-0 overflow-y-auto p-6">
          <ImageEngineBanner />
          <div key={pathname} className="animate-in fade-in duration-200">
            {children}
          </div>
        </main>
      </div>
    </SellerProvider>
  )
}
```

- [ ] **Step 3: Rodar o build de TypeScript**

Run: `cd frontend && npx tsc --noEmit`
Expected: sem erros.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/system/ImageEngineBanner.tsx "frontend/src/app/(dashboard)/layout.tsx"
git commit -m "feat: adiciona banner global de troca de motor de imagem"
```

---

## Task 12: Frontend — badge no card "Imagens" + card de confirmação

**Files:**
- Modify: `frontend/src/app/(dashboard)/listings/[id]/page.tsx`

**Interfaces:**
- Consumes: `getImageEngineState`, `confirmImageEngine` (Task 10).

- [ ] **Step 1: Importar o necessário**

Editar `frontend/src/app/(dashboard)/listings/[id]/page.tsx` — adicionar aos imports do topo:

```tsx
import { getListing, retryPipeline, deleteListing, generateImages, confirmImageEngine } from "@/lib/api/listings"
import { getImageEngineState } from "@/lib/api/system"
import { Badge } from "@/components/ui/badge"
```

- [ ] **Step 2: Buscar o estado do motor**

Dentro do componente `ListingDetailPage`, logo após a query `categoryName` (linha ~60), adicionar:

```tsx
  const { data: engineState } = useQuery({
    queryKey: ["image-engine-state"],
    queryFn: getImageEngineState,
    refetchInterval: 8_000,
  })

  const confirmEngineMutation = useMutation({
    mutationFn: (action: "use_gemini" | "retry_openai") => confirmImageEngine(id, action),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["listing", id] })
      queryClient.invalidateQueries({ queryKey: ["listings"] })
      queryClient.invalidateQueries({ queryKey: ["image-engine-state"] })
      toast.success("Motor de imagem atualizado")
    },
    onError: (err: Error) => {
      toast.error(err.message || "Erro ao confirmar motor de imagem")
    },
  })
```

- [ ] **Step 3: Adicionar o badge nos dois cards de imagem**

No card "Gerar imagens do produto" (`status === "pending_description"`), trocar o `CardHeader`:

```tsx
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Gerar imagens do produto</CardTitle>
            {engineState && <Badge variant="outline">{engineState.engine_label}</Badge>}
          </CardHeader>
```

No card "Imagens geradas" (`status === "pending_image_approval"`), trocar o `CardHeader`:

```tsx
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Imagens geradas</CardTitle>
            {engineState && <Badge variant="outline">{engineState.engine_label}</Badge>}
          </CardHeader>
```

- [ ] **Step 4: Adicionar o card de confirmação de motor**

Adicionar, logo após o bloco `{status === "pending_image_approval" && (...)}` e antes de `{status === "ready_to_publish" && (...)}`:

```tsx
      {status === "pending_image_engine_confirmation" && (
        <Card className="border-amber-200 bg-amber-50">
          <CardHeader>
            <CardTitle className="text-base text-amber-900 flex items-center gap-2">
              <AlertCircle className="w-5 h-5" />
              Confirmação necessária: motor de imagem
            </CardTitle>
          </CardHeader>
          <CardContent>
            {listing.error_message && (
              <p className="text-sm text-amber-800 mb-4 p-3 bg-amber-100 rounded-md font-mono">
                {listing.error_message}
              </p>
            )}
            <div className="flex gap-2">
              <Button
                variant="outline"
                className="flex-1"
                disabled={confirmEngineMutation.isPending}
                onClick={() => confirmEngineMutation.mutate("retry_openai")}
              >
                {confirmEngineMutation.isPending && confirmEngineMutation.variables === "retry_openai" ? (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                ) : null}
                Tentar novamente com OpenAI
              </Button>
              <Button
                className="flex-1"
                disabled={confirmEngineMutation.isPending}
                onClick={() => confirmEngineMutation.mutate("use_gemini")}
              >
                {confirmEngineMutation.isPending && confirmEngineMutation.variables === "use_gemini" ? (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                ) : null}
                Usar Gemini neste anúncio
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
```

- [ ] **Step 5: Rodar o build de TypeScript**

Run: `cd frontend && npx tsc --noEmit`
Expected: sem erros.

- [ ] **Step 6: Commit**

```bash
git add "frontend/src/app/(dashboard)/listings/[id]/page.tsx"
git commit -m "feat: adiciona badge de motor e card de confirmação na página do anúncio"
```

---

## Task 13: Validação manual end-to-end

**Files:** nenhum (só validação — sem suíte de UI automatizada neste projeto).

- [ ] **Step 1: Subir o ambiente completo**

Run: `docker compose up -d && docker compose exec backend alembic upgrade head`
Run: `cd frontend && npm run dev` (em terminal separado)

- [ ] **Step 2: Configurar `OPENAI_API_KEY` real no `.env`**

Editar `.env` na raiz do projeto, preencher `OPENAI_API_KEY` com uma chave válida. Reiniciar backend: `docker compose restart backend celery_worker`.

- [ ] **Step 3: Testar o caminho feliz (OpenAI funcionando)**

No navegador (`http://localhost:3000`), criar ou avançar um anúncio até "Gerar imagens" — confirmar que:
- O badge no card mostra `OpenAI · gpt-image-1`.
- As imagens são geradas e aparecem em "Imagens geradas".

- [ ] **Step 4: Simular falha da OpenAI (banner de confirmação)**

Temporariamente, colocar uma `OPENAI_API_KEY` inválida no `.env` e reiniciar (`docker compose restart backend celery_worker`). Gerar imagens de um novo anúncio — confirmar que:
- O anúncio entra em "Aguardando confirmação de motor de imagem" (card amarelo na página do anúncio, coluna "Imagens" no kanban).
- O banner global aparece em qualquer página do dashboard, com o erro resumido.
- Clicar em "Usar Gemini neste anúncio" (ou no banner) muda o anúncio para gerar com Gemini e o badge passa a mostrar `Gemini · imagen-4.0-fast`.

- [ ] **Step 5: Testar a volta automática para OpenAI**

Restaurar a `OPENAI_API_KEY` válida no `.env` e reiniciar (`docker compose restart backend celery_worker`). Gerar imagens de outro anúncio (motor ainda em "gemini" do passo anterior) — confirmar que:
- O sistema volta sozinho para OpenAI (sem pedir confirmação).
- Aparece o toast "Geração de imagens voltou a usar a OpenAI".
- O badge volta a mostrar `OpenAI · gpt-image-1`.

- [ ] **Step 6: Rodar a suíte completa de backend uma última vez**

Run: `docker compose exec backend python -m pytest tests/ -v`
Expected: todos os testes passam.

- [ ] **Step 7: Reportar ao usuário**

Sem commit nesta task — é só validação. Reportar ao usuário (Daniel) o resultado dos passos 3-5 antes de considerar a migração concluída.
