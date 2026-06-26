# SPEC-014: Pipeline Journey UI & Bulk Actions — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the pipeline kanban em 6 colunas operacionais com ações em lote (aprovação de títulos, preenchimento de atributos via grid editor, aprovação de imagens, publicação) e visualização de erros inline por coluna.

**Architecture:** A `failed_step` column on `listings` captures where each failure occurred, allowing failed cards to appear in the correct kanban column. A new `listings_bulk.py` endpoint file exposes 8 bulk endpoints consumed by a new `BulkActionsBar` component that floats at the bottom of the screen when cards are selected. The attribute grid editor lives at `/listings/attributes` as a full page.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, Celery 5, PostgreSQL 16, Next.js 14 (App Router), TypeScript, Tailwind, shadcn/ui, @tanstack/react-query.

## Global Constraints

- All new backend endpoints under `/api/v1/`, JWT Bearer required.
- Multi-tenant: active seller resolved from `X-Seller-ID` header via `get_active_seller` dependency — never from request body.
- `listing_ids` in bulk requests must all belong to the active seller — each method validates this via `Listing.seller_id == self.seller_id` in the WHERE clause.
- Bulk endpoints are idempotent: listings already in the target status return `success=False` with `"estado inválido"` — no side effects.
- `failed_step` is nullable; old failed records without it fall back to the "Fila" column in the frontend.
- Every new model field must appear in the Alembic migration AND the SQLAlchemy model before running `alembic check`.
- Backend port: **8001**. Frontend port: **3000**.
- Conventional Commits: `feat:`, `fix:`, `test:`, `chore:`.

---

## File Map

### New files
| Path | Responsibility |
|---|---|
| `backend/alembic/versions/<rev>_spec014.py` | Migration: `failed_step` on listings |
| `backend/app/schemas/bulk.py` | `BulkListingRequest`, `BulkAttributeRequest`, `BulkItemResult`, `BulkResult`, `ListingAttributesRow`, `AttributeItem` |
| `backend/app/api/v1/endpoints/listings_bulk.py` | 8 bulk endpoints |
| `backend/tests/test_bulk_service.py` | Unit tests for bulk service methods |
| `frontend/src/components/listings/BulkActionsBar.tsx` | Floating action bar (column-aware) |
| `frontend/src/app/(dashboard)/listings/attributes/page.tsx` | Attribute grid editor page |
| `frontend/src/components/listings/AttributeGridEditor.tsx` | Grid editor component |

### Modified files
| Path | What changes |
|---|---|
| `backend/app/models/listing.py` | Add `failed_step: Mapped[Optional[str]]` |
| `backend/app/workers/tasks/image_tasks.py` | `_mark_failed_async` sets `listing.failed_step = listing.status` |
| `backend/app/workers/tasks/category_tasks.py` | Error handler sets `listing.failed_step` |
| `backend/app/workers/tasks/ai_tasks.py` | Error handlers set `listing.failed_step` |
| `backend/app/workers/tasks/publish_tasks.py` | Error handler sets `listing.failed_step` |
| `backend/app/services/listing_service.py` | Add 7 bulk methods |
| `backend/app/api/v1/router.py` | Register `listings_bulk_router` |
| `frontend/src/types/listing.ts` | Add `failed_step?: string \| null` to `ListingSummary` |
| `frontend/src/lib/api/listings.ts` | Add 7 bulk API functions + `getListingsForGrid` |
| `frontend/src/components/listings/PipelineBoard.tsx` | Full redesign: 6 columns, selection state, failed routing |
| `frontend/src/components/listings/ListingCard.tsx` | Add checkbox + inline error subcard |

---

## Task 1 — Migration: `failed_step` + Worker Capture

**Files:**
- Create: `backend/alembic/versions/<rev>_spec014.py`
- Modify: `backend/app/models/listing.py`
- Modify: `backend/app/workers/tasks/image_tasks.py`
- Modify: `backend/app/workers/tasks/category_tasks.py`
- Modify: `backend/app/workers/tasks/ai_tasks.py`
- Modify: `backend/app/workers/tasks/publish_tasks.py`

**Interfaces:**
- Produces: `Listing.failed_step` (String 50, nullable) available in DB and ORM.
- Produces: Every worker that transitions a listing to `"failed"` also sets `listing.failed_step = listing.status` (the status at failure time) immediately before the transition.

- [ ] **Step 1: Add `failed_step` to the Listing model**

In `backend/app/models/listing.py`, find where the other `Mapped[Optional[str]]` status fields are declared. Add after the `status` field:

```python
    failed_step: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
```

- [ ] **Step 2: Generate the migration**

```bash
docker compose exec backend alembic revision --autogenerate -m "spec014 add failed_step to listings"
```

Open the generated file and verify `upgrade()` contains exactly:

```python
def upgrade() -> None:
    op.add_column("listings", sa.Column("failed_step", sa.String(50), nullable=True))

def downgrade() -> None:
    op.drop_column("listings", "failed_step")
```

If autogenerate added extra operations, remove them — only this column changes.

- [ ] **Step 3: Apply the migration**

```bash
docker compose exec backend alembic upgrade head
```

Expected: `Running upgrade ... -> <rev>, spec014 add failed_step to listings`

- [ ] **Step 4: Verify in DB**

```bash
docker compose exec postgres psql -U mlb_user -d publicar_ad_mlb -c "\d listings" | grep failed_step
```

Expected: `failed_step | character varying(50) | | |`

- [ ] **Step 5: Update `_mark_failed_async` in `image_tasks.py`**

Find the function `_mark_failed_async` (or `_mark_failed` equivalent). Locate the line `listing.status = "failed"`. Immediately before it, add:

```python
            listing.failed_step = listing.status  # capture column for UI routing
            listing.status = "failed"
```

The result should look like:
```python
async def _mark_failed_async(listing_id: str, error_msg: str) -> None:
    from app.database import worker_session
    from app.models.listing import Listing
    from app.models.listing_job import ListingJob
    from sqlalchemy import select
    async with worker_session() as db:
        result = await db.execute(select(Listing).where(Listing.id == listing_id))
        listing = result.scalar_one_or_none()
        if listing and listing.status != "failed":
            listing.failed_step = listing.status  # ← added
            listing.status = "failed"
            db.add(ListingJob(
                listing_id=listing.id,
                task_name="generate_images",
                status="failed",
                error_message=error_msg[:500] if error_msg else None,
            ))
            await db.commit()
```

- [ ] **Step 6: Update `category_tasks.py` error handler**

In `predict_category` (or `_predict_category_async`), find every `listing.status = "failed"` assignment and add the capture line before it:

```python
            listing.failed_step = listing.status  # ← add this line
            listing.status = "failed"
```

- [ ] **Step 7: Update `ai_tasks.py` error handlers**

Same pattern — in both `_generate_title_async` and `_generate_description_async`, before every `listing.status = "failed"`:

```python
            listing.failed_step = listing.status  # ← add this line
            listing.status = "failed"
```

- [ ] **Step 8: Update `publish_tasks.py` error handler**

Same pattern in `_publish_listing_async`:

```python
            listing.failed_step = listing.status  # ← add this line
            listing.status = "failed"
```

- [ ] **Step 9: Rebuild workers and verify startup**

```bash
docker compose build backend celery_worker && docker compose up -d backend celery_worker
docker compose logs celery_worker --tail=20
```

Expected: no import errors, worker starts normally.

- [ ] **Step 10: Commit**

```bash
git add backend/alembic/versions/ backend/app/models/listing.py \
        backend/app/workers/tasks/image_tasks.py \
        backend/app/workers/tasks/category_tasks.py \
        backend/app/workers/tasks/ai_tasks.py \
        backend/app/workers/tasks/publish_tasks.py
git commit -m "feat: add failed_step to listings and capture in all worker error handlers"
```

---

## Task 2 — Backend Schemas

**Files:**
- Create: `backend/app/schemas/bulk.py`

**Interfaces:**
- Produces: `BulkListingRequest`, `BulkAttributeRequest`, `BulkItemResult`, `BulkResult`, `ListingAttributesRow`, `AttributeItem` — used by Tasks 3, 4, and 5.

