import { apiFetch } from "./client"
import type { TitleConfig, TitleConfigCreate, TitleConfigUpdate } from "@/types/title-config"

export async function getTitleConfigs(): Promise<TitleConfig[]> {
  return apiFetch<TitleConfig[]>("/api/v1/title-configs")
}

export async function createTitleConfig(payload: TitleConfigCreate): Promise<TitleConfig> {
  return apiFetch<TitleConfig>("/api/v1/title-configs", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export async function updateTitleConfig(id: string, payload: TitleConfigUpdate): Promise<TitleConfig> {
  return apiFetch<TitleConfig>(`/api/v1/title-configs/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  })
}

export async function deleteTitleConfig(id: string): Promise<void> {
  return apiFetch<void>(`/api/v1/title-configs/${id}`, { method: "DELETE" })
}
