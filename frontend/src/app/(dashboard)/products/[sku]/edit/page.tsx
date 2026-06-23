"use client"

import Link from "next/link"
import { ArrowLeft, Loader2 } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import { getProduct, updateProduct } from "@/lib/api/products"
import { ProductForm } from "@/components/products/ProductForm"

export default function EditProductPage({ params }: { params: { sku: string } }) {
  const decodedSku = decodeURIComponent(params.sku)

  const { data: product, isLoading, isFetching } = useQuery({
    queryKey: ["product", decodedSku],
    queryFn: () => getProduct(decodedSku),
    staleTime: 0,
  })

  return (
    <div className="max-w-3xl mx-auto">
      <div className="mb-6">
        <Link
          href="/products"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-4"
        >
          <ArrowLeft className="w-4 h-4" />
          Catálogo de produtos
        </Link>
        <h1 className="text-2xl font-bold text-foreground">Editar produto</h1>
        <p className="text-sm text-muted-foreground mt-1 font-mono">{decodedSku}</p>
      </div>

      {isLoading || isFetching ? (
        <div className="flex items-center justify-center h-48">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      ) : product ? (
        <ProductForm
          initial={product}
          onSubmit={(data) => updateProduct(decodedSku, data)}
        />
      ) : (
        <p className="text-muted-foreground">Produto não encontrado.</p>
      )}
    </div>
  )
}
