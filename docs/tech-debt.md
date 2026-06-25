# Pendências técnicas

Itens identificados em code review mas fora do escopo das sprints em que surgiram.
Resolver antes de ou durante a Fase 6 (deploy produção).

---

## Pré-deploy (Fase 6)

### pytest em requirements.txt de produção
**Origem:** review final dos quick fixes F-1..F-4 (2026-06-24)

`pytest==8.3.5` e `pytest-asyncio==0.24.0` estão em `backend/requirements.txt`, o que faz o
Docker de produção instalar ferramentas de teste desnecessariamente. Criar
`backend/requirements-dev.txt` com essas dependências e removê-las do `requirements.txt` principal.
O `Dockerfile.dev` pode instalar os dois arquivos; o Dockerfile de produção, apenas o principal.

---

## Qualidade de código (baixa prioridade)

### logging em nível de módulo em `_mark_failed`
**Origem:** review final dos quick fixes F-1..F-4 (2026-06-24)

`import logging` e `logger = logging.getLogger(__name__)` estão dentro do corpo de
`_mark_failed` (`backend/app/workers/tasks/image_tasks.py`), sendo executados a cada chamada.
Mover para o nível de módulo (junto aos outros imports do arquivo) é mais idiomático e
marginalmente mais eficiente.

### `test_large_image_is_not_downscaled` — asserção fraca
**Origem:** task review Task 1 (2026-06-24)

O teste cria uma imagem 1500×1500 e verifica `min(img.size) >= 1024`. Correto, mas não detectaria
uma regressão que encolhesse a imagem para exatamente 1024px. Trocar por `assert min(img.size) >= 1500`
para cobrir o caso de downscaling acidental.

### `test_listing_not_found_does_not_raise` — sem asserção positiva
**Origem:** task review Task 2 (2026-06-24)

O teste só verifica que não levanta exceção. Adicionar
`mock_db.commit.assert_not_called()` para confirmar que o branch de "listing não encontrado"
percorre o caminho correto (sem commit).
