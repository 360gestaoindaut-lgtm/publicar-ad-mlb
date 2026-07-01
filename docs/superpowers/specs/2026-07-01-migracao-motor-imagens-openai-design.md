# Migração do motor de geração de imagens: Gemini Imagen 4 → OpenAI gpt-image-1

**Data:** 2026-07-01
**Status:** aprovado para planejamento (aguardando revisão final do usuário)

## Contexto e motivação

O pipeline de imagens hoje gera fotos de produto usando o Gemini Imagen 4 fast
(`GeminiImageService` em `backend/app/services/image_service.py`). O resultado
não tem sido satisfatório e o motor de geração de pixels será trocado para a
OpenAI (`gpt-image-1`).

A troca é **configurável**, não uma substituição definitiva: o Gemini
permanece no sistema como motor de contingência, acionável manualmente pelo
usuário quando a OpenAI apresentar problemas.

Duas etapas distintas compõem a geração de uma imagem hoje:
1. **Escrita do prompt** (`AIProvider.generate_image_prompt`, texto) — decide
   marca/título/descrição e escreve a instrução em inglês para o gerador de
   imagem. Usa o provider de texto configurado em `AI_PROVIDER` (Gemini Flash
   por padrão).
2. **Geração dos pixels** (`GeminiImageService.generate`) — é essa etapa que
   está com resultado ruim e será substituída.

**Fora de escopo:** a Etapa 1 (escrita do prompt) não muda nesta migração.
Ver memória `project_image_prompt_audit` — se as imagens continuarem ruins ou
desconexas do produto após a troca do motor, uma investigação futura deve
auditar o prompt escrito na Etapa 1, não assumir que o problema é só do motor.

## Requisitos funcionais

### RF1 — Abstração de motor de imagem
Criar uma interface comum para motores de geração de imagem, análoga ao que já
existe para texto (`AIProvider`/`GeminiProvider`/`ClaudeProvider` em
`backend/app/services/ai/`).

### RF2 — Motor padrão: OpenAI gpt-image-1
- Modelo: `gpt-image-1`
- Qualidade: `medium`
- Imagens por chamada: `n=4` (mesma quantidade que o Gemini gera hoje)
- Tamanho: `1024x1024` (quadrado, igual ao padrão atual)
- Fundo: `background="opaque"` + prompt reforçando fundo branco puro,
  produto centralizado, sem pessoas/texto/sombras — reaproveita o mesmo
  `_PROMPT_SUFFIX` que já existe hoje.

### RF3 — Motor de contingência: Gemini Imagen 4
Continua existindo no código (reorganizado, não reescrito), disponível como
alternativa manual.

### RF4 — Troca de motor com aprovação assimétrica
- **OpenAI → Gemini:** só acontece mediante confirmação explícita do usuário.
- **Gemini → OpenAI:** acontece automaticamente assim que a OpenAI voltar a
  responder, apenas notificando o usuário (sem pedir confirmação).

### RF5 — Critério de falha que aciona a troca
Só erros de infraestrutura dão gatilho ao fluxo de troca de motor:
- Timeout de rede
- HTTP 5xx (erro do servidor da OpenAI)
- HTTP 429 (rate limit)

Erros de conteúdo (ex: HTTP 400/422 por prompt rejeitado por política) **não**
acionam troca de motor — seguem o fluxo de falha normal já existente do
anúncio (status `failed`).

### RF6 — Granularidade por execução
Cada execução da task `generate_images` (um anúncio por vez, seja manual ou
parte de um batch) decide o motor de forma independente, conforme o fluxo de
decisão abaixo. Não existe conceito de "teste 1x por lote de planilha" — o
teste de conectividade acontece a cada execução em que o motor atual é Gemini.

### RF7 — Visibilidade do motor ativo na UI
O card "Imagens" (tanto "Gerar imagens do produto" quanto "Imagens geradas")
na página `/listings/[id]` mostra um badge com o motor ativo no momento, ex.
`OpenAI · gpt-image-1` ou `Gemini · imagen-4.0-fast`.

## Modelo de dados

### Nova tabela `image_engine_state` (singleton — sempre 1 linha)
```
id                  UUID (PK)
current_engine      String  — "openai" | "gemini" (default: "openai")
last_openai_error   String, nullable — texto resumido do último erro de infra
last_switch_to_openai_at  Timestamp, nullable — quando current_engine voltou
                          para "openai" automaticamente (usado pelo frontend
                          para decidir se deve disparar o toast)
updated_at          Timestamp
```

A linha única é criada por uma migration de dados (não por lógica de
"cria se não existir" em runtime, para evitar condição de corrida entre
workers concorrentes na primeira execução).

### Novo valor de status em `Listing.status`
`pending_image_engine_confirmation` — sem migration necessária, pois
`Listing.status` já é `String(50)` livre (não há enum/check constraint no
banco). Usa o campo `error_message` já existente para guardar o erro.

## Fluxo de decisão (dentro de `_generate_images_async`)

Executado no início da geração, após o guard de idempotência existente
(`if listing.status != "generating_images": return`):

