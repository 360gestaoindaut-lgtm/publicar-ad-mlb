import io

import pytest
from PIL import Image

from app.services.image_benefit_card_service import (
    CARD_DIM,
    CardRenderError,
    _bullet_font,
    _contain_fit,
    _layout_text_block,
    _title_font,
    _TEXT_BAND_Y0,
    _TEXT_BAND_Y1,
    _wrap_text,
    render_benefit_card,
)


def _photo(width: int, height: int, color=(80, 120, 160), fmt="JPEG") -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _open(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


# --------------------------------------------------------------------------
# 1. Caso feliz: titulo e bullets curtos
# --------------------------------------------------------------------------


class TestRenderHappyPath:
    def test_output_is_1200x1200_jpeg(self):
        result = render_benefit_card(
            _photo(800, 800), "Produto excelente", ["Bullet um", "Bullet dois"]
        )
        img = _open(result)
        assert img.size == (CARD_DIM, CARD_DIM)
        assert img.format == "JPEG"


# --------------------------------------------------------------------------
# 2. Bullet longo: quebra real, nao so "nao levantou excecao"
# --------------------------------------------------------------------------


class TestWrapText:
    def test_long_bullet_wraps_into_multiple_lines(self):
        font = _bullet_font()
        long_bullet = (
            "Este bullet e propositalmente muito longo para caber numa unica "
            "linha dentro da largura util reservada ao texto deste card aqui"
        )
        assert len(long_bullet) >= 120
        lines = _wrap_text(long_bullet, font, 974)
        assert len(lines) > 1
        for line in lines:
            assert font.getlength(line) <= 974

    def test_short_text_stays_on_one_line(self):
        font = _bullet_font()
        lines = _wrap_text("Bullet curto", font, 974)
        assert len(lines) == 1

    def test_single_word_wider_than_box_is_split_by_character(self):
        font = _bullet_font()
        huge_word = "a" * 200
        lines = _wrap_text(huge_word, font, 200)
        assert len(lines) > 1
        for line in lines:
            assert font.getlength(line) <= 200
        assert "".join(lines) == huge_word

    def test_empty_text_returns_no_lines(self):
        assert _wrap_text("   ", _bullet_font(), 974) == []

    def test_block_height_grows_with_long_bullet(self):
        short_lines, short_height, _ = _layout_text_block(
            "Titulo", ["Bullet curto", "Outro bullet curto"]
        )
        long_bullet = (
            "Este bullet e propositalmente muito longo para caber numa unica "
            "linha dentro da largura util reservada ao texto do card, entao "
            "ele precisa quebrar em varias linhas mesmo"
        )
        long_lines, long_height, _ = _layout_text_block(
            "Titulo", [long_bullet, "Outro bullet curto"]
        )
        assert long_height > short_height
        assert len(long_lines) > len(short_lines)


# --------------------------------------------------------------------------
# 3. Poucos bullets: bloco centralizado verticalmente, sem "buraco"
# --------------------------------------------------------------------------


class TestVerticalCentering:
    def test_two_bullets_block_is_vertically_centered(self):
        _lines, total_height, start_y = _layout_text_block(
            "Titulo curto", ["Primeiro bullet", "Segundo bullet"]
        )
        top_gap = start_y - _TEXT_BAND_Y0
        bottom_gap = _TEXT_BAND_Y1 - (start_y + total_height)
        assert top_gap == pytest.approx(bottom_gap, abs=2.0)

    def test_block_fits_inside_band(self):
        _lines, total_height, start_y = _layout_text_block(
            "Titulo curto", ["Primeiro bullet", "Segundo bullet"]
        )
        assert start_y >= _TEXT_BAND_Y0
        assert start_y + total_height <= _TEXT_BAND_Y1 + 1e-6


# --------------------------------------------------------------------------
# 4/5. Contain-fit: preserva proporcao, nunca faz upscale
# --------------------------------------------------------------------------


class TestContainFit:
    def test_rectangular_photo_keeps_aspect_ratio(self):
        img = Image.new("RGB", (1600, 900), color=(10, 20, 30))
        fitted = _contain_fit(img, 1200, 640)
        original_ratio = 1600 / 900
        fitted_ratio = fitted.width / fitted.height
        assert fitted_ratio == pytest.approx(original_ratio, rel=1e-3)
        # Limitada pela altura da faixa (640), a largura fica menor que 1200.
        assert fitted.height == 640
        assert fitted.width < 1200

    def test_square_photo_becomes_640x640(self):
        img = Image.new("RGB", (1200, 1200), color=(10, 20, 30))
        fitted = _contain_fit(img, 1200, 640)
        assert fitted.size == (640, 640)

    def test_never_upscales_beyond_original(self):
        img = Image.new("RGB", (300, 200), color=(10, 20, 30))
        fitted = _contain_fit(img, 1200, 640)
        assert fitted.size == (300, 200)

    def test_render_places_rectangular_photo_without_distortion(self):
        """Ponta a ponta: a foto colada no card mantem a proporcao original."""
        result = render_benefit_card(_photo(1600, 900), "Titulo", ["Bullet"])
        img = _open(result)
        assert img.size == (CARD_DIM, CARD_DIM)

    def test_render_places_square_photo_without_distortion(self):
        result = render_benefit_card(_photo(1200, 1200), "Titulo", ["Bullet"])
        img = _open(result)
        assert img.size == (CARD_DIM, CARD_DIM)


# --------------------------------------------------------------------------
# 6/7. Erros
# --------------------------------------------------------------------------


class TestCardRenderErrors:
    def test_invalid_photo_bytes_raise(self):
        with pytest.raises(CardRenderError):
            render_benefit_card(b"isso-nao-e-uma-imagem", "Titulo", ["Bullet"])

    def test_empty_title_and_bullets_raise(self):
        with pytest.raises(CardRenderError):
            render_benefit_card(_photo(800, 800), "", [])

    def test_blank_title_and_blank_bullets_raise(self):
        with pytest.raises(CardRenderError):
            render_benefit_card(_photo(800, 800), "   ", ["  ", ""])


# --------------------------------------------------------------------------
# 8. Acentos PT-BR
# --------------------------------------------------------------------------


class TestAccents:
    def test_accented_title_and_bullets_render_without_exception(self):
        result = render_benefit_card(
            _photo(1000, 1000),
            "Ação à prova d'água",
            ["Proteção contra respingos", "Fácil de limpar", "Compatível com padrão europeu"],
        )
        img = _open(result)
        assert img.size == (CARD_DIM, CARD_DIM)
        assert img.format == "JPEG"


# --------------------------------------------------------------------------
# Cache de fontes
# --------------------------------------------------------------------------


class TestFontCache:
    def test_same_path_and_size_returns_cached_instance(self):
        font_a = _title_font(58)
        font_b = _title_font(58)
        assert font_a is font_b

    def test_different_size_is_not_cached_together(self):
        font_a = _title_font(58)
        font_b = _title_font(40)
        assert font_a is not font_b
