"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { toast } from "sonner"
import { Loader2, Save } from "lucide-react"
import type { Product, ProductFormData } from "@/types/product"

interface Props {
  initial?: Product
  onSubmit: (data: ProductFormData) => Promise<Product>
}

function Field({
  label, name, value, onChange, placeholder, readOnly, type = "text", min, max,
}: {
  label: string
  name: string
  value: string
  onChange: (name: string, value: string) => void
  placeholder?: string
  readOnly?: boolean
  type?: string
  min?: number
  max?: number
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
        {label}
      </label>
      <Input
        type={type}
        value={value}
        onChange={(e) => onChange(name, e.target.value)}
        placeholder={placeholder}
        readOnly={readOnly}
        min={min}
        max={max}
        className={readOnly ? "bg-muted text-muted-foreground cursor-not-allowed" : ""}
      />
    </div>
  )
}

function empty(p?: Product): ProductFormData {
  if (!p) return { sku: "", description: "" }
  return {
    sku: p.sku,
    description: p.description,
    brand: p.brand ?? "",
    model: p.model ?? "",
    ean: p.ean ?? "",
    ncm: p.ncm ?? "",
    fiscal_origin: p.fiscal_origin != null ? String(p.fiscal_origin) as any : "",
    icms_cst: p.icms_cst ?? "",
    icms_rate: p.icms_rate ?? "",
    pis_cst: p.pis_cst ?? "",
    cofins_cst: p.cofins_cst ?? "",
    weight_kg: p.weight_kg ?? "",
    length_cm: p.length_cm != null ? String(p.length_cm) as any : "",
    width_cm: p.width_cm != null ? String(p.width_cm) as any : "",
    height_cm: p.height_cm != null ? String(p.height_cm) as any : "",
    acquisition_cost: p.acquisition_cost ?? "",
    product_group: p.product_group ?? "",
    technical_reference: p.technical_reference ?? "",
    vehicle_application: p.vehicle_application ?? "",
    color: p.color ?? "",
    size: p.size ?? "",
    capacity: p.capacity ?? "",
    material: p.material ?? "",
    gender: p.gender ?? "",
  }
}

function toPayload(form: Record<string, string>): ProductFormData {
  const str = (v: string) => v.trim() || null
  const num = (v: string) => v.trim() ? Number(v.trim()) : null
  const dec = (v: string) => v.trim().replace(",", ".") || null
  return {
    sku: form.sku.trim(),
    description: form.description.trim(),
    brand: str(form.brand),
    model: str(form.model),
    ean: str(form.ean),
    ncm: str(form.ncm),
    fiscal_origin: num(form.fiscal_origin) as any,
    icms_cst: str(form.icms_cst),
    icms_rate: dec(form.icms_rate) as any,
    pis_cst: str(form.pis_cst),
    cofins_cst: str(form.cofins_cst),
    weight_kg: dec(form.weight_kg) as any,
    length_cm: num(form.length_cm) as any,
    width_cm: num(form.width_cm) as any,
    height_cm: num(form.height_cm) as any,
    acquisition_cost: dec(form.acquisition_cost) as any,
    product_group: str(form.product_group),
    technical_reference: str(form.technical_reference),
    vehicle_application: str(form.vehicle_application),
    color: str(form.color),
    size: str(form.size),
    capacity: str(form.capacity),
    material: str(form.material),
    gender: str(form.gender),
  }
}

