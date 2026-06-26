export interface TitleConfig {
  id: string
  seller_id: string
  product_group: string
  title_structure: string
  title_rules: string | null
  is_default: boolean
  created_at: string
  updated_at: string
}

export interface TitleConfigCreate {
  product_group: string
  title_structure: string
  title_rules?: string | null
  is_default?: boolean
}

export interface TitleConfigUpdate {
  title_structure?: string
  title_rules?: string | null
  is_default?: boolean
}