- [ ] **Step 1: Create `backend/app/schemas/bulk.py`**

```python
# backend/app/schemas/bulk.py
from uuid import UUID
from pydantic import BaseModel, field_validator


class BulkListingRequest(BaseModel):
    listing_ids: list[UUID]

    @field_validator("listing_ids")
    @classmethod
    def not_empty(cls, v: list[UUID]) -> list[UUID]:
        if not v:
            raise ValueError("listing_ids não pode ser vazio")
        if len(v) > 200:
            raise ValueError("máximo 200 listings por operação")
        return v


class BulkAttributeRequest(BaseModel):
    listing_ids: list[UUID]
    attribute_id: str
    value_name: str
    value_id: str | None = None

    @field_validator("listing_ids")
    @classmethod
    def not_empty(cls, v: list[UUID]) -> list[UUID]:
        if not v:
            raise ValueError("listing_ids não pode ser vazio")
        if len(v) > 200:
            raise ValueError("máximo 200 listings por operação")
        return v

    @field_validator("attribute_id", "value_name")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("campo não pode ser vazio")
        return v.strip()


class BulkItemResult(BaseModel):
    listing_id: UUID
    success: bool
    error: str | None = None


class BulkResult(BaseModel):
    processed: int
    failed: int
    results: list[BulkItemResult]


class AttributeItem(BaseModel):
    attribute_id: str
    attribute_name: str
    value_name: str | None
    value_id: str | None
    is_required: bool

    model_config = {"from_attributes": True}


class ListingAttributesRow(BaseModel):
    listing_id: UUID
    sku_external_id: str
    selected_title: str | None
    ml_category_id: str | None
    status: str
    attributes: list[AttributeItem]

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/bulk.py
git commit -m "feat: bulk operation schemas"
```

---

## Task 3 — Bulk Service Tests (TDD)

**Files:**
- Create: `backend/tests/test_bulk_service.py`

**Interfaces:**
- Consumes: `ListingService` (from `app.services.listing_service`), `BulkListingRequest`, `BulkAttributeRequest`.
- Produces: 7 failing tests that pass after Task 4.

- [ ] **Step 1: Create the test file**

```python
# backend/tests/test_bulk_service.py
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from app.services.listing_service import ListingService
from app.schemas.bulk import BulkListingRequest, BulkAttributeRequest


def make_listing(status: str, seller_id=None):
    listing = MagicMock()
    listing.id = uuid.uuid4()
    listing.seller_id = seller_id or uuid.uuid4()
    listing.status = status
    listing.failed_step = None
    listing.selected_title = None
    return listing


def make_title(score: float | None, created_at=None):
    from datetime import datetime
    t = MagicMock()
    t.title_text = f"Título score={score}"
    t.ai_score = score
    t.selected = False
    t.created_at = created_at or datetime.utcnow()
    return t


def mock_execute_single(obj):
    result = MagicMock()
    result.scalar_one_or_none.return_value = obj
    result.scalars.return_value.all.return_value = []
    return result


@pytest.mark.asyncio
async def test_bulk_approve_titles_selects_highest_score():
    db = AsyncMock()
    seller_id = uuid.uuid4()
    listing = make_listing("pending_title_approval", seller_id)
    titles = [make_title(8.5), make_title(9.2), make_title(7.1)]

    execute_calls = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=listing)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=titles[1])),  # highest score
    ]
    db.execute = AsyncMock(side_effect=execute_calls)

    svc = ListingService(db, seller_id)
    with patch("app.workers.tasks.category_tasks.predict_category") as mock_task:
        mock_task.delay = MagicMock()
        result = await svc.bulk_approve_titles([listing.id])

    assert result.processed == 1
    assert result.failed == 0
    assert listing.selected_title == titles[1].title_text
    assert listing.status == "predicting_category"
    mock_task.delay.assert_called_once_with(str(listing.id))


@pytest.mark.asyncio
async def test_bulk_approve_titles_skips_wrong_status():
    db = AsyncMock()
    seller_id = uuid.uuid4()
    listing = make_listing("generating_title", seller_id)
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=listing)))

    svc = ListingService(db, seller_id)
    result = await svc.bulk_approve_titles([listing.id])

    assert result.processed == 0
    assert result.failed == 1
    assert result.results[0].error == "estado inválido"


@pytest.mark.asyncio
async def test_bulk_reject_titles_returns_to_draft():
    db = AsyncMock()
    seller_id = uuid.uuid4()
    listing = make_listing("pending_title_approval", seller_id)
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=listing)))

    svc = ListingService(db, seller_id)
    result = await svc.bulk_reject_titles([listing.id])

    assert result.processed == 1
    assert listing.status == "draft"
    assert listing.selected_title is None


@pytest.mark.asyncio
async def test_bulk_fill_attribute_advances_when_all_required_filled():
    db = AsyncMock()
    seller_id = uuid.uuid4()
    listing = make_listing("pending_seller_attributes", seller_id)

    # execute calls: 1 = get listing, 2 = update attribute, 3 = check unfilled
    execute_calls = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=listing)),  # listing fetch
        MagicMock(rowcount=1),                                           # attr update
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),  # no unfilled
    ]
    db.execute = AsyncMock(side_effect=execute_calls)

    svc = ListingService(db, seller_id)
    result = await svc.bulk_fill_attribute(
        listing_ids=[listing.id],
        attribute_id="BRAND",
        value_name="NSK",
        value_id=None,
    )

    assert result.processed == 1
    assert listing.status == "pending_description"


@pytest.mark.asyncio
async def test_bulk_fill_attribute_does_not_advance_when_unfilled_remain():
    db = AsyncMock()
    seller_id = uuid.uuid4()
    listing = make_listing("pending_seller_attributes", seller_id)
    unfilled_attr = MagicMock()

    execute_calls = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=listing)),
        MagicMock(rowcount=1),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[unfilled_attr])))),
    ]
    db.execute = AsyncMock(side_effect=execute_calls)

    svc = ListingService(db, seller_id)
    result = await svc.bulk_fill_attribute(
        listing_ids=[listing.id],
        attribute_id="BRAND",
        value_name="NSK",
        value_id=None,
    )

    assert result.processed == 1
    assert listing.status == "pending_seller_attributes"  # unchanged


@pytest.mark.asyncio
async def test_bulk_approve_images_transitions_and_dispatches():
    db = AsyncMock()
    seller_id = uuid.uuid4()
    listing = make_listing("pending_image_approval", seller_id)
    db.execute = AsyncMock(return_value=MagicMock(
        scalar_one_or_none=MagicMock(return_value=listing),
        rowcount=1,
    ))

    svc = ListingService(db, seller_id)
    with patch("app.workers.tasks.ai_tasks.generate_description") as mock_task:
        mock_task.delay = MagicMock()
        result = await svc.bulk_approve_images([listing.id])

    assert result.processed == 1
    assert listing.status == "generating_description"
    mock_task.delay.assert_called_once_with(str(listing.id))


@pytest.mark.asyncio
async def test_bulk_publish_transitions_and_dispatches():
    db = AsyncMock()
    seller_id = uuid.uuid4()
    execute_result = MagicMock()
    execute_result.rowcount = 1
    db.execute = AsyncMock(return_value=execute_result)

    svc = ListingService(db, seller_id)
    listing_id = uuid.uuid4()
    with patch("app.workers.tasks.publish_tasks.publish_listing") as mock_task:
        mock_task.delay = MagicMock()
        result = await svc.bulk_publish([listing_id])

    assert result.processed == 1
    mock_task.delay.assert_called_once_with(str(listing_id))
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
docker compose exec backend python -m pytest backend/tests/test_bulk_service.py -v
```

Expected: `AttributeError: 'ListingService' object has no attribute 'bulk_approve_titles'` or similar.

- [ ] **Step 3: Commit (tests only)**

```bash
git add backend/tests/test_bulk_service.py
git commit -m "test: bulk service unit tests (red)"
```

---

## Task 4 — Bulk Service Methods Implementation

**Files:**
- Modify: `backend/app/services/listing_service.py`

