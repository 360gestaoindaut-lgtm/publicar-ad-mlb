"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { submitAttributes } from "@/lib/api/listings"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { toast } from "sonner"
import { Loader2 } from "lucide-react"
import type { AttributeOut } from "@/types/listing"

interface AttributeValue {
  value_id?: string
  value_name: string
}

interface Props {
  listingId: string
  attributes: AttributeOut[]
}

export function AttributeForm({ listingId, attributes }: Props) {
  const router = useRouter()
  const queryClient = useQueryClient()

  const requiredAttributes = attributes.filter((a) => a.is_required)

  const initialValues: Record<string, AttributeValue> = {}
  requiredAttributes.forEach((attr) => {
    initialValues[attr.attribute_id] = {
      value_id: attr.value_id || undefined,
      value_name: attr.value_name || "",
    }
  })

  const [values, setValues] = useState<Record<string, AttributeValue>>(initialValues)

  const mutation = useMutation({
    mutationFn: () => {
      const payload = requiredAttributes.map((attr) => {
        const val = values[attr.attribute_id]
        return {
          attribute_id: attr.attribute_id,
          value_id: val?.value_id,
          value_name: val?.value_name || "",
        }
      })
      return submitAttributes(listingId, payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["listing", listingId] })
      queryClient.invalidateQueries({ queryKey: ["listings"] })
      toast.success("Atributos salvos com sucesso!")
      router.push(`/listings/${listingId}`)
    },
    onError: (err: Error) => {
      toast.error(err.message || "Erro ao salvar atributos")
    },
  })

  const handleSelectChange = (attributeId: string, optionId: string, optionName: string) => {
    setValues((prev) => ({
      ...prev,
      [attributeId]: { value_id: optionId, value_name: optionName },
    }))
  }

  const handleTextChange = (attributeId: string, text: string) => {
    setValues((prev) => ({
      ...prev,
      [attributeId]: { value_name: text },
    }))
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()

    const missing = requiredAttributes.filter((attr) => {
      const val = values[attr.attribute_id]
      return !val?.value_name?.trim()
    })

    if (missing.length > 0) {
      toast.error(`Preencha os campos obrigatórios: ${missing.map((a) => a.attribute_name).join(", ")}`)
      return
    }

    mutation.mutate()
  }

  if (requiredAttributes.length === 0) {
    return (
      <div className="text-center py-12 text-slate-500">
        <p>Nenhum atributo obrigatório para preencher.</p>
        <Button
          className="mt-4"
          onClick={() => {
            mutation.mutate()
          }}
        >
          Continuar
        </Button>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <p className="text-sm text-slate-600">
        Preencha os atributos obrigatórios para a categoria do seu produto.
      </p>

      {requiredAttributes.map((attr) => (
        <div key={attr.attribute_id} className="space-y-2">
          <Label htmlFor={attr.attribute_id}>
            {attr.attribute_name}
            <span className="text-red-500 ml-1">*</span>
          </Label>

          {attr.allowed_values && attr.allowed_values.length > 0 ? (
            <select
              id={attr.attribute_id}
              value={values[attr.attribute_id]?.value_id || ""}
              onChange={(e) => {
                const selected = attr.allowed_values!.find((o) => o.id === e.target.value)
                if (selected) {
                  handleSelectChange(attr.attribute_id, selected.id, selected.name)
                }
              }}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              <option value="">Selecione...</option>
              {attr.allowed_values.map((opt) => (
                <option key={opt.id} value={opt.id}>
                  {opt.name}
                </option>
              ))}
            </select>
          ) : (
            <Input
              id={attr.attribute_id}
              value={values[attr.attribute_id]?.value_name || ""}
              onChange={(e) => handleTextChange(attr.attribute_id, e.target.value)}
              placeholder={`Digite ${attr.attribute_name.toLowerCase()}`}
            />
          )}

          {attr.source === "ai" && (
            <p className="text-xs text-slate-400">Sugerido pela IA — confirme ou altere</p>
          )}
        </div>
      ))}

      <Button type="submit" disabled={mutation.isPending} className="w-full">
        {mutation.isPending ? (
          <>
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            Salvando...
          </>
        ) : (
          "Salvar e continuar"
        )}
      </Button>
    </form>
  )
}
