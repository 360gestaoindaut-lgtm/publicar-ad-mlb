"use client"

import { useState } from "react"
import Link from "next/link"
import { CardContent, CardHeader } from "@/components/ui/card"
import { ListingStatusBadge } from "./ListingStatusBadge"
import type { ListingSummary } from "@/types/listing"
import { activateListing } from "@/lib/api/listings"
import { formatDistanceToNow } from "date-fns"
import { ptBR } from "date-fns/locale"
import { User, Upload } from "lucide-react"

interface ListingCardProps {
  listing: ListingSummary
  selected?: boolean
  onSelect?: (id: string, checked: boolean) => void
}

function OriginBadge({ via }: { via: "manual" | "batch" }) {
  if (via === "batch") {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded bg-amber-100 text-amber-700">
        <Upload className="w-2.5 h-2.5" />
        Lote
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
      <User className="w-2.5 h-2.5" />
      Manual
    </span>
  )
}

export function ListingCard({ listing, selected = false, onSelect }: ListingCardProps) {
  const [activating, setActivating] = useState(false)
  const [activateError, setActivateError] = useState<string | null>(null)

  const timeAgo = formatDistanceToNow(new Date(listing.updated_at), {
    addSuffix: true,
    locale: ptBR,
  })

  return (
    <Link href={`/listings/${listing.id}`}>
      <div className="relative group rounded-lg border border-border bg-card p-3 text-sm shadow-sm hover:shadow-md transition-shadow">
        {onSelect && (
          <input
            type="checkbox"
            checked={selected}
            onChange={(e) => onSelect(listing.id, e.target.checked)}
            onClick={(e) => e.stopPropagation()}
            className="absolute top-2 left-2 h-4 w-4 rounded border-slate-300 cursor-pointer"
          />
        )}
        <div className={onSelect ? "pl-6" : ""}>
          <CardHeader className="pb-2 pt-3 px-4">
            <div className="flex items-start justify-between gap-2">
              <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">
                {listing.sku_brand}
              </span>
              <ListingStatusBadge status={listing.status} />
            </div>
          </CardHeader>
          <CardContent className="px-4 pb-3">
            <p className="text-sm font-medium text-foreground line-clamp-2 min-h-[2.5rem]">
              {listing.selected_title || (
                <span className="text-muted-foreground italic">Título não gerado</span>
              )}
            </p>
            <div className="flex items-center gap-2 mt-2">
              <span className="text-xs text-muted-foreground">{timeAgo}</span>
              <OriginBadge via={listing.created_via} />
            </div>
            {listing.mlb_id && (
              <span className="block text-xs text-blue-600 font-mono mt-1">{listing.mlb_id}</span>
            )}
          </CardContent>
          {listing.status === "published_paused" && (
            <>
              <button
                onClick={async (e) => {
                  e.stopPropagation()
                  setActivating(true)
                  setActivateError(null)
                  try {
                    await activateListing(listing.id)
                  } catch {
                    setActivateError("Falha ao ativar. Tente novamente.")
                  } finally {
                    setActivating(false)
                  }
                }}
                disabled={activating}
                className="mt-2 w-full text-xs font-medium bg-green-600 hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded px-2 py-1"
              >
                {activating ? "Ativando…" : "Ativar anúncio"}
              </button>
              {activateError && (
                <p className="mt-1 text-xs text-red-500">{activateError}</p>
              )}
            </>
          )}
        </div>

        {/* Inline error subcard */}
        {listing.status === "failed" && (
          <div className="mt-2 rounded-md bg-red-50 border border-red-200 px-3 py-2 flex items-center justify-between gap-2">
            <div className="text-xs text-red-700">
              <span className="font-medium">Falha</span>
              {listing.failed_step && (
                <span className="text-red-500 ml-1">em {listing.failed_step.replace(/_/g, " ")}</span>
              )}
            </div>
            <a
              href={`/listings/${listing.id}`}
              className="text-xs text-red-600 underline underline-offset-2 hover:text-red-800 whitespace-nowrap"
            >
              Ver detalhes
            </a>
          </div>
        )}
      </div>
    </Link>
  )
}