**Interfaces:**
- Consumes: `ListingTitle`, `ListingImage`, `ListingAttribute` models; `BulkItemResult`, `BulkResult` schemas.
- Produces: `ListingService.bulk_start_pipeline`, `.bulk_approve_titles`, `.bulk_reject_titles`, `.bulk_approve_images`, `.bulk_generate_images`, `.bulk_publish`, `.bulk_fill_attribute` — all `async`, return `BulkResult`.

- [ ] **Step 1: Add imports to `listing_service.py`**

At the top of `backend/app/services/listing_service.py`, ensure these imports exist (add any missing):

```python
from sqlalchemy import update as sa_update, delete as sa_delete
from app.models.listing_title import ListingTitle
from app.models.listing_image import ListingImage
from app.models.listing_attribute import ListingAttribute
from app.schemas.bulk import BulkItemResult, BulkResult
```

- [ ] **Step 2: Add `_bulk_result` helper method**

Inside `ListingService`, add a private helper at the top of the class body (after `__init__`):

```python
    @staticmethod
    def _bulk_result(results: list[BulkItemResult]) -> BulkResult:
        return BulkResult(
            processed=sum(1 for r in results if r.success),
            failed=sum(1 for r in results if not r.success),
            results=results,
        )
```

- [ ] **Step 3: Add `bulk_start_pipeline`**

```python
    async def bulk_start_pipeline(self, listing_ids: list) -> BulkResult:
        results: list[BulkItemResult] = []
        for lid in listing_ids:
            try:
                r = await self.db.execute(
                    sa_update(Listing)
                    .where(Listing.id == lid, Listing.seller_id == self.seller_id, Listing.status == "draft")
                    .values(status="generating_title")
                    .execution_options(synchronize_session=False)
                )
                await self.db.commit()
                if r.rowcount == 0:
                    results.append(BulkItemResult(listing_id=lid, success=False, error="estado inválido"))
                    continue
                from app.workers.tasks.ai_tasks import generate_title
                generate_title.delay(str(lid))
                results.append(BulkItemResult(listing_id=lid, success=True))
            except Exception as e:
                await self.db.rollback()
                results.append(BulkItemResult(listing_id=lid, success=False, error=str(e)))
        return self._bulk_result(results)
```

- [ ] **Step 4: Add `bulk_approve_titles`**

```python
    async def bulk_approve_titles(self, listing_ids: list) -> BulkResult:
        results: list[BulkItemResult] = []
        for lid in listing_ids:
            try:
                r = await self.db.execute(
                    select(Listing).where(Listing.id == lid, Listing.seller_id == self.seller_id)
                )
                listing = r.scalar_one_or_none()
                if not listing or listing.status != "pending_title_approval":
                    results.append(BulkItemResult(listing_id=lid, success=False, error="estado inválido"))
                    continue
                title_r = await self.db.execute(
                    select(ListingTitle)
                    .where(ListingTitle.listing_id == lid)
                    .order_by(ListingTitle.ai_score.desc().nulls_last(), ListingTitle.created_at.asc())
                    .limit(1)
                )
                top = title_r.scalar_one_or_none()
                if not top:
                    results.append(BulkItemResult(listing_id=lid, success=False, error="nenhum título encontrado"))
                    continue
                listing.selected_title = top.title_text
                top.selected = True
                listing.status = "predicting_category"
                await self.db.commit()
                from app.workers.tasks.category_tasks import predict_category
                predict_category.delay(str(lid))
                results.append(BulkItemResult(listing_id=lid, success=True))
            except Exception as e:
                await self.db.rollback()
                results.append(BulkItemResult(listing_id=lid, success=False, error=str(e)))
        return self._bulk_result(results)
```

- [ ] **Step 5: Add `bulk_reject_titles`**

```python
    async def bulk_reject_titles(self, listing_ids: list) -> BulkResult:
        results: list[BulkItemResult] = []
        for lid in listing_ids:
            try:
                r = await self.db.execute(
                    select(Listing).where(Listing.id == lid, Listing.seller_id == self.seller_id)
                )
                listing = r.scalar_one_or_none()
                if not listing or listing.status != "pending_title_approval":
                    results.append(BulkItemResult(listing_id=lid, success=False, error="estado inválido"))
                    continue
                await self.db.execute(
                    sa_delete(ListingTitle).where(ListingTitle.listing_id == lid)
                )
                listing.selected_title = None
                listing.status = "draft"
                await self.db.commit()
                results.append(BulkItemResult(listing_id=lid, success=True))
            except Exception as e:
                await self.db.rollback()
                results.append(BulkItemResult(listing_id=lid, success=False, error=str(e)))
        return self._bulk_result(results)
```

- [ ] **Step 6: Add `bulk_approve_images`**

```python
    async def bulk_approve_images(self, listing_ids: list) -> BulkResult:
        results: list[BulkItemResult] = []
        for lid in listing_ids:
            try:
                r = await self.db.execute(
                    select(Listing).where(Listing.id == lid, Listing.seller_id == self.seller_id)
                )
                listing = r.scalar_one_or_none()
                if not listing or listing.status != "pending_image_approval":
                    results.append(BulkItemResult(listing_id=lid, success=False, error="estado inválido"))
                    continue
                await self.db.execute(
                    sa_update(ListingImage)
                    .where(ListingImage.listing_id == lid)
                    .values(approved=True)
                    .execution_options(synchronize_session=False)
                )
                listing.status = "generating_description"
                await self.db.commit()
                from app.workers.tasks.ai_tasks import generate_description
                generate_description.delay(str(lid))
                results.append(BulkItemResult(listing_id=lid, success=True))
            except Exception as e:
                await self.db.rollback()
                results.append(BulkItemResult(listing_id=lid, success=False, error=str(e)))
        return self._bulk_result(results)
```

- [ ] **Step 7: Add `bulk_generate_images`**

```python
    async def bulk_generate_images(self, listing_ids: list) -> BulkResult:
        results: list[BulkItemResult] = []
        for lid in listing_ids:
            try:
                r = await self.db.execute(
                    sa_update(Listing)
                    .where(
                        Listing.id == lid,
                        Listing.seller_id == self.seller_id,
                        Listing.status == "pending_description",
                    )
                    .values(status="generating_images")
                    .execution_options(synchronize_session=False)
                )
                await self.db.commit()
                if r.rowcount == 0:
                    results.append(BulkItemResult(listing_id=lid, success=False, error="estado inválido"))
                    continue
                from celery import chain as celery_chain
                from app.workers.tasks.image_tasks import generate_images
                from app.workers.tasks.ai_tasks import generate_description
                from app.workers.tasks.publish_tasks import publish_listing
                celery_chain(
                    generate_images.si(str(lid)),
                    generate_description.si(str(lid)),
                    publish_listing.si(str(lid)),
                ).delay()
                results.append(BulkItemResult(listing_id=lid, success=True))
            except Exception as e:
                await self.db.rollback()
                results.append(BulkItemResult(listing_id=lid, success=False, error=str(e)))
        return self._bulk_result(results)
```

- [ ] **Step 8: Add `bulk_publish`**

```python
    async def bulk_publish(self, listing_ids: list) -> BulkResult:
        results: list[BulkItemResult] = []
        for lid in listing_ids:
            try:
                r = await self.db.execute(
                    sa_update(Listing)
                    .where(
                        Listing.id == lid,
                        Listing.seller_id == self.seller_id,
                        Listing.status == "ready_to_publish",
                    )
                    .values(status="publishing")
                    .execution_options(synchronize_session=False)
                )
                await self.db.commit()
                if r.rowcount == 0:
                    results.append(BulkItemResult(listing_id=lid, success=False, error="estado inválido"))
                    continue
                from app.workers.tasks.publish_tasks import publish_listing
                publish_listing.delay(str(lid))
                results.append(BulkItemResult(listing_id=lid, success=True))
            except Exception as e:
                await self.db.rollback()
                results.append(BulkItemResult(listing_id=lid, success=False, error=str(e)))
        return self._bulk_result(results)
```

- [ ] **Step 9: Add `bulk_fill_attribute`**

