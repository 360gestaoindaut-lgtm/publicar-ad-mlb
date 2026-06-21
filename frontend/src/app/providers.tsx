"use client"

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { Toaster } from "sonner"
import { useState } from "react"
import { ThemeProvider } from "@/contexts/ThemeContext"

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 5000,
            retry: 1,
          },
        },
      })
  )

  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        {children}
        <Toaster position="top-right" richColors />
      </QueryClientProvider>
    </ThemeProvider>
  )
}
