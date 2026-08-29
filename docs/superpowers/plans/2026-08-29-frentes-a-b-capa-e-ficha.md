# Frentes A e B — variantes por IA sob demanda (branch `feature/descoberta-fotos-brutas`)

## Contexto

Piloto do esquema de 5 posições (ver
`docs/superpowers/specs/esquema-5-posicoes.md`). **Nada aqui muda o
comportamento automático do pipeline de produção** — tudo é sob demanda, via
endpoint explícito.

- **Frente A** — capa: variante ambientada por IA, gerada sob demanda a partir
  dos bytes salvos da capa determinística, e endpoint para promover qual das
  duas ocupa `sort_order=0`.
- **Frente B** — ficha técnica: variante por IA do `card_specs`, sob demanda,
  para A/B contra a versão Pillow. Mais instrumentação manual de custo de
  curadoria.

## Decisões já tomadas pelo Gabriel (não revisitar)

1. **Nomes de `kind`:** `cover_ai` e `specs_ai`. A coluna é `String(20)` e
   `card_specs_ai_candidate` (23 chars) estouraria.
2. **Origem da capa: NÃO re-derivar.** Novo campo `image_bytes`
   (`LargeBinary`, nullable) em `ListingImage`, populado na geração da capa
   determinística. Sem backfill: registro antigo sem bytes → o endpoint
   responde claramente "sem bytes salvos", nunca re-deriva nem adivinha.
   Escopo limitado à capa — não é o rework de write-back do R2.
3. **`sort_order` dos candidatos:** 90 (capa) e 91 (ficha), documentado.
4. Execução via SDD.

## Global Constraints

1. **Nada automático.** Nenhuma alteração em `_try_i2i_generation` além de
   popular `image_bytes` na capa. O pipeline continua gerando capa + até 4
   individuais + até 3 cards, sem variantes.
2. **Testes:** `docker compose exec -T backend python -m pytest tests -q` da
   raiz. **Baseline: 288 passed.** Nenhuma tarefa pode reduzir.
3. **`ListingImage.kind` é `String(20)`.** `cover_ai` (8) e `specs_ai` (8)
   cabem. Não criar valor que estoure.
4. Candidatos nascem `approved=False` e **nunca** entram no payload de upload
   do `publish_service` (que filtra por `approved`).
5. Comentários e docstrings em **PT-BR**, no tom do código existente (explicam
   o porquê). Commits Conventional Commits em PT-BR, **sem acentos no assunto**.
6. Migrations: `docker compose exec backend alembic revision --autogenerate -m "..."`
   e todo model novo precisa estar importado em `app/models/__init__.py`.
7. Endpoints em `/api/v1/`, JWT Bearer, erro como `{"detail": "..."}`.

---

## Task 1 — Persistir os bytes da capa + colunas novas

### Arquivos
- `backend/app/models/listing_image.py` (editar)
- `backend/alembic/versions/<nova>.py` (gerar)
- `backend/app/workers/tasks/image_tasks.py` (editar)
- `backend/tests/test_image_bytes_persistence.py` (criar)

### 1.1 — Duas colunas novas em `ListingImage`

```python
# Bytes exatos que subiram para o ML, guardados para que a variante de capa
# parta do MESMO arquivo publicado — nao de uma re-derivacao. Re-derivar seria
# identico enquanto a foto bruta nao mudasse, mas o seller PODE trocar a foto
# (aconteceu com 37-2.jpg), e ai a variante sairia de uma imagem diferente da
# que esta no anuncio, sem ninguem perceber.
image_bytes: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)

# Tempo que um humano levou conferindo a versao gerada por IA contra o dado
# real. Instrumentacao manual, amostra de 10-15 SKUs — nao e analytics.
review_seconds: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
```

Nullable e **sem backfill**: registros antigos ficam com `NULL`.

### 1.2 — Popular na capa determinística

Em `_try_i2i_generation`, no `db.add(ListingImage(...))` do bloco
`cover_deterministic` que já existe (por volta da linha 275), adicionar
`image_bytes=prepared`. **Só a capa.** Individuais e cards não recebem — o
escopo é a Frente A.

