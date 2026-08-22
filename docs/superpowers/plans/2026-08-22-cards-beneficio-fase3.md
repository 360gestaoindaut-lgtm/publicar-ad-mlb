# Fase 3 — Motor de cards de benefício (Trilha 2)

## Contexto

Texto, infográfico e especificação são permitidos nas imagens 2 em diante do
anúncio do Mercado Livre (não na capa). Objetivo: gerar 3 imagens adicionais
por anúncio — "benefícios", "modo de uso" e "especificações técnicas" — sem
chamar nenhum motor de IA de imagem. Cada card reaproveita uma foto de
produto já gerada pelo pipeline (Fases 0-2) e sobrepõe texto gerado por LLM,
usando Pillow.

Ordem final das imagens do anúncio: capa, individuais (já existentes), depois
os 3 cards nesta ordem: benefícios → modo de uso → especificações técnicas.

## Investigação já concluída (não repetir)

- **Fonte:** `Inter-Regular.ttf` (peso 400) e `Inter-Bold.ttf` (peso 700), SIL
  OFL, já baixadas em `backend/app/assets/fonts/` junto com `OFL.txt`. Não
  havia nenhuma TTF no repo nem na imagem `python:3.12-slim`. Já validado no
  container: `ImageFont.truetype()` carrega as duas, `getname()` devolve
  `('Inter','Regular')` / `('Inter','Bold')`, acentos PT-BR e travessão sem
  glifo ausente.
- **Pillow 11.1.0.** `font.getlength()` e `draw.textbbox()` disponíveis;
  `font.getsize()` NÃO existe mais (removido no Pillow 10) — não usar.
- **Provider de IA:** `get_ai_provider()` em `app/services/ai/service.py`
  devolve um `AIProvider` (ABC em `ai/base.py`) com 3 métodos abstratos.
  `GeminiProvider` e `ClaudeProvider` compartilham `_call(prompt, max_tokens,
  temperature) -> str` com assinatura idêntica. Prompts centralizados em
  `ai/prompts.py` como funções `build_*_prompt()`.
- **Foto-base dos cards:** em `_try_i2i_generation`
  (`app/workers/tasks/image_tasks.py`), no loop de imagens individuais, a
  variável `prepared` — retorno de `_prepare_image_for_upload()` — são os
  bytes JPEG 1200x1200 já normalizados e já aprovados pelo `validate_image()`,
  disponíveis em memória imediatamente antes de `ml_pic.upload(...)`.
- **Ordem do pipeline:** `generate_images` roda ANTES de
  `generate_description`. Não existe descrição gerada nesse momento. As fontes
  de texto disponíveis são `listing.selected_title`, `listing.sku_description`
  (descrição do ERP), `listing.sku_brand`, `listing.sku_model` e os
  `listing_attributes` (preenchidos na etapa `predicting_category`).
- **Rede bloqueada nos testes:** `backend/tests/conftest.py` tem fixture
  autouse que levanta `NetworkAccessAttempted` em qualquer egresso HTTP real.

## Global Constraints

1. **Nenhuma dependência nova.** Pillow e httpx já estão em
   `requirements.txt`. Não adicionar nada.
2. **Rodar os testes assim, da raiz do repo:**
   `docker compose exec -T backend python -m pytest tests -q`
   (o bind mount `./backend:/app` já reflete o código; não precisa rebuild).
3. **Baseline da suíte: 171 passed.** Nenhuma tarefa pode reduzir esse número.
4. **`ListingImage.kind` é `String(20)`.** Os kinds novos —
   `"card_benefits"` (13), `"card_usage"` (10), `"card_specs"` (10) — cabem.
   Nenhuma migration é necessária. Não criar migration.
5. **Resiliência acima de tudo:** falha em copy ou render NUNCA pode derrubar
   o anúncio nem as imagens já salvas. Loga e segue sem os cards.
