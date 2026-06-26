"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import {
  bulkStartPipeline,
  bulkApproveTitles,
  bulkRejectTitles,
  bulkApproveImages,
  bulkGenerateImages,
  bulkPublish,
} from "@/lib/api/listings"
import type { BulkResult } from "@/types/listing"
import { CheckCircle, XCircle, Loader2, X } from "lucide-react"

type ColumnId = "fila" | "titulos" | "categoria" | "imagens" | "descricao" | "publicados"

interface BulkActionsBarProps {
  selectedIds: string[]
  activeColumnId: ColumnId | null
  onSuccess: () => void
  onClear: () => void
}

function useToast() {
  const [message, setMessage] = useState<{ text: string; type: "success" | "error" } | null>(null)
  const show = (text: string, type: "success" | "error") => {
    setMessage({ text, type })
    setTimeout(() => setMessage(null), 4000)
  }
  return { message, show }
}

export function BulkActionsBar({ selectedIds, activeColumnId, onSuccess, onClear }: BulkActionsBarProps) {
  const router = useRouter()
  const { message, show } = useToast()
  const [loading, setLoading] = useState(false)

  if (selectedIds.length === 0) return null

  const run = async (fn: (ids: string[]) => Promise<BulkResult>, successLabel: string) => {
    setLoading(true)
    try {
      const result = await fn(selectedIds)
      if (result.failed === 0) {
        show(`${successLabel}: ${result.processed} processados`, "success")
      } else {
        show(`${result.processed} ok, ${result.failed} com erro`, "error")
      }
      onSuccess()
    } catch {
      show("Erro inesperado. Tente novamente.", "error")
    } finally {
      setLoading(false)
    }
  }

  const columnLabel: Record<ColumnId, string> = {
    fila: "Fila",
    titulos: "Títulos",
    categoria: "Categoria & Atributos",
    imagens: "Imagens",
    descricao: "Descrição",
    publicados: "Publicados",
  }

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 flex justify-center pb-4 pointer-events-none">
      <div className="pointer-events-auto bg-slate-900 text-white rounded-xl shadow-2xl px-5 py-3 flex items-center gap-4 min-w-[400px] max-w-xl">
        <div className="flex-1 text-sm">
          <span className="font-semibold">{selectedIds.length}</span>
          <span className="text-slate-300 ml-1">
            {selectedIds.length === 1 ? "anúncio selecionado" : "anúncios selecionados"}
            {activeColumnId && ` em ${columnLabel[activeColumnId]}`}
          </span>
        </div>

        {loading && <Loader2 className="w-4 h-4 animate-spin text-slate-400" />}

        {!loading && activeColumnId === "fila" && (
          <button
            onClick={() => run(bulkStartPipeline, "Pipeline iniciado")}
            className="flex items-center gap-1.5 bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium px-3 py-1.5 rounded-lg transition-colors"
          >
            <CheckCircle className="w-4 h-4" /> Iniciar pipeline
          </button>
        )}

        {!loading && activeColumnId === "titulos" && (
          <>
            <button
              onClick={() => run(bulkRejectTitles, "Títulos reprovados")}
              className="flex items-center gap-1.5 bg-red-600 hover:bg-red-500 text-white text-sm font-medium px-3 py-1.5 rounded-lg transition-colors"
            >
              <XCircle className="w-4 h-4" /> Reprovar
            </button>
            <button
              onClick={() => run(bulkApproveTitles, "Títulos aprovados")}
              className="flex items-center gap-1.5 bg-green-600 hover:bg-green-500 text-white text-sm font-medium px-3 py-1.5 rounded-lg transition-colors"
            >
              <CheckCircle className="w-4 h-4" /> Aprovar títulos
            </button>
          </>
        )}

        {!loading && activeColumnId === "categoria" && (
          <>
            <button
              onClick={() => {
                router.push("/listings/attributes")
              }}
              className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium px-3 py-1.5 rounded-lg transition-colors"
            >
              Preencher atributos
            </button>
            <button
              onClick={() => run(bulkGenerateImages, "Imagens iniciadas")}
              className="flex items-center gap-1.5 bg-orange-600 hover:bg-orange-500 text-white text-sm font-medium px-3 py-1.5 rounded-lg transition-colors"
            >
              <CheckCircle className="w-4 h-4" /> Gerar imagens
            </button>
          </>
        )}

        {!loading && activeColumnId === "imagens" && (
          <button
            onClick={() => run(bulkApproveImages, "Imagens aprovadas")}
            className="flex items-center gap-1.5 bg-green-600 hover:bg-green-500 text-white text-sm font-medium px-3 py-1.5 rounded-lg transition-colors"
          >
            <CheckCircle className="w-4 h-4" /> Aprovar imagens
          </button>
        )}

        {!loading && activeColumnId === "descricao" && (
          <button
            onClick={() => run(bulkPublish, "Publicação iniciada")}
            className="flex items-center gap-1.5 bg-green-600 hover:bg-green-500 text-white text-sm font-medium px-3 py-1.5 rounded-lg transition-colors"
          >
            <CheckCircle className="w-4 h-4" /> Publicar
          </button>
        )}

        <button
          onClick={onClear}
          className="text-slate-400 hover:text-white transition-colors ml-1"
          title="Cancelar seleção"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {message && (
        <div
          className={`fixed bottom-20 left-1/2 -translate-x-1/2 px-4 py-2 rounded-lg text-sm font-medium text-white shadow-lg ${
            message.type === "success" ? "bg-green-700" : "bg-red-700"
          }`}
        >
          {message.text}
        </div>
      )}
    </div>
  )
}