### 1.3 — Testes
1. A capa determinística é gravada com `image_bytes` preenchido e igual aos
   bytes que foram para o upload.
2. Individuais e cards continuam com `image_bytes` nulo (escopo é só a capa).
3. Migration aplica e reverte (`upgrade head` / `downgrade -1`) sem erro.

---

## Task 2 — Frente A: gerar a variante de capa

### Arquivos
- `backend/app/services/cover_variant_service.py` (criar)
- `backend/app/api/v1/endpoints/listings.py` (editar)
- `backend/tests/test_cover_variant.py` (criar)

### 2.1 — Serviço

```python
COVER_AI_KIND = "cover_ai"
COVER_AI_SORT_ORDER = 90  # fora da faixa 0..N da galeria


class CoverVariantError(RuntimeError):
    """Nao ha capa deterministica com bytes salvos para este anuncio."""


async def generate_cover_variant(db, listing, access_token: str) -> ListingImage:
    """Gera 1 variante ambientada a partir dos bytes SALVOS da capa."""
```

Comportamento:
- Busca o `ListingImage` do listing com `kind == "cover_deterministic"`.
- **Se não existir, ou se `image_bytes` for `None`: levanta `CoverVariantError`
  com mensagem explícita** ("capa determinística sem bytes salvos — anúncio
  gerado antes desta funcionalidade"). Nunca re-derivar.
- Chama `OpenAIEditEngine().edit(images=[bytes], prompt=_COVER_PROMPT, n=1)`.
- `_prepare_image_for_upload(..., requires_white_bg=<resolver pela categoria>)`
  — a variante pode ir para `sort_order=0`, então a regra de fundo branco vale.
- Upload via `MLPictureService`, e grava `ListingImage(kind="cover_ai",
  approved=False, sort_order=90, source_sku=..., image_bytes=<os bytes>)`.
- Log de uma linha no padrão do módulo: `cover_variant listing_id=... result=...`

### 2.2 — Prompt (usar VERBATIM)

```
Place this exact product photo into a subtle studio environment.

ALLOWED: replace the flat white background with a soft neutral gradient or a
subtle surface texture; add gentle directional lighting and a soft contact
shadow beneath the product; adjust framing margins only.

FORBIDDEN — the product itself must be pixel-faithful to the reference:
do not redraw, reshape, recolor, rotate or relight the product body; do not
add, remove or move any object; do not introduce props, hands, backgrounds
with objects, logos, badges, borders or decorative elements.

CRITICAL: do not alter, redraw, translate, correct or re-render ANY text
printed on the product or its packaging. Brand names, product names, volumes
and measurement units must be preserved exactly as they appear, character for
character. Never change a number or a unit. If any text is unreadable, keep it
unreadable rather than inventing plausible text.

The result must be recognisable as the same photograph of the same physical
unit, only better lit and better staged.
```

### 2.3 — Endpoint

`POST /api/v1/listings/{listing_id}/images/cover-ai-variant` — sem corpo.
Devolve o `ImageOut` do candidato criado. `CoverVariantError` → **409** com
`{"detail": "..."}`.

### 2.4 — Testes
1. Gera a variante a partir dos bytes salvos (o engine recebe **exatamente**
   `image_bytes` da capa, não outra coisa).
2. Sem capa determinística → `CoverVariantError`.
3. Capa existe mas `image_bytes` é `None` → `CoverVariantError`, e o engine
   **não é chamado** (não gasta IA à toa).
4. Candidato nasce `approved=False`, `sort_order=90`, `kind="cover_ai"`.
5. Reprovado no QA → grava linha `validation_failed`, não sobe.
6. O prompt enviado contém a cláusula `CRITICAL` e `pixel-faithful`.

---

## Task 3 — Frente A: promover a capa

### Arquivos
- `backend/app/services/cover_variant_service.py` (editar)
- `backend/app/api/v1/endpoints/listings.py` (editar)
- `backend/tests/test_cover_promote.py` (criar)

### 3.1 — Serviço

```python
async def promote_cover(db, listing, image_id: UUID) -> None:
    """Troca qual imagem ocupa sort_order=0 na galeria."""
```

Comportamento:
- A imagem alvo tem que ser do listing e ter `kind` em
  `{"cover_deterministic", "cover_ai"}`; senão **422**.
- A imagem alvo passa a `approved=True, sort_order=0`.
- A capa que estava em `sort_order=0` vai para o lugar de candidata:
  `approved=False`, `sort_order=90`.
- As demais imagens **não são tocadas**.
- Idempotente: promover quem já está em 0 não quebra nem duplica.

### 3.2 — Endpoint

`POST /api/v1/listings/{listing_id}/images/{image_id}/promote-cover` — sem
corpo. Devolve `ListingSummary`.

### 3.3 — Testes
1. Promover a variante: ela vai para 0/aprovada; a determinística vai para
   90/não aprovada.
2. Promover a determinística de volta: reordena no sentido inverso.
3. A não escolhida **nunca aparece no payload de upload** — montar a lista como
   o `publish_service` monta (filtrando `approved`) e conferir que só a
   promovida está lá.
4. Promover imagem de outro `kind` (ex.: `individual`) → 422.
5. Promover imagem de outro listing → 404.
6. Idempotência: promover duas vezes seguidas mantém o estado.

---

## Task 4 — Frente B: ficha técnica por IA + `review_seconds` + documento

### Arquivos
- `backend/app/services/specs_variant_service.py` (criar)
- `backend/app/api/v1/endpoints/listings.py` (editar)
- `backend/app/schemas/listing.py` (editar)
- `backend/app/services/listing_service.py` (editar)
- `backend/tests/test_specs_variant.py` (criar)
- `docs/superpowers/specs/esquema-5-posicoes.md` (editar)

### 4.1 — Serviço

```python
SPECS_AI_KIND = "specs_ai"
SPECS_AI_SORT_ORDER = 91


async def generate_specs_variant(db, listing, access_token: str) -> ListingImage:
```

- Reusa o mecanismo de copy que já existe: `generate_card_copy(listing,
  attributes)` e pega o ângulo `card_specs`. **Não inventar copy nova** — os
  dados vêm dos atributos reais, como já acontece.
- Se o ângulo `card_specs` não vier (o sanitizador pode descartar), levanta
  erro claro → **409**. Não tentar 3 vezes aqui; o chamador repete se quiser.
- Renderiza **por IA**, não por Pillow: `OpenAIEditEngine`, partindo dos bytes
  salvos da capa (mesma fonte da Frente A), com prompt que compõe um card de
  ficha técnica com o título e os bullets da copy.
- Grava `kind="specs_ai"`, `approved=False`, `sort_order=91`. **Não toca** no
  `card_specs` (Pillow) existente.

### 4.2 — `review_seconds`

- `ImageApproveRequest` ganha `review_seconds: Optional[int] = None`.
- `ListingService.approve_images` grava o valor nas imagens aprovadas naquela
  chamada. Campo opcional: ausente → fica `NULL`, comportamento atual.
- Não construir dashboard, agregação nem endpoint de leitura.

### 4.3 — Documento

Atualizar a tabela de estado em `esquema-5-posicoes.md`: posição 1 (variante) e
posição 5 (variante) como **disponíveis sob demanda**, com os endpoints;
posições 2 e 3 seguem no pipeline de produção, sem mudança.

### 4.4 — Testes
1. Gera o candidato `specs_ai` com `approved=False`, `sort_order=91`.
2. O `card_specs` (Pillow) existente permanece intacto e aprovado.
3. Copy sem o ângulo `card_specs` → erro claro, sem gravar imagem.
4. `review_seconds` é gravado nas imagens aprovadas quando enviado.
5. `review_seconds` ausente → `NULL`, e a aprovação funciona como hoje.

---

## Definition of Done

- Suíte ≥ 288 passed, zero falhas.
- Nenhuma mudança de comportamento automático: `_try_i2i_generation` continua
  produzindo o mesmo conjunto de imagens, com a única diferença de gravar
  `image_bytes` na capa.
- Candidatos (`cover_ai`, `specs_ai`) nunca entram no payload de publicação.
- **Sem merge em `master`** — a branch fica para avaliação conjunta do piloto.
