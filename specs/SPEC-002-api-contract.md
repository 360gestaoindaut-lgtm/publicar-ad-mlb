# SPEC-002 — Contrato da API REST

**Versão**: 1.0 | **Status**: Aprovado | **Base URL**: `/api/v1`

---

## Autenticação

Todos os endpoints (exceto `/health` e `/auth/ml/callback`) exigem:
```
Authorization: Bearer <jwt_access_token>
```

Formato de erro padrão (todos os erros):
```json
{
  "detail": "Mensagem descritiva do erro"
}
```

---

## Endpoints

### Auth

| Método | Path | Auth | Descrição |
|---|---|---|---|
| POST | `/auth/login` | Não | Login com email + senha |
| POST | `/auth/refresh` | Não | Renova access token com refresh token |
| GET | `/auth/ml/connect` | Sim | Inicia OAuth ML → retorna URL de redirect |
| GET | `/auth/ml/callback` | Não | Callback OAuth ML (redirect do ML) |
| GET | `/auth/ml/status` | Sim | Verifica se conta ML está conectada |

**POST /auth/login**
```json
// Request
{ "email": "operador@empresa.com", "password": "senha" }

// Response 200
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

---

### Listings (anúncios)

| Método | Path | Descrição |
|---|---|---|
| GET | `/listings` | Lista anúncios com filtros e paginação |
| POST | `/listings` | Cria novo listing (inicia o pipeline) |
| GET | `/listings/{id}` | Detalhe completo de um listing |
| PATCH | `/listings/{id}` | Atualiza campos permitidos |
| DELETE | `/listings/{id}` | Remove listing em status draft ou failed |

**GET /listings** — query params:
- `status` (opcional): filtro por status
- `page` (default 1), `page_size` (default 20, max 100)

```json
// Response 200
{
  "items": [
    {
      "id": "uuid",
      "sku_external_id": "SKU-123",
      "sku_brand": "Samsung",
      "selected_title": "Smartphone Samsung Galaxy A55...",
      "status": "pending_seller_attributes",
      "mlb_id": null,
      "created_at": "2026-06-20T14:00:00Z",
      "updated_at": "2026-06-20T14:05:00Z"
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20
}
```

**POST /listings**
```json
// Request
{
  "sku_external_id": "SKU-123",
  "sku_description": "Smartphone Samsung Galaxy A55 5G 256GB Azul",
  "sku_brand": "Samsung",
  "price": 1899.90,
  "stock_quantity": 5,
  "condition": "new"
}

// Response 201
{ "id": "uuid", "status": "draft" }
```

---

### Pipeline de ações por listing

| Método | Path | Descrição |
|---|---|---|
| POST | `/listings/{id}/start` | Inicia pipeline (draft → generating_title) |
| GET | `/listings/{id}/titles` | Lista variações de título geradas |
| POST | `/listings/{id}/titles/{tid}/select` | Seller seleciona um título |
| GET | `/listings/{id}/attributes` | Lista atributos a preencher |
| PUT | `/listings/{id}/attributes` | Seller submete atributos preenchidos |
| GET | `/listings/{id}/images` | Lista imagens geradas |
| PATCH | `/listings/{id}/images/{iid}` | Seller aprova/rejeita imagem |
| GET | `/listings/{id}/description` | Retorna descrição rica gerada |
| POST | `/listings/{id}/publish` | Seller confirma e publica |
| POST | `/listings/{id}/retry` | Retenta após falha |

**PUT /listings/{id}/attributes** — body:
```json
{
  "attributes": [
    { "attribute_id": "BRAND", "value_id": "SAMSUNG", "value_name": "Samsung" },
    { "attribute_id": "MODEL", "value_id": null, "value_name": "Galaxy A55" },
    { "attribute_id": "STORAGE_CAPACITY", "value_id": "256GB", "value_name": "256 GB" }
  ]
}
```

---

### Jobs

| Método | Path | Descrição |
|---|---|---|
| GET | `/listings/{id}/jobs` | Lista todos os jobs e seus status |

```json
// Response 200
[
  {
    "job_type": "generate_title",
    "status": "success",
    "attempts": 1,
    "started_at": "2026-06-20T14:01:00Z",
    "completed_at": "2026-06-20T14:01:03Z"
  },
  {
    "job_type": "generate_images",
    "status": "running",
    "attempts": 1,
    "started_at": "2026-06-20T14:02:00Z",
    "completed_at": null
  }
]
```

---

### Health

| Método | Path | Auth | Descrição |
|---|---|---|---|
| GET | `/health` | Não | Status dos serviços (DB, Redis, ML) |

```json
// Response 200
{
  "status": "ok",
  "services": {
    "database": "ok",
    "redis": "ok",
    "ml_api": "ok"
  }
}
```

---

## Convenções

- Datas sempre em ISO 8601 UTC: `"2026-06-20T14:00:00Z"`
- IDs sempre UUID v4 em string
- Paginação: `page` começa em 1
- `PATCH` aceita apenas os campos enviados (partial update)
- Status HTTP usados: 200, 201, 400, 401, 403, 404, 409, 422, 500
- 422 Unprocessable Entity para erros de validação (Pydantic)
- 409 Conflict para operações inválidas no estado atual (ex: publicar listing que não está ready)
