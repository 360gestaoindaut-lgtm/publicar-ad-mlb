# Esquema de 5 posições (piloto, branch `feature/descoberta-fotos-brutas`)

Estrutura-alvo, em discussão, para anúncio de produto único (não kit):

1. **Capa** — determinística (Pillow, já em produção) por padrão. Variante
   ambientada por IA disponível sob demanda (Frente A desta branch), nunca
   automática. Usuário escolhe qual promove.
2. **Apresentação** — foto de produto tratada via i2i (equivalente ao que hoje
   chamamos de "individual"), a partir da 1ª ou 2ª foto bruta.
3. **Características/benefícios** — card com IA, composição rica (evolução do
   piloto já aprovado), copy vem da DESCRIÇÃO real do produto.
4. **Detalhes** — close-up/textura do produto, SEM callouts/setas (decisão
   tomada: apontamento preciso via IA não é confiável o suficiente). Fonte: se
   houver mais de 2 fotos brutas disponíveis (ver Passo 0.1 desta branch), usa
   uma foto extra (ex: a 3ª) como fonte, com tratamento i2i similar à posição
   2. Se só houver as 2 mínimas, usa fallback genérico a partir do que existe —
   não inventa detalhe que a foto não mostra.
5. **Ficha técnica** — dado permanece determinístico (Pillow, já em produção:
   `card_specs`). Variante gerada por IA disponível sob demanda para teste A/B
   de custo de curadoria (Frente B desta branch) — nunca substitui a versão
   Pillow automaticamente.

**Callouts/setas:** não existem no código, é conceito descartado nesta mesma
discussão — não implementar.

Este documento descreve uma estrutura **em avaliação**, não o comportamento de
produção atual. O pipeline em produção (`_try_i2i_generation`, capa
determinística + até 4 individuais + até 3 cards) continua sendo a fonte de
verdade até decisão explícita de substituição.

---

## Estado da implementação (atualizado conforme a branch avança)

| Item | Estado |
|---|---|
| Passo 0.1 — descoberta de fotos além do mínimo | ✅ `fetch_raw_photos` sonda até `RAW_PHOTOS_MAX` (10); as 2 primeiras seguem obrigatórias |
| Passo 0.2 — fonte da posição 4 | ✅ `pick_detail_source()`, função pura, sem efeito colateral |
| Posições 1, 2, 3, 5 | 🔲 não implementadas — o pipeline de produção continua como está |

### Isolamento em relação à produção

`fetch_raw_photos` é **compartilhada** entre o piloto e o pipeline de produção.
Como ela passou a devolver mais fotos, o loop de individuais em
`_try_i2i_generation` passaria a consumir todas — um seller com 5 fotos geraria
**10 individuais em vez de 4**, 2,5× o custo de IA, e um total de 14 imagens
contra o teto de **12** do Mercado Livre.

Por isso aquele loop tem um corte explícito em `[:RAW_PHOTOS_MIN]`. O piloto
enxerga as fotos extras; a produção não. **Se alguém remover esse corte achando
que é redundante, reintroduz a explosão de custo e o estouro do teto.**
