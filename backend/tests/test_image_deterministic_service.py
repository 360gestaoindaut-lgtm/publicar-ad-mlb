import io

from PIL import Image

from app.services.image_deterministic_service import try_deterministic_cover


def _encode(img: Image.Image, fmt="JPEG") -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=fmt, quality=95)
    return buf.getvalue()


def _uniform_bg_with_product(
    size=(1000, 1000),
    bg=(200, 200, 205),
    product=(40, 60, 120),
    product_ratio=0.5,
) -> bytes:
    """Fundo uniforme com um retangulo centralizado fazendo as vezes do produto."""
    img = Image.new("RGB", size, color=bg)
    pw = int(size[0] * product_ratio)
    ph = int(size[1] * product_ratio)
    img.paste(
        Image.new("RGB", (pw, ph), color=product),
        ((size[0] - pw) // 2, (size[1] - ph) // 2),
    )
    return _encode(img)


def _open(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


def _corner_is_white(img: Image.Image, inset=8) -> bool:
    w, h = img.size
    for point in [(inset, inset), (w - inset, inset), (inset, h - inset), (w - inset, h - inset)]:
        r, g, b = img.convert("RGB").getpixel(point)
        if min(r, g, b) < 245:
            return False
    return True


class TestDeterministicCoverAccepts:
    def test_product_touching_one_border_is_accepted(self):
        """1 borda e tolerado; so 2+ indica enquadramento cortado."""
        img = Image.new("RGB", (1000, 1000), color=(210, 210, 210))
        img.paste(Image.new("RGB", (400, 600), color=(30, 30, 30)), (300, 400))

        assert try_deterministic_cover(_encode(img)) is not None

    def test_noisy_background_still_accepted(self):
        """Foto real nao tem fundo perfeitamente chapado; ruido leve deve passar."""
        import random

        random.seed(7)
        img = Image.new("RGB", (1000, 1000), color=(200, 200, 205))
        px = img.load()
        for y in range(0, 1000, 2):
            for x in range(0, 1000, 2):
                n = random.randint(-9, 9)
                px[x, y] = (200 + n, 200 + n, 205 + n)
        img.paste(Image.new("RGB", (500, 500), color=(40, 60, 120)), (250, 250))

        assert try_deterministic_cover(_encode(img)) is not None

    def test_uniform_background_with_centered_product(self):
        result = try_deterministic_cover(_uniform_bg_with_product())

        assert result is not None
        out = _open(result)
        assert out.size == (1200, 1200)
        assert out.format == "JPEG"

    def test_output_background_is_pure_white(self):
        result = try_deterministic_cover(_uniform_bg_with_product())

        assert result is not None
        assert _corner_is_white(_open(result)), "cantos do canvas devem sair em branco puro"

    def test_product_survives_at_the_center(self):
        result = try_deterministic_cover(
            _uniform_bg_with_product(product=(20, 40, 200))
        )

        assert result is not None
        r, g, b = _open(result).convert("RGB").getpixel((600, 600))
        assert b > r and b > g, f"centro deveria manter o produto azul, veio {(r, g, b)}"

    def test_works_on_non_square_photo(self):
        result = try_deterministic_cover(_uniform_bg_with_product(size=(1400, 900)))

        assert result is not None
        assert _open(result).size == (1200, 1200)

    def test_product_is_not_distorted(self):
        """Produto quadrado na origem continua quadrado na saida."""
        img = Image.new("RGB", (1400, 900), color=(210, 210, 210))
        img.paste(Image.new("RGB", (400, 400), color=(30, 30, 30)), (500, 250))

        result = try_deterministic_cover(_encode(img))
        assert result is not None
        out = _open(result).convert("RGB")

        # Mede a extensao do produto escuro nos eixos, pelo centro.
        row = [x for x in range(1200) if sum(out.getpixel((x, 600))) < 300]
        col = [y for y in range(1200) if sum(out.getpixel((600, y))) < 300]
        assert row and col
        largura = row[-1] - row[0]
        altura = col[-1] - col[0]
        assert abs(largura - altura) <= 20, f"produto distorcido: {largura}x{altura}"


class TestDeterministicCoverRejects:
    def test_gradient_background_is_rejected(self):
        """Cantos nao convergem -> fundo nao-uniforme, nem tenta."""
        img = Image.new("RGB", (1000, 1000))
        for y in range(1000):
            shade = int(255 * y / 999)
            for x in range(0, 1000, 4):
                img.paste((shade, shade, shade), (x, y, min(x + 4, 1000), y + 1))
        img.paste(Image.new("RGB", (300, 300), color=(200, 20, 20)), (350, 350))

        assert try_deterministic_cover(_encode(img)) is None

    def test_product_bleeding_off_two_borders_is_rejected(self):
        """Produto encostando em 2+ bordas foi cortado no enquadramento original.

        Barra vertical estreita: toca topo e base sem alcancar os cantos, entao
        a amostragem de fundo continua limpa e quem reprova e a regra de bordas.
        """
        img = Image.new("RGB", (1000, 1000), color=(210, 210, 210))
        img.paste(Image.new("RGB", (300, 1000), color=(30, 30, 30)), (350, 0))

        assert try_deterministic_cover(_encode(img)) is None

    def test_product_in_the_corner_is_rejected(self):
        """Bloco no canto contamina o patch de amostragem: cantos nao convergem."""
        img = Image.new("RGB", (1000, 1000), color=(210, 210, 210))
        img.paste(Image.new("RGB", (600, 600), color=(30, 30, 30)), (0, 0))

        assert try_deterministic_cover(_encode(img)) is None

    def test_tiny_product_in_the_corner_is_rejected(self):
        """Area abaixo do minimo -> mascara pegou ruido, nao um produto."""
        img = Image.new("RGB", (1000, 1000), color=(210, 210, 210))
        img.paste(Image.new("RGB", (40, 40), color=(20, 20, 20)), (60, 60))

        assert try_deterministic_cover(_encode(img)) is None

    def test_product_filling_almost_everything_is_rejected(self):
        """Area acima do maximo -> nao ha fundo real para recortar."""
        img = Image.new("RGB", (1000, 1000), color=(210, 210, 210))
        img.paste(Image.new("RGB", (980, 980), color=(30, 30, 30)), (10, 10))

        assert try_deterministic_cover(_encode(img)) is None

    def test_area_ceiling_is_the_binding_rule_not_corner_contamination(self):
        """Pina o teto de area em 0.80, medido: 77.9% aprova, 81.4% reprova.

        Ambos ficam abaixo do ponto em que o produto contamina os patches dos
        cantos (~85%), entao quem decide aqui e mesmo a regra de area.
        """
        def _centered(linear: float) -> bytes:
            img = Image.new("RGB", (1000, 1000), color=(210, 210, 210))
            side = int(1000 * linear)
            img.paste(
                Image.new("RGB", (side, side), color=(30, 30, 30)),
                ((1000 - side) // 2, (1000 - side) // 2),
            )
            return _encode(img)

        assert try_deterministic_cover(_centered(0.88)) is not None, "77.9% deve passar"
        assert try_deterministic_cover(_centered(0.90)) is None, "81.4% deve reprovar"

    def test_area_floor_is_the_binding_rule(self):
        """Pina o piso de area em 0.10, medido: 9.0% reprova, 11.0% aprova."""
        def _centered(linear: float) -> bytes:
            img = Image.new("RGB", (1000, 1000), color=(210, 210, 210))
            side = int(1000 * linear)
            img.paste(
                Image.new("RGB", (side, side), color=(30, 30, 30)),
                ((1000 - side) // 2, (1000 - side) // 2),
            )
            return _encode(img)

        assert try_deterministic_cover(_centered(0.30)) is None, "9.0% deve reprovar"
        assert try_deterministic_cover(_centered(0.33)) is not None, "11.0% deve passar"

    def test_blank_photo_without_product_is_rejected(self):
        img = Image.new("RGB", (1000, 1000), color=(210, 210, 210))

        assert try_deterministic_cover(_encode(img)) is None

    def test_corrupted_bytes_are_rejected(self):
        assert try_deterministic_cover(b"this-is-not-an-image") is None

    def test_empty_bytes_are_rejected(self):
        assert try_deterministic_cover(b"") is None

    def test_photo_on_busy_scene_is_rejected(self):
        """Cena com texturas diferentes em cada canto."""
        img = Image.new("RGB", (1000, 1000), color=(120, 180, 90))
        img.paste(Image.new("RGB", (500, 500), color=(30, 30, 200)), (0, 0))
        img.paste(Image.new("RGB", (500, 500), color=(220, 200, 40)), (500, 500))

        assert try_deterministic_cover(_encode(img)) is None
