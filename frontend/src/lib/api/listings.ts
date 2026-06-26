import { apiFetch } from "./client"
import type {
  ListingDetail,
  ListingSummary,
  ListingsResponse,
  Condition,
} from "@/types/listing"

export interface CreateListingPayload {
  sku_description: string
  sku_brand: string
  price: number
  stock_quantity: number
  condition: Condition
  listing_type_id?: string
}

export async function createListing(
  payload: CreateListingPayload
): Promise<ListingSummary> {
  return apiFetch<ListingSummary>("/api/v1/listings", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export async function getListings(params?: {
  status?: string
  page?: number
  page_size?: number
}): Promise<ListingsResponse> {
  const query = new URLSearchParams()
  if (params?.status) query.set("status", params.status)
  if (params?.page) query.set("page", String(params.page))
  if (params?.page_size) query.set("page_size", String(params.page_size))
  const qs = query.toString()
  return apiFetch<ListingsResponse>(`/api/v1/listings${qs ? `?${qs}` : ""}`)
}

export async function getListing(id: string): Promise<ListingDetail> {
  return apiFetch<ListingDetail>(`/api/v1/listings/${id}`)
}

export async function deleteListing(id: string): Promise<void> {
  return apiFetch<void>(`/api/v1/listings/${id}`, { method: "DELETE" })
}

export async function startPipeline(id: string): Promise<ListingSummary> {
  return apiFetch<ListingSummary>(`/api/v1/listings/${id}/pipeline/start`, {
    method: "POST",
  })
}

export async function retryPipeline(id: string): Promise<ListingSummary> {
  return apiFetch<ListingSummary>(`/api/v1/listings/${id}/pipeline/retry`, {
    method: "POST",
  })
}

export async function selectTitle(
  listingId: string,
  titleId: string
): Promise<ListingSummary> {
  return apiFetch<ListingSummary>(
    `/api/v1/listings/${listingId}/titles/${titleId}/select`,
    { method: "POST" }
  )
}

export interface AttributeInput {
  attribute_id: string
  value_id?: string
  value_name: string
}

export async function submitAttributes(
  listingId: string,
  attributes: AttributeInput[]
): Promise<ListingSummary> {
  return apiFetch<ListingSummary>(`/api/v1/listings/${listingId}/attributes`, {
    method: "PUT",
    body: JSON.stringify({ attributes }),
  })
}

export async function generateImages(id: string): Promise<ListingSummary> {
  return apiFetch<ListingSummary>(
    `/api/v1/listings/${id}/pipeline/generate_images`,
    { method: "POST" }
  )
}

export async function approveImages(
  id: string,
  approved_ids: string[]
): Promise<ListingSummary> {
  return apiFetch<ListingSummary>(`/api/v1/listings/${id}/images/approve`, {
    method: "POST",
    body: JSON.stringify({ approved_ids }),
  })
}

export async function publishListing(id: string): Promise<ListingSummary> {
  return apiFetch<ListingSummary>(`/api/v1/listings/${id}/pipeline/publish`, {
    method: "POST",
  })
}
