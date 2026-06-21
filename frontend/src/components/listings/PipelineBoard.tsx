"use client"

import { useQuery } from "@tanstack/react-query"
import { getListings } from "@/lib/api/listings"
import { ListingCard } from "./ListingCard"
import type { ListingStatus, ListingSummary } from "@/types/listing"
import { Loader2 } from "lucide-react"

const COLUMNS: {
  title: string
  statuses: ListingStatus[]
  colorClass: string
}[] = [
  {
    title: "Rascunho",
    statuses: ["draft"],
    colorClass: "border-t-slate-400",
  },
  {
    title: "Em processamento",
    statuses: [
      "generating_title",
      "predicting_category",
      "generating_images",
      "generating_description",
      "publishing",
    ],
    colorClass: "border-t-purple-400",
  },
  {
    title: "Aguardando você",
    statuses: [
      "pending_title_approval",
      "pending_seller_attributes",
      "pending_description",
      "pending_image_approval",
      "ready_to_publish",
    ],
    colorClass: "border-t-yellow-400",
  },
  {
    title: "Publicado",
    statuses: ["published"],
    colorClass: "border-t-green-400",
  },
  {
    title: "Com erro",
    statuses: ["failed"],
    colorClass: "border-t-red-400",
  },
]

export function PipelineBoard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["listings"],
    queryFn: () => getListings({ page_size: 100 }),
    refetchInterval: 8000,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-slate-500" />
        <span className="ml-2 text-slate-500">Carregando anúncios...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-red-500">Erro ao carregar anúncios. Tente recarregar a página.</p>
      </div>
    )
  }

  const allItems: ListingSummary[] = data?.items || []

  const getColumnItems = (statuses: ListingStatus[]) =>
    allItems.filter((item) => statuses.includes(item.status))

  return (
    <div className="flex gap-4 overflow-x-auto pb-4 min-h-[calc(100vh-12rem)]">
      {COLUMNS.map((col) => {
        const items = getColumnItems(col.statuses)
        return (
          <div
            key={col.title}
            className={`flex-shrink-0 w-72 bg-muted/40 rounded-lg border-t-4 ${col.colorClass} border border-border p-3`}
          >
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-sm text-foreground">{col.title}</h3>
              <span className="text-xs bg-muted text-muted-foreground rounded-full px-2 py-0.5 font-medium">
                {items.length}
              </span>
            </div>
            <div className="space-y-2">
              {items.length === 0 ? (
                <p className="text-xs text-slate-400 text-center py-6">
                  Nenhum anúncio
                </p>
              ) : (
                items.map((listing) => (
                  <ListingCard key={listing.id} listing={listing} />
                ))
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
