# SPEC-006 — Pipeline de Imagens

**Versão**: 1.0 | **Status**: Aprovado

---

## Fluxo completo

```
[FASE 3 - paralelo com coleta de atributos]

FreePik API              Cloudflare R2           ML API
     │                        │                    │
     │ 1. POST /ai/text-to-image                   │
     │    prompt: {produto}   │                    │
     │◀────────────────────── │                    │
     │ job_id                 │                    │
     │                        │                    │
     │ 2. GET /ai/text-to-image/{job_id}           │
     │    (poll até done)     │                    │
     │◀────────────────────── │                    │
     │ image_url (temp)       │                    │
     │                        │                    │
     │ 3. Download da imagem  │                    │
     │──────────────────────▶│                    │
     │                        │ 4. Upload para R2  │
     │                        │──────────────────▶│
     │                        │ url_r2             │
     │                        │                    │
     │                 5. POST /pictures/items/upload
     │                        │────────────────────▶
     │                        │   { source: url_r2 }
     │                        │                    │
     │                        │◀───────────────────│
     │                        │  { id: "MLB_PIC_ID" }
     │                        │                    │
     │             6. Salvar ml_picture_id no banco │
```

---

## Geração no FreePik

### Endpoint
**POST** `https://api.freepik.com/v1/ai/text-to-image`

**Headers:**
```
x-freepik-api-key: {FREEPIK_API_KEY}
Content-Type: application/json
```

**Body:**
```json
{
  "prompt": "{prompt_gerado}",
  "negative_prompt": "text, watermark, logo, blurry, low quality, distorted",
  "guidance_scale": 7,
  "num_inference_steps": 30,
  "num_images": 4,
  "image": {
    "size": "square_1_1"
  },
  "styling": {
    "style": "photo"
  }
}
```

**Prompt de geração de imagem:**
```
Professional product photo of {sku_brand} {model_from_description},
on pure white background, studio lighting, high resolution,
e-commerce style, no text, no watermark, no people
```

### Polling de resultado
**GET** `https://api.freepik.com/v1/ai/text-to-image/{task_id}`

Fazer poll a cada 3 segundos, timeout máximo de 90 segundos.

**Resposta quando pronto:**
```json
{
  "data": {
    "status": "COMPLETED",
    "generated": [
      { "base64": "..." },
      ...
    ]
  }
}
```

---

## Requisitos de imagem do Mercado Livre

Validar ANTES do upload ao ML:

| Requisito | Valor |
|---|---|
| Formato | JPG ou PNG |
| Tamanho mínimo | 500x500 pixels |
| Tamanho máximo | 10 MB |
| Fundo | Branco puro (#FFFFFF) recomendado para primeira imagem |
| Máx de imagens por anúncio | 12 |

---

## Upload para ML CDN

**POST** `https://api.mercadolibre.com/pictures/items/upload`

**Headers:**
```
Authorization: Bearer {access_token}
Content-Type: application/json
```

**Body:**
```json
{
  "source": "https://pub-SEU_ID.r2.dev/imagens/listing_uuid/img_1.jpg"
}
```

**Resposta:**
```json
{
  "id": "MLB123456789_012025",
  "url": "https://http2.mlstatic.com/D_NQ_NP_...",
  "secure_url": "https://http2.mlstatic.com/D_NQ_NP_...",
  "size": "500x500",
  "max_size": "1200x1200",
  "quality": ""
}
```

Salvar o campo `id` como `ml_picture_id` na tabela `listing_images`.

---

## Uso dos picture_ids no payload do anúncio

```json
"pictures": [
  { "id": "MLB123456789_012025" },
  { "id": "MLB987654321_012025" }
]
```

A ordem do array define a ordem das fotos no anúncio. A primeira imagem é a capa.

---

## Fluxo de aprovação pelo seller

1. Imagens geradas e enviadas para ML → status `uploaded`
2. Frontend exibe grade de imagens (até 4)
3. Seller pode:
   - Aprovar imagens (mínimo 1 obrigatório)
   - Rejeitar imagens individualmente
   - Reordenar (drag-and-drop) → atualiza `sort_order`
4. Apenas imagens aprovadas entram no payload final

---

## Tratamento de erros

| Cenário | Ação |
|---|---|
| FreePik timeout (90s) | Marcar job images como failed, retry disponível |
| Imagem < 500x500 | Descartar imagem, tentar próxima do lote |
| Upload ML falhou (5xx) | Retry 3x com backoff de 5s |
| Zero imagens aprovadas | Bloquear publicação, exibir alerta ao seller |
