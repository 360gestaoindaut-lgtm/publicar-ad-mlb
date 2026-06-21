def build_title_prompt(sku_description: str, sku_brand: str, condition: str) -> str:
    condition_pt = "Novo" if condition == "new" else "Usado"
    return f"""Você é um especialista em SEO para o Mercado Livre Brasil.
Crie 3 variações de título para um anúncio do produto abaixo.

REGRAS OBRIGATÓRIAS:
- Máximo 60 caracteres por título (incluindo espaços)
- Comece com o nome do produto mais relevante para busca
- Inclua marca, modelo e característica principal
- Não use: pontuação desnecessária, maiúsculas em excesso
- Palavras PROIBIDAS pelo ML: Melhor, Promoção, Oferta, Barato, Grátis, Desconto
- Priorize termos que compradores realmente buscam no Brasil

PRODUTO:
Descrição do ERP: {sku_description}
Marca: {sku_brand}
Condição: {condition_pt}

Responda EXCLUSIVAMENTE em JSON válido, sem markdown, sem ```json:
{{"titles": [{{"title": "título aqui", "score": 9.2, "rationale": "motivo breve"}}, {{"title": "título aqui", "score": 8.7, "rationale": "motivo breve"}}, {{"title": "título aqui", "score": 8.1, "rationale": "motivo breve"}}]}}"""


def build_image_prompt_request(brand: str, title: str, description: str) -> str:
    return f"""You are an expert prompt engineer for Google Imagen 4 AI image generation.

Write a concise English prompt (max 80 words) to generate a professional e-commerce product photo.
Rules:
- The image must show ONLY the product, isolated on a pure white background with studio lighting
- Describe the product's exact physical appearance: shape, material, color, size, key features
- Never mention people, clothing, scenes, or unrelated objects
- Start with the product type in English (e.g. "ball bearing", "smartphone", "power drill")

Product:
Brand: {brand}
Title: {title}
Description: {description}

Output ONLY the Imagen prompt. No explanations, no markdown, no quotes."""


def build_description_prompt(listing_data: dict) -> str:
    attrs_text = "\n".join(
        f"- {a['attribute_name']}: {a['value_name']}"
        for a in listing_data.get("attributes", [])
        if a.get("value_name")
    )
    condition_pt = "Novo" if listing_data.get("condition") == "new" else "Usado"

    return f"""Você é um redator especialista em e-commerce para o Mercado Livre Brasil.
Crie uma descrição de produto atrativa e informativa para o anúncio abaixo.

REGRAS:
- Use HTML simples: <h2>, <p>, <ul>, <li>, <strong>
- Não use: scripts, CSS inline, iframes, tabelas complexas
- Estrutura: parágrafo introdutório > benefícios principais > especificações > informações adicionais
- Tom: profissional, direto, focado em benefícios para o comprador
- Idioma: português brasileiro
- Extensão: entre 200 e 400 palavras no texto (sem contar as tags HTML)

DADOS DO PRODUTO:
Título do anúncio: {listing_data.get("selected_title") or listing_data.get("title")}
Marca: {listing_data.get("sku_brand") or listing_data.get("brand")}
Condição: {condition_pt}
Descrição original: {listing_data.get("sku_description") or listing_data.get("description")}

ATRIBUTOS CONFIRMADOS:
{attrs_text or "Não informados"}

Responda EXCLUSIVAMENTE com o HTML, sem markdown, sem ```html, sem explicações."""
