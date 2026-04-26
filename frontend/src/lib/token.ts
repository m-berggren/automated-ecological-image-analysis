import { jwtDecode, type JwtPayload } from 'jwt-decode'

interface AppJwtPayload extends JwtPayload {
  user_id: number
  username: string
  email: string
  is_staff: boolean
  exp: number
}

const ACCESS_KEY = 'access_token'
const REFRESH_KEY = 'refresh_token'

class TokenManager {
  private access: string | null
  private refresh: string | null
  private decoded: AppJwtPayload | null

  constructor() {
    this.access = localStorage.getItem(ACCESS_KEY)
    this.refresh = localStorage.getItem(REFRESH_KEY)
    this.decoded = this.access ? this.decode(this.access) : null
    this.checkExpiry()
  }

  set(access: string, refresh: string): void {
    this.access = access
    this.refresh = refresh
    this.decoded = this.decode(access)
    localStorage.setItem(ACCESS_KEY, access)
    localStorage.setItem(REFRESH_KEY, refresh)
  }

  clear(): void {
    this.access = null
    this.refresh = null
    this.decoded = null
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  }

  getAccessToken(): string | null {
    this.checkExpiry()
    return this.access
  }

  getRefreshToken(): string | null {
    return this.refresh
  }

  isSignedIn(): boolean {
    this.checkExpiry()
    return !!this.access
  }

  getUserId(): number | null {
    this.checkExpiry()
    return this.decoded?.user_id ?? null
  }

  getUsername(): string | null {
    this.checkExpiry()
    return this.decoded?.username ?? null
  }

  getEmail(): string | null {
    this.checkExpiry()
    return this.decoded?.email ?? null
  }

  isStaff(): boolean {
    this.checkExpiry()
    return this.decoded?.is_staff ?? false
  }

  /** Update tokens after a refresh response. */
  setFromRefresh(access: string, refresh?: string): void {
    this.access = access
    this.decoded = this.decode(access)
    localStorage.setItem(ACCESS_KEY, access)
    if (refresh) {
      this.refresh = refresh
      localStorage.setItem(REFRESH_KEY, refresh)
    }
  }

  private decode(token: string): AppJwtPayload | null {
    try {
      return jwtDecode<AppJwtPayload>(token)
    } catch {
      return null
    }
  }

  private checkExpiry(): void {
    if (!this.decoded) return
    if (this.decoded.exp < Date.now() / 1000) {
      // Access token expired — keep refresh (auto-refresh will try it)
      this.access = null
      this.decoded = null
      localStorage.removeItem(ACCESS_KEY)
    }
  }
}

export const tokenManager = new TokenManager()
