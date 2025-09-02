// src/lib/api.ts
import axios, { isAxiosError } from 'axios';
import { getToken, saveToken, clearToken } from './auth';

// Base URL dinámica para funcionar en cualquier IP/host.
// Prioriza variables Vite y, si no existen, usa el hostname actual a puerto 8000.
const API_BASE = (import.meta as any).env?.VITE_API_BASE?.trim()
  || `${window.location.protocol}//${window.location.hostname}:${(import.meta as any).env?.VITE_API_PORT || '8000'}`;

const API = axios.create({
  baseURL: API_BASE,
  timeout: 15000,
});

// ---------- Adjunta JWT en cada request (compatible Axios v1) ----------
API.interceptors.request.use((cfg) => {
  const t = getToken();
  if (t) {
    const h = cfg.headers as any;
    if (h?.set && typeof h.set === 'function') {
      // AxiosHeaders (v1)
      h.set('Authorization', `Bearer ${t}`);
    } else {
      // Objeto plano
      cfg.headers = { ...(cfg.headers as any), Authorization: `Bearer ${t}` } as any;
    }
  }
  return cfg;
});

// ---------- Manejo 401: revalida con /auth/me antes de limpiar token ----------
API.interceptors.response.use(
  (r) => r,
  async (err) => {
    if (isAxiosError(err) && err.response?.status === 401) {
      try {
        // si el 401 ya fue en /auth/me, limpia y corta
        const url = err.config?.url || '';
        if (url.includes('/auth/me')) throw new Error('me failed');

        const t = getToken();
        if (!t) throw new Error('no token');

        await API.get('/auth/me'); // si funciona, no limpiamos; propagamos error original
      } catch {
        clearToken();
      }
    }
    return Promise.reject(err);
  }
);

export type RealPoint = {
  ts: string;
  value: any;
  type?: 'analog' | 'digital';
  device_ip?: string;
  endpoint?: string;
};

// ------- auth -------
export async function login(username: string, password: string) {
  const { data } = await API.post('/auth/login', { username, password });
  if (data?.access_token) saveToken(data.access_token);
  return data as {
    access_token: string;
    role: 'admin' | 'user';
    username: string;
    expires_in: number;
  };
}

export async function me() {
  const { data } = await API.get('/auth/me');
  return data as { username: string; role: 'admin' | 'user' };
}

// ------- datos -------
export async function fetchSensors() {
  const { data } = await API.get('/sensors');
  return data.items as string[];
}

// Solo pide realtime de seleccionados; si no hay, no mandes names
export async function fetchRealtime(names?: string[], signal?: AbortSignal) {
  const body: any = {};
  if (names && names.length) body.names = names;
  const { data } = await API.post('/realtime', body, { signal });
  return data as Record<string, RealPoint>;
}

export async function fetchMeasurements(name: string, start?: string, end?: string) {
  const params: any = { name };
  if (start) params.start = start;
  if (end) params.end = end;
  const { data } = await API.get('/measurements', { params });
  return data as Array<{ ts: string; value: number; device_ip: string; endpoint: string; type: string }>;
}

// ------- exportaciones -------
export async function exportExcel(names: string[], start?: string, end?: string) {
  const params = new URLSearchParams();
  names.forEach((n) => params.append('names', n));
  if (start) params.append('start', start);
  if (end) params.append('end', end);
  const { data } = await API.get(`/export/excel?${params.toString()}`, { responseType: 'blob' });
  const url = URL.createObjectURL(new Blob([data]));
  const a = document.createElement('a');
  a.href = url;
  a.download = 'export.xlsx';
  a.click();
  URL.revokeObjectURL(url);
}

export async function exportPDF(names: string[], start?: string, end?: string) {
  const params = new URLSearchParams();
  names.forEach((n) => params.append('names', n));
  if (start) params.append('start', start);
  if (end) params.append('end', end);
  const { data } = await API.get(`/export/pdf?${params.toString()}`, { responseType: 'blob' });
  const url = URL.createObjectURL(new Blob([data], { type: 'application/pdf' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = 'report.pdf';
  a.click();
  URL.revokeObjectURL(url);
}
