"use client"

import Link from "next/link"
import { ArrowLeft } from "lucide-react"
import { ProductForm } from "@/components/products/ProductForm"
import { createProduct } from "@/lib/api/products"

export default function NewProductPage() {
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
        <h1 className="text-2xl font-bold text-foreground">Novo produto</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Preencha os dados do produto. SKU e descrição são obrigatórios.
        </p>
      </div>

      <ProductForm onSubmit={createProduct} />
    </div>
  )
}
