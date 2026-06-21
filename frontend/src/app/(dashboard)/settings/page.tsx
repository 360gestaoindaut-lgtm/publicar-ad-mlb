"use client"

import { useQuery } from "@tanstack/react-query"
import { listSellers } from "@/lib/api/sellers"
import { getMLConnectUrl } from "@/lib/api/auth"
import { useSeller } from "@/contexts/SellerContext"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Loader2, CheckCircle, ExternalLink, ShoppingBag, Plus, Check } from "lucide-react"
import { toast } from "sonner"
import { useState } from "react"
import { format } from "date-fns"
import { ptBR } from "date-fns/locale"

export default function SettingsPage() {
  const [connecting, setConnecting] = useState(false)
  const { activeSeller, setActiveSeller, reload } = useSeller()

  const { data: sellers = [], isLoading } = useQuery({
    queryKey: ["sellers"],
    queryFn: listSellers,
    retry: 1,
    refetchOnWindowFocus: true,
  })

  const handleConnect = async () => {
    setConnecting(true)
    try {
      const url = await getMLConnectUrl()
      window.location.href = url
    } catch (err) {
      const message = err instanceof Error ? err.message : "Erro ao obter URL de conexão"
      toast.error(message)
      setConnecting(false)
    }
  }

  // Quando voltar do OAuth com ml_connected=true, recarrega a lista de sellers
  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search)
    if (params.get("ml_connected") === "true") {
      reload()
      window.history.replaceState({}, "", "/settings")
    }
  }

  return (
    <div className="max-w-xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Configurações</h1>
        <p className="text-sm text-slate-500 mt-1">
          Gerencie as contas do Mercado Livre conectadas.
        </p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <ShoppingBag className="w-5 h-5 text-yellow-500" />
                Contas Mercado Livre
              </CardTitle>
              <CardDescription className="mt-1">
                Cada conta conectada pode ter seus próprios anúncios gerenciados independentemente.
              </CardDescription>
            </div>
            <Button size="sm" onClick={handleConnect} disabled={connecting}>
              {connecting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <>
                  <Plus className="w-4 h-4 mr-1" />
                  Conectar conta
                </>
              )}
            </Button>
          </div>
        </CardHeader>

        <CardContent>
          {isLoading ? (
            <div className="flex items-center gap-2 text-slate-500">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="text-sm">Carregando contas...</span>
            </div>
          ) : sellers.length === 0 ? (
            <div className="text-center py-8">
              <ShoppingBag className="w-10 h-10 text-slate-300 mx-auto mb-3" />
              <p className="text-slate-500 text-sm">Nenhuma conta conectada ainda.</p>
              <Button className="mt-4" onClick={handleConnect} disabled={connecting}>
                {connecting ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Redirecionando...
                  </>
                ) : (
                  <>
                    <ExternalLink className="w-4 h-4 mr-2" />
                    Conectar conta Mercado Livre
                  </>
                )}
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              {sellers.map((seller) => {
                const isActive = activeSeller?.id === seller.id
                return (
                  <div
                    key={seller.id}
                    className={`border rounded-lg p-4 transition-colors ${
                      isActive ? "border-green-300 bg-green-50" : "border-slate-200 bg-white"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center gap-2 min-w-0">
                        <CheckCircle className={`w-4 h-4 flex-shrink-0 ${isActive ? "text-green-600" : "text-slate-400"}`} />
                        <span className="font-medium text-slate-900 truncate">{seller.ml_nickname}</span>
                        {isActive && (
                          <span className="text-xs font-medium text-green-700 bg-green-100 px-2 py-0.5 rounded-full flex-shrink-0">
                            Ativa
                          </span>
                        )}
                      </div>
                      {!isActive && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setActiveSeller(seller)}
                          className="flex-shrink-0"
                        >
                          <Check className="w-3.5 h-3.5 mr-1" />
                          Usar esta
                        </Button>
                      )}
                    </div>

                    <div className="mt-3 space-y-1 text-sm text-slate-500">
                      <div className="flex justify-between">
                        <span>ML User ID</span>
                        <span className="font-mono text-xs">{seller.ml_user_id}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Token expira em</span>
                        <span>
                          {format(new Date(seller.token_expires_at), "dd/MM/yyyy HH:mm", { locale: ptBR })}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span>Conectada em</span>
                        <span>
                          {format(new Date(seller.granted_at), "dd/MM/yyyy", { locale: ptBR })}
                        </span>
                      </div>
                    </div>

                    <Button
                      variant="ghost"
                      size="sm"
                      className="mt-3 text-slate-500 hover:text-slate-700 w-full justify-start px-0"
                      onClick={handleConnect}
                      disabled={connecting}
                    >
                      <ExternalLink className="w-3.5 h-3.5 mr-1.5" />
                      Reconectar / renovar token
                    </Button>
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
