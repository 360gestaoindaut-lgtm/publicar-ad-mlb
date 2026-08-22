import { apiFetch } from "./client"
import type { SellerImageConfig, SellerImageConfigUpsert } from "@/types/seller-image-config"

export async function getSellerImageConfig(): Promise<SellerImageConfig | null> {
  return apiFetch<SellerImageConfig | null>("/api/v1/sellers/image-config")
}

export async function upsertSellerImageConfig(
  payload: SellerImageConfigUpsert
): Promise<SellerImageConfig> {
  return apiFetch<SellerImageConfig>("/api/v1/sellers/image-config", {
    method: "PUT",
    body: JSON.stringify(payload),
  })
}
