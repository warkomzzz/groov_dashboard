// src/lib/auth.ts
const KEY = 'jwt';

export function saveToken(t: string) { localStorage.setItem(KEY, t); }
export function getToken(): string | null { return localStorage.getItem(KEY); }
export function clearToken() { localStorage.removeItem(KEY); }
