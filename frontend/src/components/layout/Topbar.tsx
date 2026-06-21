"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Plus } from "lucide-react"

const BREADCRUMB_LABELS: Record<string, string> = {
  listings: "Anúncios",
  new: "Novo anúncio",
  titles: "Escolher título",
  attributes: "Atributos",
  images: "Imagens",
  preview: "Revisão e publicação",
  settings: "Configurações",
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

      {isListingsRoot && (
        <Button asChild size="sm">
          <Link href="/listings/new">
            <Plus className="w-4 h-4 mr-1" />
            Novo anúncio
          </Link>
        </Button>
      )}
    </header>
  )
}
