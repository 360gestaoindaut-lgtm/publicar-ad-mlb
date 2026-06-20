# SPEC-004 — Serviço de IA (Títulos e Descrições)

**Versão**: 1.0 | **Status**: Aprovado

---

## Responsabilidade

Gerar, via API de IA (Gemini ou Claude), dois artefatos:
1. **Título** do anúncio (máx 60 caracteres, otimizado para ML)
2. **Descrição rica** em HTML (após atributos preenchidos)

---

## Abstração de provider

O sistema NÃO chama Gemini ou Claude diretamente nos services.
Existe uma classe `AIProvider` abstrata com implementações `GeminiProvider` e `ClaudeProvider`.
O provider ativo é selecionado pela env var `AI_PROVIDER`.

```
services/ai/
  __init__.py
  base.py          classe abstrata AIProvider
  gemini.py        implementação Gemini
  claude.py        implementação Claude
  prompts.py       templates de prompt (strings)
  service.py       lógica de negócio (chama o provider)
```

---

## Geração de Título

### Prompt template

```
Você é um especialista em SEO para o Mercado Livre Brasil.
Crie 3 variações de título para um anúncio do produto abaixo.

REGRAS OBRIGATÓRIAS:
- Máximo 60 caracteres por título (incluindo espaços)
- Comece com o nome do produto mais relevante para busca
- Inclua marca, modelo e característica principal
- Não use: pontuação desnecessária, maiúsculas em excesso, palavras proibidas ML
- Palavras proibidas ML: "Melhor", "Promoção", "Oferta", "Barato", "Grátis", "Desconto"
- Priorize termos que compradores realmente buscam

PRODUTO:
Descrição do ERP: {sku_description}
Marca: {sku_brand}
Condição: {condition}

Responda EXCLUSIVAMENTE em JSON válido, sem markdown:
{
  "titles": [
    {"text": "título 1", "score": 9.2, "rationale": "motivo breve"},
    {"text": "título 2", "score": 8.7, "rationale": "motivo breve"},
    {"text": "título 3", "score": 8.1, "rationale": "motivo breve"}
  ]
}
```

### Validações pós-geração
- Remover títulos > 60 caracteres
- Remover títulos que contenham palavras proibidas ML
- Ordenar por `score` decrescente
- Se menos de 1 título válido: marcar job como failed e notificar

---

## Geração de Descrição Rica

### Prompt template

```
Você é um redator especialista em e-commerce para o Mercado Livre Brasil.
Crie uma descrição de produto atrativa e informativa para o anúncio abaixo.

REGRAS:
- Use HTML simples: <h2>, <p>, <ul>, <li>, <strong>
- Não use: scripts, CSS inline, iframes, tabelas complexas
- Estrutura: [Parágrafo introdutório] > [Benefícios principais] > [Especificações] > [Informações adicionais]
- Tom: profissional, direto, focado em benefícios para o comprador
- Idioma: português brasileiro
- Extensão: entre 300 e 800 palavras no texto (sem contar as tags HTML)

DADOS DO PRODUTO:
Título do anúncio: {selected_title}
Marca: {sku_brand}
Condição: {condition}
Descrição original: {sku_description}

ATRIBUTOS CONFIRMADOS:
{attributes_formatted}

Responda EXCLUSIVAMENTE com o HTML, sem markdown, sem ```html, sem explicações.
```

### Formatação dos atributos no prompt
```
- Capacidade de Armazenamento: 256 GB
- Cor: Azul
- Memória RAM: 8 GB
```

---

## Configuração de chamada à API

| Parâmetro | Título | Descrição |
|---|---|---|
| Temperature | 0.7 | 0.6 |
| Max tokens | 500 | 2000 |
| Timeout | 20s | 45s |
| Retries | 3 | 3 |
| Retry delay | 2s, 4s, 8s | 2s, 4s, 8s |

---

## Tratamento de erros

| Cenário | Ação |
|---|---|
| API retorna JSON inválido | Retry imediato (até 3x) |
| API indisponível (5xx) | Retry com backoff exponencial |
| Rate limit (429) | Aguardar `Retry-After` header + retry |
| Timeout | Retry imediato |
| 3 tentativas falharam | Marcar job como `failed`, setar `error_message` |
| JSON válido mas sem títulos válidos | Marcar job como `failed` com motivo |

---

## Custo estimado (referência, pode variar)

| Operação | Tokens aprox. | Provider |
|---|---|---|
| Geração de título | ~400 in + 200 out | Gemini Flash ou Haiku |
| Geração de descrição | ~800 in + 1500 out | Gemini Flash ou Sonnet |

Usar modelos mais baratos (Flash/Haiku) por padrão; Sonnet/Pro apenas se configurado.
