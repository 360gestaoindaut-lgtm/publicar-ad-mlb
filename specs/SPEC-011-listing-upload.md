# SPEC-011 — Upload de Anúncios (TGFMLB)

## 1. Objetivo

Definir o contrato do upload de anúncios — a planilha que o seller envia para criar/atualizar publicações no Mercado Livre a partir de produtos já cadastrados no catálogo (SPEC-010).

Um anúncio referencia obrigatoriamente um produto existente. Dados de produto (fiscal, físico) não são repetidos aqui — são herdados automaticamente do cadastro.

---

## 2. Relação com SPEC-010

```
products ──(product_id)──► listings
    ↑                          ↑
 TGFPRO                    TGFMLB
 (esta SPEC)              (esta SPEC)

Upload de produto → cria/atualiza products
Upload de anúncio → cria listings referenciando products
```

O seller faz os uploads nessa ordem:
1. Upload de produtos (uma vez, ou quando muda o cadastro)
2. Upload de anúncios (quando quer publicar, repromoções, novos preços)

---

## 3. Modelo — Alterações em `listings`

### Campos adicionados

```sql
ALTER TABLE listings ADD COLUMN product_id UUID REFERENCES products(id);
```

### Campos que se tornam redundantes (mantidos na fase 1, deprecados na fase 2)

| Campo em `listings` | Origem futura         | Fase |
|---------------------|-----------------------|------|
| `sku_external_id`   | `products.sku`        | 2    |
| `sku_description`   | `products.description`| 2    |
| `sku_brand`         | `products.brand`      | 2    |
| `package_weight_kg` | `products.weight_kg`  | 2    |
| `package_length_cm` | `products.length_cm`  | 2    |
| `package_width_cm`  | `products.width_cm`   | 2    |
| `package_height_cm` | `products.height_cm`  | 2    |

Na fase 1: o worker de batch preenche os campos de `listings` copiando de `products` no momento da criação (desnormalização controlada). Isso preserva compatibilidade com o pipeline atual sem refatorar `publish_service` e `category_service`.

Na fase 2 (Sprint futura): `product_id NOT NULL`, colunas redundantes dropadas, todos os serviços fazem JOIN com `products` quando necessário.

### Segurança no vínculo listing → product

Ao criar um listing via upload, o worker valida:
```python
product = await db.execute(
    select(Product).where(
        Product.seller_id == listing.seller_id,  # OBRIGATÓRIO
        Product.sku == row["sku"],
    )
)
```
Se o produto não existe para aquele seller → row rejeitada, não aborta o batch.

---

## 4. Planilha de Anúncios (CSV/XLSX)

### Colunas canônicas e aliases aceitos

| Campo canônico  | Aliases na planilha                                   | Tipo    | Obrig. |
|-----------------|-------------------------------------------------------|---------|--------|
| `sku`           | sku, cod, codigo, referencia, ref                     | string  | ✅ |
| `preco`         | preco, preço, price, valorvenda, prv                  | decimal | ✅ |
| `estoque`       | estoque, qty, quantidade, saldo, stock                | int     | — (default 1) |
| `tipo_anuncio`  | tipoanuncio, tipo, listingtype                        | string  | — (default gold_special) |
| `condicao`      | condicao, condição, condition                         | string  | — (default new) |
| `seo_context`   | seocontext, contexto, seo, contextoseo                | string  | — |

### Valores aceitos para `tipo_anuncio`

| Planilha (qualquer capitalização) | Valor interno   |
|-----------------------------------|-----------------|
| classico, clássico, classic, gold_special, special | `gold_special` |
| premium, ouro, pro, gold_pro      | `gold_pro`      |

### O que NÃO pertence à planilha de anúncios

- EAN, NCM, ICMS, PIS, COFINS → planilha de produto
- Peso, dimensões → planilha de produto
- Custo de aquisição → planilha de produto
- Marca, descrição → herdados do produto

---

## 5. Fluxo de Upload de Anúncio

