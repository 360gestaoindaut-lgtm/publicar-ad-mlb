import { apiFetch } from "./client"
import type { ImageEngineState } from "@/types/system"

export async function getImageEngineState(): Promise<ImageEngineState> {
  return apiFetch<ImageEngineState>("/api/v1/system/image-engine")
}