```python
    async def bulk_fill_attribute(
        self,
        listing_ids: list,
        attribute_id: str,
        value_name: str,
        value_id: str | None,
    ) -> BulkResult:
        results: list[BulkItemResult] = []
        for lid in listing_ids:
            try:
                r = await self.db.execute(
                    select(Listing).where(
                        Listing.id == lid,
                        Listing.seller_id == self.seller_id,
                        Listing.status.in_(["pending_seller_attributes", "pending_description"]),
                    )
                )
                listing = r.scalar_one_or_none()
                if not listing:
                    results.append(BulkItemResult(listing_id=lid, success=False, error="estado inválido"))
                    continue
                attr_r = await self.db.execute(
                    sa_update(ListingAttribute)
                    .where(
                        ListingAttribute.listing_id == lid,
                        ListingAttribute.attribute_id == attribute_id,
                    )
                    .values(value_name=value_name, value_id=value_id)
                    .execution_options(synchronize_session=False)
                )
                if attr_r.rowcount == 0:
                    results.append(BulkItemResult(listing_id=lid, success=False, error="atributo não encontrado"))
                    continue
                # Advance status if all required attrs are now filled
                unfilled_r = await self.db.execute(
                    select(ListingAttribute).where(
                        ListingAttribute.listing_id == lid,
                        ListingAttribute.is_required == True,
                        ListingAttribute.value_name.is_(None),
                    )
                )
                if not unfilled_r.scalars().all() and listing.status == "pending_seller_attributes":
                    listing.status = "pending_description"
                await self.db.commit()
                results.append(BulkItemResult(listing_id=lid, success=True))
            except Exception as e:
                await self.db.rollback()
                results.append(BulkItemResult(listing_id=lid, success=False, error=str(e)))
        return self._bulk_result(results)
```

- [ ] **Step 10: Run tests — expect PASS**

```bash
docker compose exec backend python -m pytest backend/tests/test_bulk_service.py -v
```

Expected: 7 passed.

- [ ] **Step 11: Commit**

```bash
git add backend/app/services/listing_service.py
git commit -m "feat: bulk service methods on ListingService"
```

---

## Task 5 — Bulk API Endpoints

**Files:**
- Create: `backend/app/api/v1/endpoints/listings_bulk.py`
- Modify: `backend/app/api/v1/router.py`

**Interfaces:**
- Produces:
  - `POST /api/v1/listings/bulk/start-pipeline` → `BulkResult`
  - `POST /api/v1/listings/bulk/approve-titles` → `BulkResult`
  - `POST /api/v1/listings/bulk/reject-titles` → `BulkResult`
  - `POST /api/v1/listings/bulk/approve-images` → `BulkResult`
  - `POST /api/v1/listings/bulk/generate-images` → `BulkResult`
  - `POST /api/v1/listings/bulk/publish` → `BulkResult`
  - `PUT /api/v1/listings/bulk/attribute` → `BulkResult`
  - `GET /api/v1/listings/bulk/attributes` → `list[ListingAttributesRow]`

- [ ] **Step 1: Create `backend/app/api/v1/endpoints/listings_bulk.py`**

```python
# backend/app/api/v1/endpoints/listings_bulk.py
import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.dependencies import get_db, get_current_user, get_active_seller
from app.models.user import User
from app.models.seller import Seller
from app.models.listing import Listing
from app.models.listing_attribute import ListingAttribute
from app.schemas.bulk import (
    BulkListingRequest, BulkAttributeRequest, BulkResult,
    ListingAttributesRow, AttributeItem,
)
from app.services.listing_service import ListingService

router = APIRouter(prefix="/bulk", tags=["listings-bulk"])


def _svc(db: AsyncSession, seller: Seller) -> ListingService:
    return ListingService(db, seller.id)


@router.get("/attributes", response_model=list[ListingAttributesRow])
async def get_listings_for_attribute_grid(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    seller: Seller = Depends(get_active_seller),
):
    result = await db.execute(
        select(Listing)
        .where(
            Listing.seller_id == seller.id,
            Listing.status.in_(["pending_seller_attributes", "pending_description"]),
        )
        .order_by(Listing.ml_category_id.nulls_last(), Listing.created_at)
    )
    listings = result.scalars().all()
    rows: list[ListingAttributesRow] = []
    for listing in listings:
        attrs_r = await db.execute(
            select(ListingAttribute)
            .where(ListingAttribute.listing_id == listing.id)
            .order_by(ListingAttribute.is_required.desc(), ListingAttribute.attribute_name)
        )
        rows.append(ListingAttributesRow(
            listing_id=listing.id,
            sku_external_id=listing.sku_external_id,
            selected_title=listing.selected_title,
            ml_category_id=listing.ml_category_id,
            status=listing.status,
            attributes=[
                AttributeItem(
                    attribute_id=a.attribute_id,
                    attribute_name=a.attribute_name,
                    value_name=a.value_name,
                    value_id=a.value_id,
                    is_required=a.is_required,
                )
                for a in attrs_r.scalars().all()
            ],
        ))
    return rows


@router.post("/start-pipeline", response_model=BulkResult)
async def bulk_start_pipeline(
    payload: BulkListingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    seller: Seller = Depends(get_active_seller),
):
    return await _svc(db, seller).bulk_start_pipeline(payload.listing_ids)


@router.post("/approve-titles", response_model=BulkResult)
async def bulk_approve_titles(
    payload: BulkListingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    seller: Seller = Depends(get_active_seller),
):
    return await _svc(db, seller).bulk_approve_titles(payload.listing_ids)


@router.post("/reject-titles", response_model=BulkResult)
async def bulk_reject_titles(
    payload: BulkListingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    seller: Seller = Depends(get_active_seller),
):
    return await _svc(db, seller).bulk_reject_titles(payload.listing_ids)


@router.post("/approve-images", response_model=BulkResult)
async def bulk_approve_images(
    payload: BulkListingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    seller: Seller = Depends(get_active_seller),
):
    return await _svc(db, seller).bulk_approve_images(payload.listing_ids)


@router.post("/generate-images", response_model=BulkResult)
async def bulk_generate_images(
    payload: BulkListingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    seller: Seller = Depends(get_active_seller),
):
    return await _svc(db, seller).bulk_generate_images(payload.listing_ids)


@router.post("/publish", response_model=BulkResult)
async def bulk_publish(
    payload: BulkListingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    seller: Seller = Depends(get_active_seller),
):
    return await _svc(db, seller).bulk_publish(payload.listing_ids)


@router.put("/attribute", response_model=BulkResult)
async def bulk_fill_attribute(
    payload: BulkAttributeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    seller: Seller = Depends(get_active_seller),
):
    return await _svc(db, seller).bulk_fill_attribute(
        listing_ids=payload.listing_ids,
        attribute_id=payload.attribute_id,
        value_name=payload.value_name,
        value_id=payload.value_id,
    )
```

- [ ] **Step 2: Register in router**

In `backend/app/api/v1/router.py`, add alongside the existing `listings` router import:

```python
from app.api.v1.endpoints.listings_bulk import router as listings_bulk_router
# ...
router.include_router(listings_bulk_router, prefix="/listings")
```

- [ ] **Step 3: Rebuild and verify endpoints appear in OpenAPI**

```bash
docker compose build backend && docker compose up -d backend
curl -s http://localhost:8001/openapi.json | python -c "
import sys, json
paths = json.load(sys.stdin)['paths']
[print(p) for p in sorted(paths) if 'bulk' in p]
"
```

Expected output:
```
/api/v1/listings/bulk/approve-images
/api/v1/listings/bulk/approve-titles
/api/v1/listings/bulk/attribute
/api/v1/listings/bulk/attributes
/api/v1/listings/bulk/generate-images
/api/v1/listings/bulk/publish
/api/v1/listings/bulk/reject-titles
/api/v1/listings/bulk/start-pipeline
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/v1/endpoints/listings_bulk.py backend/app/api/v1/router.py
git commit -m "feat: bulk action REST endpoints for listings"
```

---

## Task 6 — Frontend Types + API Client