**Se `image_engine_state.current_engine == "gemini"`:**
1. Faz uma checagem leve de conectividade com a API da OpenAI antes de gerar
   — uma chamada `GET` simples e barata (ex. `GET /v1/models`) só para saber
   se a API responde, sem gerar imagem nessa checagem.
2. Se responder OK → atualiza `current_engine = "openai"`, `last_openai_error
   = null`, `last_switch_to_openai_at = now()`, e gera a imagem com OpenAI.
   O frontend detecta a troca comparando o `last_switch_to_openai_at`
   recebido no polling com o último valor visto (guardado em memória do
   componente) e dispara o toast só quando o valor mudar.
3. Se ainda falhar → segue gerando com Gemini normalmente, sem pedir nada
   (não houve transição de estado, já estava em Gemini).

**Se `image_engine_state.current_engine == "openai"`:**
1. Tenta gerar a imagem direto na OpenAI (a própria chamada real já serve de
   teste).
2. Sucesso → segue o fluxo normal (upload pro ML CDN, etc.), sem mudança.
3. Falha de infraestrutura (RF5) → grava erro em
   `image_engine_state.last_openai_error` e `listing.error_message`; muda
   `listing.status` para `pending_image_engine_confirmation`; **não** altera
   `current_engine` ainda (só muda quando o usuário confirmar); task termina
   sem retry automático do Celery.
4. Falha de conteúdo (4xx que não seja rate limit) → segue o fluxo de falha
   normal já existente (`failed`), sem envolver troca de motor.

## Endpoint de confirmação

`POST /api/v1/listings/{id}/pipeline/confirm_image_engine`
Body: `{"action": "use_gemini" | "retry_openai"}`

- **`use_gemini`**: define `image_engine_state.current_engine = "gemini"`;
  busca todos os listings com `status == "pending_image_engine_confirmation"`
  (`SELECT ... WHERE status = 'pending_image_engine_confirmation'`, sem
  filtro de seller — a troca de motor é global) e, para cada um, volta o
  status para `generating_images` e reenfileira `generate_images` (mesmo
  padrão de dispatch atômico via `UPDATE` já usado no resto do pipeline).
- **`retry_openai`**: reenfileira só o listing do path da URL, voltando seu
  status para `generating_images` e tentando a OpenAI de novo, sem alterar
  `image_engine_state`.

## Frontend

### Endpoint de leitura
`GET /api/v1/system/image-engine` →
`{current_engine, pending_confirmation_count, last_openai_error, last_switch_to_openai_at}`

### Banner global
Novo componente `ImageEngineBanner.tsx`, montado em
`frontend/src/app/(dashboard)/layout.tsx` (acima de `{children}`), visível em
qualquer página do dashboard. Faz polling no mesmo intervalo do kanban (8s).

Quando `pending_confirmation_count > 0`: banner de alerta com o erro resumido
e dois botões — "Usar Gemini nestes anúncios" e "Tentar novamente com
OpenAI" — chamando o endpoint de confirmação.

### Toast de troca automática
Quando o motor volta sozinho de Gemini→OpenAI, dispara
`toast.success("Geração de imagens voltou a usar a OpenAI")` via `sonner`
(biblioteca já usada no projeto).

### Badge no card "Imagens"
Em `listings/[id]/page.tsx`, ao lado do `CardTitle` dos cards "Gerar imagens
do produto" e "Imagens geradas", busca o `current_engine` do mesmo endpoint
de leitura e exibe como badge.

## Configuração / variáveis de ambiente

Novas entradas em `.env.example` / `Settings` (`backend/app/config.py`):
- `OPENAI_API_KEY` — chave da API da OpenAI
- `OPENAI_IMAGE_MODEL` — default `gpt-image-1`

Não é necessária uma variável `IMAGE_PROVIDER` estático — o motor ativo é
dinâmico, controlado pela tabela `image_engine_state`, cuja linha única
(`current_engine = "openai"`) é seedada pela migration que cria a tabela.

## Testes

- **`OpenAIImageEngine`** (equivalente a `TestGeminiImageService429` já
  existente): sucesso, 429→erro de infraestrutura, 5xx/timeout→erro de
  infraestrutura, 4xx de conteúdo→erro normal (não aciona troca de motor).
- **Fluxo de decisão em `image_tasks.py`**: os 4 cenários do fluxo acima —
  motor OpenAI falha infra→ `pending_image_engine_confirmation`; motor Gemini
  detecta OpenAI saudável→auto-switch + flag de toast; motor Gemini com
  OpenAI ainda fora→segue Gemini sem pedir nada; endpoint de confirmação
  reenfileirando múltiplos listings de uma vez.
- **Frontend**: sem suíte automatizada de UI no projeto hoje — validação
  manual no navegador (simulando falha da OpenAI) antes de fechar a tarefa.

## Fora de escopo (explicitamente)

- Não altera a Etapa 1 (escrita do prompt de imagem, `generate_image_prompt`).
- Não remove o código do Gemini Imagen 4.
- Não cria uma tabela genérica de notificações — o par
  `image_engine_state` + status do listing cobre a necessidade atual.
- Não versiona por seller — o motor ativo é global ao sistema (a chave da
  OpenAI/Gemini é de aplicação, não por seller).
