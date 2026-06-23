"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import {
  uploadBatch,
  listBatches,
  getBatch,
  type BatchImportOut,
  type BatchImportDetail,
} from "@/lib/api/import"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { toast } from "sonner"
import {
  Upload,
  FileSpreadsheet,
  Loader2,
  CheckCircle,
  XCircle,
  Clock,
  ChevronDown,
  ChevronRight,
  Download,
  Link as LinkIcon,
} from "lucide-react"
import { formatDistanceToNow } from "date-fns"
import { ptBR } from "date-fns/locale"
import Link from "next/link"
import { downloadListingTemplate } from "@/lib/download-template"

const STATUS_LABEL: Record<string, string> = {
  pending: "Na fila",
  running: "Processando",
  done: "Concluído",
  partial_error: "Concluído c/ erros",
  error: "Falhou",
}

const ROW_STATUS_LABEL: Record<string, string> = {
  pending: "Na fila",
  processing: "Processando",
  done: "Concluído",
  failed: "Falhou",
}

function ProgressBar({ value, total }: { value: number; total: number }) {
  const pct = total === 0 ? 0 : Math.round((value / total) * 100)
  return (
    <div className="w-full bg-slate-100 rounded-full h-2 mt-2">
      <div
        className="bg-blue-500 h-2 rounded-full transition-all duration-500"
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

function BatchCard({ batch: initial }: { batch: BatchImportOut }) {
  const [expanded, setExpanded] = useState(false)
  const isActive = initial.status === "pending" || initial.status === "running"

  const { data: detail } = useQuery<BatchImportDetail>({
    queryKey: ["batch", initial.id],
    queryFn: () => getBatch(initial.id),
    enabled: expanded,
    refetchInterval: isActive ? 3000 : false,
  })

  const { data: batch } = useQuery<BatchImportOut>({
    queryKey: ["batch-summary", initial.id],
    queryFn: () => getBatch(initial.id).then((d) => d),
    initialData: initial,
    refetchInterval: isActive ? 3000 : false,
  })

  const done = (batch?.processed_rows ?? 0) + (batch?.failed_rows ?? 0)
  const total = batch?.total_rows ?? 0

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <FileSpreadsheet className="w-4 h-4 text-green-600 flex-shrink-0" />
              <span className="font-medium text-foreground truncate text-sm">{batch?.filename}</span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              {formatDistanceToNow(new Date(batch?.created_at ?? initial.created_at), {
                addSuffix: true,
                locale: ptBR,
              })}
            </p>
          </div>
          <span
            className={`text-xs font-medium px-2 py-0.5 rounded-full flex-shrink-0 ${
              batch?.status === "done"
                ? "bg-green-100 text-green-700"
                : batch?.status === "partial_error"
                ? "bg-amber-100 text-amber-700"
                : batch?.status === "error"
                ? "bg-red-100 text-red-700"
                : "bg-blue-100 text-blue-700"
            }`}
          >
            {STATUS_LABEL[batch?.status ?? "pending"] ?? batch?.status}
          </span>
        </div>

        <div className="flex items-center gap-4 text-xs text-slate-500 mt-1">
          <span>{total} SKUs</span>
          <span className="text-green-600 font-medium">{batch?.processed_rows ?? 0} criados</span>
          {(batch?.failed_rows ?? 0) > 0 && (
            <span className="text-red-600 font-medium">{batch?.failed_rows} falhas</span>
          )}
        </div>

        {isActive && <ProgressBar value={done} total={total} />}
      </CardHeader>

      <CardContent className="pt-0">
        <button
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600 transition-colors"
        >
          {expanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
          {expanded ? "Ocultar linhas" : "Ver linhas"}
        </button>

        {expanded && detail && (
          <div className="mt-3 border rounded-md overflow-hidden">
            <table className="w-full text-xs">
              <thead className="bg-muted text-muted-foreground">
                <tr>
                  <th className="text-left px-3 py-2 font-medium">#</th>
                  <th className="text-left px-3 py-2 font-medium">SKU</th>
                  <th className="text-left px-3 py-2 font-medium">Status</th>
                  <th className="text-left px-3 py-2 font-medium">Anúncio</th>
                  <th className="text-left px-3 py-2 font-medium">Erro</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {detail.rows.map((row) => (
                  <tr key={row.id} className="hover:bg-muted/50">
                    <td className="px-3 py-2 text-slate-400">{row.row_number}</td>
                    <td className="px-3 py-2 font-mono text-foreground">{row.sku}</td>
                    <td className="px-3 py-2">
                      {row.status === "done" || row.status === "processing" ? (
                        <span className="flex items-center gap-1 text-green-600">
                          <CheckCircle className="w-3 h-3" />
                          {ROW_STATUS_LABEL[row.status]}
                        </span>
                      ) : row.status === "failed" ? (
                        <span className="flex items-center gap-1 text-red-600">
                          <XCircle className="w-3 h-3" />
                          Falhou
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-slate-400">
                          <Clock className="w-3 h-3" />
                          {ROW_STATUS_LABEL[row.status] ?? row.status}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {row.listing_id ? (
                        <Link
                          href={`/listings/${row.listing_id}`}
                          className="flex items-center gap-1 text-blue-600 hover:underline"
                        >
                          <LinkIcon className="w-3 h-3" />
                          Ver
                        </Link>
                      ) : (
                        <span className="text-slate-300">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-red-500 max-w-xs truncate" title={row.error_message ?? ""}>
                      {row.error_message ?? ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default function ImportPage() {
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  const { data: batches = [], isLoading } = useQuery<BatchImportOut[]>({
    queryKey: ["batches"],
    queryFn: listBatches,
  })

  const hasActive = batches.some((b) => b.status === "pending" || b.status === "running")

  useEffect(() => {
    if (!hasActive) return
    const t = setInterval(() => queryClient.invalidateQueries({ queryKey: ["batches"] }), 5000)
    return () => clearInterval(t)
  }, [hasActive, queryClient])

  const handleFile = useCallback(
    async (file: File) => {
      if (!file.name.match(/\.(csv|xlsx)$/i)) {
        toast.error("Apenas arquivos .csv ou .xlsx são suportados")
        return
      }
      setUploading(true)
      try {
        await uploadBatch(file)
        toast.success(`"${file.name}" enviado — pipeline iniciado`)
        queryClient.invalidateQueries({ queryKey: ["batches"] })
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Erro no upload")
      } finally {
        setUploading(false)
      }
    },
    [queryClient]
  )

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragging(false)
      const file = e.dataTransfer.files[0]
      if (file) handleFile(file)
    },
    [handleFile]
  )

  return (
    <div className="max-w-3xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-foreground">Importar anúncios</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Faça upload da planilha de anúncios. O pipeline roda automaticamente para cada SKU.
        </p>
      </div>

      {/* Aviso de pré-requisito */}
      <div className="mb-5 flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-900/20 px-4 py-3">
        <span className="text-amber-500 text-base leading-none mt-0.5">⚠</span>
        <div className="text-sm">
          <span className="font-semibold text-amber-800 dark:text-amber-300">Pré-requisito: </span>
          <span className="text-amber-700 dark:text-amber-400">
            Os produtos precisam estar cadastrados no{" "}
            <Link href="/products" className="underline hover:no-underline font-medium">
              Catálogo de Produtos
            </Link>{" "}
            antes de importar anúncios. Linhas com SKU não cadastrado serão rejeitadas.
          </span>
        </div>
      </div>

      {/* Colunas aceitas */}
      <div className="mb-5 rounded-lg border border-border bg-muted/30 px-4 py-3">
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            Colunas da planilha de anúncios
          </p>
          <button
            type="button"
            onClick={() => downloadListingTemplate()}
            className="inline-flex items-center gap-1.5 text-xs text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300 font-medium transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
            Baixar modelo
          </button>
        </div>
        <div className="grid grid-cols-2 gap-x-8 gap-y-0.5 text-xs text-muted-foreground">
          {[
            ["sku *", "Referência ao produto cadastrado"],
            ["preco *", "Preço de venda (R$)"],
            ["estoque", "Quantidade disponível (padrão: 1)"],
            ["tipo", "classico ou premium (padrão: classico)"],
            ["condicao", "novo ou usado (padrão: novo)"],
            ["seo", "Contexto SEO para geração de título"],
          ].map(([col, desc]) => (
            <div key={col} className="flex gap-2 py-0.5">
              <span className="font-mono w-24 shrink-0">{col}</span>
              <span>{desc}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => !uploading && inputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-12 flex flex-col items-center justify-center gap-3 cursor-pointer transition-colors ${
          dragging
            ? "border-blue-400 bg-blue-50"
            : "border-border bg-muted/40 hover:border-muted-foreground hover:bg-muted/60"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.xlsx"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
        />
        {uploading ? (
          <>
            <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
            <p className="text-sm text-slate-600 font-medium">Enviando arquivo...</p>
          </>
        ) : (
          <>
            <Upload className="w-8 h-8 text-slate-400" />
            <div className="text-center">
              <p className="text-sm font-medium text-foreground">
                Arraste o arquivo aqui ou clique para selecionar
              </p>
              <p className="text-xs text-slate-400 mt-1">.csv ou .xlsx · máximo 10 MB · até 5.000 SKUs</p>
            </div>
            <Button variant="outline" size="sm" tabIndex={-1}>
              <FileSpreadsheet className="w-4 h-4 mr-2" />
              Selecionar arquivo
            </Button>
          </>
        )}
      </div>

      {/* Histórico de imports */}
      <div className="mt-8">
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">
          Importações recentes
        </h2>

        {isLoading ? (
          <div className="flex items-center gap-2 text-slate-400">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span className="text-sm">Carregando...</span>
          </div>
        ) : batches.length === 0 ? (
          <p className="text-sm text-slate-400 italic">Nenhuma importação realizada ainda.</p>
        ) : (
          <div className="space-y-3">
            {batches.map((b) => (
              <BatchCard key={b.id} batch={b} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
