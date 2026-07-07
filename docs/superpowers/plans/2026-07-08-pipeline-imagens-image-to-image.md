# Pipeline de imagens image-to-image — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que o pipeline de geração de imagens use fotos brutas reais do produto (fornecidas pelo seller num bucket próprio) como entrada de um motor de edição de imagem por IA, em vez de gerar do zero a partir de texto — de forma aditiva e sem quebrar o comportamento atual para sellers sem essa configuração.

**Architecture:** Novo caminho opt-in por seller (`SellerImageConfig`), plugado em `_generate_images_async` antes do bloco de texto-imagem existente. Se o seller não tiver configuração ou faltar alguma foto bruta, cai automaticamente no fluxo atual, inalterado. Um novo motor (`OpenAIEditEngine`, `/v1/images/edits`) trata as fotos reais (por SKU, e composição de capa quando o anúncio tem mais de um SKU). Escrita de volta no bucket do seller é best-effort, feita depois da publicação (quando o `mlb_id` já existe).

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async (backend), Celery (worker), httpx (chamadas HTTP), boto3 (S3-compatível, já presente em `requirements.txt`), Next.js 14 + TypeScript (frontend).

**Spec de referência:** `docs/superpowers/specs/2026-07-08-pipeline-imagens-image-to-image-design.md`

## Global Constraints

- Fotos brutas: sempre exatamente 2 por SKU, extensão fixa `.jpg`, nomeadas `{SKU}-1.jpg` e `{SKU}-2.jpg`.
- Leitura das fotos brutas: URL pública, sem credenciais.
- Escrita de volta no bucket do seller: best-effort, opcional, nunca bloqueia a publicação.
- Se **qualquer** SKU do anúncio não tiver as 2 fotos brutas, o anúncio inteiro cai no fluxo texto-imagem atual (tudo ou nada, sem mistura).
- Indisponibilidade do provedor de i2i (OpenAI Edits API) vai para `failed` — **sem** fallback automático para texto-imagem.
- Cada SKU gera 4 imagens individuais (2 fotos brutas × 2 variações cada, uma chamada de edição por foto bruta).
- Capa composta (múltiplos SKUs) só é tentada quando o anúncio tem mais de 1 SKU; falha na composição da capa não afeta as imagens individuais.
- Toda tabela/model novo precisa ser importado em `app/models/__init__.py` (convenção do projeto — Alembic não detecta FKs sem isso).
- Segredos (credenciais de escrita) sempre criptografados com `encrypt_value`/`decrypt_value` (`app/core/security.py`), nunca em texto plano.
- Testes seguem o padrão já estabelecido no projeto: `unittest.mock` + `patch("httpx.AsyncClient")` / `patch("boto3.client")`, sem servidor HTTP real nem `moto`.

---

### Task 1: Migração e modelos de dados

**Files:**
- Create: `backend/app/models/seller_image_config.py`
- Modify: `backend/app/models/listing_image.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/a3f7c9d2e841_add_seller_image_config_and_listing_.py`

**Interfaces:**
- Produces: `SellerImageConfig` (colunas: `id`, `seller_id`, `raw_base_url`, `write_bucket_name`, `write_endpoint_url`, `write_access_key_id_enc`, `write_secret_access_key_enc`, `created_at`, `updated_at`).
- Produces: `ListingImage` ganha `kind` (str, default `"individual"`), `source_sku` (str opcional), `r2_write_status` (str opcional).

- [ ] **Step 1: Criar o model `SellerImageConfig`**

Criar `backend/app/models/seller_image_config.py`:

```python
import uuid
from typing import Optional
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class SellerImageConfig(Base, TimestampMixin):
    __tablename__ = "seller_image_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    raw_base_url: Mapped[str] = mapped_column(Text, nullable=False)
    write_bucket_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    write_endpoint_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    write_access_key_id_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    write_secret_access_key_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

- [ ] **Step 2: Adicionar as novas colunas em `ListingImage`**

Editar `backend/app/models/listing_image.py` — adicionar após a linha `sort_order`:

```python
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="individual")
    source_sku: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    r2_write_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
```

O arquivo final (trecho relevante) deve ficar:

```python
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="generating")
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="individual")
    source_sku: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    r2_write_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 3: Registrar o novo model em `app/models/__init__.py`**

Editar `backend/app/models/__init__.py`, adicionando o import e a entrada em `__all__`:

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
from app.models.seller_image_config import SellerImageConfig