**Files:**
- Modify: `frontend/src/types/listing.ts`
- Modify: `frontend/src/lib/api/listings.ts`

**Interfaces:**
- Produces: `ListingSummary.failed_step?: string | null`; `BulkResult` type; 7 bulk API functions + `getListingsForGrid`.

- [ ] **Step 1: Add `failed_step` to `ListingSummary` in `frontend/src/types/listing.ts`**

Locate the `ListingSummary` interface and add:

```typescript
  failed_step?: string | null
```

Also add these new types (at the end of the file):

```typescript
export interface BulkItemResult {
  listing_id: string
  success: boolean
  error?: string | null
}

export interface BulkResult {
  processed: number
  failed: number
  results: BulkItemResult[]
}

export interface AttributeItem {
  attribute_id: string
  attribute_name: string
  value_name: string | null
  value_id: string | null
  is_required: boolean
}

export interface ListingAttributesRow {
  listing_id: string
  sku_external_id: string
  selected_title: string | null
  ml_category_id: string | null
  status: string
  attributes: AttributeItem[]
}
```

- [ ] **Step 2: Add bulk API functions to `frontend/src/lib/api/listings.ts`**

Append to the end of the file:

```typescript
export async function bulkStartPipeline(listingIds: string[]): Promise<BulkResult> {
  return apiFetch<BulkResult>("/api/v1/listings/bulk/start-pipeline", {
    method: "POST",
    body: JSON.stringify({ listing_ids: listingIds }),
  })
}

export async function bulkApproveTitles(listingIds: string[]): Promise<BulkResult> {
  return apiFetch<BulkResult>("/api/v1/listings/bulk/approve-titles", {
    method: "POST",
    body: JSON.stringify({ listing_ids: listingIds }),
  })
}

export async function bulkRejectTitles(listingIds: string[]): Promise<BulkResult> {
  return apiFetch<BulkResult>("/api/v1/listings/bulk/reject-titles", {
    method: "POST",
    body: JSON.stringify({ listing_ids: listingIds }),
  })
}

export async function bulkApproveImages(listingIds: string[]): Promise<BulkResult> {
  return apiFetch<BulkResult>("/api/v1/listings/bulk/approve-images", {
    method: "POST",
    body: JSON.stringify({ listing_ids: listingIds }),
  })
}

export async function bulkGenerateImages(listingIds: string[]): Promise<BulkResult> {
  return apiFetch<BulkResult>("/api/v1/listings/bulk/generate-images", {
    method: "POST",
    body: JSON.stringify({ listing_ids: listingIds }),
  })
}

export async function bulkPublish(listingIds: string[]): Promise<BulkResult> {
  return apiFetch<BulkResult>("/api/v1/listings/bulk/publish", {
    method: "POST",
    body: JSON.stringify({ listing_ids: listingIds }),
  })
}

export async function bulkFillAttribute(payload: {
  listing_ids: string[]
  attribute_id: string
  value_name: string
  value_id?: string | null
}): Promise<BulkResult> {
  return apiFetch<BulkResult>("/api/v1/listings/bulk/attribute", {
    method: "PUT",
    body: JSON.stringify(payload),
  })
}

export async function getListingsForGrid(): Promise<ListingAttributesRow[]> {
  return apiFetch<ListingAttributesRow[]>("/api/v1/listings/bulk/attributes")
}
```

> **Important:** `frontend/src/lib/` is captured by `.gitignore`. After editing, stage with:
> ```bash
> git add -f frontend/src/lib/api/listings.ts
> ```

- [ ] **Step 3: TypeScript check**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

