"use client"

import { useQuery } from "@tanstack/react-query"
import { getListing } from "@/lib/api/listings"
import { useParams } from "next/navigation"
import { TitleSelector } from "@/components/listings/TitleSelector"
import { Loader2, ArrowLeft } from "lucide-react"
import Link from "next/link"

export default function TitlesPage() {
  const params = useParams<{ id: string }>()
  const id = params.id

  const { data: listing, isLoading } = useQuery({
    queryKey: ["listing", id],
    queryFn: () => getListing(id),
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-slate-500" />
      </div>
    )
  }

  if (!listing) return null

  return (
    <div className="max-w-xl mx-auto">
      <div className="mb-6">
        <Link
          href={`/listings/${id}`}
          className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700 mb-4"
        >
          <ArrowLeft className="w-4 h-4" />
          Voltar ao anúncio
        </Link>
        <h1 className="text-2xl font-bold text-slate-900">Escolher título</h1>
        <p className="text-sm text-slate-500 mt-1">
          {listing.sku_brand} — {listing.sku_description.slice(0, 60)}
          {listing.sku_description.length > 60 ? "..." : ""}
        </p>
      </div>

      <TitleSelector listingId={id} titles={listing.titles} />
    </div>
  )
}
