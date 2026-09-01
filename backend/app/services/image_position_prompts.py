"""Prompts das posicoes 2, 3 e 4 do esquema de 5 posicoes.

Modulo separado de `image_position_profiles` de proposito: aquele e uma
TABELA de dados (formato + legendas por categoria), este e a montagem de
texto. Separar deixa o perfil legivel para quem so quer cadastrar uma
vertical nova, sem atravessar centenas de linhas de prompt.

A estrutura ALLOWED / FORBIDDEN / CRITICAL e a mesma ja validada na capa
(SKU 37) e na ficha tecnica (SKU 38). A clausula CRITICAL e IDENTICA nas
tres posicoes, palavra por palavra: e a licao da Fase 5c, quando o motor
reescreveu "100ml" como "160ml" e "wepink" como "weoink" num anuncio real.
Ela nao pode variar por posicao — o risco de o modelo reescrever o rotulo
nao depende do que se esta compondo ao redor dele.

Canvas quadrado (1200x1200) porque o perfil manda, nao porque esta cravado
aqui: `canvas` vem do `PositionProfile`. Ver o comentario de
`CANVAS_QUADRADO` para por que vertical seria destrutivo neste pipeline.
"""

# Repetida verbatim nas tres posicoes. Ver o docstring do modulo.
_CRITICAL = (
    "CRITICAL: do not alter, translate, or re-render any text printed on the\n"
    "product or its packaging. Preserve every brand name, product name,\n"
    "number and unit exactly as it appears, character for character."
)


def build_presentation_prompt(
    nome_produto: str, marca: str | None, volume: str | None
) -> str:
    """Posicao 2 — Apresentacao.

    A hierarquia do texto espelha o ROTULO FISICO do produto: nome do produto
    em destaque, marca menor abaixo. Nao se inventa hierarquia nova quando a
    embalagem real ja resolveu isso — no frasco do SKU 38, "wepink" e pequeno
    e "FATAL BLACK" e grande.

    `marca` e `volume` sao opcionais: linha ausente e OMITIDA do prompt, em
    vez de virar string vazia. Pedir ao motor para renderizar uma linha vazia
    convida a inventar conteudo para preenche-la.
    """
    linhas = [f'- Headline: "{nome_produto}"']
    if marca:
        linhas.append(f'- Line 2: "{marca}"')
    if volume:
        linhas.append(f'- Line 3: "{volume}"')
    bloco = "\n".join(linhas)

    return (
        "Compose a premium square product presentation card (1200x1200) using\n"
        "the reference photos of this exact product as the visual source.\n\n"
        "ALLOWED: recompose the product on a clean, softly lit backdrop; frame\n"
        "the product large and dominant in the upper 55-65% of the image; add a\n"
        "clean lower panel (solid color or very subtle texture) for the text\n"
        "below.\n\n"
        "FORBIDDEN: do not redraw, reshape, recolor, or re-proportion the\n"
        "product; do not invent props, hands, or unrelated background objects.\n\n"
        f"{_CRITICAL}\n\n"
        "Text to render in the lower panel — reproduce EXACTLY as given, do not\n"
        "paraphrase or add any extra line:\n"
        f"{bloco}\n\n"
        "Typography: bold, high-contrast, clearly legible sans-serif. No other\n"
        "text, logo, badge or border beyond what is specified above."
    )


def build_benefits_prompt(headline: str, bullets: list[str]) -> str:
    """Posicao 3 — Caracteristicas/beneficios.

    Aceita 2 OU 3 bullets. `generate_card_copy` garante `MIN_BULLETS`=2 e no
    maximo 3, entao exigir exatamente tres no prompt faria o motor inventar a
    terceira linha quando a copy viesse com duas — que e precisamente o tipo
    de invencao que a clausula abaixo proibe.
    """
    bloco = "\n".join(f'- Bullet {i}: "{b}"' for i, b in enumerate(bullets, start=1))

    return (
        "Compose a premium square benefits/characteristics card (1200x1200)\n"
        "using the reference photo of this exact product as the visual source.\n\n"
        "ALLOWED: place the product against an elegant color block sampled from\n"
        "the product's own dominant color, with soft paper-like texture and\n"
        "radial lighting — not flat white. Reserve a clear panel for a headline\n"
        "and a short bulleted list.\n\n"
        "FORBIDDEN: do not redraw, reshape, recolor, or re-proportion the\n"
        "product itself.\n\n"
        f"{_CRITICAL}\n\n"
        "Text to render — reproduce EXACTLY as given, one bullet per line, each\n"
        "with a small line-icon matching its theme. Do not add, remove or reword\n"
        "any bullet:\n"
        f'- Headline: "{headline}"\n'
        f"{bloco}\n\n"
        "Typography: geometric sans-serif, clear hierarchy, headline dominant."
    )


def build_detail_prompt(legenda: str) -> str:
    """Posicao 4 — Detalhes.

    A proibicao de seta/callout nao e estetica: uma seta apontando para uma
    parte especifica vira AFIRMACAO sobre aquela parte, e a legenda aqui e
    generica ("Acabamento refinado"), escolhida de uma lista fixa do perfil.
    Legenda generica com seta especifica diria ao comprador algo que o
    catalogo nao sustenta.
    """
    return (
        "Compose a premium square detail/texture card (1200x1200) using the\n"
        "reference photo of this exact product as the visual source. Frame this\n"
        "as a close-up — tighter, macro-style framing of the product's texture,\n"
        "finish, cap or closure — while keeping the object fully recognisable.\n\n"
        "ALLOWED: soft studio lighting, shallow depth of field, subtle\n"
        "background blur or soft color block. Reserve a small lower area for one\n"
        "short caption.\n\n"
        "FORBIDDEN: do not redraw, reshape or recolor the product; do not add\n"
        "arrows, pointer lines, or any annotation aimed at specific parts —\n"
        "the caption is generic, never an annotated callout.\n\n"
        f"{_CRITICAL}\n\n"
        "Text to render — reproduce EXACTLY as given, do not invent a different\n"
        "caption:\n"
        f'- Caption: "{legenda}"\n\n'
        "Typography: clean sans-serif, single short line."
    )
