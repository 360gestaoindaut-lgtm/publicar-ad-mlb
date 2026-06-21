import { PipelineBoard } from "@/components/listings/PipelineBoard"

export default function ListingsPage() {
  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Anúncios</h1>
        <p className="text-sm text-slate-500 mt-1">
          Gerencie seus anúncios no Mercado Livre. Atualiza automaticamente a cada 8 segundos.
        </p>
      </div>
      <PipelineBoard />
    </div>
  )
}