6. **Logging:** mesmo padrão da Fase 2 — `logger.info` com pares
   `chave=valor` numa linha só, via `logger` de módulo
   (`logging.getLogger(__name__)`).
7. **Comentários e docstrings em PT-BR**, no mesmo tom do código existente
   (explicam o porquê, não o quê). Commits em Conventional Commits, mensagem
   em PT-BR **sem acentos no assunto** (padrão do repo).
8. **Nada de emoji ou glifo unicode exótico** no card renderizado — marcadores
   são desenhados com `ImageDraw`.
9. **Kits (`len(skus) > 1`) estão fora de escopo.** Não gerar cards nesse caso.
10. **Não usar as cores de marca da 360 Gestão.** Paleta neutra: essas imagens
    vão para anúncios de sellers diversos.

---

## Task 1 — Copy dos cards via LLM

### Arquivos
- `backend/app/services/ai/base.py` (editar)
- `backend/app/services/ai/prompts.py` (editar)
- `backend/app/services/ai/gemini.py` (editar)
- `backend/app/services/ai/claude.py` (editar)
- `backend/app/services/image_card_copy_service.py` (criar)
- `backend/tests/test_image_card_copy_service.py` (criar)

### 1.1 — `AIProvider.generate_card_copy`

Adicionar como 4º método abstrato em `ai/base.py`:

```python
@abstractmethod
async def generate_card_copy(self, source: dict) -> dict:
    """Copy dos 3 cards de imagem. Recebe o dicionario montado por
    `image_card_copy_service._build_source()` e devolve
    {"benefits": {...}, "usage": {...}, "specs": {...}}, cada valor
    {"title": str, "bullets": list[str]}."""
```

Implementar nos DOIS providers, exatamente no mesmo formato que
`generate_titles` já usa:

```python
async def generate_card_copy(self, source: dict) -> dict:
    prompt = build_card_copy_prompt(source)
    text = await self._call(prompt, max_tokens=1200, temperature=0.4)
    parsed = json.loads(_extract_json(text))
    if not isinstance(parsed, dict):
        raise RuntimeError(f"...nao retornou um JSON de card valido: {text[:300]!r}")
    return parsed
```

`claude.py` importa `_extract_json` de `app.services.ai.gemini` — esse
precedente de reuso cruzado já existe no `batch_mode` de
`ClaudeProvider.generate_titles`, siga-o em vez de duplicar a função.

### 1.2 — `build_card_copy_prompt(source: dict) -> str` em `prompts.py`

O prompt deve, obrigatoriamente:
- Pedir saída **só JSON**, com as 3 chaves `benefits`, `usage`, `specs`.
- Fixar os limites: `title` até **40 caracteres**, **2 a 3** bullets, cada
  bullet até **50 caracteres**.
- Escrever em **português do Brasil**.
- **Proibir explicitamente inventar especificação técnica** (medida,
  composição, voltagem, capacidade, material) que não esteja no texto de
  origem. Essa é a regra mais importante do prompt.
- Instruir: se não houver dado suficiente para um ângulo (ex.: SKU sem
  instrução de uso clara), gerar algo **genérico e seguro** em vez de
  inventar detalhe.
- Nada de preço, promessa de prazo de entrega, superlativo não comprovável
  ("o melhor do mercado") ou menção a concorrente.

### 1.3 — `image_card_copy_service.py` (módulo novo)

Decisão já tomada: módulo próprio, **não** dentro de
`image_deterministic_service.py` — aquele módulo é sobre recorte de pixels, e
copy de texto não tem relação com ele.

```python
CARD_KINDS = ("card_benefits", "card_usage", "card_specs")  # ordem de sort_order

MAX_TITLE_CHARS = 40
MAX_BULLET_CHARS = 50
MIN_BULLETS = 2
MAX_BULLETS = 3


@dataclass(frozen=True)
class CardCopy:
    kind: str          # um de CARD_KINDS
    title: str
    bullets: list[str]


async def generate_card_copy(listing, attributes: list | None = None) -> list[CardCopy]:
    """Copy dos 3 cards, na ordem de CARD_KINDS. Resiliente por angulo:
    devolve so os angulos que vieram utilizaveis, possivelmente lista vazia.
    Nunca levanta excecao."""
```

