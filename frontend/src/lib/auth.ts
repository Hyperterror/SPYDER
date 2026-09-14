import { authApi } from './api'
import type { User } from '@/types'

export function getStoredUser(): User | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = localStorage.getItem('user')
    return raw ? (JSON.parse(raw) as User) : null
  } catch {
    return null
  }
}

export function setStoredTokens(accessToken: string, refreshToken: string) {
  localStorage.setItem('access_token', accessToken)
  localStorage.setItem('refresh_token', refreshToken)
}

export function setStoredUser(user: User) {
  localStorage.setItem('user', JSON.stringify(user))
}

export function clearAuth() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  localStorage.removeItem('user')
}

export async function login(email: string, password: string): Promise<User> {
  const { data } = await authApi.login(email, password)
  setStoredTokens(data.access_token, data.refresh_token)
  setStoredUser(data.user as User)
  return data.user as User
}

export async function logout() {
  try { await authApi.logout() } catch { /* ignore */ }
  clearAuth()
}

export function isAuthenticated(): boolean {
  if (typeof window === 'undefined') return false
  return !!localStorage.getItem('access_token')
}
