export async function api(url: string, options: RequestInit = {}) {
  const token = localStorage.getItem("token")

  const res = await fetch(`http://localhost:8000${url}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
      ...(token && { Authorization: `Token ${token}` })
    }
  })

  if (res.status === 401) {
    localStorage.removeItem("token")
  }

  return res
}