__all__ = [
    "Seller", "User", "UserSellerAccess", "Product", "Listing", "ListingJob",
    "ListingTitle", "ListingAttribute", "ListingImage", "ListingDescription",
    "ProductImage", "BatchImport", "BatchImportRow", "SellerTitleConfig",
    "ImageEngineState", "SellerImageConfig",
]
```

- [ ] **Step 4: Criar a migration**

Criar `backend/alembic/versions/a3f7c9d2e841_add_seller_image_config_and_listing_.py`:

```python
"""add_seller_image_config_and_listing_image_i2i_columns

Revision ID: a3f7c9d2e841
Revises: b7e4a1c92f83
Create Date: 2026-07-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'a3f7c9d2e841'
down_revision = 'b7e4a1c92f83'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'seller_image_configs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('seller_id', sa.UUID(), nullable=False),
        sa.Column('raw_base_url', sa.Text(), nullable=False),
        sa.Column('write_bucket_name', sa.String(length=200), nullable=True),
        sa.Column('write_endpoint_url', sa.Text(), nullable=True),
        sa.Column('write_access_key_id_enc', sa.Text(), nullable=True),
        sa.Column('write_secret_access_key_enc', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['seller_id'], ['sellers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('seller_id', name='uq_seller_image_configs_seller_id'),
    )
    op.add_column('listing_images', sa.Column('kind', sa.String(length=20), nullable=False, server_default='individual'))
    op.add_column('listing_images', sa.Column('source_sku', sa.String(length=100), nullable=True))
    op.add_column('listing_images', sa.Column('r2_write_status', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('listing_images', 'r2_write_status')
    op.drop_column('listing_images', 'source_sku')
    op.drop_column('listing_images', 'kind')
    op.drop_table('seller_image_configs')
```

- [ ] **Step 5: Rodar a migration no ambiente de dev e validar**

Run: `docker compose exec backend alembic upgrade head`
Expected: sem erros, e `alembic heads` mostra `a3f7c9d2e841 (head)`.

Run: `docker compose exec -T backend python -c "from app.models import SellerImageConfig; from app.models.listing_image import ListingImage; print('ok')"`
Expected: `ok` (sem `ImportError`).

Run:
```bash
docker compose exec -T postgres psql -U mlb_user -d publicar_ad_mlb -c "\d seller_image_configs" -c "\d listing_images"
```
Expected: `seller_image_configs` existe com as colunas esperadas; `listing_images` mostra `kind`, `source_sku`, `r2_write_status`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/seller_image_config.py backend/app/models/listing_image.py backend/app/models/__init__.py backend/alembic/versions/a3f7c9d2e841_add_seller_image_config_and_listing_.py
git commit -m "feat: adiciona SellerImageConfig e colunas i2i em listing_images"
```

---

### Task 2: Serviço de resolução e download de fotos brutas

**Files:**
- Create: `backend/app/services/seller_image_source_service.py`
- Test: `backend/tests/test_seller_image_source_service.py`

**Interfaces:**
- Consumes: nenhuma dependência de outras tasks deste plano.
- Produces:
  - `async def resolve_listing_skus(listing) -> list[str]`
  - `async def fetch_raw_photos(raw_base_url: str, sku: str) -> list[bytes] | None`
  - `async def fetch_all_raw_photos(raw_base_url: str, skus: list[str]) -> dict[str, list[bytes]] | None`

- [ ] **Step 1: Escrever os testes (falhando)**

Criar `backend/tests/test_seller_image_source_service.py`:

```python
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.seller_image_source_service import (
    resolve_listing_skus,
    fetch_raw_photos,
    fetch_all_raw_photos,
)


class TestResolveListingSkus:
    @pytest.mark.asyncio
    async def test_returns_single_sku_list(self):
        listing = MagicMock()
        listing.sku_external_id = "SKU0001"
        assert await resolve_listing_skus(listing) == ["SKU0001"]

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_sku(self):
        listing = MagicMock()
        listing.sku_external_id = None
        assert await resolve_listing_skus(listing) == []


def _mock_response(status_code: int, content: bytes = b"") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content
    return resp


class TestFetchRawPhotos:
    @pytest.mark.asyncio
    async def test_returns_both_photos_when_both_exist(self):
        mock_get = AsyncMock(side_effect=[
            _mock_response(200, b"photo1-bytes"),
            _mock_response(200, b"photo2-bytes"),
        ])
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.get = mock_get
            result = await fetch_raw_photos("https://pub-xxx.r2.dev/sku", "SKU0001")

        assert result == [b"photo1-bytes", b"photo2-bytes"]
        assert mock_get.await_args_list[0].args[0] == "https://pub-xxx.r2.dev/sku/SKU0001-1.jpg"
        assert mock_get.await_args_list[1].args[0] == "https://pub-xxx.r2.dev/sku/SKU0001-2.jpg"

    @pytest.mark.asyncio
    async def test_returns_none_when_second_photo_missing(self):
        mock_get = AsyncMock(side_effect=[
            _mock_response(200, b"photo1-bytes"),
            _mock_response(404),
        ])
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.get = mock_get
            result = await fetch_raw_photos("https://pub-xxx.r2.dev/sku", "SKU0001")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self):
        mock_get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.get = mock_get
            result = await fetch_raw_photos("https://pub-xxx.r2.dev/sku", "SKU0001")

        assert result is None


class TestFetchAllRawPhotos:
    @pytest.mark.asyncio
    async def test_returns_dict_when_all_skus_have_photos(self):
        with patch(
            "app.services.seller_image_source_service.fetch_raw_photos",
            new_callable=AsyncMock,
            side_effect=[[b"s1-1", b"s1-2"], [b"s2-1", b"s2-2"]],
        ):
            result = await fetch_all_raw_photos("https://pub-xxx.r2.dev/sku", ["SKU0001", "SKU0002"])

        assert result == {"SKU0001": [b"s1-1", b"s1-2"], "SKU0002": [b"s2-1", b"s2-2"]}

    @pytest.mark.asyncio
    async def test_returns_none_all_or_nothing_when_any_sku_missing_photos(self):
        with patch(
            "app.services.seller_image_source_service.fetch_raw_photos",
            new_callable=AsyncMock,
            side_effect=[[b"s1-1", b"s1-2"], None],
        ):
            result = await fetch_all_raw_photos("https://pub-xxx.r2.dev/sku", ["SKU0001", "SKU0002"])

        assert result is None
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `docker compose exec -T backend python -m pytest tests/test_seller_image_source_service.py -v`
Expected: `ModuleNotFoundError: No module named 'app.services.seller_image_source_service'`

- [ ] **Step 3: Implementar o serviço**

Criar `backend/app/services/seller_image_source_service.py`:

```python
import httpx

RAW_PHOTOS_PER_SKU = 2


async def resolve_listing_skus(listing) -> list[str]:
    """Resolve a lista de SKUs componentes do anúncio. Hoje um anúncio sempre
    mapeia para exatamente 1 SKU; retorna uma lista para que os chamadores já
    estejam prontos para quando um projeto de kit fizer isso retornar mais
    de um SKU."""
    return [listing.sku_external_id] if listing.sku_external_id else []


async def fetch_raw_photos(raw_base_url: str, sku: str) -> list[bytes] | None:
    """Baixa as 2 fotos brutas de um SKU a partir do bucket do seller. Retorna
    None se qualquer uma das 2 fotos esperadas estiver faltando ou falhar —
    os chamadores devem tratar isso como "sem fotos brutas disponíveis"."""
    urls = [f"{raw_base_url}/{sku}-{n}.jpg" for n in range(1, RAW_PHOTOS_PER_SKU + 1)]
    photos: list[bytes] = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        for url in urls:
            try:
                resp = await client.get(url)
            except httpx.HTTPError:
                return None
            if resp.status_code != 200:
                return None
            photos.append(resp.content)
    return photos


async def fetch_all_raw_photos(raw_base_url: str, skus: list[str]) -> dict[str, list[bytes]] | None:
    """Busca as fotos brutas de todos os SKUs da lista. Tudo ou nada: retorna
    None se QUALQUER SKU estiver sem as 2 fotos brutas."""
    result: dict[str, list[bytes]] = {}
    for sku in skus:
        photos = await fetch_raw_photos(raw_base_url, sku)
        if photos is None:
            return None
        result[sku] = photos
    return result
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `docker compose exec -T backend python -m pytest tests/test_seller_image_source_service.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/seller_image_source_service.py backend/tests/test_seller_image_source_service.py
git commit -m "feat: adiciona resolucao e download de fotos brutas por SKU"
```

---

### Task 3: Motor de edição de imagem (OpenAI `/v1/images/edits`)

**Files:**
- Create: `backend/app/services/image_engines/openai_edit_engine.py`
- Test: `backend/tests/test_openai_edit_engine.py`

**Interfaces:**
- Consumes: `app.services.image_engines.base.ImageEngineUnavailableError` (já existe).
- Produces: `OpenAIEditEngine.edit(images: list[bytes], prompt: str, n: int) -> list[bytes]` (async).

- [ ] **Step 1: Escrever os testes (falhando)**

Criar `backend/tests/test_openai_edit_engine.py`:

```python
import base64
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.image_engines.base import ImageEngineUnavailableError
from app.services.image_engines.openai_edit_engine import OpenAIEditEngine


def _b64_image() -> str:
    return base64.b64encode(b"fake-edited-image-bytes").decode()


class TestOpenAIEditEngine:
    @pytest.mark.asyncio
    async def test_success_returns_decoded_images(self):
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {"data": [{"b64_json": _b64_image()}]}

        mock_post = AsyncMock(return_value=mock_response)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            engine = OpenAIEditEngine()
            result = await engine.edit(images=[b"raw-photo-bytes"], prompt="tratamento", n=2)

        assert result == [b"fake-edited-image-bytes"]
        call_kwargs = mock_post.await_args.kwargs
        assert call_kwargs["data"]["n"] == "2"
        assert call_kwargs["data"]["input_fidelity"] == "high"
        assert len(call_kwargs["files"]) == 1

    @pytest.mark.asyncio
    async def test_multiple_input_images_sent_as_multiple_files(self):
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {"data": [{"b64_json": _b64_image()}]}

        mock_post = AsyncMock(return_value=mock_response)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            engine = OpenAIEditEngine()
            await engine.edit(images=[b"photo-a", b"photo-b", b"photo-c"], prompt="capa", n=1)

        call_kwargs = mock_post.await_args.kwargs
        assert len(call_kwargs["files"]) == 3

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
            engine = OpenAIEditEngine()
            with pytest.raises(ImageEngineUnavailableError):
                await engine.edit(images=[b"x"], prompt="p", n=2)

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
            engine = OpenAIEditEngine()
            with pytest.raises(ImageEngineUnavailableError):
                await engine.edit(images=[b"x"], prompt="p", n=2)

    @pytest.mark.asyncio
    async def test_timeout_raises_unavailable_error(self):
        mock_post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            engine = OpenAIEditEngine()
            with pytest.raises(ImageEngineUnavailableError):
                await engine.edit(images=[b"x"], prompt="p", n=2)

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
            engine = OpenAIEditEngine()
            with pytest.raises(httpx.HTTPStatusError):
                await engine.edit(images=[b"x"], prompt="p", n=2)
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `docker compose exec -T backend python -m pytest tests/test_openai_edit_engine.py -v`
Expected: `ModuleNotFoundError: No module named 'app.services.image_engines.openai_edit_engine'`

- [ ] **Step 3: Implementar o motor**

Criar `backend/app/services/image_engines/openai_edit_engine.py`:

```python
import base64
import httpx

from app.config import get_settings
from app.services.image_engines.base import ImageEngineUnavailableError

_OPENAI_EDITS_URL = "https://api.openai.com/v1/images/edits"


class OpenAIEditEngine:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def edit(self, images: list[bytes], prompt: str, n: int) -> list[bytes]:
        files = [
            ("image[]", (f"input_{i}.jpg", img, "image/jpeg"))
            for i, img in enumerate(images)
        ]
        data = {
            "model": self.settings.openai_image_model,
            "prompt": prompt,
            "n": str(n),
            "quality": "medium",
            "input_fidelity": "high",
            "output_format": "jpeg",
        }
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(
                    _OPENAI_EDITS_URL,
                    headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
                    data=data,
                    files=files,
                )
        except httpx.TimeoutException as exc:
            raise ImageEngineUnavailableError(f"Timeout ao chamar a OpenAI (edits): {exc}") from exc

        if not resp.is_success:
            if resp.status_code in (401, 403, 429) or resp.status_code >= 500:
                raise ImageEngineUnavailableError(
                    f"OpenAI Edits API {resp.status_code}: {resp.text[:600]}"
                )
            raise httpx.HTTPStatusError(
                f"OpenAI Edits API {resp.status_code}: {resp.text[:600]}",
                request=resp.request,
                response=resp,
            )

        data_resp = resp.json().get("data", [])
        return [base64.b64decode(item["b64_json"]) for item in data_resp]
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `docker compose exec -T backend python -m pytest tests/test_openai_edit_engine.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/image_engines/openai_edit_engine.py backend/tests/test_openai_edit_engine.py
git commit -m "feat: adiciona OpenAIEditEngine (image-to-image via /v1/images/edits)"
```

---

### Task 4: Configuração de imagens do seller (service + endpoint)

**Files:**
- Create: `backend/app/schemas/seller_image_config.py`
- Create: `backend/app/services/seller_image_config_service.py`
- Create: `backend/app/api/v1/endpoints/seller_image_config.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/test_seller_image_config_service.py`

**Interfaces:**
- Consumes: `SellerImageConfig` (Task 1), `encrypt_value`/`decrypt_value` (`app/core/security.py`, já existentes).
- Produces:
  - `SellerImageConfigService(db, seller_id).get() -> SellerImageConfig | None`
  - `SellerImageConfigService(db, seller_id).upsert(payload: SellerImageConfigUpsert) -> SellerImageConfig`
  - Endpoints `GET /api/v1/sellers/image-config` e `PUT /api/v1/sellers/image-config`.

- [ ] **Step 1: Escrever os testes do service (falhando)**

Criar `backend/tests/test_seller_image_config_service.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.schemas.seller_image_config import SellerImageConfigUpsert
from app.services.seller_image_config_service import SellerImageConfigService


class TestSellerImageConfigService:
    @pytest.mark.asyncio
    async def test_get_returns_none_when_not_configured(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        svc = SellerImageConfigService(mock_db, "seller-1")
        result = await svc.get()

        assert result is None

    @pytest.mark.asyncio
    async def test_upsert_creates_new_config_with_encrypted_credentials(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        payload = SellerImageConfigUpsert(
            raw_base_url="https://pub-xxx.r2.dev/sku",
            write_bucket_name="meu-bucket",
            write_endpoint_url="https://account.r2.cloudflarestorage.com",
            write_access_key_id="AKIA_TEST",
            write_secret_access_key="secret-value",
        )

        svc = SellerImageConfigService(mock_db, "seller-1")
        cfg = await svc.upsert(payload)

        assert cfg.seller_id == "seller-1"
        assert cfg.raw_base_url == "https://pub-xxx.r2.dev/sku"
        assert cfg.write_access_key_id_enc != "AKIA_TEST"  # nunca em texto plano
        assert cfg.write_secret_access_key_enc != "secret-value"
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_updates_existing_config_raw_base_url(self):
        existing = MagicMock()
        existing.raw_base_url = "https://old-url/sku"
        existing.write_access_key_id_enc = None
        existing.write_secret_access_key_enc = None

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        payload = SellerImageConfigUpsert(raw_base_url="https://new-url/sku")

        svc = SellerImageConfigService(mock_db, "seller-1")
        cfg = await svc.upsert(payload)

        assert cfg is existing
        assert cfg.raw_base_url == "https://new-url/sku"
        mock_db.add.assert_not_called()  # atualização, não criação
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `docker compose exec -T backend python -m pytest tests/test_seller_image_config_service.py -v`
Expected: `ModuleNotFoundError: No module named 'app.schemas.seller_image_config'`

- [ ] **Step 3: Implementar o schema**

Criar `backend/app/schemas/seller_image_config.py`:

```python
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, field_validator


class SellerImageConfigUpsert(BaseModel):
    raw_base_url: str
    write_bucket_name: Optional[str] = None
    write_endpoint_url: Optional[str] = None
    write_access_key_id: Optional[str] = None
    write_secret_access_key: Optional[str] = None

    @field_validator("raw_base_url")
    @classmethod
    def base_url_not_empty(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not v:
            raise ValueError("raw_base_url não pode ser vazio")
        return v


class SellerImageConfigOut(BaseModel):
    id: UUID
    seller_id: UUID
    raw_base_url: str
    write_bucket_name: Optional[str]
    write_endpoint_url: Optional[str]
    has_write_credentials: bool
    created_at: datetime
    updated_at: datetime
```

- [ ] **Step 4: Implementar o service**

Criar `backend/app/services/seller_image_config_service.py`:

```python
import uuid as _uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.security import encrypt_value
from app.models.seller_image_config import SellerImageConfig
from app.schemas.seller_image_config import SellerImageConfigUpsert


class SellerImageConfigService:
    def __init__(self, db: AsyncSession, seller_id: _uuid.UUID) -> None:
        self.db = db
        self.seller_id = seller_id

    async def get(self) -> Optional[SellerImageConfig]:
        result = await self.db.execute(
            select(SellerImageConfig).where(SellerImageConfig.seller_id == self.seller_id)
        )
        return result.scalar_one_or_none()

    async def upsert(self, payload: SellerImageConfigUpsert) -> SellerImageConfig:
        cfg = await self.get()
        if cfg is None:
            cfg = SellerImageConfig(seller_id=self.seller_id, raw_base_url=payload.raw_base_url)
            self.db.add(cfg)
        else:
            cfg.raw_base_url = payload.raw_base_url

        cfg.write_bucket_name = payload.write_bucket_name
        cfg.write_endpoint_url = payload.write_endpoint_url
        if payload.write_access_key_id:
            cfg.write_access_key_id_enc = encrypt_value(payload.write_access_key_id)
        if payload.write_secret_access_key:
            cfg.write_secret_access_key_enc = encrypt_value(payload.write_secret_access_key)

        await self.db.commit()
        await self.db.refresh(cfg)
        return cfg
```

- [ ] **Step 5: Rodar os testes do service e confirmar que passam**

Run: `docker compose exec -T backend python -m pytest tests/test_seller_image_config_service.py -v`
Expected: 3 passed

- [ ] **Step 6: Implementar o endpoint**

Criar `backend/app/api/v1/endpoints/seller_image_config.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_db, get_current_user, get_active_seller
from app.models.user import User
from app.models.seller import Seller
from app.models.seller_image_config import SellerImageConfig
from app.schemas.seller_image_config import SellerImageConfigUpsert, SellerImageConfigOut
from app.services.seller_image_config_service import SellerImageConfigService

router = APIRouter(prefix="/sellers/image-config", tags=["seller-image-config"])


def _to_out(cfg: SellerImageConfig) -> SellerImageConfigOut:
    return SellerImageConfigOut(
        id=cfg.id,
        seller_id=cfg.seller_id,
        raw_base_url=cfg.raw_base_url,
        write_bucket_name=cfg.write_bucket_name,
        write_endpoint_url=cfg.write_endpoint_url,
        has_write_credentials=bool(cfg.write_access_key_id_enc and cfg.write_secret_access_key_enc),
        created_at=cfg.created_at,
        updated_at=cfg.updated_at,
    )


@router.get("", response_model=SellerImageConfigOut | None)
async def get_image_config(
    current_user: User = Depends(get_current_user),
    active_seller: Seller = Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    svc = SellerImageConfigService(db, active_seller.id)
    cfg = await svc.get()
    return _to_out(cfg) if cfg else None


@router.put("", response_model=SellerImageConfigOut)
async def upsert_image_config(
    body: SellerImageConfigUpsert,
    current_user: User = Depends(get_current_user),
    active_seller: Seller = Depends(get_active_seller),
    db: AsyncSession = Depends(get_db),
):
    svc = SellerImageConfigService(db, active_seller.id)
    cfg = await svc.upsert(body)
    return _to_out(cfg)
```

- [ ] **Step 7: Registrar o router**

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
from app.api.v1.endpoints.seller_image_config import router as seller_image_config_router

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
router.include_router(seller_image_config_router)
```

- [ ] **Step 8: Validar a API sobe sem erros**

Run: `docker compose restart backend`
Run: `curl -s http://localhost:8001/api/v1/health`
Expected: `{"status":"ok","services":{"database":"ok","redis":"ok"}}` (confirma que o app FastAPI carregou o novo router sem erro de import)

- [ ] **Step 9: Commit**

```bash
git add backend/app/schemas/seller_image_config.py backend/app/services/seller_image_config_service.py backend/app/api/v1/endpoints/seller_image_config.py backend/app/api/v1/router.py backend/tests/test_seller_image_config_service.py
git commit -m "feat: adiciona configuracao de imagens do seller (service + endpoint)"
```

---

### Task 5: Orquestração i2i — caminho simples (1 SKU) com fallback

**Files:**
- Modify: `backend/app/workers/tasks/image_tasks.py`
- Test: `backend/tests/test_image_tasks_i2i.py`

**Interfaces:**
- Consumes: `resolve_listing_skus`, `fetch_all_raw_photos` (Task 2); `OpenAIEditEngine.edit` (Task 3); `SellerImageConfig` (Task 1); `validate_image`, `ensure_dimensions`, `MLPictureService.upload` (já existentes em `app/services/image_service.py`).
- Produces: `_try_i2i_generation(db, listing, seller, access_token) -> int | None` — `None` sinaliza "sem config ou sem fotos, cair no texto-imagem"; `int` é a contagem de imagens salvas pelo caminho i2i.

- [ ] **Step 1: Escrever os testes (falhando)**

Criar `backend/tests/test_image_tasks_i2i.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_listing():
    listing = MagicMock()
    listing.id = "lid"
    listing.seller_id = "sid"
    listing.sku_external_id = "SKU0001"
    listing.created_via = "manual"
    return listing


class TestTryI2iGeneration:
    @pytest.mark.asyncio
    async def test_returns_none_when_seller_has_no_config(self):
        from app.workers.tasks.image_tasks import _try_i2i_generation

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # sem SellerImageConfig
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await _try_i2i_generation(mock_db, _make_listing(), MagicMock(), "token")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_raw_photos_missing(self):
        from app.workers.tasks.image_tasks import _try_i2i_generation

        mock_config = MagicMock()
        mock_config.raw_base_url = "https://pub-xxx.r2.dev/sku"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.services.seller_image_source_service.fetch_all_raw_photos",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await _try_i2i_generation(mock_db, _make_listing(), MagicMock(), "token")

        assert result is None

    @pytest.mark.asyncio
    async def test_generates_4_individual_images_for_single_sku(self):
        from app.workers.tasks.image_tasks import _try_i2i_generation

        mock_config = MagicMock()
        mock_config.raw_base_url = "https://pub-xxx.r2.dev/sku"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock()

        raw_photos = {"SKU0001": [b"raw1", b"raw2"]}

        with patch(
            "app.services.seller_image_source_service.fetch_all_raw_photos",
            new_callable=AsyncMock,
            return_value=raw_photos,
        ), patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as mock_engine_cls, patch(
            "app.services.image_service.validate_image", return_value=True
        ), patch(
            "app.services.image_service.ensure_dimensions", side_effect=lambda b: b
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(
                side_effect=[[b"v1", b"v2"], [b"v3", b"v4"]]  # 2 chamadas (1 por foto bruta), 2 imagens cada
            )
            mock_ml_cls.return_value.upload = AsyncMock(
                side_effect=["pic1", "pic2", "pic3", "pic4"]
            )
            result = await _try_i2i_generation(mock_db, _make_listing(), MagicMock(), "token")

        assert result == 4
        assert mock_engine_cls.return_value.edit.await_count == 2  # uma chamada por foto bruta
        assert mock_ml_cls.return_value.upload.await_count == 4
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `docker compose exec -T backend python -m pytest tests/test_image_tasks_i2i.py -v`
Expected: `ImportError: cannot import name '_try_i2i_generation' from 'app.workers.tasks.image_tasks'`

- [ ] **Step 3: Implementar `_try_i2i_generation` e integrar no fluxo**

Editar `backend/app/workers/tasks/image_tasks.py`. Adicionar a nova função (antes de `_generate_images_async`, logo após os imports do topo):

```python
async def _try_i2i_generation(db, listing, seller, access_token: str) -> int | None:
    """Tenta o caminho image-to-image (fotos brutas reais do seller). Retorna
    None se o seller não tiver SellerImageConfig ou faltar alguma foto bruta
    — nesses casos o chamador deve cair no texto-imagem existente, inalterado."""
    from sqlalchemy import select
    from app.models.seller_image_config import SellerImageConfig
    from app.models.listing_image import ListingImage
    from app.models.product_image import ProductImage
    from app.services.seller_image_source_service import resolve_listing_skus, fetch_all_raw_photos
    from app.services.image_engines.openai_edit_engine import OpenAIEditEngine
    from app.services.image_service import validate_image, ensure_dimensions, MLPictureService

    config = (
        await db.execute(
            select(SellerImageConfig).where(SellerImageConfig.seller_id == listing.seller_id)
        )
    ).scalar_one_or_none()
    if config is None:
        return None

    skus = await resolve_listing_skus(listing)
    if not skus:
        return None

    raw_photos_by_sku = await fetch_all_raw_photos(config.raw_base_url, skus)
    if raw_photos_by_sku is None:
        return None

    treatment_prompt = (
        "Professional e-commerce product photo. Pure white background, "
        "studio lighting, product centered and isolated, no text, no watermark, "
        "no people. Keep the exact product from the reference image — same "
        "shape, color, materials and proportions — only improve background, "
        "lighting and framing."
    )

    engine = OpenAIEditEngine()
    ml_pic = MLPictureService()
    saved = 0

    for sku in skus:
        for raw_photo in raw_photos_by_sku[sku]:
            variants = await engine.edit(images=[raw_photo], prompt=treatment_prompt, n=2)
            for img_bytes in variants:
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
                    kind="individual",
                    source_sku=sku,
                ))
                db.add(ProductImage(
                    seller_id=listing.seller_id,
                    sku=sku,
                    ml_picture_id=ml_picture_id,
                    source="openai_edit",
                    is_approved=False,
                ))
                saved += 1

    return saved
```

Agora integrar no `_generate_images_async`. Localizar o trecho:

```python
        seller = (
            await db.execute(select(Seller).where(Seller.id == listing.seller_id))
        ).scalar_one()
        access_token = await _fetch_upload_token(seller, db)

        engine_state = await get_engine_state(db)
```

E inserir a chamada ao caminho i2i entre as duas linhas, ficando:

```python
        seller = (
            await db.execute(select(Seller).where(Seller.id == listing.seller_id))
        ).scalar_one()
        access_token = await _fetch_upload_token(seller, db)

        i2i_saved = await _try_i2i_generation(db, listing, seller, access_token)
        if i2i_saved is not None:
            if i2i_saved == 0:
                raise RuntimeError("Nenhuma imagem válida foi gerada pelo motor 'openai_edit'")
            if listing.created_via == "batch":
                images = (await db.execute(
                    select(ListingImage).where(ListingImage.listing_id == listing.id)
                )).scalars().all()
                for img in images:
                    img.approved = True
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
            else:
                listing.status = "pending_image_approval"
                await db.commit()
            return {"listing_id": listing_id, "images_saved": i2i_saved, "source": "i2i"}

        engine_state = await get_engine_state(db)
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `docker compose exec -T backend python -m pytest tests/test_image_tasks_i2i.py -v`
Expected: 3 passed

- [ ] **Step 5: Rodar a suíte completa e confirmar que nada quebrou**

Run: `docker compose exec -T backend python -m pytest -v`
Expected: todos os testes existentes continuam passando (o caminho t2i não muda quando `_try_i2i_generation` retorna `None`).

- [ ] **Step 6: Commit**

```bash
git add backend/app/workers/tasks/image_tasks.py backend/tests/test_image_tasks_i2i.py
git commit -m "feat: integra caminho i2i (1 SKU) no pipeline de geracao de imagens"
```

---

### Task 6: Composição de capa para anúncios com múltiplos SKUs

**Files:**
- Modify: `backend/app/workers/tasks/image_tasks.py`
- Test: `backend/tests/test_image_tasks_i2i.py`

**Interfaces:**
- Consumes: `_try_i2i_generation` (Task 5, será estendida).
- Produces: mesma assinatura de `_try_i2i_generation`, agora suportando `len(skus) > 1`.

- [ ] **Step 1: Escrever o teste (falhando)**

Adicionar em `backend/tests/test_image_tasks_i2i.py`, dentro de `TestTryI2iGeneration`:

```python
    @pytest.mark.asyncio
    async def test_generates_cover_plus_individuals_for_kit_with_two_skus(self):
        from app.workers.tasks.image_tasks import _try_i2i_generation

        mock_config = MagicMock()
        mock_config.raw_base_url = "https://pub-xxx.r2.dev/sku"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock()

        raw_photos = {
            "SKU0001": [b"sku1-raw1", b"sku1-raw2"],
            "SKU0002": [b"sku2-raw1", b"sku2-raw2"],
        }

        listing = _make_listing()

        with patch(
            "app.services.seller_image_source_service.resolve_listing_skus",
            new_callable=AsyncMock,
            return_value=["SKU0001", "SKU0002"],
        ), patch(
            "app.services.seller_image_source_service.fetch_all_raw_photos",
            new_callable=AsyncMock,
            return_value=raw_photos,
        ), patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as mock_engine_cls, patch(
            "app.services.image_service.validate_image", return_value=True
        ), patch(
            "app.services.image_service.ensure_dimensions", side_effect=lambda b: b
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(
                side_effect=[
                    [b"cover"],                # 1a chamada: composicao da capa (n=1)
                    [b"v1", b"v2"],             # SKU0001 foto 1
                    [b"v3", b"v4"],             # SKU0001 foto 2
                    [b"v5", b"v6"],             # SKU0002 foto 1
                    [b"v7", b"v8"],             # SKU0002 foto 2
                ]
            )
            mock_ml_cls.return_value.upload = AsyncMock(
                side_effect=[f"pic{i}" for i in range(1, 10)]
            )
            result = await _try_i2i_generation(mock_db, listing, MagicMock(), "token")

        # 1 capa + (2 fotos x 2 variacoes x 2 SKUs) = 9
        assert result == 9
        assert mock_engine_cls.return_value.edit.await_count == 5

        added_images = [
            call.args[0] for call in mock_db.add.call_args_list
            if type(call.args[0]).__name__ == "ListingImage"
        ]
        assert added_images[0].kind == "cover_composed"
        assert added_images[0].source_sku is None
        assert all(img.kind == "individual" for img in added_images[1:])

    @pytest.mark.asyncio
    async def test_cover_composition_failure_falls_back_to_individual_only(self):
        from app.workers.tasks.image_tasks import _try_i2i_generation

        mock_config = MagicMock()
        mock_config.raw_base_url = "https://pub-xxx.r2.dev/sku"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock()

        raw_photos = {
            "SKU0001": [b"sku1-raw1", b"sku1-raw2"],
            "SKU0002": [b"sku2-raw1", b"sku2-raw2"],
        }

        with patch(
            "app.services.seller_image_source_service.resolve_listing_skus",
            new_callable=AsyncMock,
            return_value=["SKU0001", "SKU0002"],
        ), patch(
            "app.services.seller_image_source_service.fetch_all_raw_photos",
            new_callable=AsyncMock,
            return_value=raw_photos,
        ), patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as mock_engine_cls, patch(
            "app.services.image_service.validate_image", return_value=True
        ), patch(
            "app.services.image_service.ensure_dimensions", side_effect=lambda b: b
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(
                side_effect=[
                    RuntimeError("composicao falhou"),  # capa falha
                    [b"v1", b"v2"], [b"v3", b"v4"], [b"v5", b"v6"], [b"v7", b"v8"],
                ]
            )
            mock_ml_cls.return_value.upload = AsyncMock(
                side_effect=[f"pic{i}" for i in range(1, 9)]
            )
            result = await _try_i2i_generation(mock_db, _make_listing(), MagicMock(), "token")

        # sem capa: 2 fotos x 2 variacoes x 2 SKUs = 8
        assert result == 8
        added_images = [
            call.args[0] for call in mock_db.add.call_args_list
            if type(call.args[0]).__name__ == "ListingImage"
        ]
        assert all(img.kind == "individual" for img in added_images)
        assert added_images[0].sort_order == 0  # 1a imagem individual assume a posicao de capa
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `docker compose exec -T backend python -m pytest tests/test_image_tasks_i2i.py -v`
Expected: `test_generates_cover_plus_individuals_for_kit_with_two_skus` e `test_cover_composition_failure_falls_back_to_individual_only` FALHAM (resultado atual seria `None`, já que `_try_i2i_generation` hoje só aceita `len(skus) == 1` implicitamente — na prática hoje ela não faz early-return explícito para `len(skus) > 1`, mas o teste anterior (Task 5) não cobria esse caso; o teste novo vai falhar porque a capa não é gerada nem o prompt individual é chamado na ordem esperada).

- [ ] **Step 3: Estender `_try_i2i_generation` com a composição de capa**

Editar `backend/app/workers/tasks/image_tasks.py`, substituindo o corpo de `_try_i2i_generation` (a partir da definição de `treatment_prompt` até o final da função) por:

```python
    treatment_prompt = (
        "Professional e-commerce product photo. Pure white background, "
        "studio lighting, product centered and isolated, no text, no watermark, "
        "no people. Keep the exact product from the reference image — same "
        "shape, color, materials and proportions — only improve background, "
        "lighting and framing."
    )

    engine = OpenAIEditEngine()
    ml_pic = MLPictureService()
    saved = 0

    # Capa composta — só quando o anúncio tem mais de 1 SKU. Falha na
    # composição não afeta as imagens individuais: a capa é simplesmente
    # pulada, e a 1a imagem individual assume a posição de capa por ordem
    # natural do array `pictures` (sort_order=0).
    if len(skus) > 1:
        all_raw_photos = [photo for sku in skus for photo in raw_photos_by_sku[sku]]
        cover_prompt = (
            "Professional e-commerce product photo showing all the items from "
            "the reference images together, composed in a single realistic scene. "
            "Pure white background, studio lighting, items clearly visible and "
            "proportionate to each other, no text, no watermark, no people."
        )
        try:
            cover_variants = await engine.edit(images=all_raw_photos, prompt=cover_prompt, n=1)
        except Exception:
            cover_variants = []

        for img_bytes in cover_variants:
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
                kind="cover_composed",
                source_sku=None,
            ))
            saved += 1

    # Imagens individuais — sempre, uma chamada de edição por foto bruta.
    for sku in skus:
        for raw_photo in raw_photos_by_sku[sku]:
            variants = await engine.edit(images=[raw_photo], prompt=treatment_prompt, n=2)
            for img_bytes in variants:
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
                    kind="individual",
                    source_sku=sku,
                ))
                db.add(ProductImage(
                    seller_id=listing.seller_id,
                    sku=sku,
                    ml_picture_id=ml_picture_id,
                    source="openai_edit",
                    is_approved=False,
                ))
                saved += 1

    return saved
```

Nota: a restrição "cache `ProductImage` só armazena imagens individuais" (RF do spec) já é satisfeita porque o `db.add(ProductImage(...))` só existe dentro do laço de imagens individuais — a capa composta nunca gera uma linha em `ProductImage`.

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `docker compose exec -T backend python -m pytest tests/test_image_tasks_i2i.py -v`
Expected: 5 passed

- [ ] **Step 5: Rodar a suíte completa**

Run: `docker compose exec -T backend python -m pytest -v`
Expected: todos os testes passando (nenhuma regressão no caminho de 1 SKU nem no texto-imagem).

- [ ] **Step 6: Commit**

```bash
git add backend/app/workers/tasks/image_tasks.py backend/tests/test_image_tasks_i2i.py
git commit -m "feat: adiciona composicao de capa para anuncios com multiplos SKUs"
```

**Nota para quem for testar manualmente:** hoje não existe nenhuma forma real de criar um anúncio com mais de 1 SKU pela UI/API (kit é modelagem de outro projeto, ver spec). O caminho `len(skus) > 1` só é exercitado pelos testes acima, que forçam `resolve_listing_skus` a devolver uma lista com 2 SKUs via mock. Isso é esperado e está documentado no spec.

---

### Task 7: Escrita best-effort no bucket do seller (pós-publicação)

**Files:**
- Create: `backend/app/services/r2_write_service.py`
- Modify: `backend/app/workers/tasks/publish_tasks.py`
- Test: `backend/tests/test_r2_write_service.py`

**Interfaces:**
- Consumes: `SellerImageConfig` (Task 1), `decrypt_value` (`app/core/security.py`), `ListingImage` (Task 1, colunas `url_r2`/`r2_write_status`).
- Produces: `async def write_back_images(db, listing, seller_image_config, access_token: str) -> None` — nunca levanta exceção.

- [ ] **Step 1: Escrever os testes (falhando)**

Criar `backend/tests/test_r2_write_service.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.r2_write_service import write_back_images


def _make_listing_image(ml_picture_id: str):
    img = MagicMock()
    img.ml_picture_id = ml_picture_id
    img.approved = True
    img.url_r2 = None
    img.r2_write_status = None
    return img


def _make_listing():
    listing = MagicMock()
    listing.id = "lid"
    listing.mlb_id = "MLB123456789"
    return listing


class TestWriteBackImages:
    @pytest.mark.asyncio
    async def test_skips_when_no_config(self):
        img = _make_listing_image("pic1")
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [img]
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        await write_back_images(mock_db, _make_listing(), None, "token")

        assert img.r2_write_status == "skipped_no_config"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_when_write_credentials_incomplete(self):
        img = _make_listing_image("pic1")
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [img]
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        config = MagicMock()
        config.write_bucket_name = "bucket"
        config.write_endpoint_url = None  # incompleto
        config.write_access_key_id_enc = "enc-key"
        config.write_secret_access_key_enc = "enc-secret"

        await write_back_images(mock_db, _make_listing(), config, "token")

        assert img.r2_write_status == "skipped_no_config"

    @pytest.mark.asyncio
    async def test_writes_successfully_and_updates_status(self):
        img = _make_listing_image("pic1")
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [img]
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        config = MagicMock()
        config.write_bucket_name = "bucket"
        config.write_endpoint_url = "https://account.r2.cloudflarestorage.com"
        config.write_access_key_id_enc = "enc-key"
        config.write_secret_access_key_enc = "enc-secret"

        ml_item_response = MagicMock()
        ml_item_response.status_code = 200
        ml_item_response.json.return_value = {
            "pictures": [{"id": "pic1", "secure_url": "https://http2.mlstatic.com/pic1.jpg"}]
        }
        photo_response = MagicMock()
        photo_response.content = b"photo-bytes"
        photo_response.raise_for_status = MagicMock()

        mock_get = AsyncMock(side_effect=[ml_item_response, photo_response])

        with patch("httpx.AsyncClient") as mock_client_cls, \
             patch("app.services.r2_write_service.decrypt_value", side_effect=["access-key", "secret-key"]), \
             patch("boto3.client") as mock_boto_client:
            mock_client_cls.return_value.__aenter__.return_value.get = mock_get
            mock_s3 = MagicMock()
            mock_boto_client.return_value = mock_s3

            await write_back_images(mock_db, _make_listing(), config, "token")

        assert img.r2_write_status == "success"
        assert img.url_r2 == "anuncios/MLB123456789-1.jpg"
        mock_s3.put_object.assert_called_once()
        call_kwargs = mock_s3.put_object.call_args.kwargs
        assert call_kwargs["Bucket"] == "bucket"
        assert call_kwargs["Key"] == "anuncios/MLB123456789-1.jpg"
        assert call_kwargs["Body"] == b"photo-bytes"

    @pytest.mark.asyncio
    async def test_ml_item_fetch_failure_marks_all_as_failed(self):
        img = _make_listing_image("pic1")
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [img]
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        config = MagicMock()
        config.write_bucket_name = "bucket"
        config.write_endpoint_url = "https://account.r2.cloudflarestorage.com"
        config.write_access_key_id_enc = "enc-key"
        config.write_secret_access_key_enc = "enc-secret"

        ml_item_response = MagicMock()
        ml_item_response.status_code = 404

        mock_get = AsyncMock(return_value=ml_item_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.get = mock_get
            await write_back_images(mock_db, _make_listing(), config, "token")

        assert img.r2_write_status == "failed"

    @pytest.mark.asyncio
    async def test_missing_picture_in_ml_response_marks_that_image_failed(self):
        img = _make_listing_image("pic-not-found")
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [img]
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        config = MagicMock()
        config.write_bucket_name = "bucket"
        config.write_endpoint_url = "https://account.r2.cloudflarestorage.com"
        config.write_access_key_id_enc = "enc-key"
        config.write_secret_access_key_enc = "enc-secret"

        ml_item_response = MagicMock()
        ml_item_response.status_code = 200
        ml_item_response.json.return_value = {"pictures": []}  # pic-not-found nao esta la

        mock_get = AsyncMock(return_value=ml_item_response)

        with patch("httpx.AsyncClient") as mock_client_cls, \
             patch("boto3.client"):
            mock_client_cls.return_value.__aenter__.return_value.get = mock_get
            await write_back_images(mock_db, _make_listing(), config, "token")

        assert img.r2_write_status == "failed"
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `docker compose exec -T backend python -m pytest tests/test_r2_write_service.py -v`
Expected: `ModuleNotFoundError: No module named 'app.services.r2_write_service'`

- [ ] **Step 3: Implementar o serviço**

Criar `backend/app/services/r2_write_service.py`:

```python
import httpx
import boto3

from app.core.security import decrypt_value

ML_ITEMS_URL = "https://api.mercadolibre.com/items"


async def write_back_images(db, listing, seller_image_config, access_token: str) -> None:
    """Best-effort: baixa cada imagem publicada do CDN do ML e regrava no
    bucket do seller. Nunca levanta exceção — falhas ficam registradas em
    ListingImage.r2_write_status, e a publicação (que já aconteceu antes
    desta função rodar) nunca é revertida por causa disso."""
    from sqlalchemy import select
    from app.models.listing_image import ListingImage

    images = (
        await db.execute(
            select(ListingImage).where(
                ListingImage.listing_id == listing.id, ListingImage.approved == True
            )
        )
    ).scalars().all()

    has_write_config = bool(
        seller_image_config
        and seller_image_config.write_bucket_name
        and seller_image_config.write_endpoint_url
        and seller_image_config.write_access_key_id_enc
        and seller_image_config.write_secret_access_key_enc
    )
    if not has_write_config:
        for img in images:
            img.r2_write_status = "skipped_no_config"
        await db.commit()
        return

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{ML_ITEMS_URL}/{listing.mlb_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code != 200:
        for img in images:
            img.r2_write_status = "failed"
        await db.commit()
        return

    pictures_by_id = {p["id"]: p for p in resp.json().get("pictures", [])}

    s3 = boto3.client(
        "s3",
        endpoint_url=seller_image_config.write_endpoint_url,
        aws_access_key_id=decrypt_value(seller_image_config.write_access_key_id_enc),
        aws_secret_access_key=decrypt_value(seller_image_config.write_secret_access_key_enc),
    )

    for n, img in enumerate(images, start=1):
        picture = pictures_by_id.get(img.ml_picture_id)
        if picture is None:
            img.r2_write_status = "failed"
            continue
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                photo_resp = await client.get(picture["secure_url"])
            photo_resp.raise_for_status()
            key = f"anuncios/{listing.mlb_id}-{n}.jpg"
            s3.put_object(
                Bucket=seller_image_config.write_bucket_name,
                Key=key,
                Body=photo_resp.content,
                ContentType="image/jpeg",
            )
            img.url_r2 = key
            img.r2_write_status = "success"
        except Exception:
            img.r2_write_status = "failed"

    await db.commit()
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `docker compose exec -T backend python -m pytest tests/test_r2_write_service.py -v`
Expected: 5 passed

- [ ] **Step 5: Integrar em `publish_tasks.py`**

Editar `backend/app/workers/tasks/publish_tasks.py`. Localizar:

```python
        listing.mlb_id = mlb_id
        listing.status = "published_paused"
        await db.commit()

    return {"listing_id": listing_id, "mlb_id": mlb_id}
```

Substituir por:

```python
        listing.mlb_id = mlb_id
        listing.status = "published_paused"
        await db.commit()

        from app.models.seller_image_config import SellerImageConfig
        from app.services.r2_write_service import write_back_images

        seller_image_config = (
            await db.execute(
                select(SellerImageConfig).where(SellerImageConfig.seller_id == listing.seller_id)
            )
        ).scalar_one_or_none()
        try:
            await write_back_images(db, listing, seller_image_config, access_token)
        except Exception:
            pass  # best-effort — nunca bloqueia a publicacao, que ja aconteceu com sucesso

    return {"listing_id": listing_id, "mlb_id": mlb_id}
```

- [ ] **Step 6: Rodar a suíte completa**

Run: `docker compose exec -T backend python -m pytest -v`
Expected: todos os testes passando, incluindo `test_publish_tasks.py` (o `try/except` ao redor da nova chamada garante que o comportamento de publicação em si não muda).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/r2_write_service.py backend/app/workers/tasks/publish_tasks.py backend/tests/test_r2_write_service.py
git commit -m "feat: adiciona escrita best-effort das imagens no bucket do seller pos-publicacao"
```

---

### Task 8: Frontend — configuração de imagens do seller

**Files:**
- Create: `frontend/src/types/seller-image-config.ts`
- Create: `frontend/src/lib/api/seller-image-config.ts`
- Modify: `frontend/src/app/(dashboard)/settings/page.tsx`

**Interfaces:**
- Consumes: `GET /api/v1/sellers/image-config`, `PUT /api/v1/sellers/image-config` (Task 4).
- Produces: card "Configuração de imagens" em `/settings`.

- [ ] **Step 1: Criar os tipos**

Criar `frontend/src/types/seller-image-config.ts`:

```typescript
export interface SellerImageConfig {
  id: string
  seller_id: string
  raw_base_url: string
  write_bucket_name: string | null
  write_endpoint_url: string | null
  has_write_credentials: boolean
  created_at: string
  updated_at: string
}

export interface SellerImageConfigUpsert {
  raw_base_url: string
  write_bucket_name?: string | null
  write_endpoint_url?: string | null
  write_access_key_id?: string | null
  write_secret_access_key?: string | null
}
```

- [ ] **Step 2: Criar o client de API**

Criar `frontend/src/lib/api/seller-image-config.ts`:

```typescript
import { apiFetch } from "./client"
import type { SellerImageConfig, SellerImageConfigUpsert } from "@/types/seller-image-config"

export async function getSellerImageConfig(): Promise<SellerImageConfig | null> {
  return apiFetch<SellerImageConfig | null>("/api/v1/sellers/image-config")
}

export async function upsertSellerImageConfig(
  payload: SellerImageConfigUpsert
): Promise<SellerImageConfig> {
  return apiFetch<SellerImageConfig>("/api/v1/sellers/image-config", {
    method: "PUT",
    body: JSON.stringify(payload),
  })
}
```

- [ ] **Step 3: Adicionar o card em `/settings`**

Editar `frontend/src/app/(dashboard)/settings/page.tsx`.

Adicionar aos imports do topo:

```typescript
import { getSellerImageConfig, upsertSellerImageConfig } from "@/lib/api/seller-image-config"
import type { SellerImageConfig } from "@/types/seller-image-config"
import { ImageIcon } from "lucide-react"
```

(A linha `import { Loader2, CheckCircle, ExternalLink, ShoppingBag, Plus, Check, Tag, Pencil, Trash2 } from "lucide-react"` já existe — adicionar `ImageIcon` a essa mesma linha em vez de um import separado.)

Adicionar, dentro do componente `SettingsPage`, junto aos outros `useState`/`useQuery`/`useMutation` (após o bloco de `deleteMutation` do title config, antes de `resetForm`):

```typescript
  // --- Seller Image Config form state ---
  const [imageConfigForm, setImageConfigForm] = useState({
    raw_base_url: "",
    write_bucket_name: "",
    write_endpoint_url: "",
    write_access_key_id: "",
    write_secret_access_key: "",
  })

  const { data: imageConfig } = useQuery({
    queryKey: ["seller-image-config"],
    queryFn: getSellerImageConfig,
    retry: 1,
  })

  const imageConfigMutation = useMutation({
    mutationFn: upsertSellerImageConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["seller-image-config"] })
      toast.success("Configuração de imagens salva.")
    },
    onError: (err: Error) => {
      toast.error(err.message || "Erro ao salvar configuração de imagens.")
    },
  })

  function handleImageConfigSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!imageConfigForm.raw_base_url.trim()) {
      toast.error("URL base de leitura é obrigatória.")
      return
    }
    imageConfigMutation.mutate({
      raw_base_url: imageConfigForm.raw_base_url.trim(),
      write_bucket_name: imageConfigForm.write_bucket_name.trim() || null,
      write_endpoint_url: imageConfigForm.write_endpoint_url.trim() || null,
      write_access_key_id: imageConfigForm.write_access_key_id.trim() || null,
      write_secret_access_key: imageConfigForm.write_secret_access_key.trim() || null,
    })
  }
```

Adicionar o novo card no JSX, logo após o card "Estrutura de títulos" (depois do `</Card>` que fecha esse bloco, antes do `</div>` final do componente):

```tsx
      {/* ── Configuração de imagens ──────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ImageIcon className="w-5 h-5 text-purple-500" />
            Configuração de imagens
          </CardTitle>
          <CardDescription className="mt-1">
            Bucket próprio com as fotos brutas do produto (2 por SKU: <code>SKU-1.jpg</code>, <code>SKU-2.jpg</code>).
            Sem essa configuração, o pipeline continua gerando imagens por IA a partir do texto, como hoje.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleImageConfigSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="ic-raw-url">
                URL base de leitura <span className="text-red-500">*</span>
              </Label>
              <Input
                id="ic-raw-url"
                placeholder="ex: https://pub-xxx.r2.dev/sku"
                defaultValue={imageConfig?.raw_base_url ?? ""}
                onChange={(e) => setImageConfigForm((f) => ({ ...f, raw_base_url: e.target.value }))}
              />
            </div>

            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide pt-2">
              Escrita de volta (opcional — best-effort)
            </p>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="ic-write-bucket">Bucket de escrita</Label>
                <Input
                  id="ic-write-bucket"
                  placeholder="ex: meu-bucket"
                  defaultValue={imageConfig?.write_bucket_name ?? ""}
                  onChange={(e) => setImageConfigForm((f) => ({ ...f, write_bucket_name: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ic-write-endpoint">Endpoint S3-compatível</Label>
                <Input
                  id="ic-write-endpoint"
                  placeholder="ex: https://account.r2.cloudflarestorage.com"
                  defaultValue={imageConfig?.write_endpoint_url ?? ""}
                  onChange={(e) => setImageConfigForm((f) => ({ ...f, write_endpoint_url: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ic-write-key">Access Key ID</Label>
                <Input
                  id="ic-write-key"
                  type="password"
                  placeholder={imageConfig?.has_write_credentials ? "•••••••• (configurado)" : "opcional"}
                  onChange={(e) => setImageConfigForm((f) => ({ ...f, write_access_key_id: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ic-write-secret">Secret Access Key</Label>
                <Input
                  id="ic-write-secret"
                  type="password"
                  placeholder={imageConfig?.has_write_credentials ? "•••••••• (configurado)" : "opcional"}
                  onChange={(e) => setImageConfigForm((f) => ({ ...f, write_secret_access_key: e.target.value }))}
                />
              </div>
            </div>

            <Button type="submit" size="sm" disabled={imageConfigMutation.isPending}>
              {imageConfigMutation.isPending ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                  Salvando...
                </>
              ) : (
                "Salvar configuração"
              )}
            </Button>
          </form>
        </CardContent>
      </Card>
```

- [ ] **Step 4: Verificar o type-check**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json`
Expected: sem erros.

- [ ] **Step 5: Validar visualmente**

Run: `curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/settings` (com `npm run dev` já rodando)
Expected: `200`

Abrir `/settings` no navegador, confirmar que o card "Configuração de imagens" aparece abaixo de "Estrutura de títulos", preencher a URL base e salvar, confirmar toast de sucesso.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/seller-image-config.ts frontend/src/lib/api/seller-image-config.ts "frontend/src/app/(dashboard)/settings/page.tsx"
git commit -m "feat: adiciona card de configuracao de imagens do seller em /settings"
```

---

## Resumo de cobertura do spec

| Requisito do spec | Task |
|---|---|
| RF1 — Integração aditiva, opt-in por seller | Task 5 |
| RF2 — Contrato de fotos brutas (leitura) | Task 2 |
| RF3 — Resolução de SKUs do anúncio | Task 2 |
| RF4 — Geração por SKU (4 imagens individuais) | Task 5 |
| RF5 — Composição de capa (N>1 SKUs) | Task 6 |
| RF6 — Fallback tudo-ou-nada + mínimo de 4 fotos | Task 2, Task 5, Task 6 |
| RF7 — Escrita best-effort pós-publicação | Task 7 |
| RF8 — Indisponibilidade do provedor i2i → `failed` | Task 5, Task 6 (nenhum catch amplo ao redor da geração individual) |
| RF9 — Provedor único (OpenAI) para i2i | Task 3 |
| Modelo de dados (`SellerImageConfig`, colunas de `listing_images`) | Task 1 |
| Configuração no `/settings` | Task 4, Task 8 |
| Estratégia de testes (incl. caminho N>1 via fixture) | Task 2, 3, 4, 5, 6, 7 |
