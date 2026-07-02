"use client"

import { useRef } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { AlertTriangle, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { getImageEngineState } from "@/lib/api/system"
import { confirmImageEngine } from "@/lib/api/listings"

export function ImageEngineBanner() {
  const lastSwitchSeen = useRef<string | null>(null)
  const queryClient = useQueryClient()

  const { data } = useQuery({
    queryKey: ["image-engine-state"],
    queryFn: getImageEngineState,
    refetchInterval: 8_000,
  })

  const mutation = useMutation({
    mutationFn: (action: "use_gemini" | "retry_openai") => {
      const targetId = data?.pending_listing_ids[0]
      if (!targetId) throw new Error("Nenhum anúncio pendente")
      return confirmImageEngine(targetId, action)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["image-engine-state"] })
      queryClient.invalidateQueries({ queryKey: ["listings"] })
    },
    onError: (err: Error) => {
      toast.error(err.message || "Erro ao trocar motor de imagem")
    },
  })

  if (data) {
    const seen = lastSwitchSeen.current
    if (data.last_switch_to_openai_at && seen !== null && seen !== data.last_switch_to_openai_at) {
      toast.success("Geração de imagens voltou a usar a OpenAI")
    }
    lastSwitchSeen.current = data.last_switch_to_openai_at
  }

  if (!data || data.pending_confirmation_count === 0) return null

  return (
    <div className="mb-4 flex items-center justify-between gap-4 rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-amber-900">
      <div className="flex items-center gap-2 text-sm">
        <AlertTriangle className="h-4 w-4 shrink-0" />
        <span>
          A geração de imagens via OpenAI apresentou falha
          {data.last_openai_error ? `: ${data.last_openai_error}` : ""}.{" "}
          {data.pending_confirmation_count} anúncio(s) aguardando decisão.
        </span>
      </div>
      <div className="flex gap-2 shrink-0">
        <Button
          size="sm"
          variant="outline"
          disabled={mutation.isPending}
          onClick={() => mutation.mutate("retry_openai")}
        >
          {mutation.isPending && mutation.variables === "retry_openai" ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            "Tentar novamente com OpenAI"
          )}
        </Button>
        <Button
          size="sm"
          disabled={mutation.isPending}
          onClick={() => mutation.mutate("use_gemini")}
        >
          {mutation.isPending && mutation.variables === "use_gemini" ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            "Usar Gemini nestes anúncios"
          )}
        </Button>
      </div>
    </div>
  )
}
