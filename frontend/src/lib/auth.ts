import { authApi, setInMemoryAccessToken, getInMemoryAccessToken } from './api'
import type { User } from '@/types'

export function getStoredUser(): User | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = sessionStorage.getItem('user') ?? localStorage.getItem('user')
    if (localStorage.getItem('user')) {
      localStorage.removeItem('user')
      if (raw) sessionStorage.setItem('user', raw)
    }
    return raw ? (JSON.parse(raw) as User) : null
  } catch {
    return null
  }
}

export function setStoredUser(user: User) {
  if (typeof window !== 'undefined') {
    sessionStorage.setItem('user', JSON.stringify(user))
  }
}

export function clearAuth() {
  setInMemoryAccessToken(null)
  if (typeof window !== 'undefined') {
    sessionStorage.removeItem('user')
    localStorage.removeItem('user')
  }
}

export async function login(email: string, password: string): Promise<User> {
  const { data } = await authApi.login(email, password)
  setInMemoryAccessToken(data.access_token)
  setStoredUser(data.user as User)
  return data.user as User
}

export async function logout() {
  try { await authApi.logout() } catch { /* ignore */ }
  clearAuth()
}

export function isAuthenticated(): boolean {
  if (typeof window === 'undefined') return false
  return !!getInMemoryAccessToken()
}
