# SPEC-001 — Schema do Banco de Dados

**Versão**: 1.0 | **Status**: Aprovado

---

## Diagrama de relacionamentos

```
users ──────────────▶ sellers
  │                      │
  │              listings (N) ◀─────── listing_jobs (N)
  │                  │
  │         ┌────────┼────────┐
  │         ▼        ▼        ▼
  │   listing_    listing_  listing_
  │   titles(N) images(N) attributes(N)
  │
  └──────────────▶ listing_descriptions(1)
```

---

## Tabelas

### `sellers`
Conta do Mercado Livre conectada ao sistema.

| Coluna | Tipo | Constraints | Descrição |
|---|---|---|---|
| id | UUID | PK, default gen_random_uuid() | |
| ml_user_id | BIGINT | NOT NULL, UNIQUE | ID do usuário na ML |
| ml_nickname | VARCHAR(100) | NOT NULL | Nickname ML (ex: VENDEDOR123) |
| ml_site_id | VARCHAR(5) | NOT NULL, default 'MLB' | Site (MLB = Brasil) |
| access_token_enc | TEXT | NOT NULL | Token ML criptografado com Fernet |
| refresh_token_enc | TEXT | NOT NULL | Refresh token ML criptografado |
| token_expires_at | TIMESTAMPTZ | NOT NULL | Quando o access_token expira |
| is_active | BOOLEAN | NOT NULL, default true | |
| created_at | TIMESTAMPTZ | NOT NULL, default now() | |
| updated_at | TIMESTAMPTZ | NOT NULL, default now() | |

---

### `users`
Usuários do sistema (operadores que usam a plataforma).

| Coluna | Tipo | Constraints | Descrição |
|---|---|---|---|
| id | UUID | PK, default gen_random_uuid() | |
| seller_id | UUID | FK → sellers.id, NOT NULL | |
| email | VARCHAR(255) | NOT NULL, UNIQUE | |
| password_hash | VARCHAR(255) | NOT NULL | bcrypt |
| full_name | VARCHAR(200) | NOT NULL | |
| role | VARCHAR(20) | NOT NULL, default 'operator' | 'admin' ou 'operator' |
| is_active | BOOLEAN | NOT NULL, default true | |
| created_at | TIMESTAMPTZ | NOT NULL, default now() | |

**Índices**: `idx_users_email` em `email`

---

### `listings`
Anúncio em qualquer estágio do pipeline.

| Coluna | Tipo | Constraints | Descrição |
|---|---|---|---|
| id | UUID | PK, default gen_random_uuid() | |
| seller_id | UUID | FK → sellers.id, NOT NULL | |
| created_by | UUID | FK → users.id, NOT NULL | |
| sku_external_id | VARCHAR(100) | | ID do SKU no ERP do seller |
| sku_description | TEXT | NOT NULL | Descrição bruta do ERP |
| sku_brand | VARCHAR(200) | NOT NULL | Marca |
| price | NUMERIC(12,2) | NOT NULL | Preço de venda |
| stock_quantity | INTEGER | NOT NULL | Quantidade em estoque |
| condition | VARCHAR(10) | NOT NULL | 'new' ou 'used' |
| listing_type_id | VARCHAR(20) | NOT NULL, default 'gold_special' | Tipo ML |
| status | VARCHAR(50) | NOT NULL, default 'draft' | Ver máquina de estados |
| ml_category_id | VARCHAR(20) | | Ex: MLB1055 |
| mlb_id | VARCHAR(20) | UNIQUE | Ex: MLB1234567890 |
| selected_title | TEXT | | Título aprovado pelo seller |
| error_message | TEXT | | Última mensagem de erro |
| created_at | TIMESTAMPTZ | NOT NULL, default now() | |
| updated_at | TIMESTAMPTZ | NOT NULL, default now() | |

**Índices**: `idx_listings_seller_status` em `(seller_id, status)`, `idx_listings_sku` em `sku_external_id`, `idx_listings_mlb_id` em `mlb_id`

---

### `listing_jobs`
Rastreamento de cada job assíncrono associado ao anúncio.

