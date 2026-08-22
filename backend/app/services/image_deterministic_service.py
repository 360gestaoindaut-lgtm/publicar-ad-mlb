"""Composição determinística da capa, sem custo de IA.

Quando a foto bruta do seller já tem fundo uniforme, dá para recortar o produto
e recolocá-lo sobre branco puro sem chamar nenhum motor pago. O recorte é feito
por distância de cor a partir dos cantos — só Pillow, sem dependência nova.

O caminho é deliberadamente conservador: qualquer sinal de que a foto não se
encaixa no caso simples (fundo texturizado, produto sangrando pela borda,
máscara incoerente) devolve None, e o chamador segue pelo caminho pago de
sempre. Falso negativo custa uma geração de IA; falso positivo publicaria uma
capa recortada errada no anúncio.
"""
import io
from PIL import Image, ImageStat

from app.services.image_postprocess_service import ML_TARGET_DIM

# A máscara é calculada sobre uma versão reduzida: 1200x1200 seriam 1.44M
# pixels em loop Python puro. Em 512px o bounding box sai igual para o que
# interessa, e o recorte final usa a resolução original.
_WORK_SIZE = 512

# Amostragem de fundo: patch quadrado em cada canto, com 6% do menor lado.
_CORNER_PATCH_RATIO = 0.06

# Os 4 cantos precisam concordar entre si sobre qual é a cor de fundo. Acima
# desta distância o fundo é gradiente/texturizado e nem tentamos.
_CORNER_CONVERGENCE = 24.0

# Pixel é fundo se a distância euclidiana RGB até a cor amostrada couber aqui.
_BG_TOLERANCE = 30.0

# O bounding box precisa parecer um produto: nem ruído, nem a foto inteira.
# O teto começou em 0.90, mas a medição mostrou que ele nunca chegava a valer:
# acima de ~85% de área o produto invade os patches dos cantos, a cor de fundo
# sai contaminada e a foto era rejeitada pela regra de bordas antes de chegar
# aqui. 0.80 é o maior teto que ainda incide enquanto a amostragem dos cantos
# está limpa, então a regra declarada é a regra que de fato decide.
_MIN_BBOX_AREA_RATIO = 0.10
_MAX_BBOX_AREA_RATIO = 0.80

# Produto sangrando por 2+ bordas foi cortado no enquadramento original.
_MAX_BORDERS_TOUCHED = 1

# Respiro ao redor do produto no recorte, e quanto do canvas ele ocupa.
_CROP_MARGIN_RATIO = 0.05
_CANVAS_FILL_RATIO = 0.85

_JPEG_QUALITY = 92
_WHITE = (255, 255, 255)


def _distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def _corner_colors(img: Image.Image) -> list[tuple[float, float, float]]:
    """Cor média de um patch em cada um dos 4 cantos."""
    width, height = img.size
    patch = max(int(min(width, height) * _CORNER_PATCH_RATIO), 1)
    boxes = (
        (0, 0, patch, patch),
        (width - patch, 0, width, patch),
        (0, height - patch, patch, height),
        (width - patch, height - patch, width, height),
    )
    colors = []
    for box in boxes:
        mean = ImageStat.Stat(img.crop(box)).mean
        colors.append((mean[0], mean[1], mean[2]))
    return colors


def _background_color(img: Image.Image) -> tuple[float, float, float] | None:
    """Cor de fundo se os 4 cantos convergirem; None se o fundo não for uniforme."""
    corners = _corner_colors(img)
    for i in range(len(corners)):
        for j in range(i + 1, len(corners)):
            if _distance(corners[i], corners[j]) > _CORNER_CONVERGENCE:
                return None
    n = len(corners)
    return (
        sum(c[0] for c in corners) / n,
        sum(c[1] for c in corners) / n,
        sum(c[2] for c in corners) / n,
    )


