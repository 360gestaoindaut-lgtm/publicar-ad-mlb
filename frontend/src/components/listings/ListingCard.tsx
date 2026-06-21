"use client"

import Link from "next/link"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { ListingStatusBadge } from "./ListingStatusBadge"
import type { ListingSummary } from "@/types/listing"
import { formatDistanceToNow } from "date-fns"
import { ptBR } from "date-fns/locale"
import { User, Upload } from "lucide-react"

interface Props {
  listing: ListingSummary
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

export function ListingCard({ listing }: Props) {
  const timeAgo = formatDistanceToNow(new Date(listing.updated_at), {
    addSuffix: true,
    locale: ptBR,
  })

  return (
    <Link href={`/listings/${listing.id}`}>
      <Card className="cursor-pointer hover:shadow-md transition-shadow border border-border">
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
      </Card>
    </Link>
  )
}
