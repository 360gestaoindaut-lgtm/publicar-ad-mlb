"""Renderizador dos cards de beneficio/uso/especificacoes, sem IA.

Cada anuncio ganha 3 imagens extras alem da capa: foto do produto (ja gerada
em algum passo anterior do pipeline) com um titulo e ate 3 bullets sobre ela,
compostos aqui com Pillow puro. Sem chamada de rede, sem motor de imagem —
so composicao de pixels e texto a partir de bytes ja prontos.

Layout fixo (nao e estilo livre, e alinhado ao restante das imagens do
anuncio): canvas 1200x1200, foto em contain-fit na faixa superior, regua
divisoria, bloco de texto centralizado verticalmente na faixa inferior. O
centro vertical do bloco de texto e o motivo real de existir de
`_layout_text_block`: sem ele, um card com 2 bullets deixa metade da faixa em
branco embaixo do texto.
"""
import io
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# __file__ e app/services/image_benefit_card_service.py, entao parents[1] e app/.
_FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
_FONT_BOLD = _FONT_DIR / "Inter-Bold.ttf"
_FONT_REGULAR = _FONT_DIR / "Inter-Regular.ttf"

CARD_DIM = 1200
_JPEG_QUALITY = 92  # mesma qualidade de app/services/image_postprocess_service.py

_WHITE = (255, 255, 255)
_RULE_COLOR = (0xE5, 0xE7, 0xEB)
_TITLE_COLOR = (0x1E, 0x29, 0x3B)
_BULLET_COLOR = (0x47, 0x55, 0x69)
_ACCENT_COLOR = (0x0F, 0x76, 0x6E)

_PHOTO_BAND_Y0 = 0
_PHOTO_BAND_Y1 = 640

_RULE_Y = 668
_RULE_X0 = 90
_RULE_X1 = 1110

_TEXT_BAND_Y0 = 700
_TEXT_BAND_Y1 = 1110

_TITLE_SIZE = 58
_TITLE_X = 90
_TITLE_MAX_WIDTH = 1020
_TITLE_MAX_LINES = 2
_TITLE_LINE_HEIGHT = 1.2
_ELLIPSIS = "..."

_BULLET_SIZE = 38
_BULLET_LINE_HEIGHT = 1.35
_BULLET_MARKER_RADIUS = 7
_BULLET_MARKER_X = 104
_BULLET_TEXT_X = 136
_BULLET_MAX_WIDTH = CARD_DIM - _BULLET_TEXT_X - 90  # 974px

_TITLE_TO_BULLETS_GAP = 40
_BULLET_GAP = 28


class CardRenderError(RuntimeError):
    """Falha ao renderizar o card (foto-base ilegivel, texto vazio)."""


@lru_cache(maxsize=None)
def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    """TTF cacheado por (arquivo, tamanho) — o worker renderiza 3 cards por
    anuncio, recarregar o mesmo TTF do disco a cada card seria desperdicio."""
    return ImageFont.truetype(path, size)


def _title_font(size: int = _TITLE_SIZE) -> ImageFont.FreeTypeFont:
    return _load_font(str(_FONT_BOLD), size)


def _bullet_font(size: int = _BULLET_SIZE) -> ImageFont.FreeTypeFont:
    return _load_font(str(_FONT_REGULAR), size)


def _line_height(font: ImageFont.FreeTypeFont, multiplier: float) -> float:
    """Altura de linha a partir da metrica da fonte (ascent+descent), nao um
    valor chutado — dois tamanhos de fonte diferentes nao tem a mesma altura."""
    ascent, descent = font.getmetrics()
    return (ascent + descent) * multiplier