def _product_bbox(
    work: Image.Image, bg_color: tuple[float, float, float]
) -> tuple[int, int, int, int] | None:
    """Bounding box dos pixels que não são fundo, na escala da imagem reduzida."""
    width, height = work.size
    br, bg_, bb = bg_color
    tolerance_sq = _BG_TOLERANCE**2

    min_x, min_y = width, height
    max_x = max_y = -1

    for index, pixel in enumerate(work.getdata()):
        dr = pixel[0] - br
        dg = pixel[1] - bg_
        db = pixel[2] - bb
        if dr * dr + dg * dg + db * db <= tolerance_sq:
            continue
        y, x = divmod(index, width)
        if x < min_x:
            min_x = x
        if x > max_x:
            max_x = x
        if y < min_y:
            min_y = y
        if y > max_y:
            max_y = y

    if max_x < 0:
        return None
    return min_x, min_y, max_x, max_y


def _borders_touched(bbox: tuple[int, int, int, int], size: tuple[int, int]) -> int:
    min_x, min_y, max_x, max_y = bbox
    width, height = size
    return sum(
        (min_x <= 0, min_y <= 0, max_x >= width - 1, max_y >= height - 1)
    )


def try_deterministic_cover(raw_photo_bytes: bytes) -> bytes | None:
    """Capa 1200x1200 em fundo branco puro a partir da foto bruta, sem IA.

    Devolve None sempre que a foto não se encaixar no caso de fundo uniforme —
    o chamador então segue pelo caminho de geração paga, inalterado.
    """
    try:
        img = Image.open(io.BytesIO(raw_photo_bytes))
        img.load()
        img = img.convert("RGB")
    except Exception:
        return None

    width, height = img.size
    if width < 2 or height < 2:
        return None

    bg_color = _background_color(img)
    if bg_color is None:
        return None  # fundo não-uniforme (gradiente, textura, cena)

    scale = min(_WORK_SIZE / max(width, height), 1.0)
    work_size = (max(int(width * scale), 1), max(int(height * scale), 1))
    work = img.resize(work_size, Image.BILINEAR) if scale < 1.0 else img

    bbox = _product_bbox(work, bg_color)
    if bbox is None:
        return None  # nenhum pixel destoou do fundo

    if _borders_touched(bbox, work.size) > _MAX_BORDERS_TOUCHED:
        return None  # produto sangra pela borda, foi cortado no enquadramento

    min_x, min_y, max_x, max_y = bbox
    bbox_area = (max_x - min_x + 1) * (max_y - min_y + 1)
    area_ratio = bbox_area / (work.size[0] * work.size[1])
    if not (_MIN_BBOX_AREA_RATIO <= area_ratio <= _MAX_BBOX_AREA_RATIO):
        return None  # ruído (pequeno demais) ou foto sem fundo real (grande demais)

    # Remapeia para a resolução original e aplica a margem de respiro.
    ratio_x = width / work.size[0]
    ratio_y = height / work.size[1]
    left = min_x * ratio_x
    top = min_y * ratio_y
    right = (max_x + 1) * ratio_x
    bottom = (max_y + 1) * ratio_y

    margin_x = (right - left) * _CROP_MARGIN_RATIO
    margin_y = (bottom - top) * _CROP_MARGIN_RATIO
    crop_box = (
        int(max(left - margin_x, 0)),
        int(max(top - margin_y, 0)),
        int(min(right + margin_x, width)),
        int(min(bottom + margin_y, height)),
    )
    product = img.crop(crop_box)
    if min(product.size) < 1:
        return None

    # Encaixa o produto no canvas preservando proporção — nunca estica.
    fill = int(ML_TARGET_DIM * _CANVAS_FILL_RATIO)
    fit = min(fill / product.size[0], fill / product.size[1])
    target = (
        max(int(product.size[0] * fit), 1),
        max(int(product.size[1] * fit), 1),
    )
    product = product.resize(target, Image.LANCZOS)

    canvas = Image.new("RGB", (ML_TARGET_DIM, ML_TARGET_DIM), _WHITE)
    canvas.paste(
        product,
        ((ML_TARGET_DIM - target[0]) // 2, (ML_TARGET_DIM - target[1]) // 2),
    )

    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=_JPEG_QUALITY)
    return buf.getvalue()
