"use client"

import Link from "next/link"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { ListingStatusBadge } from "./ListingStatusBadge"
import type { ListingSummary } from "@/types/listing"
import { formatDistanceToNow } from "date-fns"
import { ptBR } from "date-fns/locale"

interface Props {
  listing: ListingSummary
}

export function ListingCard({ listing }: Props) {
  const timeAgo = formatDistanceToNow(new Date(listing.updated_at), {
    addSuffix: true,
    locale: ptBR,
  })

  return (
    <Link href={`/listings/${listing.id}`}>
      <Card className="cursor-pointer hover:shadow-md transition-shadow border border-slate-200">
        <CardHeader className="pb-2 pt-3 px-4">
          <div className="flex items-start justify-between gap-2">
            <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">
              {listing.sku_brand}
            </span>
            <ListingStatusBadge status={listing.status} />
          </div>
        </CardHeader>
        <CardContent className="px-4 pb-3">
          <p className="text-sm font-medium text-slate-900 line-clamp-2 min-h-[2.5rem]">
            {listing.selected_title || (
              <span className="text-slate-400 italic">Título não gerado</span>
            )}
          </p>
          <div className="flex items-center justify-between mt-2">
            <span className="text-xs text-slate-400">{timeAgo}</span>
            {listing.mlb_id && (
              <span className="text-xs text-blue-600 font-mono">{listing.mlb_id}</span>
            )}
          </div>
        </CardContent>
      </Card>
    </Link>
  )
}
