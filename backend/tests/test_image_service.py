import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from app.services.image_service import validate_image


# --------------------------------------------------------------------------
# QA de imagem antes do upload para o ML
# --------------------------------------------------------------------------


def _solid(width: int, height: int, color, fmt="JPEG") -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _white(width=1200, height=1200, fmt="JPEG") -> bytes:
    return _solid(width, height, (255, 255, 255), fmt)


def _white_with_product(width=1200, height=1200) -> bytes:
    """Fundo branco com um bloco escuro no centro — o caso feliz real."""
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    img.paste(
        Image.new("RGB", (width // 2, height // 2), color=(20, 20, 20)),
        (width // 4, height // 4),
    )
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


class TestValidateImageValid:
    def test_valid_jpeg_passes(self):
        result = validate_image(_white_with_product())
        assert result.is_valid
        assert result.errors == []
        assert result.reason is None

    def test_valid_png_passes(self):
        result = validate_image(_white(800, 800, fmt="PNG"))
        assert result.is_valid

    def test_900x900_is_not_rejected_for_missing_1200(self):
        """1200 e alvo de geracao, nao criterio de reprovacao."""
        result = validate_image(_solid(900, 900, (10, 10, 10)))
        assert result.is_valid, result.errors

    def test_exactly_500_is_accepted(self):
        assert validate_image(_solid(500, 500, (10, 10, 10))).is_valid

    def test_result_is_truthy_when_valid(self):
        assert bool(validate_image(_white_with_product())) is True


class TestValidateImageIsolatedFailures:
    def test_below_minimum_dimension_fails(self):
        result = validate_image(_solid(499, 800, (10, 10, 10)))
        assert not result.is_valid
        assert len(result.errors) == 1
        assert "500x500" in result.errors[0]

    def test_corrupted_bytes_fail(self):
        result = validate_image(b"not-an-image")
        assert not result.is_valid
        assert "imagem" in result.errors[0]

    def test_unsupported_format_fails(self):
        buf = io.BytesIO()
        Image.new("RGB", (800, 800), color=(255, 255, 255)).save(buf, format="BMP")
        result = validate_image(buf.getvalue())
        assert not result.is_valid
        assert any("BMP" in e for e in result.errors)

    def test_oversized_file_fails(self):
        oversized = b"\xff\xd8\xff" + b"\x00" * (10 * 1024 * 1024 + 1)
        result = validate_image(oversized)
        assert not result.is_valid
        assert any("10MB" in e for e in result.errors)

    def test_result_is_falsy_when_invalid(self):
        assert bool(validate_image(b"not-an-image")) is False


class TestValidateImageMultipleFailures:
    def test_lists_all_reasons_not_just_the_first(self):
        """400x400 e fundo preto numa categoria de fundo branco: 2 motivos."""
        result = validate_image(
            _solid(400, 400, (0, 0, 0)), category_requires_white_bg=True
        )
        assert not result.is_valid
        assert len(result.errors) == 2, result.errors
        assert any("500x500" in e for e in result.errors)
        assert any("fundo" in e for e in result.errors)
        assert "; " in result.reason


class TestValidateImageWhiteBackground:
    def test_non_white_background_fails_when_required(self):
        result = validate_image(
            _solid(1200, 1200, (180, 120, 60)), category_requires_white_bg=True
        )
        assert not result.is_valid
        assert any("fundo" in e for e in result.errors)

    def test_same_image_passes_when_not_required(self):
        """Mesma imagem, categoria-raiz que nao exige branco: aprova."""
        image = _solid(1200, 1200, (180, 120, 60))
        assert validate_image(image, category_requires_white_bg=False).is_valid
        assert not validate_image(image, category_requires_white_bg=True).is_valid

    def test_white_background_with_centered_product_passes(self):
        result = validate_image(_white_with_product(), category_requires_white_bg=True)
        assert result.is_valid, result.errors

    def test_white_bg_check_is_skipped_by_default(self):
        assert validate_image(_solid(1200, 1200, (10, 10, 10))).is_valid


class TestCategoryRootWhiteBackground:
    """A raiz decide, nao o nome da categoria-folha."""

    @pytest.mark.asyncio
    async def test_beleza_root_requires_white_background(self):
        from app.services.category_service import category_requires_white_background

        with patch(
            "app.services.category_service.get_root_category_id",
            new_callable=AsyncMock,
            return_value="MLB1246",  # Beleza e Cuidado Pessoal
        ):
            assert await category_requires_white_background("MLB1000000") is True

    @pytest.mark.asyncio
    async def test_moda_root_does_not_require_white_background(self):
        from app.services.category_service import category_requires_white_background

        with patch(
            "app.services.category_service.get_root_category_id",
            new_callable=AsyncMock,
            return_value="MLB1430",  # Calcados, Roupas e Bolsas
        ):
            assert await category_requires_white_background("MLB1000000") is False

    @pytest.mark.asyncio
    async def test_unknown_category_does_not_require_white_background(self):
        """ML indisponivel: nao reprova imagem por isso."""
        from app.services.category_service import category_requires_white_background

        with patch(
            "app.services.category_service.get_root_category_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            assert await category_requires_white_background("MLB1055") is False

    @pytest.mark.asyncio
    async def test_root_id_comes_from_path_from_root_first_item(self):
        from app.services.category_service import get_root_category_id

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "id": "MLB1055",
            "name": "Celulares e Smartphones",
            "path_from_root": [
                {"id": "MLB1051", "name": "Celulares e Telefones"},
                {"id": "MLB1055", "name": "Celulares e Smartphones"},
            ],
        }
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.category_service.httpx.AsyncClient", return_value=mock_client):
            assert await get_root_category_id("MLB1055") == "MLB1051"

    @pytest.mark.asyncio
    async def test_leaf_of_tech_root_requires_white_background(self):
        """MLB1055 (smartphones) e folha; a raiz MLB1051 e que exige branco."""
        from app.services.category_service import category_requires_white_background

        with patch(
            "app.services.category_service.get_root_category_id",
            new_callable=AsyncMock,
            return_value="MLB1051",
        ):
            assert await category_requires_white_background("MLB1055") is True
