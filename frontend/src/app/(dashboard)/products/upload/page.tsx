"use client"

import { useRef, useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { uploadProducts } from "@/lib/api/products"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { toast } from "sonner"
import { ArrowLeft, CheckCircle, Download, FileSpreadsheet, Loader2, Upload, XCircle } from "lucide-react"
import Link from "next/link"
import type { ProductUploadResult } from "@/types/product"
import { downloadProductTemplate } from "@/lib/download-template"

export default function ProductUploadPage() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [result, setResult] = useState<ProductUploadResult | null>(null)

  const mutation = useMutation({
    mutationFn: (file: File) => uploadProducts(file),
    onSuccess: (data) => {
      setResult(data)
      if (data.rejected === 0) {
        toast.success(`${data.accepted} produto${data.accepted !== 1 ? "s" : ""} importado${data.accepted !== 1 ? "s" : ""} com sucesso!`)
      } else {
        toast.warning(`${data.accepted} aceitos, ${data.rejected} rejeitados.`)
      }
    },
    onError: (err: Error) => {
      toast.error(err.message || "Erro ao processar arquivo")
    },
  })

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] ?? null
    setSelectedFile(file)
    setResult(null)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedFile) return
    mutation.mutate(selectedFile)
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-6">
        <Link
          href="/products"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-4"
        >
          <ArrowLeft className="w-4 h-4" />
          Catálogo de produtos
        </Link>
        <h1 className="text-2xl font-bold text-foreground">Importar planilha de produtos</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Envie um arquivo CSV ou XLSX com os dados do catálogo. Produtos existentes serão atualizados pelo SKU.
        </p>
      </div>

      <Card className="mb-6">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Colunas reconhecidas</CardTitle>
            <button
              type="button"
              onClick={() => downloadProductTemplate()}
              className="inline-flex items-center gap-1.5 text-xs text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300 font-medium transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
              Baixar modelo
            </button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-x-8 gap-y-1 text-sm">
            {[
              ["sku *", "Código interno (obrigatório)"],
              ["descricao *", "Descrição / xProd (obrigatório)"],
              ["marca", "Fabricante / Brand"],
              ["ean", "GTIN / Código de barras"],
              ["ncm", "Nomenclatura Comum Mercosul"],
              ["origemfiscal", "Origem fiscal (0–8)"],
              ["icmscst", "CST do ICMS"],
              ["icmsrate", "Alíquota ICMS (%)"],
              ["piscst", "CST do PIS"],
              ["cofinscst", "CST do COFINS"],
              ["pesokg", "Peso da embalagem (kg)"],
              ["comprimentocm", "Comprimento (cm)"],
              ["larguracm", "Largura (cm)"],
              ["alturacm", "Altura (cm)"],
              ["custo", "Custo de aquisição (R$)"],
            ].map(([col, desc]) => (
              <div key={col} className="flex gap-2 py-0.5">
                <span className="font-mono text-xs text-muted-foreground w-32 shrink-0">{col}</span>
                <span className="text-xs text-muted-foreground">{desc}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div
          onClick={() => inputRef.current?.click()}
          className="border-2 border-dashed border-border rounded-lg p-8 text-center cursor-pointer hover:border-slate-400 transition-colors"
        >
          <FileSpreadsheet className="w-10 h-10 mx-auto mb-3 text-muted-foreground" />
          {selectedFile ? (
            <>
              <p className="font-medium text-foreground">{selectedFile.name}</p>
              <p className="text-xs text-muted-foreground mt-1">
                {(selectedFile.size / 1024).toFixed(0)} KB — clique para trocar
              </p>
            </>
          ) : (
            <>
              <p className="font-medium text-foreground">Clique para selecionar o arquivo</p>
              <p className="text-xs text-muted-foreground mt-1">.csv ou .xlsx · máx. 10 MB</p>
            </>
          )}
          <input
            ref={inputRef}
            type="file"
            accept=".csv,.xlsx"
            onChange={handleFileChange}
            className="sr-only"
          />
        </div>

        <Button
          type="submit"
          className="w-full"
          disabled={!selectedFile || mutation.isPending}
        >
          {mutation.isPending ? (
            <>
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              Processando...
            </>
          ) : (
            <>
              <Upload className="w-4 h-4 mr-2" />
              Importar produtos
            </>
          )}
        </Button>
      </form>

      {result && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="text-base">Resultado da importação</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="rounded-lg bg-muted p-3">
                <p className="text-2xl font-bold text-foreground">{result.total}</p>
                <p className="text-xs text-muted-foreground mt-0.5">Total</p>
              </div>
              <div className="rounded-lg bg-green-50 dark:bg-green-900/20 p-3">
                <p className="text-2xl font-bold text-green-700 dark:text-green-400">{result.accepted}</p>
                <p className="text-xs text-green-600 dark:text-green-500 mt-0.5">Aceitos</p>
              </div>
              <div className={`rounded-lg p-3 ${result.rejected > 0 ? "bg-red-50 dark:bg-red-900/20" : "bg-muted"}`}>
                <p className={`text-2xl font-bold ${result.rejected > 0 ? "text-red-700 dark:text-red-400" : "text-foreground"}`}>
                  {result.rejected}
                </p>
                <p className={`text-xs mt-0.5 ${result.rejected > 0 ? "text-red-600 dark:text-red-500" : "text-muted-foreground"}`}>
                  Rejeitados
                </p>
              </div>
            </div>

            {result.rejected === 0 && (
              <div className="flex items-center gap-2 text-green-700 dark:text-green-400 text-sm">
                <CheckCircle className="w-4 h-4" />
                Todos os produtos foram importados com sucesso.
              </div>
            )}

            {result.errors.length > 0 && (
              <div className="space-y-1.5 mt-2">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                  Erros por linha
                </p>
                <div className="max-h-48 overflow-y-auto space-y-1">
                  {result.errors.map((e, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs text-red-600 dark:text-red-400">
                      <XCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                      <span>
                        <span className="font-mono">Linha {e.row}</span>
                        {e.sku && <span className="text-muted-foreground"> · SKU {e.sku}</span>}
                        {" — "}{e.error}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
