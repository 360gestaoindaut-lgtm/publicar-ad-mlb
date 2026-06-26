import ExcelJS from "exceljs"

const FONT = { name: "Calibri", size: 11 } as const
const FONT_BOLD = { name: "Calibri", size: 11, bold: true } as const

async function triggerXlsxDownload(wb: ExcelJS.Workbook, filename: string) {
  const buffer = await wb.xlsx.writeBuffer()
  const blob = new Blob([buffer], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// Pré-formata um range de células como texto com fonte padrão.
// Necessário para EAN/NCM — evita que o Excel converta em notação científica.
function applyTextColumn(
  ws: ExcelJS.Worksheet,
  col: number,
  fromRow: number,
  toRow: number
) {
  for (let r = fromRow; r <= toRow; r++) {
    const cell = ws.getCell(r, col)
    cell.numFmt = "@"
    cell.font = FONT
  }
}

export async function downloadProductTemplate() {
  const wb = new ExcelJS.Workbook()
  wb.creator = "Publicar AD MLB"

  const ws = wb.addWorksheet("Produtos")

  ws.columns = [
    { key: "sku",           width: 14 },
    { key: "descricao",     width: 48 },
    { key: "marca",         width: 16 },
    { key: "modelo",        width: 22 },
    { key: "ean",           width: 18 },
    { key: "ncm",           width: 13 },
    { key: "origemfiscal",  width: 14 },
    { key: "icmscst",       width: 11 },
    { key: "icmsrate",      width: 12 },
    { key: "piscst",        width: 11 },
    { key: "cofinscst",     width: 12 },
    { key: "pesokg",        width: 11 },
    { key: "comprimentocm", width: 15 },
    { key: "larguracm",     width: 13 },
    { key: "alturacm",      width: 11 },
    { key: "custo",           width: 13 },
    { key: "grupo_produto",   width: 15 },
    { key: "referencia_tecnica", width: 20 },
    { key: "aplicacao_veiculo",  width: 25 },
    { key: "cor",             width: 12 },
    { key: "tamanho",         width: 10 },
    { key: "capacidade",      width: 12 },
    { key: "material",        width: 15 },
    { key: "genero",          width: 12 },
  ]

  // Cabeçalho
  const headerRow = ws.addRow([
    "sku", "descricao", "marca", "modelo", "ean", "ncm",
    "origemfiscal", "icmscst", "icmsrate", "piscst", "cofinscst",
    "pesokg", "comprimentocm", "larguracm", "alturacm", "custo",
    "grupo_produto", "referencia_tecnica", "aplicacao_veiculo",
    "cor", "tamanho", "capacidade", "material", "genero",
  ])
  headerRow.eachCell((cell) => {
    cell.font = FONT_BOLD
    cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFE2E8F0" } }
  })

  // Linha de exemplo
  const exampleRow = ws.addRow([
    "SKU001", "Smartphone Samsung Galaxy A54 128GB Preto", "Samsung", "Galaxy A54 128GB",
    "7892509082679", "8517120019",
    "0", "00", "12", "07", "07",
    "0,185", "16", "8", "1", "1299,90",
    "", "", "", "", "", "", "", "",
  ])
  exampleRow.eachCell((cell) => { cell.font = FONT })

  // Colunas EAN (5) e NCM (6): texto para linhas preenchíveis (modelo agora na col 4)
  applyTextColumn(ws, 5, 1, 201)
  applyTextColumn(ws, 6, 1, 201)

  // Fonte padrão para células vazias das demais colunas
  for (let c = 1; c <= 24; c++) {
    if (c === 5 || c === 6) continue
    for (let r = 3; r <= 201; r++) {
      ws.getCell(r, c).font = FONT
    }
  }

  await triggerXlsxDownload(wb, "modelo-produtos.xlsx")
}

export async function downloadListingTemplate() {
  const wb = new ExcelJS.Workbook()
  wb.creator = "Publicar AD MLB"

  const ws = wb.addWorksheet("Anuncios")

  ws.columns = [
    { key: "sku",     width: 14 },
    { key: "preco",   width: 12 },
    { key: "estoque", width: 11 },
    { key: "tipo",    width: 12 },
    { key: "condicao", width: 11 },
    { key: "seo",     width: 52 },
  ]

  // Cabeçalho
  const headerRow = ws.addRow(["sku", "preco", "estoque", "tipo", "condicao", "seo"])
  headerRow.eachCell((cell) => {
    cell.font = FONT_BOLD
    cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFE2E8F0" } }
  })

  // Linha de exemplo
  const exampleRow = ws.addRow([
    "SKU001", "1799,90", "5", "classico", "novo",
    "smartphone android 128gb desbloqueado",
  ])
  exampleRow.eachCell((cell) => { cell.font = FONT })

  // Fonte padrão para células vazias
  for (let c = 1; c <= 6; c++) {
    for (let r = 3; r <= 201; r++) {
      ws.getCell(r, c).font = FONT
    }
  }

  await triggerXlsxDownload(wb, "modelo-anuncios.xlsx")
}
