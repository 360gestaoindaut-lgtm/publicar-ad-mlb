"use client"

import { Badge } from "@/components/ui/badge"
import type { ListingStatus } from "@/types/listing"
import { STATUS_LABELS } from "@/types/listing"

const STATUS_VARIANTS: Record<
  ListingStatus,
  "default" | "secondary" | "destructive" | "outline"
> = {
  draft: "outline",
  generating_title: "secondary",
  pending_title_approval: "default",
  predicting_category: "secondary",
  pending_seller_attributes: "default",
  pending_description: "secondary",
  generating_images: "secondary",
  pending_image_approval: "default",
  generating_description: "secondary",
  ready_to_publish: "default",
  publishing: "secondary",
  published: "default",
  failed: "destructive",
}

const STATUS_COLORS: Partial<Record<ListingStatus, string>> = {
  published: "bg-green-100 text-green-800 border-green-200",
  ready_to_publish: "bg-blue-100 text-blue-800 border-blue-200",
  pending_title_approval: "bg-yellow-100 text-yellow-800 border-yellow-200",
  pending_seller_attributes: "bg-yellow-100 text-yellow-800 border-yellow-200",
  pending_image_approval: "bg-yellow-100 text-yellow-800 border-yellow-200",
  generating_title: "bg-purple-100 text-purple-800 border-purple-200",
  generating_images: "bg-purple-100 text-purple-800 border-purple-200",
  generating_description: "bg-purple-100 text-purple-800 border-purple-200",
  predicting_category: "bg-purple-100 text-purple-800 border-purple-200",
  publishing: "bg-purple-100 text-purple-800 border-purple-200",
}

interface Props {
  status: ListingStatus
  className?: string
}

export function ListingStatusBadge({ status, className }: Props) {
  const label = STATUS_LABELS[status] || status
  const colorClass = STATUS_COLORS[status]

  if (colorClass) {
    return (
      <span
        className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${colorClass} ${className || ""}`}
      >
        {label}
      </span>
    )
  }

  return (
    <Badge variant={STATUS_VARIANTS[status] || "outline"} className={className}>
      {label}
    </Badge>
  )
}
