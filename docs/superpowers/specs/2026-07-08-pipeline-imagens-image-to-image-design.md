# Pipeline de imagens image-to-image (fotos brutas do seller → tratamento por IA)

**Data:** 2026-07-08
**Status:** aprovado para planejamento (aguardando revisão final do usuário)

## Contexto e motivação

O pipeline de imagens hoje é 100% **texto-imagem**: `GeminiImageEngine` e
`OpenAIImageEngine` (`backend/app/services/image_engines/`) recebem só um
prompt textual e "imaginam" o produto do zero, sem nenhuma referência visual
real. Mesmo após a migração de motor de geração (Gemini → OpenAI, ver
`2026-07-01-migracao-motor-imagens-openai-design.md`), o resultado continua
insatisfatório — o problema não é (só) o motor, é a ausência de uma imagem
real do produto como base.

Este projeto introduz um fluxo **image-to-image**: o seller passa a fornecer,
como parte do contrato, 2 fotos brutas por SKU num bucket próprio (R2, S3 ou
compatível). O sistema usa essas fotos como entrada de um motor de edição de
imagem por IA, produzindo fotos tratadas (fundo, iluminação, enquadramento)
fiéis ao produto real, em vez de uma alucinação genérica.

**Fora de escopo deste projeto:**
- Modelagem de "kit" como feature de negócio (anúncio composto por múltiplos
  SKUs com preço/estoque agregado, UI de montagem de kit etc.). Este projeto
  constrói a lógica de geração de imagem já preparada para múltiplos SKUs por
  anúncio (necessária para quando um anúncio-kit existir de fato), mas o
  caminho N>1 fica **testado via fixture, inalcançável em produção** até o
  projeto de kit ser desenhado e implementado separadamente.
- Etapa de escrita do prompt de texto usado hoje pelo texto-imagem (fica
  igual, como fallback).
- Validação/onboarding assistido da configuração de bucket do seller (é só um
  formulário; nenhuma automação de setup).

**Risco/suposição a observar (não bloqueia este projeto):** a leitura de URLs
públicas do R2 já funciona hoje a partir da rede de desenvolvimento; a
**escrita** via API S3 (usada no passo best-effort de gravar de volta no
bucket do seller) foi bloqueada pelo ISP da máquina de dev no passado (ver
histórico do pipeline atual, que por isso faz upload direto pro ML,
contornando o R2). Nunca testamos se produção (Railway, ainda não deployada)
tem a mesma restrição. Por isso a escrita de volta é desenhada como
best-effort/não-bloqueante (ver RF7) — se a rede de produção também bloquear,
nada quebra, só a "cortesia" pro seller deixa de acontecer.

## Requisitos funcionais

### RF1 — Integração aditiva, opt-in por seller
O fluxo i2i é acionado **somente** se o seller tiver `SellerImageConfig`
configurado. Sem essa configuração, o pipeline se comporta **exatamente**
como hoje (texto-imagem, sem nenhuma mudança). Reversão trivial: remover a
config volta o seller ao comportamento atual.

### RF2 — Contrato de fotos brutas (leitura)
- 2 fotos fixas por SKU, extensão fixa `.jpg`: `{SKU}-1.jpg` e `{SKU}-2.jpg`.
- URL de leitura = `{raw_base_url}/{SKU}-{1|2}.jpg`, onde `raw_base_url` é
  configurado pelo seller (ex: `https://pub-xxx.r2.dev/sku`).
- Download via GET simples, **sem credenciais** (bucket de leitura pública).
- Sem validação proativa no onboarding — a checagem é sempre lazy, na hora de
  gerar (a URL genérica não tem como ser testada sem um SKU real).

### RF3 — Resolução de SKUs do anúncio
Nova função `resolve_listing_skus(listing) -> list[str]`. Hoje sempre
retorna uma lista de 1 elemento (`[listing.sku_external_id]`), mas toda a
lógica de geração abaixo já itera sobre essa lista — pronta para quando um
projeto de kit fizer essa função retornar múltiplos SKUs.

### RF4 — Geração por SKU (imagens individuais)
Para cada SKU resolvido, com as 2 fotos brutas baixadas:
```
edit(images=[raw1, raw2], prompt=<tratamento>, n=2,
     input_fidelity="high", quality="medium")
```
→ 2 imagens tratadas por SKU (`kind="individual"`, `source_sku=SKU`).
`input_fidelity="high"` preserva fidelidade ao produto real (parâmetro da
API OpenAI `/v1/images/edits`); `quality="medium"` mantém a mesma escolha já
usada pelo texto-imagem atual.