| Coluna | Tipo | Constraints | Descrição |
|---|---|---|---|
| id | UUID | PK, default gen_random_uuid() | |
| listing_id | UUID | FK → listings.id, NOT NULL | |
| job_type | VARCHAR(50) | NOT NULL | Ver tipos abaixo |
| celery_task_id | VARCHAR(255) | | ID da task no Celery |
| status | VARCHAR(20) | NOT NULL, default 'pending' | pending/running/success/failed |
| payload_in | JSONB | | Input enviado ao worker |
| payload_out | JSONB | | Output recebido do worker |
| error_message | TEXT | | Erro se status=failed |
| attempts | SMALLINT | NOT NULL, default 0 | Número de tentativas |
| started_at | TIMESTAMPTZ | | |
| completed_at | TIMESTAMPTZ | | |
| created_at | TIMESTAMPTZ | NOT NULL, default now() | |

**Tipos de job** (`job_type`): `generate_title`, `predict_category`, `generate_images`, `upload_images`, `generate_description`, `publish`

**Índices**: `idx_listing_jobs_listing` em `(listing_id, job_type)`, `idx_listing_jobs_status` em `status`

---

### `listing_titles`
Variações de título geradas pela IA para o seller escolher.

| Coluna | Tipo | Constraints | Descrição |
|---|---|---|---|
| id | UUID | PK, default gen_random_uuid() | |
| listing_id | UUID | FK → listings.id, NOT NULL | |
| title_text | VARCHAR(60) | NOT NULL | Máx 60 chars (limite ML) |
| ai_score | NUMERIC(4,2) | | Score de qualidade atribuído pela IA |
| selected | BOOLEAN | NOT NULL, default false | Apenas 1 pode ser true por listing |
| created_at | TIMESTAMPTZ | NOT NULL, default now() | |

---

### `listing_attributes`
Atributos da categoria ML (obrigatórios e opcionais).

| Coluna | Tipo | Constraints | Descrição |
|---|---|---|---|
| id | UUID | PK, default gen_random_uuid() | |
| listing_id | UUID | FK → listings.id, NOT NULL | |
| attribute_id | VARCHAR(100) | NOT NULL | ID do atributo na ML |
| attribute_name | VARCHAR(200) | NOT NULL | Nome legível |
| value_id | VARCHAR(200) | | ID do valor (para atributos de lista) |
| value_name | VARCHAR(500) | | Texto do valor |
| attribute_type | VARCHAR(30) | NOT NULL | string/number/boolean/list |
| is_required | BOOLEAN | NOT NULL | |
| source | VARCHAR(10) | NOT NULL | 'ai' ou 'seller' |
| created_at | TIMESTAMPTZ | NOT NULL, default now() | |

**Índice único**: `(listing_id, attribute_id)`

---

### `listing_images`
Imagens geradas e seus status no pipeline.

| Coluna | Tipo | Constraints | Descrição |
|---|---|---|---|
| id | UUID | PK, default gen_random_uuid() | |
| listing_id | UUID | FK → listings.id, NOT NULL | |
| freepik_job_id | VARCHAR(200) | | Job ID no FreePik |
| url_r2 | TEXT | | URL no Cloudflare R2 |
| ml_picture_id | VARCHAR(100) | | ID após upload na ML |
| status | VARCHAR(20) | NOT NULL, default 'generating' | generating/ready/uploaded/failed |
| approved | BOOLEAN | NOT NULL, default false | Seller aprovou? |
| sort_order | SMALLINT | NOT NULL, default 0 | Ordem no anúncio |
| created_at | TIMESTAMPTZ | NOT NULL, default now() | |

---

### `listing_descriptions`
Descrição rica HTML gerada pela IA.

| Coluna | Tipo | Constraints | Descrição |
|---|---|---|---|
| id | UUID | PK, default gen_random_uuid() | |
| listing_id | UUID | FK → listings.id, NOT NULL, UNIQUE | 1:1 com listing |
| description_html | TEXT | NOT NULL | HTML gerado pela IA |
| created_at | TIMESTAMPTZ | NOT NULL, default now() | |

---

## Notas de migração

- Usar Alembic com `--autogenerate` a partir dos models SQLAlchemy
- UUID como PK em todas as tabelas (sem inteiros sequenciais expostos)
- `updated_at` atualizado via trigger PostgreSQL ou hook SQLAlchemy
- Todos os `TIMESTAMPTZ` armazenam em UTC; conversão de timezone no frontend
