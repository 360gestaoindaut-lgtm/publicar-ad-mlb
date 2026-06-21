"use client"

import { useQuery } from "@tanstack/react-query"
import { getMLStatus, getMLConnectUrl } from "@/lib/api/auth"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Loader2, CheckCircle, XCircle, ExternalLink, ShoppingBag } from "lucide-react"
import { toast } from "sonner"
import { useState } from "react"
import { format } from "date-fns"
import { ptBR } from "date-fns/locale"

export default function SettingsPage() {
  const [connecting, setConnecting] = useState(false)

  const { data: mlStatus, isLoading } = useQuery({
    queryKey: ["ml-status"],
    queryFn: getMLStatus,
    retry: 1,
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

  return (
    <div className="max-w-xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Configurações</h1>
        <p className="text-sm text-slate-500 mt-1">
          Gerencie a integração com o Mercado Livre.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShoppingBag className="w-5 h-5 text-yellow-500" />
            Conta Mercado Livre
          </CardTitle>
          <CardDescription>
            Conecte sua conta do Mercado Livre para publicar anúncios.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center gap-2 text-slate-500">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="text-sm">Verificando conexão...</span>
            </div>
          ) : mlStatus?.connected ? (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-green-600">
                <CheckCircle className="w-5 h-5" />
                <span className="font-medium">Conta conectada</span>
              </div>

              <div className="bg-slate-50 rounded-lg p-4 space-y-2">
                {mlStatus.ml_nickname && (
                  <div className="flex justify-between text-sm">
                    <span className="text-slate-500">Usuário</span>
                    <span className="font-medium">{mlStatus.ml_nickname}</span>
                  </div>
                )}
                {mlStatus.token_expires_at && (
                  <div className="flex justify-between text-sm">
                    <span className="text-slate-500">Token expira em</span>
                    <span className="font-medium">
                      {format(new Date(mlStatus.token_expires_at), "dd/MM/yyyy HH:mm", {
                        locale: ptBR,
                      })}
                    </span>
                  </div>
                )}
              </div>

              <Button variant="outline" onClick={handleConnect} disabled={connecting}>
                {connecting ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Redirecionando...
                  </>
                ) : (
                  <>
                    <ExternalLink className="w-4 h-4 mr-2" />
                    Reconectar conta
                  </>
                )}
              </Button>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-slate-500">
                <XCircle className="w-5 h-5 text-slate-400" />
                <span className="text-sm">Nenhuma conta conectada</span>
              </div>

              <p className="text-sm text-slate-600">
                Para publicar anúncios no Mercado Livre, você precisa autorizar o aplicativo a
                acessar sua conta.
              </p>

              <Button onClick={handleConnect} disabled={connecting} className="w-full">
                {connecting ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Redirecionando para o Mercado Livre...
                  </>
                ) : (
                  <>
                    <ShoppingBag className="w-4 h-4 mr-2" />
                    Conectar conta Mercado Livre
                  </>
                )}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
