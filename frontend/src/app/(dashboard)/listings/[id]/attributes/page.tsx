"use client"

import { useQuery } from "@tanstack/react-query"
import { getListing } from "@/lib/api/listings"
import { useParams } from "next/navigation"
import { AttributeForm } from "@/components/listings/AttributeForm"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Loader2, ArrowLeft } from "lucide-react"
import Link from "next/link"

export default function AttributesPage() {
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
        <h1 className="text-2xl font-bold text-slate-900">Atributos do produto</h1>
        <p className="text-sm text-slate-500 mt-1">
          Preencha os atributos obrigatórios exigidos pelo Mercado Livre para esta categoria.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {listing.selected_title || listing.sku_brand}
          </CardTitle>
          {listing.ml_category_id && (
            <p className="text-xs text-slate-400 font-mono">{listing.ml_category_id}</p>
          )}
        </CardHeader>
        <CardContent>
          <AttributeForm listingId={id} attributes={listing.attributes} />
        </CardContent>
      </Card>
    </div>
  )
}
