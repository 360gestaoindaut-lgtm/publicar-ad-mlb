import csv
import io
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

_COLUMN_MAP: dict[str, str] = {
    # SKU
    "sku": "sku", "cod": "sku", "codigo": "sku", "codinterno": "sku",
    "referencia": "sku", "ref": "sku",
    # Descrição
    "descricao": "descricao", "descricao": "descricao", "xprod": "descricao",
    "descricaoproduto": "descricao", "nomeproduto": "descricao",
    "nome": "descricao", "produto": "descricao", "description": "descricao",
    # Marca
    "marca": "marca", "brand": "marca", "fabricante": "marca",
    # EAN
    "ean": "ean", "gtin": "ean", "codigobarras": "ean", "barcode": "ean", "cean": "ean",
    # NCM
    "ncm": "ncm",
    # Fiscal
    "origemfiscal": "fiscal_origin", "origem": "fiscal_origin",
    "icmscst": "icms_cst", "csticms": "icms_cst",
    "icmsrate": "icms_rate", "aliquotaicms": "icms_rate", "alicms": "icms_rate",
    "piscst": "pis_cst", "cstpis": "pis_cst",
    "cofinscst": "cofins_cst", "cstcofins": "cofins_cst",
    # Físico
    "pesokg": "peso_kg", "peso": "peso_kg", "weight": "peso_kg",
    "comprimentocm": "comprimento_cm", "comprimento": "comprimento_cm", "length": "comprimento_cm",
    "larguracm": "largura_cm", "largura": "largura_cm", "width": "largura_cm",
    "alturacm": "altura_cm", "altura": "altura_cm", "height": "altura_cm",
    # Custo
    "custo": "custo", "custounif": "custo", "custounidade": "custo",
    "costprice": "custo", "precodecompra": "custo",
}


def _normalize_col(name: str) -> str:
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    return ascii_str.lower().replace(" ", "").replace("_", "").replace(".", "").replace("-", "")


def _build_header_map(headers: list[str]) -> dict[int, str]:
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


def _detect_delimiter(first_line: str) -> str:
    return ";" if first_line.count(";") >= first_line.count(",") else ","


def parse_product_csv(content: bytes) -> list[dict]:
    text = content.decode("utf-8-sig", errors="replace")
    first_line = text.splitlines()[0] if text.strip() else ""
    delimiter = _detect_delimiter(first_line)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
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


def parse_product_xlsx(content: bytes) -> list[dict]:
    try:
        import openpyxl
    except ImportError as e:
        raise RuntimeError("openpyxl não está instalado.") from e

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


def normalize_product_row(raw: dict) -> dict:
    """Converte tipos de uma linha parseada. Retorna apenas campos presentes na linha."""
    out: dict = {}

    if "sku" in raw:
        out["sku"] = (raw["sku"] or "").strip()
    if "descricao" in raw:
        out["description"] = (raw["descricao"] or "").strip()
    if "marca" in raw:
        out["brand"] = raw["marca"] or None
    if "ean" in raw:
        out["ean"] = raw["ean"] or None
    if "ncm" in raw:
        out["ncm"] = raw["ncm"] or None
    if "fiscal_origin" in raw:
        out["fiscal_origin"] = _to_int(raw["fiscal_origin"])
    if "icms_cst" in raw:
        out["icms_cst"] = raw["icms_cst"] or None
    if "icms_rate" in raw:
        out["icms_rate"] = _to_decimal(raw["icms_rate"])
    if "pis_cst" in raw:
        out["pis_cst"] = raw["pis_cst"] or None
    if "cofins_cst" in raw:
        out["cofins_cst"] = raw["cofins_cst"] or None
    if "peso_kg" in raw:
        out["weight_kg"] = _to_decimal(raw["peso_kg"])
    if "comprimento_cm" in raw:
        out["length_cm"] = _to_int(raw["comprimento_cm"])
    if "largura_cm" in raw:
        out["width_cm"] = _to_int(raw["largura_cm"])
    if "altura_cm" in raw:
        out["height_cm"] = _to_int(raw["altura_cm"])
    if "custo" in raw:
        out["acquisition_cost"] = _to_decimal(raw["custo"])

    return out


def validate_product_row(normalized: dict) -> str | None:
    if not normalized.get("sku"):
        return "Campo 'sku' obrigatório está vazio"
    if "description" in normalized and not normalized["description"]:
        return "Campo 'descricao' não pode ser vazio"
    return None
