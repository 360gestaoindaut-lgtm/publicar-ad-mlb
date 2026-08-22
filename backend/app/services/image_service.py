import asyncio
import io
from dataclasses import dataclass, field

import httpx
from PIL import Image

ML_PICTURES_URL = "https://api.mercadolibre.com/pictures/items/upload"
_MIN_DIMENSION = 500       # mínimo obrigatório do ML — abaixo disso o anúncio é recusado
_MAX_BYTES = 10 * 1024 * 1024
_ALLOWED_FORMATS = ("JPEG", "PNG")

# Triagem de fundo branco: um pixel conta como "branco" se todos os canais RGB
# estiverem em 245+. Amostramos o anel de borda porque é onde o fundo aparece
# sem risco de pegar o produto, que fica centralizado.
_WHITE_MIN_CHANNEL = 245
_WHITE_MIN_RATIO = 0.90
_BORDER_INSET_RATIO = 0.02   # ignora 2% da borda — artefato de compressão JPEG
_BORDER_SAMPLES_PER_EDGE = 32


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


@dataclass(frozen=True)
class ImageValidationResult:
    """Resultado do QA de uma imagem antes do upload para o ML.

    `__bool__` devolve `is_valid` para que qualquer checagem em contexto
    booleano (`if not validate_image(...)`) continue correta.
    """

    is_valid: bool
    errors: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.is_valid

    @property
    def reason(self) -> str | None:
        """Motivos concatenados, prontos para persistir em listing_images."""
        return "; ".join(self.errors) if self.errors else None


def _border_white_ratio(img: Image.Image) -> float:
    """Fração de pixels quase-brancos no anel de borda da imagem."""
    width, height = img.size
    inset_x = max(int(width * _BORDER_INSET_RATIO), 1)
    inset_y = max(int(height * _BORDER_INSET_RATIO), 1)
    left, right = inset_x, max(width - inset_x - 1, inset_x)
    top, bottom = inset_y, max(height - inset_y - 1, inset_y)

    n = _BORDER_SAMPLES_PER_EDGE
    xs = [left + round((right - left) * i / max(n - 1, 1)) for i in range(n)]
    ys = [top + round((bottom - top) * i / max(n - 1, 1)) for i in range(n)]

    points = (
        [(x, top) for x in xs]
        + [(x, bottom) for x in xs]
        + [(left, y) for y in ys]
        + [(right, y) for y in ys]
    )

    white = 0
    for x, y in points:
        r, g, b = img.getpixel((x, y))[:3]
        if r >= _WHITE_MIN_CHANNEL and g >= _WHITE_MIN_CHANNEL and b >= _WHITE_MIN_CHANNEL:
            white += 1
    return white / len(points)


def validate_image(
    image_bytes: bytes,
    category_requires_white_bg: bool = False,
) -> ImageValidationResult:
    """QA da imagem contra as regras do Mercado Livre.

    Acumula todos os motivos de falha em vez de parar no primeiro. O mínimo de
    500x500 é critério de reprovação; o alvo de 1200x1200 é padrão de geração
    (ver `image_postprocess_service`) e não reprova nada aqui — uma imagem de
    900x900 vinda de outra fonte continua válida.
    """
    errors: list[str] = []

    if len(image_bytes) > _MAX_BYTES:
        mb = len(image_bytes) / (1024 * 1024)
        errors.append(f"arquivo com {mb:.1f}MB excede o limite de 10MB do ML")

    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
    except Exception:
        errors.append("bytes não são uma imagem válida")
        return ImageValidationResult(is_valid=False, errors=errors)

    if img.format not in _ALLOWED_FORMATS:
        errors.append(f"formato {img.format or 'desconhecido'} não aceito pelo ML (use JPG ou PNG)")

    width, height = img.size
    if min(width, height) < _MIN_DIMENSION:
        errors.append(
            f"dimensão {width}x{height} abaixo do mínimo de "
            f"{_MIN_DIMENSION}x{_MIN_DIMENSION}px exigido pelo ML"
        )

    if category_requires_white_bg:
        ratio = _border_white_ratio(img.convert("RGB"))
        if ratio < _WHITE_MIN_RATIO:
            errors.append(
                f"fundo da capa não é branco puro ({ratio:.0%} da borda em #FFFFFF, "
                f"mínimo {_WHITE_MIN_RATIO:.0%}) e a categoria-raiz exige fundo branco"
            )

    return ImageValidationResult(is_valid=not errors, errors=errors)


