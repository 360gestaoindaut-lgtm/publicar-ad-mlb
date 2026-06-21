import csv
import io
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

# Mapeamento normalizado de nomes de colunas para campos canônicos
_COLUMN_MAP: dict[str, str] = {
    # SKU
    "sku": "sku", "cod": "sku", "codigo": "sku", "codinternо": "sku",
    "codinterno": "sku", "referencia": "sku", "ref": "sku",
    # Descrição
    "descricao": "descricao", "descricão": "descricao", "xprod": "descricao",
    "descricaoproduto": "descricao", "nomeproduto": "descricao", "nome": "descricao",
    "produto": "descricao", "description": "descricao",
    # EAN
    "ean": "ean", "gtin": "ean", "codigobarras": "ean", "barcode": "ean",
    "cean": "ean",
    # Marca
    "marca": "marca", "brand": "marca", "fabricante": "marca",
    # SEO
    "seocontext": "seo_context", "contexto": "seo_context", "seo": "seo_context",
    "contextoseo": "seo_context", "palavraschave": "seo_context",
    # Preço
    "preco": "preco", "preço": "preco", "price": "preco", "valorvenda": "preco",
    "prv": "preco",
    # Estoque
    "estoque": "estoque", "qty": "estoque", "quantidade": "estoque",
    "saldo": "estoque", "stock": "estoque",
    # Condição
    "condicao": "condicao", "condição": "condicao", "condition": "condicao",
    # Tipo de anúncio
    "tipoanuncio": "tipo_anuncio", "tipo": "tipo_anuncio", "listingtype": "tipo_anuncio",
    # Custo (pricing infrastructure)
    "custo": "custo", "custounif": "custo", "custounidade": "custo",
    "costprice": "custo", "precodecompra": "custo",
    # Dimensões e peso
    "pesokg": "peso_kg", "peso": "peso_kg", "weight": "peso_kg",
    "comprimentocm": "comprimento_cm", "comprimento": "comprimento_cm", "length": "comprimento_cm",
    "larguracm": "largura_cm", "largura": "largura_cm", "width": "largura_cm",
    "alturacm": "altura_cm", "altura": "altura_cm", "height": "altura_cm",
    # Origem fiscal
    "origemfiscal": "origem_fiscal", "cst": "origem_fiscal", "origem": "origem_fiscal",
}


def _normalize_col(name: str) -> str:
    """Normaliza nome de coluna: strip, lowercase, remove acentos, remove espaços e underscores."""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    return ascii_str.lower().replace(" ", "").replace("_", "").replace(".", "").replace("-", "")


def _build_header_map(headers: list[str]) -> dict[int, str]:
    """Mapeia índice de coluna → campo canônico."""
    result = {}
    for i, h in enumerate(headers):
        key = _normalize_col(h)
        if key in _COLUMN_MAP:
            result[i] = _COLUMN_MAP[key]
    return result


def _to_decimal(val: Any) -> Decimal | None:
    if val is None or str(val).strip() == "":
        return None
    try:
        return Decimal(str(val).replace(",", ".").replace("R$", "").strip())
    except InvalidOperation:
        return None


def _to_int(val: Any) -> int | None:
    if val is None or str(val).strip() == "":
        return None
    try:
        return int(str(val).strip().split(".")[0])
    except (ValueError, TypeError):
        return None


def parse_csv(content: bytes) -> list[dict]:
    """Parse CSV bytes → list de dicts com campos canônicos."""
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return []

    header_map = _build_header_map(rows[0])
    result = []
    for row in rows[1:]:
        if not any(cell.strip() for cell in row):
            continue
        record: dict = {}
        for idx, field in header_map.items():
            val = row[idx].strip() if idx < len(row) else ""
            record[field] = val or None
        result.append(record)
    return result


def parse_xlsx(content: bytes) -> list[dict]:
    """Parse XLSX bytes → list de dicts com campos canônicos."""
    try:
        import openpyxl
    except ImportError as e:
        raise RuntimeError("openpyxl não está instalado. Adicione-o ao requirements.txt.") from e

    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if not rows:
        return []

    headers = [str(h) if h is not None else "" for h in rows[0]]
    header_map = _build_header_map(headers)
    result = []
    for row in rows[1:]:
        if not any(cell is not None and str(cell).strip() for cell in row):
            continue
        record: dict = {}
        for idx, field in header_map.items():
            val = row[idx] if idx < len(row) else None
            record[field] = str(val).strip() if val is not None else None
        result.append(record)
    return result


def normalize_row(raw: dict) -> dict:
    """Normaliza e converte tipos de uma linha parseada."""
    condicao = (raw.get("condicao") or "new").lower()
    if condicao in ("usado", "used", "u"):
        condicao = "used"
    else:
        condicao = "new"

    return {
        "sku": raw.get("sku") or "",
        "descricao": raw.get("descricao") or "",
        "ean": raw.get("ean") or None,
        "marca": raw.get("marca") or "Sem marca",
        "seo_context": raw.get("seo_context") or None,
        "preco": _to_decimal(raw.get("preco")),
        "estoque": _to_int(raw.get("estoque")) or 1,
        "condicao": condicao,
        "tipo_anuncio": raw.get("tipo_anuncio") or "gold_special",
        # Pricing infrastructure fields (stored in raw_data, not used yet)
        "custo": _to_decimal(raw.get("custo")),
        "peso_kg": _to_decimal(raw.get("peso_kg")),
        "comprimento_cm": _to_int(raw.get("comprimento_cm")),
        "largura_cm": _to_int(raw.get("largura_cm")),
        "altura_cm": _to_int(raw.get("altura_cm")),
        "origem_fiscal": _to_int(raw.get("origem_fiscal")),
    }


def validate_row(normalized: dict) -> str | None:
    """Retorna mensagem de erro ou None se válido."""
    if not normalized["sku"]:
        return "Campo 'sku' obrigatório está vazio"
    if not normalized["descricao"]:
        return "Campo 'descricao' obrigatório está vazio"
    if normalized["preco"] is not None and normalized["preco"] <= 0:
        return f"Preço inválido: {normalized['preco']}"
    return None