### RF5 — Composição de capa (quando o anúncio tem N>1 SKUs)
Uma chamada adicional, combinando as fotos brutas de **todos** os SKUs do
anúncio (até 16 imagens de entrada, limite da API):
```
edit(images=[sku1_raw1, sku1_raw2, sku2_raw1, sku2_raw2, ...],
     prompt=<compor cena única com os itens>, n=1,
     input_fidelity="high", quality="medium")
```
→ 1 imagem de capa (`kind="cover_composed"`, `source_sku=None`).

Se essa chamada falhar (erro de API), a capa é simplesmente pulada — a
primeira imagem individual aprovada assume a posição de capa por ordem
natural do array `pictures` (regra do ML já documentada no pipeline atual:
primeiro item = capa).

### RF6 — Fallback para texto-imagem (tudo ou nada por anúncio)
- Se **qualquer** SKU do anúncio não tiver as 2 fotos brutas disponíveis
  (HTTP 404 ou timeout), **todo o anúncio** cai no fluxo texto-imagem atual,
  sem mistura de foto real + foto gerada no mesmo anúncio.
- Contagem mínima de 4 fotos por anúncio (requisito de negócio) sai por
  construção: caso simples (1 SKU) = 2 fotos × 2 variações = 4; caso kit
  (N≥2) = 1 capa + (2×2×N) sempre > 4. Não há lógica extra necessária.

### RF7 — Escrita best-effort no bucket do seller (pós-publicação)
Depois que `publish_tasks.py` publica o anúncio e obtém `listing.mlb_id`
(a escrita **não** pode acontecer na geração de imagem, porque o MLB ainda
não existe nesse momento):
- Para cada `ListingImage` do anúncio, se o seller tiver credenciais de
  escrita configuradas, tenta `PUT` em
  `{write_bucket_name}/anuncios/{mlb_id}-{n}.jpg` (formato de saída fixado em
  `jpeg`) via client S3-compatível (`endpoint_url = write_endpoint_url`).
- Sucesso ou falha são apenas registrados (`ListingImage.url_r2`,
  `r2_write_status`) — **nunca bloqueia nem reverte a publicação**, que já
  aconteceu com sucesso no Mercado Livre antes desta etapa rodar.
- Sem credenciais de escrita configuradas → `r2_write_status =
  "skipped_no_config"`, sem tentativa.

### RF8 — Indisponibilidade do provedor de i2i vai para `failed`
Diferente do caso "SKU sem fotos" (fallback automático e silencioso para
texto-imagem), uma falha de infraestrutura do provedor de i2i (rate limit
persistente, 5xx repetido) **não** aciona fallback automático — o anúncio vai
para `failed`, exigindo retry manual. Justificativa: evita mascarar uma
degradação de serviço como se fosse um resultado normal; é consistente com o
padrão já existente no sistema (`pending_image_engine_confirmation`, que pausa
e pede confirmação em vez de trocar de motor silenciosamente).

### RF9 — Provedor único para i2i
Só OpenAI `gpt-image-1` via `/v1/images/edits` implementa edição de imagem
neste projeto (sem failover Gemini↔OpenAI para i2i, diferente do texto-imagem
atual). O texto-imagem existente (com seu failover Gemini↔OpenAI já
implementado) permanece como fallback quando não há fotos brutas.

## Modelo de dados

### Nova tabela `seller_image_configs` (1:1 com `sellers`)
```
id                          UUID (PK)
seller_id                   UUID (FK sellers, unique)
raw_base_url                TEXT NOT NULL         -- ex: https://pub-xxx.r2.dev/sku
write_bucket_name           VARCHAR(200) NULL
write_endpoint_url          TEXT NULL
write_access_key_id_enc     TEXT NULL             -- Fernet, mesmo padrão de tokens ML
write_secret_access_key_enc TEXT NULL             -- Fernet
created_at                  TIMESTAMPTZ NOT NULL
updated_at                  TIMESTAMPTZ NOT NULL
```
Escrita é considerada configurada somente se os 3 campos `write_*`
obrigatórios (bucket, endpoint, access key, secret) estiverem todos
preenchidos; caso contrário, tratado como não configurado (RF7).

### Extensão em `listing_images` (tabela existente)
```
kind             VARCHAR(20) NOT NULL DEFAULT 'individual'   -- 'individual' | 'cover_composed'
source_sku       VARCHAR(100) NULL                            -- null na capa composta
r2_write_status  VARCHAR(20) NULL                             -- 'success' | 'failed' | 'skipped_no_config'
```
`url_r2` (coluna já existente, hoje sem uso) passa a ser preenchida com a key
gravada no bucket do seller — junto com `ml_picture_id`, forma o "de-para"
completo, sem necessidade de tabela extra de log.

