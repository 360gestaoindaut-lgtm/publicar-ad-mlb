export interface SellerImageConfig {
  id: string
  seller_id: string
  raw_base_url: string
  write_bucket_name: string | null
  write_endpoint_url: string | null
  has_write_credentials: boolean
  created_at: string
  updated_at: string
}

export interface SellerImageConfigUpsert {
  raw_base_url: string
  write_bucket_name?: string | null
  write_endpoint_url?: string | null
  write_access_key_id?: string | null
  write_secret_access_key?: string | null
}