```
1. POST /api/v1/listings/upload (multipart, CSV ou XLSX)
2. Parse → lista de dicts
3. Para cada linha:
   a. Normalizar colunas
   b. Validar: sku obrigatório, preco obrigatório e > 0
   c. Buscar Product WHERE seller_id = active_seller.id AND sku = row.sku
      → não encontrado: row.status = "failed", error = "Produto 'X' não cadastrado"
      → encontrado: continuar
   d. Criar Listing com:
        product_id  = product.id
        seller_id   = active_seller.id
        -- desnormalizados do produto (fase 1):
        sku_external_id = product.sku
        sku_description = product.description
        sku_brand       = product.brand
        package_weight_kg  = product.weight_kg
        package_length_cm  = product.length_cm
        package_width_cm   = product.width_cm
        package_height_cm  = product.height_cm
        -- da planilha:
        price          = row.preco
        stock_quantity = row.estoque
        listing_type_id = row.tipo_anuncio
        condition      = row.condicao
        created_via    = "batch"
        status         = "generating_title"
   e. Criar BatchImportRow com listing_id
   f. Disparar generate_title.delay(listing_id, batch_mode=True, ean=product.ean, seo_context=row.seo_context)
4. Retornar batch_id + resumo
```

---

## 6. Validações e Erros

| Situação | Comportamento |
|---|---|
| `sku` ausente | Row rejeitada, batch continua |
| `preco` ausente ou ≤ 0 | Row rejeitada, batch continua |
| Produto não encontrado para o seller | Row rejeitada, error: "Produto '{sku}' não cadastrado" |
| Produto encontrado mas sem EAN | Listing criado, GTIN não pré-preenchido (seller preenche manualmente) |
| Produto com dados físicos incompletos | Listing criado, atributos de embalagem não pré-preenchidos |
| Listing duplicado (mesmo product_id + mesma conta, status ativo) | Criar mesmo assim — seller pode querer dois anúncios do mesmo produto (Clássico + Premium) |

---

## 7. Endpoint de Upload de Produto (separação do endpoint atual)

O endpoint atual `POST /api/v1/import` passa a ser **exclusivo para anúncios**.
Um novo endpoint `POST /api/v1/products/upload` cuida do catálogo de produtos.

Na interface, a sidebar terá dois pontos de entrada distintos:
- **Produtos** → upload de catálogo (TGFPRO)
- **Anúncios** → kanban + upload de anúncios (TGFMLB)

---

## 8. Endpoint de Status do Upload de Anúncios

Sem alteração em relação ao atual:
```
GET /api/v1/import/{batch_id}
```

Retorna progresso linha a linha, incluindo motivo de falha para linhas rejeitadas (ex: "Produto 'SKU123' não cadastrado").

---

## 9. Arquivos a modificar

| Arquivo | Ação |
|---|---|
| `backend/app/workers/tasks/batch_tasks.py` | Buscar product por sku, desnormalizar campos, passar ean do produto |
| `backend/app/services/batch_import_service.py` | Remover colunas físicas/fiscais do `_COLUMN_MAP` de anúncios (ficam em product_import_service) |
| `backend/app/schemas/listing.py` | Adicionar `product_id` opcional a `ListingCreate` e `ListingSummary` |
| `backend/alembic/versions/xxxx_add_product_id_to_listings.py` | Já coberto pela SPEC-010 |
| `frontend/src/app/(dashboard)/listings/import/page.tsx` | Adaptar upload de anúncios para mostrar erro "produto não cadastrado" |
| `frontend/src/app/(dashboard)/products/` | Novo — coberto pela SPEC-010 |

---

## 10. Ordem de Implementação

1. **SPEC-010 primeiro**: modelo Product, migration, ProductService, endpoint de upload, frontend
2. **SPEC-011 depois**: ajuste no batch_tasks para buscar product, desnormalizar na criação do listing
3. Ambos são necessários antes de qualquer campanha de upload em produção
