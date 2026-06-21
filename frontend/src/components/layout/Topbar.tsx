"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Plus, ShoppingBag, ChevronDown, Check } from "lucide-react"
import { useSeller } from "@/contexts/SellerContext"
import { useState, useRef, useEffect } from "react"

const BREADCRUMB_LABELS: Record<string, string> = {
  listings: "Anúncios",
  new: "Novo anúncio",
  titles: "Escolher título",
  attributes: "Atributos",
  images: "Imagens",
  preview: "Revisão e publicação",
  settings: "Configurações",
  dashboard: "Dashboard",
}

function getBreadcrumbs(pathname: string): { label: string; href: string }[] {
  const segments = pathname.split("/").filter(Boolean)
  const crumbs: { label: string; href: string }[] = []
  let path = ""

  for (const segment of segments) {
    path += `/${segment}`
    const label = BREADCRUMB_LABELS[segment] || segment
    crumbs.push({ label, href: path })
  }

  return crumbs
}

function SellerSelector() {
  const { sellers, activeSeller, setActiveSeller } = useSeller()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  if (!activeSeller) {
    return (
      <Link
        href="/settings"
        className="flex items-center gap-2 text-sm text-amber-600 hover:text-amber-700 font-medium"
      >
        <ShoppingBag className="w-4 h-4" />
        Conectar conta ML
      </Link>
    )
  }

  if (sellers.length === 1) {
    return (
      <div className="flex items-center gap-2 text-sm text-slate-600">
        <ShoppingBag className="w-4 h-4 text-yellow-500" />
        <span className="font-medium">{activeSeller.ml_nickname}</span>
      </div>
    )
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 text-sm text-slate-700 hover:text-slate-900 font-medium px-2 py-1 rounded-md hover:bg-slate-100 transition-colors"
      >
        <ShoppingBag className="w-4 h-4 text-yellow-500" />
        <span>{activeSeller.ml_nickname}</span>
        <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 w-64 bg-white border border-slate-200 rounded-lg shadow-lg z-50 py-1">
          <p className="text-xs text-slate-400 px-3 py-1.5 font-medium uppercase tracking-wide">
            Conta ativa
          </p>
          {sellers.map((seller) => (
            <button
              key={seller.id}
              onClick={() => {
                setActiveSeller(seller)
                setOpen(false)
              }}
              className="w-full flex items-center justify-between px-3 py-2 text-sm hover:bg-slate-50 transition-colors"
            >
              <span className="font-medium text-slate-800">{seller.ml_nickname}</span>
              {seller.id === activeSeller.id && (
                <Check className="w-4 h-4 text-green-600" />
              )}
            </button>
          ))}
          <div className="border-t border-slate-100 mt-1 pt-1">
            <Link
              href="/settings"
              onClick={() => setOpen(false)}
              className="block px-3 py-2 text-sm text-slate-500 hover:text-slate-700 hover:bg-slate-50 transition-colors"
            >
              + Conectar nova conta
            </Link>
          </div>
        </div>
      )}
    </div>
  )
}

export function Topbar() {
  const pathname = usePathname()
  const breadcrumbs = getBreadcrumbs(pathname)
  const isListingsRoot = pathname === "/listings"

  return (
    <header className="h-14 border-b border-slate-200 bg-white flex items-center justify-between px-6 flex-shrink-0">
      <nav className="flex items-center gap-1.5 text-sm">
        {breadcrumbs.map((crumb, i) => (
          <span key={crumb.href} className="flex items-center gap-1.5">
            {i > 0 && <span className="text-slate-400">/</span>}
            {i === breadcrumbs.length - 1 ? (
              <span className="font-medium text-slate-900">{crumb.label}</span>
            ) : (
              <Link href={crumb.href} className="text-slate-500 hover:text-slate-700">
                {crumb.label}
              </Link>
            )}
          </span>
        ))}
      </nav>

      <div className="flex items-center gap-4">
        <SellerSelector />
        {isListingsRoot && (
          <Button asChild size="sm">
            <Link href="/listings/new">
              <Plus className="w-4 h-4 mr-1" />
              Novo anúncio
            </Link>
          </Button>
        )}
      </div>
    </header>
  )
}
