export interface ImageEngineState {
  current_engine: "openai" | "gemini"
  engine_label: string
  pending_confirmation_count: number
  pending_listing_ids: string[]
  last_openai_error: string | null
  last_switch_to_openai_at: string | null
}
