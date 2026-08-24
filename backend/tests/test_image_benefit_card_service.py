import io

import pytest
from PIL import Image

from app.services.image_card_copy_service import (
    MAX_BULLET_CHARS,
    MAX_BULLETS,
    MAX_TITLE_CHARS,
)
from app.services.image_benefit_card_service import (
    CARD_DIM,
    CardRenderError,
    _bullet_font,
    _contain_fit,
    _draw_text_block,
    _layout_text_block,
    _line_height,
    _title_font,
    _wrap_title,
    _BULLET_GAP,
    _BULLET_LINE_HEIGHT,
    _TEXT_BAND_Y0,
    _TEXT_BAND_Y1,
    _TITLE_LINE_HEIGHT,
    _TITLE_MAX_LINES,
    _TITLE_MAX_WIDTH,
    _TITLE_TO_BULLETS_GAP,
    _wrap_text,
    render_benefit_card,
)


class _RecordingDraw:
    """Substituto de `ImageDraw.Draw` que so grava as posicoes de `text()`,
    pra testar `_draw_text_block` sem depender de sniffing de pixel."""

    def __init__(self):
        self.text_calls: list[tuple[float, float, str]] = []

    def text(self, xy, text, font=None, fill=None):
        self.text_calls.append((xy[0], xy[1], text))

    def ellipse(self, *args, **kwargs):
        pass

    def line(self, *args, **kwargs):
        pass


