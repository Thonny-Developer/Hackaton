// Запросы к бэкенду для аккаунта: вход, профиль, избранное, сообщения о доступности
import { API_BASE } from "./geo";

export type AccessPref = "noSteps" | "elevator" | "wide" | "ramp" | "toilet";

export type ApiUser = {
  id: number;
  email: string;
  name: string | null;
  role: "admin" | "editor" | "user";
  accessibility_prefs: AccessPref[];
  created_at: string;
};

export type ApiBuilding = { id: number; name: string; address: string | null; lat: number | null; lon: number | null };

export type ApiReport = {
  id: number;
  building_id: number;
  building_name: string | null;
  text: string;
  status: "new" | "confirmed" | "rejected";
  created_at: string;
};

type Page<T> = { items: T[]; total: number };

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

const TOKEN_KEY = "seeway.token";

// «Запомнить меня» кладёт токен в localStorage, иначе он живёт до закрытия вкладки
export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY); } catch { return null; }
}

export function setToken(token: string | null, remember = false) {
  try {
    localStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(TOKEN_KEY);
    if (token) (remember ? localStorage : sessionStorage).setItem(TOKEN_KEY, token);
  } catch { /* хранилище недоступно: токен останется только в памяти до перезагрузки */ }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && typeof init.body === "string") headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/v1${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Сервер недоступен. Проверьте подключение и попробуйте ещё раз.");
  }
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    const message = typeof detail === "string" ? detail
      : response.status === 429 ? "Слишком много попыток. Подождите минуту."
      : response.status === 422 ? "Проверьте правильность заполнения полей."
      : "Не удалось выполнить запрос.";
    throw new ApiError(response.status, message);
  }
  return data as T;
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });

export async function login(email: string, password: string): Promise<string> {
  const form = new URLSearchParams({ username: email, password });
  const data = await request<{ access_token: string }>("/auth/login", { method: "POST", body: form });
  return data.access_token;
}

export async function register(name: string, email: string, password: string): Promise<string> {
  const data = await request<{ access_token: string }>("/auth/register", json("POST", { name, email, password }));
  return data.access_token;
}

export const getMe = () => request<ApiUser>("/auth/me");
export const updateMe = (patch: { name?: string; email?: string; accessibility_prefs?: string[] }) =>
  request<ApiUser>("/auth/me", json("PATCH", patch));

export const forgotPassword = (email: string) => request<{ detail: string }>("/auth/forgot-password", json("POST", { email }));
export const resetPassword = (token: string, password: string) =>
  request<{ detail: string }>("/auth/reset-password", json("POST", { token, password }));

export const getFavorites = () => request<ApiBuilding[]>("/auth/me/favorites");
export const addFavorite = (buildingId: number) => request<void>(`/auth/me/favorites/${buildingId}`, { method: "PUT" });
export const removeFavorite = (buildingId: number) => request<void>(`/auth/me/favorites/${buildingId}`, { method: "DELETE" });

export const sendReport = (buildingId: number, text: string) =>
  request<ApiReport>("/reports", json("POST", { building_id: buildingId, text }));
export const getMyReports = () => request<Page<ApiReport>>("/auth/me/reports?limit=50").then((page) => page.items);

// Должно совпадать с RegisterRequest/Password на бэкенде
export const PASSWORD_MIN = 10;
