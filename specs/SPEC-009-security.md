# SPEC-009 — Modelo de Segurança

**Versão**: 1.0 | **Status**: Aprovado

---

## Princípios

1. **Defense in depth**: múltiplas camadas — não confiar em apenas uma
2. **Least privilege**: cada componente acessa só o que precisa
3. **Secrets never in code**: tudo em env vars, nunca hardcoded
4. **Encrypt at rest**: tokens sensíveis sempre criptografados no banco
5. **Log sem dados sensíveis**: tokens, senhas e PII nunca nos logs

---

## Autenticação de usuários do sistema

- Senhas: **bcrypt** com work factor 12 (nunca MD5, SHA1 ou SHA256 puro)
- JWT access token: expiração **30 minutos**
- JWT refresh token: expiração **7 dias**, armazenado como cookie httpOnly no frontend
- Refresh token rotation: a cada renovação, emitir novo refresh token e invalidar o anterior
- Secret key JWT: mínimo 32 bytes aleatórios (`openssl rand -hex 32`)

---

## Tokens do Mercado Livre

- `access_token` e `refresh_token` ML: criptografados com **Fernet** antes de persistir
- `FERNET_KEY` fica apenas na env var, nunca no banco
- Fernet usa AES-128-CBC + HMAC-SHA256 — simétrico e revogável
- Geração: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- Tokens ML **nunca aparecem em logs**, respostas de API ou payloads para o frontend

---

## Chaves de API externas (FreePik, Gemini, etc.)

- Apenas em variáveis de ambiente
- Nunca retornadas por nenhum endpoint da API
- Em produção: usar secret manager (Railway Secrets, Cloudflare env)

---

## CORS

Whitelist explícita — **nunca `*`** em produção:

```python
# backend/app/core/config.py
ALLOWED_ORIGINS = [
    "http://localhost:3000",          # dev
    "https://app.seudominio.com",    # produção
]
```

---

## Rate Limiting

Aplicado no backend (middleware FastAPI via `slowapi`):

| Endpoint | Limite |
|---|---|
| `POST /auth/login` | 10 req/min por IP |
| `POST /auth/refresh` | 20 req/min por IP |
| `GET /auth/ml/connect` | 5 req/min por usuário |
| `POST /listings` | 30 req/min por usuário |
| Demais endpoints | 120 req/min por usuário |

---

## Validação de input

- **Backend**: todos os inputs validados via **Pydantic v2** (modelos tipados)
- **Frontend**: validação com **Zod** antes de enviar ao backend
- Queries ao banco: sempre via **SQLAlchemy ORM** (parâmetros vinculados — sem SQL raw concatenado)
- Upload de arquivos: tamanho máximo e tipo MIME validados antes de processar

---

## Proteção contra ataques comuns

| Ataque | Proteção |
|---|---|
| XSS | Cookies httpOnly; React escapa HTML por padrão; CSP header |
| CSRF | Cookie SameSite=Strict + state token no OAuth ML |
| SQL Injection | SQLAlchemy ORM com bind params |
| Brute force | Rate limiting em `/auth/login` |
| Secrets exposure | Env vars; `.env` no `.gitignore`; nada hardcoded |
| Path traversal | Nenhum input de usuário compõe caminhos de arquivo |

---

## Headers de segurança HTTP (backend)

```python
# Adicionar via middleware FastAPI
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: default-src 'self'
Referrer-Policy: strict-origin-when-cross-origin
```

---

## Audit log

Eventos a registrar (tabela `audit_logs` — V2, mas estrutura preparada):

| Evento | Dados gravados |
|---|---|
| Login bem-sucedido | user_id, IP, timestamp |
| Login falho | email tentado, IP, timestamp |
| Conta ML conectada | user_id, ml_user_id, timestamp |
| Anúncio publicado | user_id, listing_id, mlb_id, timestamp |
| Anúncio deletado | user_id, listing_id, timestamp |

**Regra**: nunca gravar senhas, tokens ou chaves de API no audit log.

---

## Checklist de segurança antes de ir para produção

- [ ] `SECRET_KEY` gerada com `openssl rand -hex 32`
- [ ] `FERNET_KEY` gerada com Python Fernet
- [ ] CORS configurado com domínio real (não localhost)
- [ ] HTTPS obrigatório (Vercel e Railway já fornecem)
- [ ] Rate limiting ativo
- [ ] `.env` **nunca** commitado no git
- [ ] pgAdmin desabilitado em produção (remover do docker-compose.prod.yml)
- [ ] Logs sem dados sensíveis verificados
- [ ] `DEBUG=False` no backend em produção
