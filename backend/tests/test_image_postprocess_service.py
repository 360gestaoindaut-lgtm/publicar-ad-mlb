import io

from PIL import Image

from app.services.image_postprocess_service import ML_TARGET_DIM, normalize_to_square


def _make_image(width: int, height: int, color=(128, 128, 128), fmt="JPEG") -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _open(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


class TestNormalizeToSquare:
    def test_target_is_1200(self):
        assert ML_TARGET_DIM == 1200

    def test_landscape_becomes_1200_square(self):
        result = normalize_to_square(_make_image(1536, 1024))
        assert result is not None
        assert _open(result).size == (1200, 1200)

    def test_portrait_becomes_1200_square(self):
        result = normalize_to_square(_make_image(1024, 1536))
        assert result is not None
        assert _open(result).size == (1200, 1200)

    def test_already_square_target_is_unchanged_in_size(self):
        result = normalize_to_square(_make_image(1200, 1200))
        assert result is not None
        assert _open(result).size == (1200, 1200)

    def test_small_square_is_upscaled(self):
        result = normalize_to_square(_make_image(512, 512))
        assert result is not None
        assert _open(result).size == (1200, 1200)

    def test_output_is_jpeg(self):
        result = normalize_to_square(_make_image(900, 700, fmt="PNG"))
        assert result is not None
        assert _open(result).format == "JPEG"

    def test_corrupted_bytes_return_none(self):
        assert normalize_to_square(b"this-is-not-an-image") is None

    def test_empty_bytes_return_none(self):
        assert normalize_to_square(b"") is None

    def test_crops_center_not_stretches(self):
        """Produto centralizado sobrevive; as bordas laterais é que somem.

        Imagem 1500x500: faixa vermelha central de 500px de largura ladeada
        por verde. O recorte 1:1 central pega exatamente a faixa vermelha, e
        um resize distorcido (sem crop) traria verde para o centro.
        """
        img = Image.new("RGB", (1500, 500), color=(0, 255, 0))
        img.paste(Image.new("RGB", (500, 500), color=(255, 0, 0)), (500, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")

        result = normalize_to_square(buf.getvalue())
        assert result is not None
        out = _open(result).convert("RGB")
        assert out.size == (1200, 1200)

        # O recorte 1:1 central pega exatamente a faixa vermelha (x 500..1000).
        for point in [(600, 600), (100, 100), (1100, 1100)]:
            r, g, b = out.getpixel(point)
            assert r > g, f"{point} deveria ser vermelho (produto), veio {(r, g, b)}"

    def test_custom_target_is_respected(self):
        result = normalize_to_square(_make_image(2000, 1000), target=800)
        assert result is not None
        assert _open(result).size == (800, 800)
