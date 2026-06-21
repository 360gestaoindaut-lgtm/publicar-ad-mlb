const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001"

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message)
    this.name = "ApiError"
  }
}

function getToken(): string | null {
  if (typeof window === "undefined") return null
  return localStorage.getItem("access_token")
}

export function getActiveSellerId(): string | null {
  if (typeof window === "undefined") return null
  return localStorage.getItem("active_seller_id")
}

export function clearAuth() {
  if (typeof window === "undefined") return
  localStorage.removeItem("access_token")
  localStorage.removeItem("refresh_token")
  localStorage.removeItem("active_seller_id")
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (res.status === 401) {
    clearAuth()
    if (typeof window !== "undefined") {
      window.location.href = "/login"
    }
    throw new ApiError(401, "Sessão expirada. Faça login novamente.")
  }

  if (res.status === 204) {
    return undefined as T
  }

  const data = await res.json().catch(() => ({ detail: res.statusText }))

  if (!res.ok) {
    throw new ApiError(res.status, data?.detail || "Erro desconhecido")
  }

  return data as T
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken()
  const sellerId = getActiveSellerId()

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  }

  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }

  if (sellerId) {
    headers["X-Seller-ID"] = sellerId
  }

  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
  })

  return handleResponse<T>(res)
}
