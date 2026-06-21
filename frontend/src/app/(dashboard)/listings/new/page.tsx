"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { createListing, startPipeline } from "@/lib/api/listings"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { toast } from "sonner"
import { Loader2, ArrowLeft } from "lucide-react"
import Link from "next/link"
import type { Condition } from "@/types/listing"

export default function NewListingPage() {
  const router = useRouter()
  const queryClient = useQueryClient()

  const [form, setForm] = useState({
    sku_description: "",
    sku_brand: "",
    price: "",
    stock_quantity: "",
    condition: "new" as Condition,
  })

  const mutation = useMutation({
    mutationFn: async () => {
      const listing = await createListing({
        sku_description: form.sku_description,
        sku_brand: form.sku_brand,
        price: parseFloat(form.price.replace(/\./g, "").replace(",", ".")),
        stock_quantity: parseInt(form.stock_quantity),
        condition: form.condition,
      })
      await startPipeline(listing.id)
      return listing
    },
    onSuccess: (listing) => {
      queryClient.invalidateQueries({ queryKey: ["listings"] })
      toast.success("Anúncio criado! Pipeline iniciado.")
      router.push(`/listings/${listing.id}`)
    },
    onError: (err: Error) => {
      toast.error(err.message || "Erro ao criar anúncio")
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()

    if (!form.sku_description.trim()) {
      toast.error("Descrição do produto é obrigatória")
      return
    }
    if (!form.sku_brand.trim()) {
      toast.error("Marca é obrigatória")
      return
    }
    if (!form.price || parseFloat(form.price.replace(/\./g, "").replace(",", ".")) <= 0) {
      toast.error("Preço inválido")
      return
    }
    if (!form.stock_quantity || parseInt(form.stock_quantity) < 0) {
      toast.error("Quantidade em estoque inválida")
      return
    }

    mutation.mutate()
  }

  return (
    <div className="max-w-xl mx-auto">
      <div className="mb-6">
        <Link
          href="/listings"
          className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700 mb-4"
        >
          <ArrowLeft className="w-4 h-4" />
          Voltar
        </Link>
        <h1 className="text-2xl font-bold text-slate-900">Novo anúncio</h1>
        <p className="text-sm text-slate-500 mt-1">
          Preencha as informações do produto. A IA vai gerar o título e as imagens automaticamente.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Informações do produto</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="sku_description">
                Descrição do produto <span className="text-red-500">*</span>
              </Label>
              <textarea
                id="sku_description"
                value={form.sku_description}
                onChange={(e) => setForm((prev) => ({ ...prev, sku_description: e.target.value }))}
                placeholder="Ex: Notebook Dell Inspiron 15 3000, Intel Core i5 12ª Geração, 8GB RAM, SSD 256GB, Windows 11"
                className="flex min-h-[100px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring resize-none"
                required
              />
              <p className="text-xs text-slate-400">
                Seja detalhista — quanto mais informações, melhor o título gerado pela IA.
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="sku_brand">
                Marca <span className="text-red-500">*</span>
              </Label>
              <Input
                id="sku_brand"
                value={form.sku_brand}
                onChange={(e) => setForm((prev) => ({ ...prev, sku_brand: e.target.value }))}
                placeholder="Ex: Dell, Samsung, Apple..."
                required
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="price">
                  Preço (R$) <span className="text-red-500">*</span>
                </Label>
                <Input
                  id="price"
                  type="text"
                  inputMode="decimal"
                  value={form.price}
                  onChange={(e) => setForm((prev) => ({ ...prev, price: e.target.value }))}
                  onBlur={(e) => {
                    const val = parseFloat(e.target.value.replace(",", "."))
                    if (!isNaN(val) && val > 0) {
                      setForm((prev) => ({
                        ...prev,
                        price: val.toLocaleString("pt-BR", {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        }),
                      }))
                    }
                  }}
                  placeholder="0,00"
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="stock_quantity">
                  Estoque <span className="text-red-500">*</span>
                </Label>
                <Input
                  id="stock_quantity"
                  type="number"
                  min="0"
                  value={form.stock_quantity}
                  onChange={(e) =>
                    setForm((prev) => ({ ...prev, stock_quantity: e.target.value }))
                  }
                  placeholder="1"
                  required
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label>Condição</Label>
              <div className="flex gap-3">
                {[
                  { value: "new", label: "Novo" },
                  { value: "used", label: "Usado" },
                ].map(({ value, label }) => (
                  <label
                    key={value}
                    className={`flex items-center gap-2 px-4 py-2 rounded-md border cursor-pointer transition-colors ${
                      form.condition === value
                        ? "border-slate-900 bg-slate-900 text-white"
                        : "border-slate-200 hover:border-slate-300"
                    }`}
                  >
                    <input
                      type="radio"
                      name="condition"
                      value={value}
                      checked={form.condition === value}
                      onChange={() =>
                        setForm((prev) => ({ ...prev, condition: value as Condition }))
                      }
                      className="sr-only"
                    />
                    <span className="text-sm font-medium">{label}</span>
                  </label>
                ))}
              </div>
            </div>

            <Button type="submit" disabled={mutation.isPending} className="w-full" size="lg">
              {mutation.isPending ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Criando e iniciando pipeline...
                </>
              ) : (
                "Criar e iniciar pipeline"
              )}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
