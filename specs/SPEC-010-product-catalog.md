# SPEC-010 — Catálogo de Produtos (TGFPRO)

## 1. Objetivo

Separar o domínio de **produto** do domínio de **anúncio**. Um produto é uma entidade atômica com dados estáveis (fiscais, físicos, de custo). Um anúncio é uma publicação de um produto num canal específico, com dados variáveis (preço, estoque, tipo, SEO).

Sem essa separação, dados fiscais de ICMS/PIS/COFINS e dimensões físicas são repetidos em cada upload de anúncio — impossível manter consistência em escala.

---

## 2. Modelo de Dados

### Tabela `products`

```sql
CREATE TABLE products (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    seller_id       UUID NOT NULL REFERENCES sellers(id),
    sku             VARCHAR(100) NOT NULL,

    -- Identificação
    description     TEXT NOT NULL,
    brand           VARCHAR(200),
    ean             VARCHAR(20),             -- GTIN/EAN-13
    ncm             VARCHAR(10),             -- Nomenclatura Comum do Mercosul

    -- Fiscal
    fiscal_origin   SMALLINT,                -- 0-8 (origem NF-e)
    icms_cst        VARCHAR(4),              -- ex: "00", "40", "60"
    icms_rate       NUMERIC(5,2),            -- alíquota %, ex: 12.00
    pis_cst         VARCHAR(4),              -- ex: "01", "07"
    cofins_cst      VARCHAR(4),

    -- Físico (embalagem)
    weight_kg       NUMERIC(10,3),           -- kg
    length_cm       INTEGER,
    width_cm        INTEGER,
    height_cm       INTEGER,

    -- Custo
    acquisition_cost NUMERIC(12,2),

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_products_seller_sku UNIQUE (seller_id, sku)
);

CREATE INDEX idx_products_seller_id ON products(seller_id);
```

### Relação com `listings`

```
products (1) ──► listings (N)
```

- `listings.product_id UUID FK → products.id`
- Um produto pode ter múltiplos anúncios (ex: Clássico + Premium, com preços diferentes)
- Dados físicos e fiscais vivem em `products`; preço, estoque e tipo vivem em `listings`

### Campos que migram de `listings` para `products`

| Campo atual em `listings`   | Campo em `products`  |
|-----------------------------|----------------------|
| `sku_external_id`           | `sku`                |
| `sku_description`           | `description`        |
| `sku_brand`                 | `brand`              |
| `package_weight_kg`         | `weight_kg`          |
| `package_length_cm`         | `length_cm`          |
| `package_width_cm`          | `width_cm`           |
| `package_height_cm`         | `height_cm`          |

Campos fiscais (`fiscal_origin`, `icms_cst`, `icms_rate`, `pis_cst`, `cofins_cst`, `acquisition_cost`) são novos — não existiam em `listings`.

### Estratégia de migração (sem downtime)

1. Criar tabela `products`
2. Adicionar `listings.product_id` nullable
3. Backfill: para cada listing com `sku_external_id` não-nulo, criar um `Product` e atualizar `product_id`
4. Código passa a exigir `product_id` em novos listings (soft enforcement)
5. Sprint futura: tornar `product_id NOT NULL`, dropar colunas denormalizadas de `listings`

Na fase atual (fase 2 desta SPEC), `sku_description` e `sku_brand` são mantidos em `listings` como cópia desnormalizada para evitar JOIN em toda listagem — atualizados na criação do listing a partir do produto.

---

## 3. Segurança e Isolamento Multi-Tenant

### Regra fundamental

> **Todo acesso a `products` deve incluir `WHERE seller_id = :active_seller_id`.**

Não existe consulta legítima que retorne produtos de mais de um seller ao mesmo tempo (exceto superadmin — fora de escopo desta SPEC).

### Implementação

```python
class ProductService:
    def __init__(self, db: AsyncSession, seller_id: UUID) -> None:
        self.db = db
        self.seller_id = seller_id  # nunca ausente

    async def get_or_404(self, sku: str) -> Product:
        # seller_id SEMPRE no WHERE — impede acesso cross-seller
        result = await self.db.execute(
            select(Product).where(
                Product.seller_id == self.seller_id,
                Product.sku == sku,
            )
        )
        product = result.scalar_one_or_none()
        if not product:
            raise HTTPException(404, f"Produto '{sku}' não encontrado")
        return product
```

`ProductService` é instanciado nos endpoints com `ProductService(db, seller_id=active_seller.id)` — o `seller_id` nunca vem do body do request, sempre do JWT + `get_active_seller()`.

### O que não fazer