Regras de saneamento (o serviço NÃO confia no LLM):
- Mapear as chaves do LLM para os kinds:
  `benefits`→`card_benefits`, `usage`→`card_usage`, `specs`→`card_specs`.
- `title`: `str`, `.strip()`; se vazio → ângulo descartado. Se passar de
  `MAX_TITLE_CHARS`, truncar em limite de palavra quando der, senão cortar
  seco. Nunca deixar reticências órfãs no meio de palavra.
- `bullets`: descartar não-strings e vazios; truncar cada um em
  `MAX_BULLET_CHARS` pela mesma regra; manter no máximo `MAX_BULLETS`. Se
  sobrar menos que `MIN_BULLETS` → ângulo descartado.
- Ângulo descartado é logado (`logger.info`, `card_copy ... result=dropped
  kind=... reason=...`) e não entra na lista.
- Qualquer exceção no caminho (provider, HTTP, JSON, chave faltando) → log
  `logger.warning` e retorno de **lista vazia**. Nunca propagar.

`_build_source(listing, attributes) -> dict` monta o dicionário de origem a
partir de `selected_title`, `sku_description`, `sku_brand`, `sku_model` e dos
atributos (`attribute_name` → `value_name`, só os que têm `value_name`).
Não incluir preço nem estoque.

### 1.4 — Testes (`test_image_card_copy_service.py`)

Provider sempre mockado — `patch("app.services.ai.service.get_ai_provider")`
ou o ponto de import usado pelo serviço; a rede está bloqueada pelo conftest,
então um mock faltando aparece como `NetworkAccessAttempted`.

Casos mínimos:
1. Resposta bem formada → 3 `CardCopy` na ordem exata de `CARD_KINDS`.
2. Título com 60 caracteres → truncado para ≤ 40.
3. Bullet com 80 caracteres → truncado para ≤ 50.
4. Ângulo com só 1 bullet → descartado; os outros 2 sobrevivem.
5. Ângulo com título vazio → descartado; os outros sobrevivem.
6. Provider levanta exceção → `[]`, sem propagar.
7. JSON sem uma das 3 chaves → só os ângulos presentes voltam.
8. `_build_source` inclui título/descrição/marca/modelo/atributos e **não**
   inclui preço.

---

## Task 2 — Renderizador de card (Pillow)

### Arquivos
- `backend/app/services/image_benefit_card_service.py` (criar)
- `backend/tests/test_image_benefit_card_service.py` (criar)

### 2.1 — Assinatura

```python
class CardRenderError(RuntimeError):
    """Falha ao renderizar o card (foto-base ilegivel, texto vazio)."""


def render_benefit_card(product_photo_bytes: bytes, title: str, bullets: list[str]) -> bytes:
    """Card 1200x1200 JPEG: foto do produto em cima, titulo e bullets embaixo.

    Levanta CardRenderError se a foto-base nao abrir como imagem ou se nao
    houver texto nenhum para renderizar."""
```

### 2.2 — Layout (fixo, não improvisar)

Canvas **1200x1200**, fundo branco puro `#FFFFFF`, saída **JPEG qualidade 92**
(mesma qualidade de `image_postprocess_service`).

- **Faixa da foto:** de `y=0` até `y=640`. A foto entra em **contain-fit**
  (cabe inteira, proporção preservada, centralizada horizontal e
  verticalmente na faixa). **Nunca `resize` direto para a caixa** — isso
  distorce. Foto retangular deita na faixa com margem branca nas laterais;
  foto quadrada vira 640x640 centralizada. Nunca fazer upscale além do
  tamanho original da foto.
- **Régua divisória:** linha de 1px em `#E5E7EB` na largura útil
  (x de 90 a 1110), em `y=668`.
