"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { selectTitle } from "@/lib/api/listings"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { toast } from "sonner"
import { CheckCircle, Loader2, Star } from "lucide-react"
import type { TitleOption } from "@/types/listing"

interface Props {
  listingId: string
  titles: TitleOption[]
}

export function TitleSelector({ listingId, titles }: Props) {
  const router = useRouter()
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: (titleId: string) => selectTitle(listingId, titleId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["listing", listingId] })
      queryClient.invalidateQueries({ queryKey: ["listings"] })
      toast.success("Título selecionado com sucesso!")
      router.push(`/listings/${listingId}`)
    },
    onError: (err: Error) => {
      toast.error(err.message || "Erro ao selecionar título")
    },
  })

  const handleSelect = (titleId: string) => {
    setSelectedId(titleId)
    mutation.mutate(titleId)
  }

  if (titles.length === 0) {
    return (
      <div className="text-center py-12 text-slate-500">
        <p>Nenhum título disponível ainda. Aguarde a geração pela IA.</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600 mb-4">
        Selecione o melhor título gerado pela IA para seu anúncio no Mercado Livre.
      </p>
      {titles.map((title) => (
        <Card
          key={title.id}
          className={`cursor-pointer transition-all border-2 ${
            title.selected
              ? "border-green-500 bg-green-50"
              : selectedId === title.id
                ? "border-blue-500 bg-blue-50"
                : "border-slate-200 hover:border-slate-300 hover:shadow-sm"
          }`}
          onClick={() => !mutation.isPending && handleSelect(title.id)}
        >
          <CardContent className="p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1">
                <p className="text-sm font-medium text-foreground leading-relaxed">
                  {title.title_text}
                </p>
                {title.ai_score !== null && (
                  <div className="flex items-center gap-1 mt-2">
                    <Star className="w-3.5 h-3.5 text-yellow-500 fill-yellow-500" />
                    <span className="text-xs text-slate-500">
                      Pontuação IA: {(title.ai_score * 100).toFixed(0)}%
                    </span>
                  </div>
                )}
              </div>
              <div className="flex-shrink-0">
                {title.selected ? (
                  <CheckCircle className="w-5 h-5 text-green-500" />
                ) : selectedId === title.id && mutation.isPending ? (
                  <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={mutation.isPending}
                    onClick={(e) => {
                      e.stopPropagation()
                      handleSelect(title.id)
                    }}
                  >
                    Escolher
                  </Button>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
