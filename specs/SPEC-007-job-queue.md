# SPEC-007 — Job Queue (Celery + Redis)

**Versão**: 1.0 | **Status**: Aprovado

---

## Configuração do Celery

**Filas e seus workers:**

| Fila | Concorrência | Tasks |
|---|---|---|
| `default` | 4 | predict_category, refresh_ml_tokens |
| `ai` | 2 | generate_title, generate_description |
| `images` | 2 | generate_images, upload_images_to_ml |
| `publish` | 2 | publish_listing |

Workers escalam independentemente. Em produção, cada fila pode ter seu próprio container.

**Broker**: Redis  
**Result backend**: Redis (TTL de 24h para resultados)  
**Serialização**: JSON (nunca pickle por segurança)

---

## Tasks

### `task_generate_title`
**Fila**: `ai` | **Timeout**: 30s | **Max retries**: 3 | **Retry delay**: backoff exp. (2, 4, 8s)

```
Input:  { listing_id, sku_description, sku_brand, condition }
Output: { titles: [{ text, score, rationale }] }
Efeitos:
  - Persiste listing_titles no banco
  - Atualiza listings.status → 'pending_title_approval'
  - Marca listing_job como 'success'
```

---

### `task_predict_category`
**Fila**: `default` | **Timeout**: 15s | **Max retries**: 3

```
Input:  { listing_id, selected_title }
Output: { category_id, category_name, score, attributes: [...] }
Efeitos:
  - Persiste listings.ml_category_id
  - Chama IA para pré-preencher atributos inferíveis
  - Persiste listing_attributes (fonte: 'ai')
  - Se atributos pendentes: status → 'pending_seller_attributes'
  - Se tudo preenchido: status → 'generating_description' (raro)
  - Dispara task_generate_images em paralelo
```

---

### `task_generate_images`
**Fila**: `images` | **Timeout**: 120s | **Max retries**: 2

```
Input:  { listing_id, sku_brand, sku_description, ml_category_id }
Output: { images: [{ url_r2, filename }] }
Efeitos:
  - Chama FreePik API (poll até done)
  - Faz download das imagens
  - Upload para Cloudflare R2
  - Persiste listing_images com status 'ready'
  - Dispara task_upload_images_to_ml
```

---

### `task_upload_images_to_ml`
**Fila**: `images` | **Timeout**: 60s | **Max retries**: 3

```
Input:  { listing_id }
Output: { picture_ids: [...] }
Efeitos:
  - Para cada listing_image com status 'ready':
    → POST /pictures/items/upload na ML
    → Salva ml_picture_id
    → Status da imagem: 'uploaded'
  - Ao finalizar: marca job de imagens como 'success'
```

---

### `task_generate_description`
**Fila**: `ai` | **Timeout**: 60s | **Max retries**: 3

Disparada quando: `pending_seller_attributes` → seller submete atributos.

```
Input:  { listing_id }
Output: { description_html: "..." }
Efeitos:
  - Busca no banco: título + atributos + descrição original
  - Chama IA para gerar HTML
  - Persiste listing_descriptions
  - Status: 'ready_to_publish'
```

---

### `task_publish_listing`
**Fila**: `publish` | **Timeout**: 30s | **Max retries**: 2

Disparada quando: seller clica "Publicar" no preview.

```
Input:  { listing_id }
Output: { mlb_id: "MLB..." }
Efeitos:
  - Monta payload completo (ver SPEC-002 para estrutura)
  - POST /items na ML API
  - Salva listings.mlb_id
  - Status: 'published'
```

**Payload completo para ML:**
```json
{
  "title": "{selected_title}",
  "category_id": "{ml_category_id}",
  "price": 1899.90,
  "currency_id": "BRL",
  "available_quantity": 5,
  "buying_mode": "buy_it_now",
  "condition": "new",
  "listing_type_id": "gold_special",
  "description": { "plain_text": "{description_html_stripped}" },
  "pictures": [
    { "id": "MLB..." }
  ],
  "attributes": [
    { "id": "BRAND", "value_name": "Samsung" }
  ]
}
```

---

### `task_refresh_ml_tokens` (Celery Beat)
**Fila**: `default` | **Agendamento**: a cada 5 horas

```
Efeito:
  - Busca sellers com token_expires_at < now() + 1h
  - Renova access_token via refresh_token
  - Atualiza banco com tokens criptografados
  - Se falhar: is_active=false + e-mail de alerta
```

---

## Tratamento de falhas e retry

```python
# Exemplo de configuração de retry
@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=2,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=30
)
```

Ao esgotar retries:
1. Marcar `listing_job.status = 'failed'`
2. Gravar `error_message` com detalhes
3. Setar `listings.status = 'failed'`
4. Seller vê o erro no dashboard e pode clicar "Tentar novamente"

---

## Monitoramento

Flower (UI do Celery) disponível em `http://localhost:5555` em dev.
Para adicionar ao Docker Compose quando necessário.

Métricas a monitorar:
- Jobs em fila por tipo
- Taxa de falha por task
- Tempo médio de execução
- Tokens ML próximos do vencimento