- **Bloco de texto:** ocupa de `y=700` até `y=1110`. O bloco inteiro
  (título + bullets, já com as quebras calculadas) é **centralizado
  verticalmente** nessa faixa. É isso que impede o "buraco" quando só há 2
  bullets — não deixar o texto ancorado no topo.
- **Título:** Inter Bold **58px**, cor `#1E293B`, alinhado à esquerda em
  `x=90`, largura útil `1020px`, quebra automática, no máximo **2 linhas**
  (a 2ª linha excedente é truncada com "…"). Entrelinha 1.2.
- **Bullets:** Inter Regular **38px**, cor `#475569`, entrelinha 1.35.
  - Marcador: círculo preenchido de **raio 7px** desenhado com
    `ImageDraw.ellipse`, cor de destaque `#0F766E`, centro em `x=104` e
    verticalmente centrado na **primeira linha** do bullet.
  - Texto do bullet em `x=136`, largura útil `1200-136-90 = 974px`, quebra
    automática, sem limite de linhas.
  - Espaço entre bullets: **28px**.
- **Gap entre título e primeiro bullet:** 40px.

### 2.3 — Quebra de linha

Usar `font.getlength(texto)` para medir (NÃO `font.getsize`, removido no
Pillow 10). Quebra por palavra; palavra isolada mais larga que a caixa é
cortada por caractere. Altura de linha via `draw.textbbox()` ou métrica da
fonte — não chutar valor fixo.

### 2.4 — Carregamento das fontes

Resolver o caminho relativo ao pacote, nunca hardcode absoluto:

```python
_FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
```

(`__file__` é `app/services/…`, então `parents[1]` é `app/`.) Cachear com
`functools.lru_cache` por `(arquivo, tamanho)` — o worker renderiza 3 cards
por anúncio e recarregar TTF a cada chamada é desperdício.

### 2.5 — Testes (`test_image_benefit_card_service.py`)

Fixture: gerar a foto-base em memória com Pillow (`Image.new` + salvar em
`BytesIO`), sem arquivo no disco.

Casos mínimos:
1. Título e bullets curtos (cabem sem quebra) → saída abre como imagem,
   é **1200x1200**, formato **JPEG**.
2. Bullet longo (~120 caracteres) → renderiza sem estourar a caixa; a
   asserção deve verificar quebra real (ex.: contar linhas via a função
   interna de wrap, ou checar que a altura do bloco cresceu em relação ao
   caso curto), não só "não levantou exceção".
3. Só 2 bullets → sem buraco: verificar que o bloco de texto está
   verticalmente centralizado (ex.: distância do topo do bloco ao `y=700`
   é próxima da distância da base ao `y=1110`, com tolerância).
4. Foto retangular (ex.: 1600x900) → sem distorção: verificar que a razão
   de aspecto da região colada bate com a da origem.
5. Foto quadrada (1200x1200) → ocupa a faixa centralizada.
6. Bytes que não são imagem → `CardRenderError`.
7. Título e bullets vazios → `CardRenderError`.
8. Acentos PT-BR ("Ação à prova d'água") renderizam sem exceção.

---

## Task 3 — Integração no worker + ajuste dos testes existentes

### Arquivos
- `backend/app/workers/tasks/image_tasks.py` (editar)
- `backend/tests/test_image_tasks_i2i.py` (editar)
- `backend/tests/test_image_tasks.py` (editar)

### 3.1 — Helper `_append_benefit_cards`

Extrair o passo inteiro num helper próprio em `image_tasks.py` — isso é o que
permite que os testes existentes o neutralizem com um patch de escopo:

```python
async def _append_benefit_cards(
    db, listing, access_token: str, base_photo: bytes, source_sku: str, start_sort_order: int
) -> int:
    """Gera os 3 cards de texto a partir da 1a foto individual bem-sucedida.

    Devolve quantos cards subiram. Nunca levanta: qualquer falha vira log e
    zero cards — o anuncio nao pode cair por causa de um card."""
```

