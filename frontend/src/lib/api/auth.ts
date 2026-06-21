import { apiFetch } from "./client"

export interface LoginResponse {
  access_token: string
  refresh_token: string
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  return apiFetch<LoginResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  })
}

export async function getMLConnectUrl(): Promise<string> {
  const res = await apiFetch<{ auth_url: string }>("/api/v1/auth/ml/connect")
  return res.auth_url
}
