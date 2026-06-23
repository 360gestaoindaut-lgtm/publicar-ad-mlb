"use client"

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { getProducts } from "@/lib/api/products"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent } from "@/components/ui/card"
import { ChevronDown, ChevronRight, Loader2, Upload, Search, Package, Plus, Pencil } from "lucide-react"
import Link from "next/link"
import { formatDistanceToNow } from "date-fns"
import { ptBR } from "date-fns/locale"
import type { Product } from "@/types/product"

function fmt(v: string | number | null | undefined, suffix = "") {
  if (v == null || v === "") return "—"
  return `${v}${suffix}`
}

function ProductRow({ product, index }: { product: Product; index: number }) {
  const [expanded, setExpanded] = useState(false)

  const hasDimensions = product.length_cm || product.width_cm || product.height_cm
  const dimensions = hasDimensions
    ? `${product.length_cm ?? "?"}×${product.width_cm ?? "?"}×${product.height_cm ?? "?"} cm`
    : null

  const hasDetail =
    product.ncm ||
    product.fiscal_origin != null ||
    product.icms_cst ||
    product.icms_rate ||
    product.pis_cst ||
    product.cofins_cst ||
    hasDimensions ||
    product.acquisition_cost

  const isEven = index % 2 === 0

  const rowBase = expanded
    ? "bg-blue-50 dark:bg-blue-950/30 border-l-2 border-l-blue-400"
    : isEven
    ? "bg-background hover:bg-muted/50"
    : "bg-muted/20 hover:bg-muted/50"

  return (
    <>
      <tr
        className={`border-b border-border transition-colors ${rowBase} ${hasDetail ? "cursor-pointer" : ""}`}
        onClick={() => hasDetail && setExpanded((v) => !v)}
      >
        <td className="px-3 py-3 w-6">
          {hasDetail && (
            expanded
              ? <ChevronDown className="w-3.5 h-3.5 text-blue-500" />
              : <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
          )}
        </td>
        <td className="px-4 py-3 font-mono text-xs text-muted-foreground whitespace-nowrap">
          {product.sku}
        </td>
        <td className="px-4 py-3 font-medium text-foreground max-w-xs truncate">
          {product.description}
        </td>
        <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">{fmt(product.brand)}</td>
        <td className="px-4 py-3 font-mono text-xs text-muted-foreground whitespace-nowrap">{fmt(product.ean)}</td>
        <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">{fmt(product.ncm)}</td>
        <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
          {product.weight_kg ? `${product.weight_kg} kg` : "—"}
        </td>
        <td className="px-4 py-3 text-muted-foreground whitespace-nowrap text-xs">
          {dimensions ?? "—"}
        </td>
        <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
          {product.acquisition_cost
            ? Number(product.acquisition_cost).toLocaleString("pt-BR", { style: "currency", currency: "BRL" })
            : "—"}
        </td>
        <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">
          {formatDistanceToNow(new Date(product.updated_at), { addSuffix: true, locale: ptBR })}
        </td>
        <td className="px-3 py-3">
          <Link
            href={`/products/${encodeURIComponent(product.sku)}/edit`}
            onClick={(e) => e.stopPropagation()}
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            title="Editar produto"
          >
            <Pencil className="w-3.5 h-3.5" />
          </Link>
        </td>
      </tr>

      {expanded && (
        <tr className="border-b border-border border-l-2 border-l-blue-400 bg-blue-50/70 dark:bg-blue-950/20">
          <td colSpan={11} className="px-6 py-4">
            <p className="text-[10px] font-semibold text-blue-500 uppercase tracking-widest mb-3">
              Dados fiscais
            </p>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-x-8 gap-y-3 text-xs">
              <div>
                <p className="text-muted-foreground font-medium uppercase tracking-wide text-[10px] mb-1">Origem Fiscal</p>
                <p className="text-foreground font-mono">{fmt(product.fiscal_origin)}</p>
              </div>
              <div>
                <p className="text-muted-foreground font-medium uppercase tracking-wide text-[10px] mb-1">CST ICMS</p>
                <p className="text-foreground font-mono">{fmt(product.icms_cst)}</p>
              </div>
              <div>
                <p className="text-muted-foreground font-medium uppercase tracking-wide text-[10px] mb-1">Alíq. ICMS</p>
                <p className="text-foreground font-mono">
                  {product.icms_rate ? `${product.icms_rate}%` : "—"}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground font-medium uppercase tracking-wide text-[10px] mb-1">CST PIS</p>
                <p className="text-foreground font-mono">{fmt(product.pis_cst)}</p>
              </div>
              <div>
                <p className="text-muted-foreground font-medium uppercase tracking-wide text-[10px] mb-1">CST COFINS</p>
                <p className="text-foreground font-mono">{fmt(product.cofins_cst)}</p>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

export default function ProductsPage() {
  const [search, setSearch] = useState("")
  const [page, setPage] = useState(1)
  const pageSize = 50

  const { data, isLoading } = useQuery({
    queryKey: ["products", search, page],
    queryFn: () => getProducts({ search: search || undefined, page, page_size: pageSize }),
    placeholderData: (prev) => prev,
  })

  const totalPages = data ? Math.ceil(data.total / pageSize) : 1

  return (
    <div className="max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Catálogo de produtos</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {data ? `${data.total} produto${data.total !== 1 ? "s" : ""}` : "Carregando..."}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button asChild variant="outline">
            <Link href="/products/upload">
              <Upload className="w-4 h-4 mr-2" />
              Importar planilha
            </Link>
          </Button>
          <Button asChild>
            <Link href="/products/new">
              <Plus className="w-4 h-4 mr-2" />
              Novo produto
            </Link>
          </Button>
        </div>
      </div>

      <div className="relative mb-4">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <Input
          placeholder="Buscar por SKU, descrição, marca ou EAN..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1) }}
          className="pl-9"
        />
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-48">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      ) : !data || data.items.length === 0 ? (
        <div className="text-center py-20 text-muted-foreground">
          <Package className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p className="font-medium">
            {search ? "Nenhum produto encontrado para a busca." : "Nenhum produto cadastrado."}
          </p>
          {!search && (
            <Button asChild className="mt-4" variant="outline">
              <Link href="/products/upload">Importar primeira planilha</Link>
            </Button>
          )}
        </div>
      ) : (
        <>
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-muted-foreground text-xs uppercase tracking-wide">
                      <th className="px-4 py-3 w-6" />
                      <th className="text-left px-4 py-3 font-medium whitespace-nowrap">SKU</th>
                      <th className="text-left px-4 py-3 font-medium">Descrição</th>
                      <th className="text-left px-4 py-3 font-medium whitespace-nowrap">Marca</th>
                      <th className="text-left px-4 py-3 font-medium whitespace-nowrap">EAN</th>
                      <th className="text-left px-4 py-3 font-medium whitespace-nowrap">NCM</th>
                      <th className="text-left px-4 py-3 font-medium whitespace-nowrap">Peso</th>
                      <th className="text-left px-4 py-3 font-medium whitespace-nowrap">Dimensões</th>
                      <th className="text-left px-4 py-3 font-medium whitespace-nowrap">Custo</th>
                      <th className="text-left px-4 py-3 font-medium whitespace-nowrap">Atualizado</th>
                      <th className="px-3 py-3 w-8" />
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((product, i) => (
                      <ProductRow key={product.id} product={product} index={i} />
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          <p className="text-xs text-muted-foreground mt-2 text-center">
            Clique em uma linha para ver dados fiscais (CST ICMS/PIS/COFINS, Alíq. ICMS, Origem)
          </p>

          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-3 mt-4">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
              >
                Anterior
              </Button>
              <span className="text-sm text-muted-foreground">
                Página {page} de {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
              >
                Próxima
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