```python
# ERRADO — busca por produto sem filtrar seller
select(Product).where(Product.id == product_id)

# CORRETO — sempre filtrar por seller + identificador
select(Product).where(
    Product.seller_id == self.seller_id,
    Product.id == product_id,
)
```

Toda FK `listings.product_id → products.id` ainda deve ser validada com `seller_id` ao criar um listing — impede que um seller referencie `product_id` de outro seller via payload manipulado.

---

## 4. API

### Upload de Produtos

```
POST /api/v1/products/upload
Content-Type: multipart/form-data

Request: { file: CSV | XLSX }
Response 202: { batch_id, total_rows, accepted, rejected, errors: [...] }
```

Comportamento: **upsert por `(seller_id, sku)`**.
- Se o produto não existe → INSERT
- Se já existe → UPDATE nos campos fornecidos (campos ausentes na planilha não são sobrescritos)
- Retorna o resultado sincrônico (sem worker Celery — operação simples de I/O de banco)

### Listagem e Detalhe

```
GET /api/v1/products?search=&page=&page_size=
GET /api/v1/products/{sku}
PUT /api/v1/products/{sku}     — atualização individual
DELETE /api/v1/products/{sku}  — soft delete (marca inactive) se não houver listing ativo
```

Todos os endpoints filtram implicitamente por `active_seller.id`.

---

## 5. Planilha de Produtos (CSV/XLSX)

### Colunas canônicas e aliases aceitos

| Campo canônico   | Aliases na planilha                                      | Tipo      | Obrig. |
|------------------|----------------------------------------------------------|-----------|--------|
| `sku`            | sku, cod, codigo, referencia, ref, codinterno            | string    | ✅ |
| `descricao`      | descricao, xprod, nomeproduto, produto, description      | string    | ✅ |
| `marca`          | marca, brand, fabricante                                 | string    | — |
| `ean`            | ean, gtin, codigobarras, barcode, cean                   | string    | — |
| `ncm`            | ncm                                                      | string    | — |
| `fiscal_origin`  | origemfiscal, cst, origem                                | int 0-8   | — |
| `icms_cst`       | icmscst, csticms                                         | string    | — |
| `icms_rate`      | icmsrate, aliquotaicms, alicms                           | decimal   | — |
| `pis_cst`        | piscst, cstpis                                           | string    | — |
| `cofins_cst`     | cofinscst, cstcofins                                     | string    | — |
| `peso_kg`        | pesokg, peso, weight                                     | decimal   | — |
| `comprimento_cm` | comprimentocm, comprimento, length                       | int       | — |
| `largura_cm`     | larguracm, largura, width                                | int       | — |
| `altura_cm`      | alturacm, altura, height                                 | int       | — |
| `custo`          | custo, custounif, costprice, precodecompra               | decimal   | — |

### Comportamento de upsert por coluna

Campos ausentes da planilha (coluna não presente) → não sobrescritos no banco.
Campo presente mas vazio → interpretado como "limpar o valor" (SET NULL).

---

## 6. Serviço de Upload — Fluxo Detalhado

```
1. Parse CSV/XLSX → lista de dicts
2. Para cada linha:
   a. Normalizar colunas (strip, lowercase, remove acentos)
   b. Validar: sku obrigatório, descricao obrigatória
   c. Upsert: INSERT ... ON CONFLICT (seller_id, sku) DO UPDATE SET ...
   d. Registrar resultado (accepted / rejected + motivo)
3. Retornar resumo síncrono: { total, accepted, rejected, errors }
```

Sem Celery para uploads de produto — a operação é simples e o volume esperado é menor do que uploads de anúncio. Para volumes acima de 2.000 linhas, avaliar Celery na Sprint futura.

---

## 7. Arquivos a criar/modificar

| Arquivo | Ação |
|---|---|
| `backend/app/models/product.py` | NOVO — modelo Product |
| `backend/app/services/product_service.py` | NOVO — ProductService (upsert, get, list) |
| `backend/app/api/v1/endpoints/products.py` | NOVO — router /products |
| `backend/app/schemas/product.py` | NOVO — ProductCreate, ProductOut, ProductUploadResult |
| `backend/app/services/product_import_service.py` | NOVO — parse + upsert de planilha de produto |
| `backend/alembic/versions/xxxx_add_products_table.py` | NOVO — migration |
| `backend/alembic/versions/xxxx_add_product_id_to_listings.py` | NOVO — migration |
| `backend/app/api/v1/router.py` | Registrar router de produtos |
| `frontend/src/app/(dashboard)/products/` | NOVO — página de catálogo + upload |
| `frontend/src/components/layout/Sidebar.tsx` | Adicionar link "Produtos" |