export function ProductForm({ initial, onSubmit }: Props) {
  const router = useRouter()
  const isEdit = !!initial

  const [form, setForm] = useState<Record<string, string>>(() => {
    const d = empty(initial)
    return Object.fromEntries(
      Object.entries(d).map(([k, v]) => [k, v == null ? "" : String(v)])
    )
  })
  const [saving, setSaving] = useState(false)

  const handleChange = (name: string, value: string) =>
    setForm((prev) => ({ ...prev, [name]: value }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.sku.trim()) { toast.error("SKU é obrigatório"); return }
    if (!form.description.trim()) { toast.error("Descrição é obrigatória"); return }

    setSaving(true)
    try {
      await onSubmit(toPayload(form))
      toast.success(isEdit ? "Produto atualizado." : "Produto criado.")
      router.push("/products")
    } catch (err: any) {
      toast.error(err?.message || "Erro ao salvar produto")
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Identificação */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
            Identificação
          </CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="SKU *" name="sku" value={form.sku} onChange={handleChange}
            placeholder="ex: SKU001" readOnly={isEdit} />
          <Field label="Marca" name="brand" value={form.brand} onChange={handleChange}
            placeholder="ex: Samsung" />
          <Field label="Modelo" name="model" value={form.model} onChange={handleChange}
            placeholder="ex: Galaxy A54 128GB" />
          <div className="sm:col-span-2">
            <Field label="Descrição *" name="description" value={form.description}
              onChange={handleChange} placeholder="ex: Smartphone Samsung Galaxy A54 128GB Preto" />
          </div>
          <Field label="EAN / GTIN" name="ean" value={form.ean} onChange={handleChange}
            placeholder="ex: 7892509082679" />
          <Field label="NCM" name="ncm" value={form.ncm} onChange={handleChange}
            placeholder="ex: 8517120019" />
        </CardContent>
      </Card>

      {/* Fiscal */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
            Fiscal
          </CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 sm:grid-cols-3 gap-4">
          <Field label="Origem fiscal (0–8)" name="fiscal_origin" value={form.fiscal_origin}
            onChange={handleChange} placeholder="ex: 0" type="number" min={0} max={8} />
          <Field label="CST ICMS" name="icms_cst" value={form.icms_cst}
            onChange={handleChange} placeholder="ex: 00" />
          <Field label="Alíq. ICMS (%)" name="icms_rate" value={form.icms_rate}
            onChange={handleChange} placeholder="ex: 12" />
          <Field label="CST PIS" name="pis_cst" value={form.pis_cst}
            onChange={handleChange} placeholder="ex: 07" />
          <Field label="CST COFINS" name="cofins_cst" value={form.cofins_cst}
            onChange={handleChange} placeholder="ex: 07" />
        </CardContent>
      </Card>

      {/* Embalagem */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
            Embalagem e custo
          </CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <Field label="Peso (kg)" name="weight_kg" value={form.weight_kg}
            onChange={handleChange} placeholder="ex: 0.185" />
          <Field label="Comprimento (cm)" name="length_cm" value={form.length_cm}
            onChange={handleChange} placeholder="ex: 16" type="number" />
          <Field label="Largura (cm)" name="width_cm" value={form.width_cm}
            onChange={handleChange} placeholder="ex: 8" type="number" />
          <Field label="Altura (cm)" name="height_cm" value={form.height_cm}
            onChange={handleChange} placeholder="ex: 1" type="number" />
          <div className="sm:col-span-2">
            <Field label="Custo de aquisição (R$)" name="acquisition_cost"
              value={form.acquisition_cost} onChange={handleChange} placeholder="ex: 1299,90" />
          </div>
        </CardContent>
      </Card>

      {/* Título & SEO */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
            Título &amp; SEO
          </CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="sm:col-span-2">
            <Field label="Grupo de produto" name="product_group" value={form.product_group}
              onChange={handleChange} placeholder="ex: rolamentos, pastilhas" />
          </div>
          <Field label="Referência técnica" name="technical_reference" value={form.technical_reference}
            onChange={handleChange} placeholder="ex: 6203 DDU C3" />
          <Field label="Aplicação / Veículo" name="vehicle_application" value={form.vehicle_application}
            onChange={handleChange} placeholder="ex: Honda CG 125 / Yamaha YBR" />
          <Field label="Cor" name="color" value={form.color}
            onChange={handleChange} placeholder="ex: Preto" />
          <Field label="Tamanho" name="size" value={form.size}
            onChange={handleChange} placeholder="ex: M, 42, 500ml" />
          <Field label="Capacidade" name="capacity" value={form.capacity}
            onChange={handleChange} placeholder="ex: 128GB, 1L" />
          <Field label="Material" name="material" value={form.material}
            onChange={handleChange} placeholder="ex: Aço inox" />
          <Field label="Gênero" name="gender" value={form.gender}
            onChange={handleChange} placeholder="ex: Masculino, Feminino, Unissex" />
        </CardContent>
      </Card>

      <div className="flex items-center justify-end gap-3">
        <Button type="button" variant="outline" onClick={() => router.push("/products")}>
          Cancelar
        </Button>
        <Button type="submit" disabled={saving}>
          {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}
          {isEdit ? "Salvar alterações" : "Criar produto"}
        </Button>
      </div>
    </form>
  )
}
