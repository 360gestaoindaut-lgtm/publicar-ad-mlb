# SPEC-003 — OAuth com Mercado Livre

**Versão**: 1.0 | **Status**: Aprovado

---

## Visão geral

O Mercado Livre usa OAuth 2.0 com Authorization Code Flow (sem PKCE obrigatório,
mas implementaremos state anti-CSRF). O seller autoriza uma vez; o sistema mantém
os tokens renovados automaticamente.

---

## Fluxo detalhado

```
Seller                  Frontend              Backend               ML Auth Server
  │                        │                     │                       │
  │ Clica "Conectar ML"    │                     │                       │
  │───────────────────────▶│                     │                       │
  │                        │ GET /auth/ml/connect │                       │
  │                        │────────────────────▶│                       │
  │                        │                     │ Gera state (UUID)     │
  │                        │                     │ Salva state no Redis  │
  │                        │                     │ (TTL 10 min)          │
  │                        │ { auth_url }        │                       │
  │                        │◀────────────────────│                       │
  │ Redirect para ML       │                     │                       │
  │◀───────────────────────│                     │                       │
  │                        │                     │                       │
  │ Seller autoriza o app  │                     │                       │
  │───────────────────────────────────────────────────────────────────▶│
  │                        │                     │                       │
  │ Redirect callback com code + state            │                       │
  │─────────────────────────────────────────────▶│                       │
  │                        │                     │ Valida state no Redis │
  │                        │                     │ POST /oauth/token     │
  │                        │                     │──────────────────────▶│
  │                        │                     │ { access_token,       │
  │                        │                     │   refresh_token,      │
  │                        │                     │   expires_in }        │
  │                        │                     │◀──────────────────────│
  │                        │                     │ Criptografa tokens    │
  │                        │                     │ Salva em sellers      │
  │                        │                     │ Redirect frontend     │
  │◀─────────────────────────────────────────────│                       │
```

---

## Configuração do app ML

Valores necessários no Mercado Livre Developers (https://developers.mercadolivre.com.br):

| Campo | Valor |
|---|---|
| Nome do App | Publicar AD MLB |
| Redirect URI (dev) | `http://localhost:8000/api/v1/auth/ml/callback` |
| Redirect URI (prod) | `https://api.seudominio.com/api/v1/auth/ml/callback` |
| Scopes | `read`, `write`, `offline_access` |

Capture e salve no `.env`:
- `ML_APP_ID` → "App ID" no painel ML
- `ML_CLIENT_SECRET` → "Secret Key" no painel ML

---

## URL de autorização ML

```
https://auth.mercadolivre.com.br/authorization
  ?response_type=code
  &client_id={ML_APP_ID}
  &redirect_uri={ML_REDIRECT_URI}
  &state={uuid_gerado}
```

---

## Troca do code por tokens

**POST** `https://api.mercadolibre.com/oauth/token`

```
grant_type=authorization_code
&client_id={ML_APP_ID}
&client_secret={ML_CLIENT_SECRET}
&code={code_recebido}
&redirect_uri={ML_REDIRECT_URI}
```

**Resposta:**
```json
{
  "access_token": "APP_USR-...",
  "token_type": "bearer",
  "expires_in": 21600,
  "scope": "offline_access read write",
  "user_id": 123456789,
  "refresh_token": "TG-..."
}
```

---

## Renovação automática

O `access_token` ML expira em **6 horas**. O backend renovará proativamente:

1. Celery Beat roda `task_refresh_ml_tokens` a cada **5 horas**
2. A task busca todos os sellers com `token_expires_at < now() + 1h`
3. Para cada seller: POST `/oauth/token` com `grant_type=refresh_token`
4. Atualiza `access_token_enc`, `refresh_token_enc` e `token_expires_at`

**POST** `https://api.mercadolibre.com/oauth/token`
```
grant_type=refresh_token
&client_id={ML_APP_ID}
&client_secret={ML_CLIENT_SECRET}
&refresh_token={refresh_token_descriptografado}
```

---

## Segurança dos tokens

- Tokens **nunca** ficam em texto plano no banco
- Criptografia: **Fernet** (AES-128-CBC + HMAC-SHA256) com chave em `FERNET_KEY`
- Tokens **nunca** aparecem em logs
- `state` anti-CSRF armazenado no Redis com TTL de 10 minutos
- Em caso de falha na renovação: marcar seller como `is_active=false` e notificar

---

## Dependência de inicialização

Antes de qualquer funcionalidade do sistema estar disponível para o seller,
o passo **Fase 1** (conectar conta ML) deve ser concluído com sucesso.
O frontend bloqueia o acesso ao pipeline enquanto `ml_connected = false`.