### Restrição no cache `ProductImage` (reuso entre anúncios do mesmo SKU)
Só deve armazenar imagens `kind="individual"`. Uma capa composta nunca é
reaproveitada — é específica da combinação exata de SKUs daquele anúncio.

### Migração
Nova tabela + novas colunas em `listing_images` + lembrar de registrar
`SellerImageConfig` em `app/models/__init__.py` (convenção já estabelecida —
omitir causa `NoReferencedTableError` na geração de migrations).

## Arquitetura e pontos de integração

- **Novo:** `app/services/image_engines/openai_edit_engine.py` — interface
  `edit(images: list[bytes], prompt: str, n: int) -> list[bytes]`, chamando
  `POST /v1/images/edits` (`model=gpt-image-1`, `input_fidelity=high`,
  `output_format=jpeg`, até 16 imagens de entrada por chamada).
- **Novo:** `app/services/seller_image_source_service.py` — dado
  `seller_id` + lista de SKUs, resolve e baixa as fotos brutas via
  `httpx.AsyncClient` (GET simples).
- **Alterado:** `_generate_images_async` (`image_tasks.py`) — antes do bloco
  atual de `get_engine_instance(...)`, tenta o caminho i2i se o seller tiver
  `SellerImageConfig`; cai no bloco existente (inalterado) caso contrário ou
  se faltar alguma foto bruta.
- **Alterado:** `publish_tasks.py` — após publicação bem-sucedida, dispara a
  escrita best-effort (RF7) usando `listing.mlb_id`.
- **Novo:** endpoint `PUT /api/v1/sellers/{id}/image-config` + card
  "Configuração de imagens" em `/settings`, seguindo o padrão multi-tenant
  existente (`X-Seller-ID`).

## Matriz de resiliência

| Cenário | Comportamento |
|---|---|
| Seller sem `SellerImageConfig` | Fluxo texto-imagem de hoje, sem nenhuma mudança |
| SKU sem as 2 fotos brutas (404) | Fallback pro texto-imagem pra todo o anúncio |
| Erro de rede/timeout baixando foto bruta | Tratado como "sem fotos" → mesmo fallback |
| Falha na geração individual (por SKU) | Retry do Celery já existente; se esgotar, `failed` (igual ao comportamento atual) |
| OpenAI Edits indisponível de forma persistente (429/5xx) | `failed` — exige retry manual, **sem** fallback automático (RF8) |
| Falha na composição da capa (N>1) | Pula a capa; 1ª imagem individual aprovada vira capa por ordem natural |
| Escrita best-effort falha | Log + `r2_write_status="failed"`; publicação já aconteceu, não é revertida |
| Seller sem credenciais de escrita | `r2_write_status="skipped_no_config"`, sem tentativa |

## Estratégia de testes

Seguindo o padrão já usado no projeto (`unittest.mock` +
`patch("httpx.AsyncClient")`, como em `test_image_engines_openai.py` e
`test_image_tasks.py`):

- `seller_image_source_service`: mock de GET — 200 (ambas fotos existem),
  404 (fallback), timeout.
- `openai_edit_engine.edit()`: mock de POST `/v1/images/edits` — sucesso,
  429, 5xx, timeout.
- Orquestração em `_generate_images_async`: regressão (seller sem config →
  idêntico ao atual), caminho simples N=1 (4 imagens individuais), fallback
  por foto faltando, falha de composição de capa (capa pulada, individuais
  salvas), provedor indisponível → `failed`.
- **Caminho N>1 (kit):** sem forma real de criar um anúncio kit hoje, o teste
  injeta diretamente um retorno fixo de `resolve_listing_skus` (ex:
  `["SKU0001", "SKU0002"]`) via mock — caminho testado, mas inalcançável em
  produção até o projeto de kit existir.
- Escrita best-effort em `publish_tasks.py`: sucesso, sem config (skip),
  falha (logada, não bloqueia).

## Plano de rollout

1. Deploy com a feature totalmente inerte (nenhum seller tem
   `SellerImageConfig`) — zero risco pro comportamento atual.
2. Configurar manualmente para 1 seller de teste (ex: DANIELSZURC), validar
   ponta a ponta com fotos brutas reais.
3. Habilitar por seller conforme cada um for capaz de disponibilizar as
   fotos brutas no contrato combinado.
4. Após validado em produção, discutir separadamente (fora deste projeto) se
   o i2i deve virar **obrigatório** para todos os sellers, conforme já
   sinalizado pelo usuário.