Comportamento:
- Carrega os `ListingAttribute` do listing com **query separada** (nunca
  acessar `listing.attributes` lazy dentro do worker — causa
  `MissingGreenlet`, ver CLAUDE.md).
- Chama `generate_card_copy(listing, attributes)`.
- Para cada `CardCopy`, na ordem: `render_benefit_card(base_photo, ...)` →
  `_prepare_image_for_upload(card_bytes, requires_white_bg=False)` → upload →
  `db.add(ListingImage(...))` com o `kind` do `CardCopy`, `source_sku`
  preenchido e `sort_order = start_sort_order + n`.
- **Fundo branco não é exigido em card nenhum** — `requires_white_bg=False`
  sempre. Cards nunca são capa.
- Falha em UM card (render ou upload) → `logger.warning`, segue para o
  próximo. Falha global (copy vazia, exceção inesperada) → `logger.warning`
  e retorna 0.
- Log de resultado no padrão da Fase 2, uma linha:
  `logger.info("benefit_cards listing_id=%s sku=%s requested=%s saved=%s", ...)`

### 3.2 — Chamada em `_try_i2i_generation`

Depois do loop de imagens individuais, **antes** do `return saved`:

```python
if len(skus) == 1 and first_individual_bytes is not None:
    saved += await _append_benefit_cards(
        db, listing, access_token,
        base_photo=first_individual_bytes,
        source_sku=skus[0],
        start_sort_order=saved,
    )
```

`first_individual_bytes` é capturado dentro do loop de individuais: a
**primeira** ocorrência de `prepared` que passou no QA e subiu com sucesso.
Se nenhuma imagem individual foi salva, `first_individual_bytes` fica `None`
e nenhum card é gerado (requisito explícito).

### 3.3 — Ajuste dos 15 testes existentes

15 testes chamam `_try_i2i_generation` e afirmam contagem exata de imagens
(11 em `test_image_tasks_i2i.py`, 4 em `test_image_tasks.py`). Adicionar a
cada um, na cadeia de `with patch(...)` que já existe:

```python
patch(
    "app.workers.tasks.image_tasks._append_benefit_cards",
    new_callable=AsyncMock,
    return_value=0,
),
```

Isso declara explicitamente que cards estão fora do escopo daquele teste.
Não alterar nenhuma asserção existente — se alguma quebrar, é regressão real
e deve ser reportada, não "consertada" mudando o número esperado.

### 3.4 — Testes de integração novos (em `test_image_tasks_i2i.py`)

Classe nova `TestBenefitCardsIntegration`, com `_append_benefit_cards` NÃO
mockado (mockar `generate_card_copy` e `render_benefit_card`):

1. **3 cards depois das individuais, na ordem certa:** os `ListingImage`
   adicionados terminam com `kind` `card_benefits`, `card_usage`,
   `card_specs`, com `sort_order` contíguo começando depois da última imagem
   individual, e `source_sku` preenchido.
2. **Falha em 1 card não derruba os outros nem o que já existe:**
   `render_benefit_card` levanta na 2ª chamada → sobram 2 cards, as imagens
   individuais continuam salvas, `saved` reflete o total correto.
3. **Nenhum card se nenhuma individual foi salva:** todas as individuais
   reprovadas no QA → `_append_benefit_cards` não é chamado (ou retorna 0 sem
   chamar o LLM), nenhum `ListingImage` de kind `card_*`.
4. **Kit (2 SKUs) não gera card nenhum.**
5. **Copy vazia → zero cards, anúncio intacto** (`saved` continua o das
   imagens de imagem).

---

## Definition of Done

- `docker compose exec -T backend python -m pytest tests -q` ≥ 171 passed,
  zero failures.
- Nenhuma dependência nova; nenhuma migration nova.
- Cards só para 1 SKU, só depois de pelo menos 1 imagem individual salva.
- Qualquer falha de copy/render/upload de card deixa o anúncio publicável.
