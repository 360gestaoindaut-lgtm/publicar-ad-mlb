# SPEC-005 — Predição de Categoria e Atributos ML

**Versão**: 1.0 | **Status**: Aprovado

---

## Fluxo completo

```
1. Título aprovado pelo seller
        │
        ▼
2. GET /sites/MLB/domain_discovery/search?q={titulo_encoded}
   → retorna lista de categorias com scores de relevância
        │
        ▼
3. Selecionar categoria com maior score (se score ≥ 0.7) OU
   apresentar top 3 ao seller para escolha manual
        │
        ▼
4. GET /categories/{category_id}/attributes
   → retorna lista completa de atributos da categoria
        │
        ▼
5. IA pré-preenche atributos inferíveis
        │
        ▼
6. Persistir todos os atributos no banco (fonte: 'ai' ou 'pending_seller')
        │
        ▼
7. Notificar seller com link para o formulário
   (apenas atributos que a IA não conseguiu preencher)
```

---

## API ML — Predição de categoria

**GET** `https://api.mercadolibre.com/sites/MLB/domain_discovery/search?q={titulo}`

Cabeçalho: `Authorization: Bearer {access_token}`

**Resposta de exemplo:**
```json
[
  {
    "domain_id": "MLB-CELLPHONES",
    "domain_name": "Celulares e Smartphones",
    "category_id": "MLB1055",
    "category_name": "Celulares e Smartphones",
    "attributes": [...],
    "score": 0.923
  }
]
```

**Regra de auto-seleção**: `score >= 0.70` → seleciona automaticamente.
Abaixo disso → frontend mostra top 3 para o seller escolher.

---

## API ML — Atributos da categoria

**GET** `https://api.mercadolibre.com/categories/{category_id}/attributes`

**Estrutura de um atributo:**
```json
{
  "id": "BRAND",
  "name": "Marca",
  "value_type": "string",
  "tags": {
    "required": true,
    "catalog_required": true
  },
  "allowed_units": null,
  "values": [
    { "id": "SAMSUNG", "name": "Samsung" },
    { "id": "APPLE",   "name": "Apple" }
  ],
  "hierarchy": "PARENT",
  "relevance": 1
}
```

**Classificação dos atributos:**
- `tags.required = true` → obrigatório, bloqueia publicação
- `tags.catalog_required = true` → obrigatório para catálogo ML
- Sem required → opcional (exibir mas não bloquear)

---

## Pré-preenchimento por IA

Após buscar os atributos, o sistema pede à IA para preencher os que puder:

**Atributos que a IA CONSEGUE inferir** (com alta confiança):
- `BRAND` → da variável `sku_brand`
- `ITEM_CONDITION` → da variável `condition`
- `MODEL` → extraído da `sku_description`
- `COLOR` → se mencionado na descrição
- `STORAGE_CAPACITY`, `RAM` → se mencionado na descrição

**Atributos que NÃO devem ser preenchidos pela IA** (riscos altos):
- Campos com `values` fixas que exigem ID exato da ML → IA pode errar o ID
  - Nesses casos, IA sugere o `value_name` e o sistema busca o `value_id` por match exato
- Dados técnicos precisos (voltagem, frequência) → deixar para o seller

**Regra de confiança**: se a IA não tiver certeza, deixar em branco e exibir ao seller.

---

## Formulário dinâmico para o seller

O backend retorna os atributos pendentes com tipagem, para o frontend renderizar:

```json
{
  "attributes_pending": [
    {
      "attribute_id": "STORAGE_CAPACITY",
      "attribute_name": "Capacidade de Armazenamento",
      "attribute_type": "list",
      "is_required": true,
      "options": [
        { "id": "64GB",  "name": "64 GB" },
        { "id": "128GB", "name": "128 GB" },
        { "id": "256GB", "name": "256 GB" }
      ]
    },
    {
      "attribute_id": "WARRANTY",
      "attribute_name": "Garantia do vendedor",
      "attribute_type": "number",
      "is_required": true,
      "unit": "months",
      "options": null
    }
  ]
}
```

**Mapeamento de tipo → componente UI:**
| attribute_type | Componente |
|---|---|
| `list` com `options` | `<Select>` (dropdown) |
| `string` sem options | `<Input type="text">` |
| `number` | `<Input type="number">` com unidade |
| `boolean` | `<Switch>` |

---

## Montagem dos atributos no payload final do anúncio

```json
"attributes": [
  { "id": "BRAND",            "value_name": "Samsung" },
  { "id": "MODEL",            "value_name": "Galaxy A55" },
  { "id": "STORAGE_CAPACITY", "value_id": "256GB", "value_name": "256 GB" },
  { "id": "COLOR",            "value_id": "BLUE",  "value_name": "Azul" }
]
```

Regra: se o atributo tem `value_id`, enviar ambos `value_id` e `value_name`.
Se é texto livre, enviar apenas `value_name`.
