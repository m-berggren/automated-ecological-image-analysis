import { API_BASE_URL } from '@/lib/config'
import { tokenManager } from '@/lib/token'

let refreshPromise: Promise<boolean> | null = null

async function tryRefresh(): Promise<boolean> {
  const refresh = tokenManager.getRefreshToken()
  if (!refresh) return false

  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/refresh/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh }),
    })
    if (!res.ok) return false
    const data = await res.json()
    tokenManager.setFromRefresh(data.access, data.refresh)
    return true
  } catch {
    return false
  }
}

export async function api(url: string, options: RequestInit = {}): Promise<Response> {
  const doFetch = () => {
    const token = tokenManager.getAccessToken()
    const isForm = options.body instanceof FormData

    const headers: Record<string, string> = {
      ...(isForm ? {} : { 'Content-Type': 'application/json' }),
      ...((options.headers as Record<string, string>) ?? {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    }

    return fetch(`${API_BASE_URL}${url}`, { ...options, headers })
  }

  let res = await doFetch()

  if (res.status === 401) {
    if (!refreshPromise) {
      refreshPromise = tryRefresh().finally(() => {
        refreshPromise = null
      })
    }
    const ok = await refreshPromise
    if (ok) {
      res = await doFetch()
    } else {
      tokenManager.clear()
    }
  }

  return res
}