Expected: no new errors beyond pre-existing ones.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/listing.ts
git add -f frontend/src/lib/api/listings.ts
git commit -m "feat: bulk types and API client functions"
```

---

## Task 7 — ListingCard Redesign

**Files:**
- Modify: `frontend/src/components/listings/ListingCard.tsx`

**Interfaces:**
- Consumes: `ListingSummary` (with `failed_step`).
- Produces: `ListingCard` accepts `onSelect?: (id: string, checked: boolean) => void` and `selected?: boolean` props; renders checkbox top-left; renders inline error subcard when `status === "failed"`.

- [ ] **Step 1: Read the current `ListingCard.tsx`**

```bash
cat frontend/src/components/listings/ListingCard.tsx
```

Note the current props interface and structure before editing.

- [ ] **Step 2: Update props and add checkbox**

Replace the props interface to include selection:

```tsx
interface ListingCardProps {
  listing: ListingSummary
  selected?: boolean
  onSelect?: (id: string, checked: boolean) => void
}
```

Inside the card's outermost `<div>`, add a checkbox in the top-left corner. Wrap the existing content so the checkbox is absolutely positioned or in a flex row. Example structure:

```tsx
export function ListingCard({ listing, selected = false, onSelect }: ListingCardProps) {
  return (
    <div className="relative group rounded-lg border border-border bg-card p-3 text-sm shadow-sm hover:shadow-md transition-shadow">
      {onSelect && (
        <input
          type="checkbox"
          checked={selected}
          onChange={(e) => onSelect(listing.id, e.target.checked)}
          onClick={(e) => e.stopPropagation()}
          className="absolute top-2 left-2 h-4 w-4 rounded border-slate-300 cursor-pointer"
        />
      )}
      <div className={onSelect ? "pl-6" : ""}>
        {/* existing card content — keep unchanged */}
      </div>

      {/* Inline error subcard */}
      {listing.status === "failed" && (
        <div className="mt-2 rounded-md bg-red-50 border border-red-200 px-3 py-2 flex items-center justify-between gap-2">
          <div className="text-xs text-red-700">
            <span className="font-medium">Falha</span>
            {listing.failed_step && (
              <span className="text-red-500 ml-1">em {listing.failed_step.replace(/_/g, " ")}</span>
            )}
          </div>
          <a
            href={`/listings/${listing.id}`}
            className="text-xs text-red-600 underline underline-offset-2 hover:text-red-800 whitespace-nowrap"
          >
            Ver detalhes
          </a>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Verify the card renders correctly in the browser**

Navigate to `http://localhost:3000`. Cards should look unchanged. (Selection checkbox not yet visible — it's wired in Task 8.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/listings/ListingCard.tsx
git commit -m "feat: ListingCard with selection checkbox and inline error subcard"
```

---

## Task 8 — New PipelineBoard (6 Columns)

**Files:**
- Modify: `frontend/src/components/listings/PipelineBoard.tsx`

**Interfaces:**
- Consumes: `ListingCard` (with selection props), `BulkActionsBar` (Task 9 — import it here).
- Produces: 6-column kanban; `failed` listings routed to column by `failed_step`; selection state managed internally; `BulkActionsBar` rendered at bottom.

- [ ] **Step 1: Replace `PipelineBoard.tsx` entirely**

```tsx
"use client"

import { useState, useCallback } from "react"
import { useQuery } from "@tanstack/react-query"
import { getListings } from "@/lib/api/listings"
import { ApiError } from "@/lib/api/client"
import { ListingCard } from "./ListingCard"
import { BulkActionsBar } from "./BulkActionsBar"
import type { ListingStatus, ListingSummary } from "@/types/listing"
import { Loader2 } from "lucide-react"
import Link from "next/link"

type ColumnId = "fila" | "titulos" | "categoria" | "imagens" | "descricao" | "publicados"

const COLUMNS: {
  id: ColumnId
  title: string
  statuses: ListingStatus[]
  failedSteps: string[]
  colorClass: string
}[] = [
  {
    id: "fila",
    title: "Fila",
    statuses: ["draft"],
    failedSteps: [],          // legacy failed (no failed_step) also land here
    colorClass: "border-t-slate-400",
  },
  {
    id: "titulos",
    title: "Títulos",
    statuses: ["generating_title", "pending_title_approval"],
    failedSteps: ["generating_title", "pending_title_approval"],
    colorClass: "border-t-violet-400",
  },
  {
    id: "categoria",
    title: "Categoria & Atributos",
    statuses: ["predicting_category", "pending_seller_attributes", "pending_description"],
    failedSteps: ["predicting_category", "pending_seller_attributes", "pending_description"],
    colorClass: "border-t-blue-400",
  },
  {
    id: "imagens",
    title: "Imagens",
    statuses: ["generating_images", "pending_image_approval"],
    failedSteps: ["generating_images", "pending_image_approval"],
    colorClass: "border-t-orange-400",
  },
  {
    id: "descricao",
    title: "Descrição",
    statuses: ["generating_description", "ready_to_publish", "publishing"],
    failedSteps: ["generating_description", "ready_to_publish", "publishing"],
    colorClass: "border-t-yellow-400",
  },
  {
    id: "publicados",
    title: "Publicados",
    statuses: ["published"],
    failedSteps: [],
    colorClass: "border-t-green-400",
  },
]

export function PipelineBoard() {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [activeColumnId, setActiveColumnId] = useState<ColumnId | null>(null)

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["listings"],
    queryFn: () => getListings({ page_size: 200 }),
    refetchInterval: 8000,
  })

  const handleSelect = useCallback((columnId: ColumnId, id: string, checked: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (checked) {
        next.add(id)
      } else {
        next.delete(id)
      }
      return next
    })
    setActiveColumnId(checked ? columnId : selectedIds.size <= 1 ? null : activeColumnId)
  }, [selectedIds, activeColumnId])

  const handleSelectAll = useCallback((columnId: ColumnId, items: ListingSummary[]) => {
    const ids = items.map((i) => i.id)
    const allSelected = ids.every((id) => selectedIds.has(id))
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (allSelected) {
        ids.forEach((id) => next.delete(id))
        setActiveColumnId(null)
      } else {
        ids.forEach((id) => next.add(id))
        setActiveColumnId(columnId)
      }
      return next
    })
  }, [selectedIds])

  const clearSelection = useCallback(() => {
    setSelectedIds(new Set())
    setActiveColumnId(null)
  }, [])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-slate-500" />
        <span className="ml-2 text-slate-500">Carregando anúncios...</span>
      </div>
    )
  }

  if (error) {
    const isNoSeller = error instanceof ApiError && error.status === 422
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <p className="text-slate-600 text-sm text-center">
          {isNoSeller
            ? (error as ApiError).message
            : "Erro ao carregar anúncios. Tente recarregar a página."}
        </p>
        {isNoSeller && (
          <Link
            href="/settings"
            className="text-sm font-medium text-primary underline underline-offset-4 hover:opacity-80"
          >
            Ir para Configurações
          </Link>
        )}
      </div>
    )
  }

  const allItems: ListingSummary[] = data?.items || []

  const getColumnItems = (col: (typeof COLUMNS)[0]) =>
    allItems.filter((item) => {
      if (item.status === "failed") {
        const step = item.failed_step ?? ""
        if (!step) return col.id === "fila"
        return col.failedSteps.includes(step)
      }
      return (col.statuses as string[]).includes(item.status)
    })

  return (
    <>
      <div className="flex gap-4 overflow-x-auto pb-20 min-h-[calc(100vh-12rem)]">
        {COLUMNS.map((col) => {
          const items = getColumnItems(col)
          const colSelectedIds = items.filter((i) => selectedIds.has(i.id)).map((i) => i.id)
          const allColSelected = items.length > 0 && items.every((i) => selectedIds.has(i.id))

          return (
            <div
              key={col.id}
              className={`flex-shrink-0 w-72 bg-muted/40 rounded-lg border-t-4 ${col.colorClass} border border-border p-3`}
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  {items.length > 0 && (
                    <input
                      type="checkbox"
                      checked={allColSelected}
                      onChange={() => handleSelectAll(col.id, items)}
                      className="h-4 w-4 rounded border-slate-300 cursor-pointer"
                      title="Selecionar todos"
                    />
                  )}
                  <h3 className="font-semibold text-sm text-foreground">{col.title}</h3>
                </div>
                <span className="text-xs bg-muted text-muted-foreground rounded-full px-2 py-0.5 font-medium">
                  {items.length}
                </span>
              </div>

              <div className="space-y-2">
                {items.length === 0 ? (
                  <p className="text-xs text-slate-400 text-center py-6">Nenhum anúncio</p>
                ) : (
                  items.map((listing) => (
                    <ListingCard
                      key={listing.id}
                      listing={listing}
                      selected={selectedIds.has(listing.id)}
                      onSelect={(id, checked) => handleSelect(col.id, id, checked)}
                    />
                  ))
                )}
              </div>
            </div>
          )
        })}
      </div>

      <BulkActionsBar
        selectedIds={[...selectedIds]}
        activeColumnId={activeColumnId}
        onSuccess={() => {
          clearSelection()
          refetch()
        }}
        onClear={clearSelection}
      />
    </>
  )
}
```

- [ ] **Step 2: Commit (will show TS error about BulkActionsBar until Task 9)**

```bash
git add frontend/src/components/listings/PipelineBoard.tsx
git commit -m "feat: redesign PipelineBoard with 6 columns and selection state"
```

---

## Task 9 — BulkActionsBar

**Files:**
- Create: `frontend/src/components/listings/BulkActionsBar.tsx`

**Interfaces:**
- Consumes: `selectedIds: string[]`, `activeColumnId: ColumnId | null`, `onSuccess: () => void`, `onClear: () => void`.
- Produces: Floating bar at bottom of viewport, visible when `selectedIds.length > 0`. Shows column-appropriate action buttons. Calls bulk API functions, toasts result, calls `onSuccess`.

- [ ] **Step 1: Create `frontend/src/components/listings/BulkActionsBar.tsx`**

```tsx
"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  bulkStartPipeline,
  bulkApproveTitles,
  bulkRejectTitles,
  bulkApproveImages,
  bulkGenerateImages,
  bulkPublish,
} from "@/lib/api/listings"
import type { BulkResult } from "@/types/listing"
import { CheckCircle, XCircle, Loader2, X } from "lucide-react"

type ColumnId = "fila" | "titulos" | "categoria" | "imagens" | "descricao" | "publicados"

interface BulkActionsBarProps {
  selectedIds: string[]
  activeColumnId: ColumnId | null
  onSuccess: () => void
  onClear: () => void
}

function useToast() {
  const [message, setMessage] = useState<{ text: string; type: "success" | "error" } | null>(null)
  const show = (text: string, type: "success" | "error") => {
    setMessage({ text, type })
    setTimeout(() => setMessage(null), 4000)
  }
  return { message, show }
}