def _max_prefix_length(word: str, font: ImageFont.FreeTypeFont, max_width: int) -> int:
    """Maior prefixo de `word` que cabe em `max_width`, por busca binaria."""
    lo, hi, best = 0, len(word), 0
    while lo <= hi:
        mid = (lo + hi) // 2
        if font.getlength(word[:mid]) <= max_width:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Quebra `text` em linhas que cabem em `max_width`, medindo com
    `font.getlength()` (getsize foi removido no Pillow 10).

    Quebra por palavra. Uma palavra isolada mais larga que a caixa e cortada
    por caractere (busca binaria pelo maior prefixo que cabe), porque nao ha
    quebra por espaco que a faca caber.
    """
    text = text.strip()
    if not text:
        return []

    lines: list[str] = []
    for word in text.split():
        while font.getlength(word) > max_width:
            cut = _max_prefix_length(word, font, max_width) or 1  # evita loop infinito
            lines.append(word[:cut])
            word = word[cut:]

        if not lines:
            lines.append(word)
            continue

        candidate = f"{lines[-1]} {word}".strip()
        if font.getlength(candidate) <= max_width:
            lines[-1] = candidate
        else:
            lines.append(word)

    return lines


def _truncate_with_ellipsis(line: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    """Garante "..." no final de `line`, cortando caracteres se precisar pra
    caber em `max_width` com a reticencia incluida.

    Sem bypass para o caso em que `line` sozinha ja cabe: quem chama esta
    funcao so faz isso quando ha conteudo do titulo alem do limite de linhas,
    entao a reticencia precisa aparecer sempre — senao um titulo cortado bem
    na borda de uma palavra vira truncamento silencioso, sem sinalizar que
    sobrou texto."""
    while line and font.getlength(line + _ELLIPSIS) > max_width:
        line = line[:-1].rstrip()
    return f"{line}{_ELLIPSIS}" if line else _ELLIPSIS


def _wrap_title(title: str, font: ImageFont.FreeTypeFont, max_width: int, max_lines: int) -> list[str]:
    """Quebra o titulo em no maximo `max_lines`, truncando a ultima com "..."
    se sobrar conteudo alem do limite."""
    lines = _wrap_text(title, font, max_width)
    if len(lines) <= max_lines:
        return lines
    kept = lines[:max_lines]
    kept[-1] = _truncate_with_ellipsis(kept[-1], font, max_width)
    return kept


def _contain_fit(img: Image.Image, box_w: int, box_h: int) -> Image.Image:
    """Redimensiona `img` para caber inteira em box_w x box_h, preservando a
    proporcao original — nunca faz upscale alem do tamanho original.

    `Image.resize` direto para a caixa distorce quando a proporcao nao bate;
    esta funcao e o unico jeito correto de encaixar uma foto retangular numa
    faixa fixa sem esticar.
    """
    src_w, src_h = img.size
    scale = min(box_w / src_w, box_h / src_h, 1.0)
    target = (max(int(src_w * scale), 1), max(int(src_h * scale), 1))
    if target == img.size:
        return img
    return img.resize(target, Image.LANCZOS)


def _paste_photo_band(canvas: Image.Image, photo: Image.Image) -> None:
    band_w = CARD_DIM
    band_h = _PHOTO_BAND_Y1 - _PHOTO_BAND_Y0
    fitted = _contain_fit(photo, band_w, band_h)
    x = (band_w - fitted.width) // 2
    y = _PHOTO_BAND_Y0 + (band_h - fitted.height) // 2
    canvas.paste(fitted, (x, y))


def _draw_rule(draw: ImageDraw.ImageDraw) -> None:
    draw.line([(_RULE_X0, _RULE_Y), (_RULE_X1, _RULE_Y)], fill=_RULE_COLOR, width=1)


@dataclass(frozen=True)
class _LineSpec:
    """Uma linha ja quebrada, pronta pra desenhar: texto, fonte, cor, altura
    de linha, o espaco a aplicar ANTES dela (gap de secao — 0 pra linhas de
    continuacao dentro do mesmo titulo/bullet) e se e a primeira linha de um
    bullet (pro marcador).

    `gap_before` existe pra `_draw_text_block` e `_build_text_block` nunca
    poderem divergir sobre quanto espaco entra no desenho: os dois somam
    exatamente os mesmos campos desta classe, nenhum valor de espacamento
    fica solto em variavel externa.
    """

    text: str
    font: ImageFont.FreeTypeFont
    color: tuple[int, int, int]
    line_height: float
    x: int
    gap_before: float = 0
    is_bullet_start: bool = False


def _build_text_block(title: str, bullets: list[str]) -> tuple[list[_LineSpec], float]:
    """Monta a sequencia de linhas (titulo + bullets, ja quebrados) e devolve
    a altura total do bloco, sem desenhar nada — usado tanto pro render
    quanto pelos testes de geometria.

    A altura total e a soma de `line_height + gap_before` de cada `_LineSpec`
    — os mesmos campos que `_draw_text_block` usa pra avancar o `y` — entao
    nao ha como o espaco contado aqui divergir do espaco realmente desenhado.
    """
    lines: list[_LineSpec] = []

    title = (title or "").strip()
    if title:
        font = _title_font()
        lh = _line_height(font, _TITLE_LINE_HEIGHT)
        wrapped = _wrap_title(title, font, _TITLE_MAX_WIDTH, _TITLE_MAX_LINES)
        for line in wrapped:
            lines.append(_LineSpec(line, font, _TITLE_COLOR, lh, _TITLE_X))

    clean_bullets = [b.strip() for b in bullets if b and b.strip()]

    bfont = _bullet_font()
    blh = _line_height(bfont, _BULLET_LINE_HEIGHT)
    for i, bullet in enumerate(clean_bullets):
        wrapped = _wrap_text(bullet, bfont, _BULLET_MAX_WIDTH)
        if not wrapped:
            continue
        for j, line in enumerate(wrapped):
            gap = 0.0
            if j == 0:
                if i == 0 and title:
                    gap = _TITLE_TO_BULLETS_GAP
                elif i > 0:
                    gap = _BULLET_GAP
            lines.append(
                _LineSpec(
                    line, bfont, _BULLET_COLOR, blh, _BULLET_TEXT_X,
                    gap_before=gap, is_bullet_start=(j == 0),
                )
            )

    total_height = sum(spec.line_height + spec.gap_before for spec in lines)
    return lines, total_height


def _layout_text_block(title: str, bullets: list[str]) -> tuple[list[_LineSpec], float, float]:
    """Devolve (linhas, altura total, y inicial) com o bloco centralizado
    verticalmente na faixa de texto (`_TEXT_BAND_Y0`..`_TEXT_BAND_Y1`)."""
    lines, total_height = _build_text_block(title, bullets)
    band_height = _TEXT_BAND_Y1 - _TEXT_BAND_Y0
    start_y = _TEXT_BAND_Y0 + max((band_height - total_height) / 2, 0)
    return lines, total_height, start_y


def _draw_text_block(draw: ImageDraw.ImageDraw, lines: list[_LineSpec], start_y: float) -> None:
    y = start_y
    for spec in lines:
        y += spec.gap_before
        if spec.is_bullet_start:
            marker_cy = y + spec.line_height / 2
            r = _BULLET_MARKER_RADIUS
            draw.ellipse(
                [
                    (_BULLET_MARKER_X - r, marker_cy - r),
                    (_BULLET_MARKER_X + r, marker_cy + r),
                ],
                fill=_ACCENT_COLOR,
            )
        # Ancora vertical no topo da linha, sem esticar pelo bbox de glifo —
        # a altura de linha ja vem da metrica da fonte (_line_height).
        draw.text((spec.x, y), spec.text, font=spec.font, fill=spec.color)
        y += spec.line_height


def render_benefit_card(product_photo_bytes: bytes, title: str, bullets: list[str]) -> bytes:
    """Card 1200x1200 JPEG: foto do produto em cima, titulo e bullets embaixo.

    Levanta CardRenderError se a foto-base nao abrir como imagem ou se nao
    houver texto nenhum para renderizar.
    """
    try:
        photo = Image.open(io.BytesIO(product_photo_bytes))
        photo.load()
        photo = photo.convert("RGB")
    except Exception as exc:
        raise CardRenderError("foto-base ilegivel") from exc

    title = (title or "").strip()
    clean_bullets = [b.strip() for b in (bullets or []) if b and b.strip()]
    if not title and not clean_bullets:
        raise CardRenderError("nenhum texto para renderizar")

    canvas = Image.new("RGB", (CARD_DIM, CARD_DIM), _WHITE)
    _paste_photo_band(canvas, photo)

    draw = ImageDraw.Draw(canvas)
    _draw_rule(draw)

    lines, _, start_y = _layout_text_block(title, clean_bullets)
    _draw_text_block(draw, lines, start_y)

    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=_JPEG_QUALITY)
    return buf.getvalue()
