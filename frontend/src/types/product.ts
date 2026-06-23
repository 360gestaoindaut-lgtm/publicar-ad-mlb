export interface ProductFormData {
  sku: string
  description: string
  brand?: string | null
  ean?: string | null
  ncm?: string | null
  fiscal_origin?: number | null
  icms_cst?: string | null
  icms_rate?: string | null
  pis_cst?: string | null
  cofins_cst?: string | null
  weight_kg?: string | null
  length_cm?: number | null
  width_cm?: number | null
  height_cm?: number | null
  acquisition_cost?: string | null
}

export interface Product {
  id: string
  seller_id: string
  sku: string
  description: string
  brand: string | null
  ean: string | null
  ncm: string | null
  fiscal_origin: number | null
  icms_cst: string | null
  icms_rate: string | null
  pis_cst: string | null
  cofins_cst: string | null
  weight_kg: string | null
  length_cm: number | null
  width_cm: number | null
  height_cm: number | null
  acquisition_cost: string | null
  created_at: string
  updated_at: string
}

export interface ProductPage {
  items: Product[]
  total: number
  page: number
  page_size: number
}

export interface ProductUploadResult {
  total: number
  accepted: number
  rejected: number
  errors: Array<{ row: number; sku: string; error: string }>
}