export function BulkActionsBar({ selectedIds, activeColumnId, onSuccess, onClear }: BulkActionsBarProps) {
  const router = useRouter()
  const { message, show } = useToast()
  const [loading, setLoading] = useState(false)

  if (selectedIds.length === 0) return null

  const run = async (fn: (ids: string[]) => Promise<BulkResult>, successLabel: string) => {
    setLoading(true)
    try {
      const result = await fn(selectedIds)
      if (result.failed === 0) {
        show(`${successLabel}: ${result.processed} processados`, "success")
      } else {
        show(`${result.processed} ok, ${result.failed} com erro`, "error")
      }
      onSuccess()
    } catch {
      show("Erro inesperado. Tente novamente.", "error")
    } finally {
      setLoading(false)
    }
  }

  const columnLabel: Record<ColumnId, string> = {
    fila: "Fila",
    titulos: "Títulos",
    categoria: "Categoria & Atributos",
    imagens: "Imagens",
    descricao: "Descrição",
    publicados: "Publicados",
  }

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 flex justify-center pb-4 pointer-events-none">
      <div className="pointer-events-auto bg-slate-900 text-white rounded-xl shadow-2xl px-5 py-3 flex items-center gap-4 min-w-[400px] max-w-xl">
        <div className="flex-1 text-sm">
          <span className="font-semibold">{selectedIds.length}</span>
          <span className="text-slate-300 ml-1">
            {selectedIds.length === 1 ? "anúncio selecionado" : "anúncios selecionados"}
            {activeColumnId && ` em ${columnLabel[activeColumnId]}`}
          </span>
        </div>

        {loading && <Loader2 className="w-4 h-4 animate-spin text-slate-400" />}

        {!loading && activeColumnId === "fila" && (
          <button
            onClick={() => run(bulkStartPipeline, "Pipeline iniciado")}
            className="flex items-center gap-1.5 bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium px-3 py-1.5 rounded-lg transition-colors"
          >
            <CheckCircle className="w-4 h-4" /> Iniciar pipeline
          </button>
        )}

        {!loading && activeColumnId === "titulos" && (
          <>
            <button
              onClick={() => run(bulkRejectTitles, "Títulos reprovados")}
              className="flex items-center gap-1.5 bg-red-600 hover:bg-red-500 text-white text-sm font-medium px-3 py-1.5 rounded-lg transition-colors"
            >
              <XCircle className="w-4 h-4" /> Reprovar
            </button>
            <button
              onClick={() => run(bulkApproveTitles, "Títulos aprovados")}
              className="flex items-center gap-1.5 bg-green-600 hover:bg-green-500 text-white text-sm font-medium px-3 py-1.5 rounded-lg transition-colors"
            >
              <CheckCircle className="w-4 h-4" /> Aprovar títulos
            </button>
          </>
        )}

        {!loading && activeColumnId === "categoria" && (
          <>
            <button
              onClick={() => {
                router.push("/listings/attributes")
              }}
              className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium px-3 py-1.5 rounded-lg transition-colors"
            >
              Preencher atributos
            </button>
            <button
              onClick={() => run(bulkGenerateImages, "Imagens iniciadas")}
              className="flex items-center gap-1.5 bg-orange-600 hover:bg-orange-500 text-white text-sm font-medium px-3 py-1.5 rounded-lg transition-colors"
            >
              <CheckCircle className="w-4 h-4" /> Gerar imagens
            </button>
          </>
        )}

        {!loading && activeColumnId === "imagens" && (
          <button
            onClick={() => run(bulkApproveImages, "Imagens aprovadas")}
            className="flex items-center gap-1.5 bg-green-600 hover:bg-green-500 text-white text-sm font-medium px-3 py-1.5 rounded-lg transition-colors"
          >
            <CheckCircle className="w-4 h-4" /> Aprovar imagens
          </button>
        )}

        {!loading && activeColumnId === "descricao" && (
          <button
            onClick={() => run(bulkPublish, "Publicação iniciada")}
            className="flex items-center gap-1.5 bg-green-600 hover:bg-green-500 text-white text-sm font-medium px-3 py-1.5 rounded-lg transition-colors"
          >
            <CheckCircle className="w-4 h-4" /> Publicar
          </button>
        )}

        <button
          onClick={onClear}
          className="text-slate-400 hover:text-white transition-colors ml-1"
          title="Cancelar seleção"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {message && (
        <div
          className={`fixed bottom-20 left-1/2 -translate-x-1/2 px-4 py-2 rounded-lg text-sm font-medium text-white shadow-lg ${
            message.type === "success" ? "bg-green-700" : "bg-red-700"
          }`}
        >
          {message.text}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd frontend && npm run build 2>&1 | tail -30
```

Expected: no new errors.

- [ ] **Step 3: Smoke test in browser**

1. Navigate to `http://localhost:3000`.
2. If any listing is in `draft`, check its checkbox — the black bar should appear at the bottom.
3. Click the X to dismiss.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/listings/BulkActionsBar.tsx
git commit -m "feat: BulkActionsBar floating component with column-aware actions"
```

---

## Task 10 — Attribute Grid Editor

**Files:**
- Create: `frontend/src/app/(dashboard)/listings/attributes/page.tsx`
- Create: `frontend/src/components/listings/AttributeGridEditor.tsx`

**Interfaces:**
- Consumes: `getListingsForGrid()`, `bulkFillAttribute()`.
- Produces: Full-page grid at `/listings/attributes`; listings grouped by `ml_category_id`; inline editable cells; row selection; "Preencher para selecionados" per column; "Salvar" button.

- [ ] **Step 1: Create `AttributeGridEditor.tsx`**

```tsx
// frontend/src/components/listings/AttributeGridEditor.tsx
"use client"

import { useState, useMemo } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { bulkFillAttribute } from "@/lib/api/listings"
import type { ListingAttributesRow, AttributeItem } from "@/types/listing"
import { Save, Loader2 } from "lucide-react"

interface Props {
  rows: ListingAttributesRow[]
}

export function AttributeGridEditor({ rows }: Props) {
  const queryClient = useQueryClient()
  // local state: Map<listingId, Map<attributeId, newValue>>
  const [dirty, setDirty] = useState<Record<string, Record<string, string>>>({})
  const [selectedRows, setSelectedRows] = useState<Set<string>>(new Set())
  const [saving, setSaving] = useState(false)
  const [saveResult, setSaveResult] = useState<string | null>(null)

  // Group by ml_category_id
  const groups = useMemo(() => {
    const map = new Map<string, ListingAttributesRow[]>()
    for (const row of rows) {
      const key = row.ml_category_id ?? "sem-categoria"
      const existing = map.get(key) ?? []
      map.set(key, [...existing, row])
    }
    return map
  }, [rows])

  const setCellValue = (listingId: string, attributeId: string, value: string) => {
    setDirty((prev) => ({
      ...prev,
      [listingId]: { ...(prev[listingId] ?? {}), [attributeId]: value },
    }))
  }

  const getCellValue = (row: ListingAttributesRow, attributeId: string): string => {
    return dirty[row.listing_id]?.[attributeId]
      ?? row.attributes.find((a) => a.attribute_id === attributeId)?.value_name
      ?? ""
  }

  const applyToSelected = (categoryRows: ListingAttributesRow[], attributeId: string) => {
    const value = prompt(`Valor para preencher em "${attributeId}" para todos os selecionados:`)
    if (!value) return
    const targetRows = categoryRows.filter((r) => selectedRows.has(r.listing_id))
    setDirty((prev) => {
      const next = { ...prev }
      for (const r of targetRows) {
        next[r.listing_id] = { ...(next[r.listing_id] ?? {}), [attributeId]: value }
      }
      return next
    })
  }

  const handleSave = async () => {
    setSaving(true)
    setSaveResult(null)
    let success = 0
    let failed = 0
    try {
      // Group dirty cells by (attributeId, value) → list of listingIds
      const batches = new Map<string, { listingIds: string[]; value: string }>()
      for (const [listingId, attrs] of Object.entries(dirty)) {
        for (const [attributeId, value] of Object.entries(attrs)) {
          const key = `${attributeId}|||${value}`
          const existing = batches.get(key) ?? { listingIds: [], value }
          existing.listingIds.push(listingId)
          batches.set(key, existing)
        }
      }
      for (const [key, { listingIds, value }] of batches) {
        const attributeId = key.split("|||")[0]
        const result = await bulkFillAttribute({
          listing_ids: listingIds,
          attribute_id: attributeId,
          value_name: value,
        })
        success += result.processed
        failed += result.failed
      }
      setDirty({})
      queryClient.invalidateQueries({ queryKey: ["listings-for-grid"] })
      setSaveResult(`${success} campos salvos${failed > 0 ? `, ${failed} com erro` : ""}.`)
    } catch {
      setSaveResult("Erro ao salvar. Tente novamente.")
    } finally {
      setSaving(false)
    }
  }

  if (rows.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-slate-500 text-sm">
        Nenhum anúncio aguarda preenchimento de atributos.
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-500">
          {rows.length} {rows.length === 1 ? "anúncio" : "anúncios"} aguardando atributos
        </p>
        <div className="flex items-center gap-3">
          {saveResult && <span className="text-sm text-slate-600">{saveResult}</span>}
          <button
            onClick={handleSave}
            disabled={saving || Object.keys(dirty).length === 0}
            className="flex items-center gap-2 bg-primary text-primary-foreground text-sm font-medium px-4 py-2 rounded-lg hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Salvar alterações
          </button>
        </div>
      </div>

      {[...groups.entries()].map(([categoryId, categoryRows]) => {
        // Collect all unique attributes for this category (union of all rows)
        const attrMap = new Map<string, AttributeItem>()
        for (const row of categoryRows) {
          for (const attr of row.attributes) {
            if (!attrMap.has(attr.attribute_id)) attrMap.set(attr.attribute_id, attr)
          }
        }
        // Required first, then optional, sorted by name
        const uniqueAttrs = [...attrMap.values()].sort((a, b) => {
          if (a.is_required !== b.is_required) return a.is_required ? -1 : 1
          return a.attribute_name.localeCompare(b.attribute_name)
        })

        const allCatSelected =
          categoryRows.length > 0 && categoryRows.every((r) => selectedRows.has(r.listing_id))

        return (
          <div key={categoryId} className="rounded-xl border border-border overflow-hidden">
            <div className="bg-muted/60 px-4 py-2 text-xs font-semibold text-slate-500 uppercase tracking-wide">
              Categoria ML: {categoryId}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/30">
                    <th className="sticky left-0 bg-muted/30 px-3 py-2 w-8">
                      <input
                        type="checkbox"
                        checked={allCatSelected}
                        onChange={() => {
                          const ids = categoryRows.map((r) => r.listing_id)
                          setSelectedRows((prev) => {
                            const next = new Set(prev)
                            if (allCatSelected) ids.forEach((id) => next.delete(id))
                            else ids.forEach((id) => next.add(id))
                            return next
                          })
                        }}
                        className="h-3.5 w-3.5 cursor-pointer"
                      />
                    </th>
                    <th className="sticky left-8 bg-muted/30 px-3 py-2 text-left font-medium text-slate-600 min-w-[180px]">
                      Produto
                    </th>
                    {uniqueAttrs.map((attr) => (
                      <th key={attr.attribute_id} className="px-3 py-2 text-left font-medium text-slate-600 min-w-[140px]">
                        <div className="flex flex-col gap-1">
                          <span>
                            {attr.attribute_name}
                            {attr.is_required && <span className="text-red-500 ml-0.5">*</span>}
                          </span>
                          {selectedRows.size > 0 && (
                            <button
                              onClick={() => applyToSelected(categoryRows, attr.attribute_id)}
                              className="text-xs text-blue-600 hover:underline text-left"
                            >
                              Preencher selecionados
                            </button>
                          )}
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {categoryRows.map((row, idx) => (
                    <tr
                      key={row.listing_id}
                      className={`border-b border-border last:border-0 ${
                        selectedRows.has(row.listing_id) ? "bg-blue-50" : idx % 2 === 0 ? "bg-white" : "bg-slate-50/50"
                      }`}
                    >
                      <td className="sticky left-0 bg-inherit px-3 py-1.5">
                        <input
                          type="checkbox"
                          checked={selectedRows.has(row.listing_id)}
                          onChange={(e) => {
                            setSelectedRows((prev) => {
                              const next = new Set(prev)
                              e.target.checked ? next.add(row.listing_id) : next.delete(row.listing_id)
                              return next
                            })
                          }}
                          className="h-3.5 w-3.5 cursor-pointer"
                        />
                      </td>
                      <td className="sticky left-8 bg-inherit px-3 py-1.5 font-medium text-slate-800 max-w-[200px] truncate">
                        <span title={row.selected_title ?? row.sku_external_id}>
                          {row.selected_title ?? row.sku_external_id}
                        </span>
                      </td>
                      {uniqueAttrs.map((attr) => {
                        const cell = row.attributes.find((a) => a.attribute_id === attr.attribute_id)
                        const value = getCellValue(row, attr.attribute_id)
                        const isDirty = dirty[row.listing_id]?.[attr.attribute_id] !== undefined
                        const isEmpty = !value && attr.is_required
                        return (
                          <td key={attr.attribute_id} className="px-2 py-1">
                            <input
                              type="text"
                              value={value}
                              onChange={(e) => setCellValue(row.listing_id, attr.attribute_id, e.target.value)}
                              className={`w-full rounded border text-xs px-2 py-1 outline-none focus:ring-1 focus:ring-blue-400 ${
                                isEmpty
                                  ? "border-red-300 bg-red-50"
                                  : isDirty
                                  ? "border-blue-300 bg-blue-50"
                                  : "border-transparent bg-transparent hover:border-slate-200"
                              }`}
                              placeholder={isEmpty ? "obrigatório" : ""}
                            />
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 2: Create the page**

```tsx
// frontend/src/app/(dashboard)/listings/attributes/page.tsx
"use client"

import { useQuery } from "@tanstack/react-query"
import { getListingsForGrid } from "@/lib/api/listings"
import { AttributeGridEditor } from "@/components/listings/AttributeGridEditor"
import { Loader2 } from "lucide-react"
import Link from "next/link"

export default function AttributesGridPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["listings-for-grid"],
    queryFn: getListingsForGrid,
  })

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/" className="text-sm text-slate-500 hover:text-slate-700">← Voltar ao kanban</Link>
        <h1 className="text-xl font-semibold text-foreground">Atributos por anúncio</h1>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-slate-500">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span className="text-sm">Carregando...</span>
        </div>
      )}

      {error && (
        <p className="text-sm text-red-600">Erro ao carregar anúncios. Tente recarregar.</p>
      )}

      {data && <AttributeGridEditor rows={data} />}
    </div>
  )
}
```

- [ ] **Step 3: TypeScript check**

```bash
cd frontend && npm run build 2>&1 | tail -30
```

Expected: no new errors.

- [ ] **Step 4: Smoke test in browser**

Navigate to `http://localhost:3000/listings/attributes`. Should show either the empty state message or a grid if any listing is in `pending_seller_attributes` / `pending_description`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/listings/AttributeGridEditor.tsx
git add frontend/src/app/(dashboard)/listings/attributes/page.tsx
git commit -m "feat: attribute grid editor page for bulk attribute fill"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] 6 colunas com nomes aprovados (Fila, Títulos, Categoria & Atributos, Imagens, Descrição, Publicados) → Task 8
- [x] Erros inline na coluna onde ocorreram, com `failed_step` → Task 1 (backend) + Task 7 (card) + Task 8 (routing)
- [x] Título reprovado volta para `draft` (Fila) → Task 4 `bulk_reject_titles` + Task 9 `BulkActionsBar`
- [x] Aprovação em lote de títulos (seleciona maior score) → Task 4 `bulk_approve_titles`
- [x] Aprovação em lote de imagens → Task 4 `bulk_approve_images`
- [x] Publicação em lote → Task 4 `bulk_publish`
- [x] Gerar imagens em lote (de `pending_description`) → Task 4 `bulk_generate_images`
- [x] Iniciar pipeline em lote (de `draft`) → Task 4 `bulk_start_pipeline`
- [x] Grid editor de atributos tipo DBExplorer — linhas = anúncios, colunas = atributos → Task 10
- [x] Preenchimento em lote de uma coluna para linhas selecionadas → Task 10 `applyToSelected`
- [x] Avanço automático para `pending_description` quando todos os atributos obrigatórios preenchidos → Task 4 `bulk_fill_attribute`
- [x] BulkActionsBar context-aware por coluna → Task 9
- [x] Checkbox "selecionar todos" por coluna → Task 8
- [x] Multi-tenant: seller_id validado em todos os métodos de serviço → Task 4 (WHERE clause)
- [x] Endpoints sob `/api/v1/`, JWT obrigatório → Task 5

**Placeholder scan:** Nenhum TBD encontrado.

**Type consistency:**
- `BulkResult` definido em `schemas/bulk.py` (Task 2) e `types/listing.ts` (Task 6) — estruturas equivalentes.
- `getListingsForGrid()` retorna `ListingAttributesRow[]` — consumido em `AttributeGridEditor` via prop `rows: ListingAttributesRow[]` — consistente.
- `bulkFillAttribute` em `api/listings.ts` usa `listing_ids: string[]` (Task 6) — `bulk_fill_attribute` no backend usa `list[UUID]` com auto-coerção do Pydantic — consistente.

**Limitação conhecida:** `GET /api/v1/listings/bulk/attributes` tem N+1 queries (uma query de atributos por listing). Para MVP é aceitável; otimizar com `selectinload` em iteração futura.

---

*Fim da SPEC-014.*
