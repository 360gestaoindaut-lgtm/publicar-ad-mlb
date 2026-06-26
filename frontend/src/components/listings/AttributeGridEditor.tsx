// frontend/src/components/listings/AttributeGridEditor.tsx
"use client"

import { useState, useMemo } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { bulkFillAttribute } from "@/lib/api/listings"
import type { ListingAttributesRow, AttributeItem } from "@/types/listing"
import { Save, Loader2 } from "lucide-react"

interface Props {
  rows: ListingAttributesRow[]
}

export function AttributeGridEditor({ rows }: Props) {
  const queryClient = useQueryClient()
  // local state: Map<listingId, Map<attributeId, newValue>>
  const [dirty, setDirty] = useState<Record<string, Record<string, string>>>({})
  const [selectedRows, setSelectedRows] = useState<Set<string>>(new Set())
  const [saving, setSaving] = useState(false)
  const [saveResult, setSaveResult] = useState<string | null>(null)

  // Group by ml_category_id
  const groups = useMemo(() => {
    const map = new Map<string, ListingAttributesRow[]>()
    for (const row of rows) {
      const key = row.ml_category_id ?? "sem-categoria"
      const existing = map.get(key) ?? []
      map.set(key, existing.concat([row]))
    }
    return map
  }, [rows])

  const setCellValue = (listingId: string, attributeId: string, value: string) => {
    setDirty((prev) => ({
      ...prev,
      [listingId]: { ...(prev[listingId] ?? {}), [attributeId]: value },
    }))
  }

  const getCellValue = (row: ListingAttributesRow, attributeId: string): string => {
    return dirty[row.listing_id]?.[attributeId]
      ?? row.attributes.find((a) => a.attribute_id === attributeId)?.value_name
      ?? ""
  }

  const applyToSelected = (categoryRows: ListingAttributesRow[], attributeId: string) => {
    const value = prompt(`Valor para preencher em "${attributeId}" para todos os selecionados:`)
    if (!value) return
    const targetRows = categoryRows.filter((r) => selectedRows.has(r.listing_id))
    setDirty((prev) => {
      const next = { ...prev }
      for (const r of targetRows) {
        next[r.listing_id] = { ...(next[r.listing_id] ?? {}), [attributeId]: value }
      }
      return next
    })
  }

  const handleSave = async () => {
    setSaving(true)
    setSaveResult(null)
    let success = 0
    let failed = 0
    try {
      // Group dirty cells by (attributeId, value) → list of listingIds
      const batches = new Map<string, { listingIds: string[]; value: string }>()
      for (const [listingId, attrs] of Object.entries(dirty)) {
        for (const [attributeId, value] of Object.entries(attrs)) {
          const key = `${attributeId}|||${value}`
          const existing = batches.get(key) ?? { listingIds: [], value }
          existing.listingIds.push(listingId)
          batches.set(key, existing)
        }
      }
      for (const [key, { listingIds, value }] of Array.from(batches.entries())) {
        const attributeId = key.split("|||")[0]
        const result = await bulkFillAttribute({
          listing_ids: listingIds,
          attribute_id: attributeId,
          value_name: value,
        })
        success += result.processed
        failed += result.failed
      }
      setDirty({})
      queryClient.invalidateQueries({ queryKey: ["listings-for-grid"] })
      setSaveResult(`${success} campos salvos${failed > 0 ? `, ${failed} com erro` : ""}.`)
    } catch {
      setSaveResult("Erro ao salvar. Tente novamente.")
    } finally {
      setSaving(false)
    }
  }

  if (rows.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-slate-500 text-sm">
        Nenhum anúncio aguarda preenchimento de atributos.
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-500">
          {rows.length} {rows.length === 1 ? "anúncio" : "anúncios"} aguardando atributos
        </p>
        <div className="flex items-center gap-3">
          {saveResult && <span className="text-sm text-slate-600">{saveResult}</span>}
          <button
            onClick={handleSave}
            disabled={saving || Object.keys(dirty).length === 0}
            className="flex items-center gap-2 bg-primary text-primary-foreground text-sm font-medium px-4 py-2 rounded-lg hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Salvar alterações
          </button>
        </div>
      </div>

      {Array.from(groups.entries()).map(([categoryId, categoryRows]) => {
        // Collect all unique attributes for this category (union of all rows)
        const attrMap = new Map<string, AttributeItem>()
        for (const row of categoryRows) {
          for (const attr of row.attributes) {
            if (!attrMap.has(attr.attribute_id)) attrMap.set(attr.attribute_id, attr)
          }
        }
        // Required first, then optional, sorted by name
        const uniqueAttrs = Array.from(attrMap.values()).sort((a, b) => {
          if (a.is_required !== b.is_required) return a.is_required ? -1 : 1
          return a.attribute_name.localeCompare(b.attribute_name)
        })

        const allCatSelected =
          categoryRows.length > 0 && categoryRows.every((r) => selectedRows.has(r.listing_id))

        return (
          <div key={categoryId} className="rounded-xl border border-border overflow-hidden">
            <div className="bg-muted/60 px-4 py-2 text-xs font-semibold text-slate-500 uppercase tracking-wide">
              Categoria ML: {categoryId}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/30">
                    <th className="sticky left-0 bg-muted/30 px-3 py-2 w-8">
                      <input
                        type="checkbox"
                        checked={allCatSelected}
                        onChange={() => {
                          const ids = categoryRows.map((r) => r.listing_id)
                          setSelectedRows((prev) => {
                            const next = new Set(prev)
                            if (allCatSelected) ids.forEach((id) => next.delete(id))
                            else ids.forEach((id) => next.add(id))
                            return next
                          })
                        }}
                        className="h-3.5 w-3.5 cursor-pointer"
                      />
                    </th>
                    <th className="sticky left-8 bg-muted/30 px-3 py-2 text-left font-medium text-slate-600 min-w-[180px]">
                      Produto
                    </th>
                    {uniqueAttrs.map((attr) => (
                      <th key={attr.attribute_id} className="px-3 py-2 text-left font-medium text-slate-600 min-w-[140px]">
                        <div className="flex flex-col gap-1">
                          <span>
                            {attr.attribute_name}
                            {attr.is_required && <span className="text-red-500 ml-0.5">*</span>}
                          </span>
                          {selectedRows.size > 0 && (
                            <button
                              onClick={() => applyToSelected(categoryRows, attr.attribute_id)}
                              className="text-xs text-blue-600 hover:underline text-left"
                            >
                              Preencher selecionados
                            </button>
                          )}
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {categoryRows.map((row, idx) => (
                    <tr
                      key={row.listing_id}
                      className={`border-b border-border last:border-0 ${
                        selectedRows.has(row.listing_id) ? "bg-blue-50" : idx % 2 === 0 ? "bg-white" : "bg-slate-50/50"
                      }`}
                    >
                      <td className="sticky left-0 bg-inherit px-3 py-1.5">
                        <input
                          type="checkbox"
                          checked={selectedRows.has(row.listing_id)}
                          onChange={(e) => {
                            setSelectedRows((prev) => {
                              const next = new Set(prev)
                              if (e.target.checked) next.add(row.listing_id)
                              else next.delete(row.listing_id)
                              return next
                            })
                          }}
                          className="h-3.5 w-3.5 cursor-pointer"
                        />
                      </td>
                      <td className="sticky left-8 bg-inherit px-3 py-1.5 font-medium text-slate-800 max-w-[200px] truncate">
                        <span title={row.selected_title ?? row.sku_external_id}>
                          {row.selected_title ?? row.sku_external_id}
                        </span>
                      </td>
                      {uniqueAttrs.map((attr) => {
                        const value = getCellValue(row, attr.attribute_id)
                        const isDirty = dirty[row.listing_id]?.[attr.attribute_id] !== undefined
                        const isEmpty = !value && attr.is_required
                        return (
                          <td key={attr.attribute_id} className="px-2 py-1">
                            <input
                              type="text"
                              value={value}
                              onChange={(e) => setCellValue(row.listing_id, attr.attribute_id, e.target.value)}
                              className={`w-full rounded border text-xs px-2 py-1 outline-none focus:ring-1 focus:ring-blue-400 ${
                                isEmpty
                                  ? "border-red-300 bg-red-50"
                                  : isDirty
                                  ? "border-blue-300 bg-blue-50"
                                  : "border-transparent bg-transparent hover:border-slate-200"
                              }`}
                              placeholder={isEmpty ? "obrigatório" : ""}
                            />
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )
      })}
    </div>
  )
}
