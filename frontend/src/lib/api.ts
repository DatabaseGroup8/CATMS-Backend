import type { Session } from './types';
export const API_READY = process.env.NEXT_PUBLIC_API_READY === 'true';
let csrf = '';
export async function api<T>(path: string, method = 'GET', data?: unknown): Promise<T> {
 if (!API_READY) throw new Error('SQL-backed APIs are not connected yet.');
 if (method !== 'GET' && !csrf) csrf = (await api<Session>('session/')).csrf_token;
 const response = await fetch(`/api/frontend/${path}`, {
  method, credentials: 'same-origin', cache: 'no-store',
  headers: {'Content-Type': 'application/json', ...(method !== 'GET' ? {'X-CSRFToken': csrf} : {})},
  ...(data === undefined ? {} : {body: JSON.stringify(data)}),
 });
 const payload = await response.json().catch(() => null);
 if (!response.ok || !payload?.success) throw new Error(payload?.message || 'Could not reach the clinic API. Check the backend connection.');
 if (payload.data?.csrf_token) csrf = payload.data.csrf_token;
 return payload.data as T;
}
