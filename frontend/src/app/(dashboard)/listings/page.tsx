import Link from "next/link"
import { Plus } from "lucide-react"
import { PipelineBoard } from "@/components/listings/PipelineBoard"
import { Button } from "@/components/ui/button"

export default function ListingsPage() {
  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Anúncios</h1>
          <p className="text-sm text-slate-500 mt-1">
            Gerencie seus anúncios no Mercado Livre. Atualiza automaticamente a cada 8 segundos.
          </p>
        </div>
        <Button asChild size="sm">
          <Link href="/listings/new">
            <Plus className="w-4 h-4 mr-1" />
            Novo anúncio
          </Link>
        </Button>
      </div>
      <PipelineBoard />
    </div>
  )
}
