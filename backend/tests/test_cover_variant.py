"""Frente A: variante ambientada da capa, gerada sob demanda.

Testes de `generate_cover_variant` no mesmo estilo dos testes de
`_try_i2i_generation` em test_image_tasks.py — db mockado com AsyncMock,
engine e MLPictureService patchados na origem (import é feito dentro da
função, então o patch precisa mirar o módulo que define a classe).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.image_service import ImageValidationResult


def _make_db(cover_image):
    """AsyncMock de sessão cuja primeira (e única) query devolve `cover_image`.

    A busca da capa usa `.scalars().first()` (e não `scalar_one_or_none`)
    porque um anúncio pode ter mais de uma linha `cover_deterministic` — ver
    `_load_latest_deterministic_cover`. `first()` sobre lista vazia devolve
    None, que é o caso "sem capa"."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = cover_image
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    return mock_db


def _make_listing():
    listing = MagicMock()
    listing.id = "lid"
    listing.ml_category_id = "MLB1055"
    return listing


def _make_cover(image_bytes, source_sku="SKU0001"):
    cover = MagicMock()
    cover.image_bytes = image_bytes
    cover.source_sku = source_sku
    return cover


class TestGenerateCoverVariantSuccess:
    @pytest.mark.asyncio
    async def test_engine_receives_exactly_the_saved_cover_bytes(self):
        from app.services.cover_variant_service import generate_cover_variant

        cover = _make_cover(image_bytes=b"exact-saved-cover-bytes")
        listing = _make_listing()
        mock_db = _make_db(cover)

        prepared = b"prepared-1200x1200"
        verdict = ImageValidationResult(is_valid=True)

        with patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as mock_engine_cls, patch(
            "app.workers.tasks.image_tasks._resolve_requires_white_bg",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "app.workers.tasks.image_tasks._prepare_image_for_upload",
            return_value=(prepared, verdict),
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(return_value=[b"variant-bytes"])
            mock_ml_cls.return_value.upload = AsyncMock(return_value="pic-ai-1")

            await generate_cover_variant(mock_db, listing, "token-xyz")

        mock_engine_cls.return_value.edit.assert_awaited_once()
        call_kwargs = mock_engine_cls.return_value.edit.await_args.kwargs
        assert call_kwargs["images"] == [b"exact-saved-cover-bytes"]
        assert call_kwargs["n"] == 1

    @pytest.mark.asyncio
    async def test_candidate_is_born_unapproved_with_cover_ai_kind_and_sort_order(self):
        from app.services.cover_variant_service import (
            COVER_AI_KIND,
            COVER_AI_SORT_ORDER,
            generate_cover_variant,
        )

        cover = _make_cover(image_bytes=b"cover-bytes")
        listing = _make_listing()
        mock_db = _make_db(cover)

        prepared = b"prepared-bytes"
        verdict = ImageValidationResult(is_valid=True)

        with patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as mock_engine_cls, patch(
            "app.workers.tasks.image_tasks._resolve_requires_white_bg",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "app.workers.tasks.image_tasks._prepare_image_for_upload",
            return_value=(prepared, verdict),
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(return_value=[b"variant-bytes"])
            mock_ml_cls.return_value.upload = AsyncMock(return_value="pic-ai-1")

            candidate = await generate_cover_variant(mock_db, listing, "token-xyz")

        assert candidate.kind == COVER_AI_KIND == "cover_ai"
        assert candidate.approved is False
        assert candidate.sort_order == COVER_AI_SORT_ORDER == 90
        assert candidate.status == "uploaded"
        assert candidate.ml_picture_id == "pic-ai-1"
        mock_db.commit.assert_awaited()


class TestGenerateCoverVariantMissingCover:
    @pytest.mark.asyncio
    async def test_no_deterministic_cover_raises(self):
        from app.services.cover_variant_service import (
            CoverVariantError,
            generate_cover_variant,
        )

        listing = _make_listing()
        mock_db = _make_db(cover_image=None)

        with pytest.raises(CoverVariantError):
            await generate_cover_variant(mock_db, listing, "token-xyz")

    @pytest.mark.asyncio
    async def test_cover_without_saved_bytes_raises_and_never_calls_engine(self):
        """Capa existe (registro pré-Task 1), mas image_bytes é NULL: nunca
        chamar o motor pago — o request não pode ter sucesso de jeito nenhum."""
        from app.services.cover_variant_service import (
            CoverVariantError,
            generate_cover_variant,
        )

        cover = _make_cover(image_bytes=None)
        listing = _make_listing()
        mock_db = _make_db(cover)

        with patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as mock_engine_cls:
            with pytest.raises(CoverVariantError):
                await generate_cover_variant(mock_db, listing, "token-xyz")

        mock_engine_cls.assert_not_called()


class TestGenerateCoverVariantQaRejection:
    @pytest.mark.asyncio
    async def test_rejected_by_qa_records_validation_failed_and_does_not_upload(self):
        from app.services.cover_variant_service import (
            COVER_AI_KIND,
            COVER_AI_SORT_ORDER,
            generate_cover_variant,
        )

        cover = _make_cover(image_bytes=b"cover-bytes")
        listing = _make_listing()
        mock_db = _make_db(cover)

        verdict = ImageValidationResult(is_valid=False, errors=["fundo não é branco puro"])

        with patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as mock_engine_cls, patch(
            "app.workers.tasks.image_tasks._resolve_requires_white_bg",
            new_callable=AsyncMock,
            return_value=True,
        ), patch(
            "app.workers.tasks.image_tasks._prepare_image_for_upload",
            return_value=(None, verdict),
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(return_value=[b"variant-bytes"])
            mock_ml_cls.return_value.upload = AsyncMock(return_value="pic-ai-1")

            candidate = await generate_cover_variant(mock_db, listing, "token-xyz")

        assert candidate.status == "validation_failed"
        assert candidate.validation_error == verdict.reason
        assert candidate.kind == COVER_AI_KIND
        assert candidate.sort_order == COVER_AI_SORT_ORDER
        assert candidate.approved is False
        assert candidate.ml_picture_id is None
        mock_ml_cls.return_value.upload.assert_not_awaited()


class TestCoverAiVariantEndpointEngineUnavailable:
    """Fix round 1: ImageEngineUnavailableError não pode virar 500 genérico.

    Testa o endpoint de verdade (não uma reimplementação da regra), chamando
    a função da rota diretamente com os Depends() substituídos por mocks —
    mesma técnica usada para as tasks Celery em test_image_tasks.py, sem
    precisar de TestClient/DB real (padrão inexistente hoje na suíte).

    Aqui o serviço inteiro é mockado — isso testa só o mapeamento de exceção
    para HTTP, nada além disso. A invariante "nenhuma escrita no banco antes
    da falha do motor" é responsabilidade do serviço, não do endpoint, e por
    isso é coberta em `TestGenerateCoverVariantEngineUnavailable` abaixo, que
    chama a implementação real.
    """

    @pytest.mark.asyncio
    async def test_engine_unavailable_maps_to_502_with_actionable_message(self):
        from fastapi import HTTPException

        from app.api.v1.endpoints.listings import generate_cover_ai_variant
        from app.services.image_engines.base import ImageEngineUnavailableError

        listing = _make_listing()
        active_seller = MagicMock()
        mock_db = AsyncMock()
        mock_db.add = MagicMock()

        with patch(
            "app.services.listing_service.ListingService.get_or_404",
            new_callable=AsyncMock,
            return_value=listing,
        ), patch(
            "app.services.publish_service.get_valid_access_token",
            new_callable=AsyncMock,
            return_value="token-xyz",
        ), patch(
            "app.services.cover_variant_service.generate_cover_variant",
            new_callable=AsyncMock,
            side_effect=ImageEngineUnavailableError("Timeout ao chamar a OpenAI (edits): boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await generate_cover_ai_variant(
                    listing_id=listing.id, active_seller=active_seller, db=mock_db
                )

        assert exc_info.value.status_code == 502, "nao pode cair no handler generico (500)"
        assert "indispon" in exc_info.value.detail.lower()


class TestGenerateCoverVariantEngineUnavailable:
    """Fix round 2: a asserção `db.add` não foi chamado precisa alcançar
    código real, não um serviço mockado inteiro (isso era teatro — o
    endpoint nunca chama `db.add` diretamente, então a asserção anterior era
    verdadeira mesmo com um `db.add()` movido para antes do `engine.edit()`).

    Aqui é `generate_cover_variant` de verdade quem roda: só o
    `OpenAIEditEngine` é mockado, levantando `ImageEngineUnavailableError`
    antes de devolver bytes. Se alguém mover uma escrita no banco para antes
    da chamada do motor, este teste quebra.
    """

    @pytest.mark.asyncio
    async def test_engine_failure_writes_nothing_to_the_database(self):
        from app.services.cover_variant_service import generate_cover_variant
        from app.services.image_engines.base import ImageEngineUnavailableError

        cover = _make_cover(image_bytes=b"cover-bytes")
        listing = _make_listing()
        mock_db = _make_db(cover)

        with patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as mock_engine_cls:
            mock_engine_cls.return_value.edit = AsyncMock(
                side_effect=ImageEngineUnavailableError("Timeout ao chamar a OpenAI (edits): boom")
            )

            with pytest.raises(ImageEngineUnavailableError):
                await generate_cover_variant(mock_db, listing, "token-xyz")

        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_awaited()


class TestGenerateCoverVariantPrompt:
    @pytest.mark.asyncio
    async def test_prompt_carries_the_critical_and_pixel_faithful_clauses(self):
        from app.services.cover_variant_service import generate_cover_variant

        cover = _make_cover(image_bytes=b"cover-bytes")
        listing = _make_listing()
        mock_db = _make_db(cover)

        prepared = b"prepared-bytes"
        verdict = ImageValidationResult(is_valid=True)

        with patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as mock_engine_cls, patch(
            "app.workers.tasks.image_tasks._resolve_requires_white_bg",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "app.workers.tasks.image_tasks._prepare_image_for_upload",
            return_value=(prepared, verdict),
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(return_value=[b"variant-bytes"])
            mock_ml_cls.return_value.upload = AsyncMock(return_value="pic-ai-1")

            await generate_cover_variant(mock_db, listing, "token-xyz")

        prompt = mock_engine_cls.return_value.edit.await_args.kwargs["prompt"]
        assert "CRITICAL" in prompt
        assert "pixel-faithful" in prompt


class _DuplicateCoversResult:
    """Resultado que se comporta como o `Result` REAL do SQLAlchemy quando a
    query casa com mais de uma linha: `scalar_one_or_none()` estoura
    `MultipleResultsFound`, `scalars().first()` devolve a primeira.

    Isso reproduz em teste o 500 opaco de produção: nada apaga
    `ListingImage`, e cada passada de `_try_i2i_generation` insere uma linha
    `cover_deterministic` (inclusive uma `validation_failed` sem bytes), então
    a 2ª geração de imagens do mesmo anúncio deixa duas linhas casando com a
    busca da capa.
    """

    def __init__(self, rows):
        self._rows = list(rows)

    def scalar_one_or_none(self):
        from sqlalchemy.exc import MultipleResultsFound

        if len(self._rows) > 1:
            raise MultipleResultsFound(
                "Multiple rows were found when one or none was required"
            )
        return self._rows[0] if self._rows else None

    def scalars(self):
        holder = MagicMock()
        holder.first.return_value = self._rows[0] if self._rows else None
        holder.all.return_value = list(self._rows)
        return holder


class TestCoverLookupWithDuplicateCovers:
    @pytest.mark.asyncio
    async def test_two_deterministic_covers_do_not_raise_multiple_results_found(self):
        """Alcançável pelo fluxo normal: retry_pipeline → submit_attributes →
        POST /pipeline/generate_images (ou confirm_image_engine('retry_openai'))
        roda `_try_i2i_generation` de novo e insere a 2ª capa."""
        from app.services.cover_variant_service import generate_cover_variant

        newest = _make_cover(image_bytes=b"capa-nova")
        oldest = _make_cover(image_bytes=b"capa-antiga")
        listing = _make_listing()

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=_DuplicateCoversResult([newest, oldest]))
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        prepared = b"prepared-bytes"
        verdict = ImageValidationResult(is_valid=True)

        with patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as mock_engine_cls, patch(
            "app.workers.tasks.image_tasks._resolve_requires_white_bg",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "app.workers.tasks.image_tasks._prepare_image_for_upload",
            return_value=(prepared, verdict),
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(return_value=[b"variant-bytes"])
            mock_ml_cls.return_value.upload = AsyncMock(return_value="pic-ai-1")

            candidate = await generate_cover_variant(mock_db, listing, "token-xyz")

        assert candidate.status == "uploaded"
        # A capa usada como origem é a que a ordenação da query põe em 1º.
        edit_kwargs = mock_engine_cls.return_value.edit.await_args.kwargs
        assert edit_kwargs["images"] == [b"capa-nova"]

    @pytest.mark.asyncio
    async def test_cover_query_skips_byteless_rows_and_takes_the_newest(self):
        """A linha `validation_failed` tem `image_bytes=None` e nunca serve de
        origem; entre as que têm bytes, a mais recente é a publicada. Isso é
        decidido no SQL (o mock não filtra nada), então é o SQL que se
        inspeciona aqui."""
        from app.services.cover_variant_service import generate_cover_variant

        cover = _make_cover(image_bytes=b"cover-bytes")
        listing = _make_listing()
        mock_db = _make_db(cover)

        prepared = b"prepared-bytes"
        verdict = ImageValidationResult(is_valid=True)

        with patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as mock_engine_cls, patch(
            "app.workers.tasks.image_tasks._resolve_requires_white_bg",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "app.workers.tasks.image_tasks._prepare_image_for_upload",
            return_value=(prepared, verdict),
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(return_value=[b"variant-bytes"])
            mock_ml_cls.return_value.upload = AsyncMock(return_value="pic-ai-1")

            await generate_cover_variant(mock_db, listing, "token-xyz")

        sql = str(mock_db.execute.await_args_list[0].args[0])
        assert "listing_images.image_bytes IS NOT NULL" in sql, sql
        assert "ORDER BY listing_images.created_at DESC" in sql, sql
        assert "LIMIT" in sql, sql


class TestCoverVariantPromptDependsOnCategory:
    """O prompt da ambientação tem que ser compatível com o QA da categoria.

    O prompt rico manda trocar o fundo branco por gradiente/textura. Em
    categoria-raiz que exige fundo branco puro, isso é reprovado por
    CONSTRUÇÃO pelo `validate_image` — 0% da borda em #FFFFFF contra um
    mínimo de 90%. Gerar assim queima uma chamada paga num resultado que já
    se sabe que será rejeitado, toda vez.
    """

    @staticmethod
    async def _capture_prompt(requires_white_bg: bool) -> str:
        from app.services.cover_variant_service import generate_cover_variant

        cover = _make_cover(image_bytes=b"cover-bytes")
        listing = _make_listing()
        mock_db = _make_db(cover)
        verdict = ImageValidationResult(is_valid=True)

        with patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as mock_engine_cls, patch(
            "app.workers.tasks.image_tasks._resolve_requires_white_bg",
            new_callable=AsyncMock,
            return_value=requires_white_bg,
        ), patch(
            "app.workers.tasks.image_tasks._prepare_image_for_upload",
            return_value=(b"prepared", verdict),
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(return_value=[b"variant"])
            mock_ml_cls.return_value.upload = AsyncMock(return_value="pic-1")
            await generate_cover_variant(mock_db, listing, "token")

        return mock_engine_cls.return_value.edit.await_args.kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_white_bg_category_never_asks_for_gradient_or_texture(self):
        """Mede o PEDIDO, não a palavra: o prompt leve cita "gradients" numa
        cláusula que os PROÍBE, e proibir é justamente o comportamento certo.
        O que não pode aparecer é o pedido do prompt rico."""
        prompt = await self._capture_prompt(requires_white_bg=True)
        lowered = prompt.lower()
        assert "replace the flat white background" not in lowered
        assert "subtle surface texture; add" not in lowered
        assert "do not add gradients" in lowered

    @pytest.mark.asyncio
    async def test_white_bg_category_asks_to_preserve_the_white_background(self):
        prompt = await self._capture_prompt(requires_white_bg=True)
        lowered = prompt.lower()
        assert "white background" in lowered
        # A ambientação permitida vira só luz e sombra de contato.
        assert "contact shadow" in lowered

    @pytest.mark.asyncio
    async def test_non_white_bg_category_keeps_the_richer_prompt(self):
        prompt = await self._capture_prompt(requires_white_bg=False)
        assert "gradient" in prompt.lower()

    @pytest.mark.asyncio
    async def test_both_prompts_keep_the_critical_text_clause(self):
        """A cláusula que protege o texto impresso no produto não pode sumir
        de nenhuma das duas variantes — é o que impede '100ml' virar '160ml'."""
        for wb in (True, False):
            prompt = await self._capture_prompt(requires_white_bg=wb)
            assert "CRITICAL" in prompt
            assert "character for" in prompt

    @pytest.mark.asyncio
    async def test_category_is_consulted_before_the_paid_engine_runs(self):
        """A consulta de categoria tem que anteceder o motor: é o que
        transforma a checagem em economia, e não só em correção."""
        from app.services.cover_variant_service import generate_cover_variant

        ordem: list[str] = []

        async def _fake_requires(listing):
            ordem.append("categoria")
            return True

        async def _fake_edit(images, prompt, n):
            ordem.append("motor")
            return [b"variant"]

        cover = _make_cover(image_bytes=b"cover-bytes")
        mock_db = _make_db(cover)
        verdict = ImageValidationResult(is_valid=True)

        with patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as mock_engine_cls, patch(
            "app.workers.tasks.image_tasks._resolve_requires_white_bg",
            new=_fake_requires,
        ), patch(
            "app.workers.tasks.image_tasks._prepare_image_for_upload",
            return_value=(b"prepared", verdict),
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(side_effect=_fake_edit)
            mock_ml_cls.return_value.upload = AsyncMock(return_value="pic-1")
            await generate_cover_variant(mock_db, _make_listing(), "token")

        assert ordem == ["categoria", "motor"]


class TestRejectedCandidateStaysReviewable:
    """Candidato reprovado existe para alguém julgar.

    Descartar os bytes na reprovação apaga justamente o que o humano
    precisaria ver para decidir se o QA foi severo demais — e o custo da
    geração já foi pago de qualquer forma.
    """

    @pytest.mark.asyncio
    async def test_rejected_candidate_persists_the_generated_bytes(self):
        from app.services.cover_variant_service import generate_cover_variant

        cover = _make_cover(image_bytes=b"cover-bytes")
        mock_db = _make_db(cover)
        verdict = ImageValidationResult(
            is_valid=False, errors=["fundo da capa não é branco puro"]
        )

        with patch(
            "app.services.image_engines.openai_edit_engine.OpenAIEditEngine"
        ) as mock_engine_cls, patch(
            "app.workers.tasks.image_tasks._resolve_requires_white_bg",
            new_callable=AsyncMock,
            return_value=True,
        ), patch(
            "app.workers.tasks.image_tasks._prepare_image_for_upload",
            return_value=(None, verdict),
        ), patch(
            "app.services.image_service.MLPictureService"
        ) as mock_ml_cls:
            mock_engine_cls.return_value.edit = AsyncMock(
                return_value=[b"o-que-a-ia-produziu"]
            )
            mock_ml_cls.return_value.upload = AsyncMock()

            candidate = await generate_cover_variant(mock_db, _make_listing(), "token")

            mock_ml_cls.return_value.upload.assert_not_awaited()

        assert candidate.status == "validation_failed"
        assert candidate.ml_picture_id is None
        assert candidate.approved is False
        assert candidate.image_bytes == b"o-que-a-ia-produziu"
        assert candidate.validation_error == verdict.reason
