"use client"

import { createContext, useContext, useEffect, useState, useCallback } from "react"
import { listSellers, type SellerOut } from "@/lib/api/sellers"

interface SellerContextValue {
  sellers: SellerOut[]
  activeSeller: SellerOut | null
  setActiveSeller: (seller: SellerOut) => void
  isLoading: boolean
  reload: () => Promise<void>
}

const SellerContext = createContext<SellerContextValue | null>(null)

const STORAGE_KEY = "active_seller_id"

export function SellerProvider({ children }: { children: React.ReactNode }) {
  const [sellers, setSellers] = useState<SellerOut[]>([])
  const [activeSeller, setActiveSellerState] = useState<SellerOut | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const data = await listSellers()
      setSellers(data)

      const savedId = typeof window !== "undefined" ? localStorage.getItem(STORAGE_KEY) : null
      const found = savedId ? data.find((s) => s.id === savedId) : null
      setActiveSellerState(found ?? data[0] ?? null)
    } catch {
      // Se a chamada falhar (ex: sem token), não propaga — o layout já redireciona
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const setActiveSeller = useCallback((seller: SellerOut) => {
    setActiveSellerState(seller)
    if (typeof window !== "undefined") {
      localStorage.setItem(STORAGE_KEY, seller.id)
    }
  }, [])

  return (
    <SellerContext.Provider value={{ sellers, activeSeller, setActiveSeller, isLoading, reload: load }}>
      {children}
    </SellerContext.Provider>
  )
}

export function useSeller(): SellerContextValue {
  const ctx = useContext(SellerContext)
  if (!ctx) throw new Error("useSeller deve ser usado dentro de <SellerProvider>")
  return ctx
}
