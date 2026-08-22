"""Pós-processamento das imagens geradas pelos motores de IA.

O Mercado Livre redimensiona para 1200px qualquer imagem maior que isso no
upload, então 1200x1200 é o teto útil — não só o mínimo recomendado. Este
módulo garante que toda imagem chegue ao upload já nesse formato, sem
distorção: recorte central para proporção 1:1 primeiro, resize depois.
"""
import io

from PIL import Image

# Alvo de saída: quadrado 1200x1200, o formato que ativa zoom no ML sem
# sofrer redimensionamento do lado deles.
ML_TARGET_DIM = 1200

_JPEG_QUALITY = 92


def normalize_to_square(image_bytes: bytes, target: int = ML_TARGET_DIM) -> bytes | None:
    """Devolve a imagem como JPEG quadrado de `target`x`target`.

    Recorta o centro para 1:1 antes de redimensionar, de modo que o produto
    centralizado nunca é esticado. Retorna None se os bytes não abrirem como
    imagem, para o chamador registrar a reprovacao sem subir nada.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
        img = img.convert("RGB")
    except Exception:
        return None

    width, height = img.size
    if width == 0 or height == 0:
        return None

    if width != height:
        side = min(width, height)
        left = (width - side) // 2
        top = (height - side) // 2
        img = img.crop((left, top, left + side, top + side))

    if img.size != (target, target):
        img = img.resize((target, target), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=_JPEG_QUALITY)
    return buf.getvalue()