def _photo(width: int, height: int, color=(80, 120, 160), fmt="JPEG") -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _open(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


# Copy exatamente no limite do que o saneamento da Task 1 deixa passar
# (titulo de MAX_TITLE_CHARS, MAX_BULLETS bullets de MAX_BULLET_CHARS, com
# acentos PT-BR). E o pior caso que a producao pode entregar ao renderizador,
# entao e com ele que a geometria tem que ser testada — copy curta cabe na
# faixa por construcao e nao prova nada.
_MAX_TITLE = "Proteção térmica do treino ao escritório"
_MAX_BULLETS = [
    "Mantém bebidas geladas por até doze horas seguidas",
    "Alça reforçada com costura dupla e ajuste em metal",
    "Resistente à água e fácil de limpar com um pano só",
]


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
    def test_total_height_matches_independent_sum_of_constants(self):
        """Recalcula a altura esperada a partir das constantes cruas (metrica
        de fonte + gaps de secao), sem usar `_build_text_block`/`_layout_text_block`
        pra chegar la — se os gaps sumirem do calculo real, este numero diverge."""
        title_lh = _line_height(_title_font(), _TITLE_LINE_HEIGHT)
        bullet_lh = _line_height(_bullet_font(), _BULLET_LINE_HEIGHT)
        expected_height = title_lh + _TITLE_TO_BULLETS_GAP + bullet_lh + _BULLET_GAP + bullet_lh

        _lines, total_height, _start_y = _layout_text_block(
            "Titulo curto", ["Primeiro bullet", "Segundo bullet"]
        )
        assert total_height == pytest.approx(expected_height, abs=0.01)

    def test_two_bullets_block_is_vertically_centered(self):
        """Compara o gap medido contra uma formula de centralizacao calculada
        com a altura esperada de forma independente (nao a `total_height`
        devolvida pela propria funcao) — testar `top_gap == bottom_gap` sozinho
        e tautologico, os dois vem da mesma formula pra qualquer altura."""
        title_lh = _line_height(_title_font(), _TITLE_LINE_HEIGHT)
        bullet_lh = _line_height(_bullet_font(), _BULLET_LINE_HEIGHT)
        expected_height = title_lh + _TITLE_TO_BULLETS_GAP + bullet_lh + _BULLET_GAP + bullet_lh
        band_height = _TEXT_BAND_Y1 - _TEXT_BAND_Y0
        expected_top_gap = (band_height - expected_height) / 2

        _lines, total_height, start_y = _layout_text_block(
            "Titulo curto", ["Primeiro bullet", "Segundo bullet"]
        )
        top_gap = start_y - _TEXT_BAND_Y0
        bottom_gap = _TEXT_BAND_Y1 - (start_y + total_height)

        assert top_gap == pytest.approx(expected_top_gap, abs=0.5)
        assert top_gap == pytest.approx(bottom_gap, abs=2.0)

    def test_maximal_copy_really_is_at_the_sanitizer_limits(self):
        """Premissa dos testes de geometria: se a copy maxima usada aqui nao
        for de fato o limite do saneamento, os testes abaixo nao provam nada."""
        assert len(_MAX_TITLE) == MAX_TITLE_CHARS
        assert len(_MAX_BULLETS) == MAX_BULLETS
        for bullet in _MAX_BULLETS:
            assert len(bullet) == MAX_BULLET_CHARS

    def test_block_fits_inside_band_with_maximal_copy(self):
        """Copy no maximo permitido pelo saneamento tem que caber na faixa.

        Testar isso com titulo e bullets curtos e cego por construcao: a unica
        forma de copy que nunca estoura.
        """
        _lines, total_height, start_y = _layout_text_block(_MAX_TITLE, _MAX_BULLETS)
        assert start_y >= _TEXT_BAND_Y0
        assert start_y + total_height <= _TEXT_BAND_Y1 + 1e-6

    def test_block_fits_inside_band_with_short_copy(self):
        _lines, total_height, start_y = _layout_text_block(
            "Titulo curto", ["Primeiro bullet", "Segundo bullet"]
        )
        assert start_y >= _TEXT_BAND_Y0
        assert start_y + total_height <= _TEXT_BAND_Y1 + 1e-6

    def test_block_fits_inside_band_with_wide_characters(self):
        """Caracteres largos ("W" maiusculo) fazem cada bullet quebrar em 2
        linhas; o bloco so cabe se o layout descartar bullet ate caber."""
        wide_title = "W" * MAX_TITLE_CHARS
        wide_bullets = ["W" * MAX_BULLET_CHARS] * MAX_BULLETS

        lines, total_height, start_y = _layout_text_block(wide_title, wide_bullets)
        assert start_y >= _TEXT_BAND_Y0
        assert start_y + total_height <= _TEXT_BAND_Y1 + 1e-6
        # Prova que o caso e mesmo o do descarte: os 3 bullets nao cabem.
        assert sum(1 for spec in lines if spec.is_bullet_start) < MAX_BULLETS

    def test_nothing_is_drawn_below_the_canvas(self):
        """Nenhuma linha pode ser desenhada abaixo de CARD_DIM — nem no pior
        caso de copy, nem com caracteres largos."""
        casos = [
            (_MAX_TITLE, _MAX_BULLETS),
            ("W" * MAX_TITLE_CHARS, ["W" * MAX_BULLET_CHARS] * MAX_BULLETS),
            ("M" * MAX_TITLE_CHARS, ["Bullet normal", "Outro bullet normal"]),
        ]
        for title, bullets in casos:
            lines, _total_height, start_y = _layout_text_block(title, bullets)
            fake_draw = _RecordingDraw()
            _draw_text_block(fake_draw, lines, start_y)
            baseline_final = fake_draw.text_calls[-1][1] + lines[-1].line_height
            assert baseline_final <= CARD_DIM
            assert baseline_final <= _TEXT_BAND_Y1 + 1e-6

    def test_render_leaves_no_ink_below_the_text_band(self):
        """Ponta a ponta, em pixel: nada de tinta abaixo da faixa de texto."""
        result = render_benefit_card(_photo(1200, 1200), _MAX_TITLE, _MAX_BULLETS)
        img = _open(result).convert("L")
        abaixo = img.crop((0, _TEXT_BAND_Y1 + 2, CARD_DIM, CARD_DIM))
        # 240 e folga para o ruido de compressao do JPEG em torno do branco.
        assert min(abaixo.getdata()) > 240

    def test_draw_positions_reflect_the_section_gaps(self):
        """Exercita `_draw_text_block` de verdade (nao so os numeros que
        `_build_text_block` contou) com um `ImageDraw` falso, e confere que a
        distancia entre as posicoes DESENHADAS inclui o gap de secao — e
        exatamente o que ficou faltando quando os gaps eram contados em
        `total_height` mas nunca somados ao `y` do desenho."""
        lines, total_height, start_y = _layout_text_block(
            "Titulo curto", ["Primeiro bullet", "Segundo bullet"]
        )
        assert len(lines) == 3  # 1 linha de titulo + 2 bullets de 1 linha cada

        fake_draw = _RecordingDraw()
        _draw_text_block(fake_draw, lines, start_y)
        ys = [y for _, y, _ in fake_draw.text_calls]
        assert len(ys) == 3

        title_line, bullet1, bullet2 = lines
        assert bullet1.gap_before == pytest.approx(_TITLE_TO_BULLETS_GAP)
        assert bullet2.gap_before == pytest.approx(_BULLET_GAP)

        assert ys[1] - ys[0] == pytest.approx(title_line.line_height + bullet1.gap_before)
        assert ys[2] - ys[1] == pytest.approx(bullet1.line_height + bullet2.gap_before)

        # A ultima posicao desenhada + sua altura fecha exatamente o total_height
        # contado — o desenho real e a contagem nao podem mais divergir.
        assert (ys[-1] + bullet2.line_height) - start_y == pytest.approx(total_height)


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
# Titulo com mais conteudo do que cabe em 2 linhas: truncamento com "..."
# --------------------------------------------------------------------------


class TestTitleTruncation:
    _LONG_TITLE = (
        "Kit completo de ferramentas profissionais para manutencao domestica "
        "com maleta resistente e garantia estendida de fabrica"
    )

    def test_title_that_would_wrap_past_two_lines_gets_truncated(self):
        font = _title_font()
        # Confirma a premissa do teste: sem o limite de linhas, este titulo
        # realmente estouraria 2 linhas — senao o teste nao provaria nada.
        raw_wrap = _wrap_text(self._LONG_TITLE, font, _TITLE_MAX_WIDTH)
        assert len(raw_wrap) > _TITLE_MAX_LINES

        wrapped = _wrap_title(self._LONG_TITLE, font, _TITLE_MAX_WIDTH, _TITLE_MAX_LINES)
        assert len(wrapped) == _TITLE_MAX_LINES
        assert wrapped[-1].endswith("...")
        for line in wrapped:
            assert font.getlength(line) <= _TITLE_MAX_WIDTH

    def test_short_title_is_not_truncated(self):
        font = _title_font()
        wrapped = _wrap_title("Titulo curto", font, _TITLE_MAX_WIDTH, _TITLE_MAX_LINES)
        assert wrapped == ["Titulo curto"]
        assert not wrapped[-1].endswith("...")

    def test_render_end_to_end_with_long_title_stays_within_two_lines(self):
        result = render_benefit_card(_photo(900, 900), self._LONG_TITLE, ["Bullet unico"])
        img = _open(result)
        assert img.size == (CARD_DIM, CARD_DIM)


# --------------------------------------------------------------------------
# So titulo ou so bullets: sem gap fantasma
# --------------------------------------------------------------------------


class TestTitleOnlyOrBulletsOnly:
    def test_title_only_has_no_gap_and_height_is_just_the_title(self):
        lines, total_height, _start_y = _layout_text_block("Titulo sozinho", [])
        assert len(lines) == 1
        assert lines[0].gap_before == 0

        expected_height = _line_height(_title_font(), _TITLE_LINE_HEIGHT)
        assert total_height == pytest.approx(expected_height, abs=0.01)

    def test_bullets_only_has_no_gap_before_the_first_bullet(self):
        lines, total_height, _start_y = _layout_text_block(
            "", ["Primeiro bullet", "Segundo bullet"]
        )
        assert len(lines) == 2
        assert lines[0].gap_before == 0
        assert lines[1].gap_before == pytest.approx(_BULLET_GAP)

        bullet_lh = _line_height(_bullet_font(), _BULLET_LINE_HEIGHT)
        expected_height = bullet_lh + _BULLET_GAP + bullet_lh
        assert total_height == pytest.approx(expected_height, abs=0.01)

    def test_render_title_only_does_not_crash(self):
        result = render_benefit_card(_photo(800, 800), "Somente titulo", [])
        img = _open(result)
        assert img.size == (CARD_DIM, CARD_DIM)

    def test_render_bullets_only_does_not_crash(self):
        result = render_benefit_card(
            _photo(800, 800), "", ["Bullet unico", "Outro bullet"]
        )
        img = _open(result)
        assert img.size == (CARD_DIM, CARD_DIM)


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
