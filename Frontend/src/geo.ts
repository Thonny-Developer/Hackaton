import { useEffect, useState } from "react";

export const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

export type LatLon = { lat: number; lon: number };
export type AddressSuggestion = { id: string; type: string; name: string; address: string | null; lat: number; lon: number };
export type OutdoorRoute = {
  provider: "2gis" | "ors" | "straight_line";
  accessibility_checked: boolean;
  distance_m: number;
  duration_s: number;
  geometry: [number, number][];
  steps: { text: string; distance_m: number }[];
};
export type RouteProfile = "default" | "wheelchair" | "walker" | "stroller" | "no_stairs";

// Центр Астаны: им поднимаем подсказки выше, пока карта не загрузилась
export const DEFAULT_CENTER: LatLon = { lat: 51.09085, lon: 71.4181 };

async function errorText(response: Response) {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
  } catch { /* тело не JSON */ }
  if (response.status === 429) return "Слишком много запросов, попробуйте через минуту";
  return `Сервер ответил ${response.status}`;
}

const suggestCache = new Map<string, AddressSuggestion[]>();

export async function fetchSuggestions(q: string, near: LatLon, signal?: AbortSignal): Promise<AddressSuggestion[]> {
  const key = `${q.toLowerCase()}|${near.lat.toFixed(2)}|${near.lon.toFixed(2)}`;
  const hit = suggestCache.get(key);
  if (hit) return hit;
  const params = new URLSearchParams({ q, lat: near.lat.toFixed(5), lon: near.lon.toFixed(5), lang: "ru" });
  const response = await fetch(`${API_BASE}/api/v1/geo/suggest?${params}`, { signal });
  if (!response.ok) throw new Error(await errorText(response));
  const items: AddressSuggestion[] = await response.json();
  suggestCache.set(key, items);
  return items;
}

/** Подсказки 2GIS с задержкой после ввода, чтобы не тратить лимит запросов на каждую букву. */
export function useAddressSuggestions(query: string, getNear: () => LatLon, enabled = true) {
  const [items, setItems] = useState<AddressSuggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const q = query.trim();

  useEffect(() => {
    if (!enabled || q.length < 2) { setItems([]); setLoading(false); setError(null); return; }
    const controller = new AbortController();
    setLoading(true);
    const timer = window.setTimeout(() => {
      fetchSuggestions(q, getNear(), controller.signal)
        .then((found) => { setItems(found); setError(null); })
        .catch((e) => { if (!controller.signal.aborted) { setItems([]); setError(e.message); } })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 300);
    return () => { controller.abort(); window.clearTimeout(timer); };
    // getNear читается в момент запроса, перезапуск на его смену не нужен
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, enabled]);

  return { items, loading, error };
}

export async function fetchOutdoorRoute(from: LatLon, to: LatLon, profile: RouteProfile) {
  const response = await fetch(`${API_BASE}/api/v1/route/outdoor?lang=ru`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ from_location: from, to_location: to, profile }),
  });
  if (!response.ok) throw new Error(await errorText(response));
  return response.json() as Promise<{ route: OutdoorRoute; notices: string[] }>;
}

export function currentPosition(): Promise<LatLon> {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) { reject(new Error("Браузер не умеет определять местоположение")); return; }
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => resolve({ lat: coords.latitude, lon: coords.longitude }),
      () => reject(new Error("Не удалось определить местоположение. Разрешите доступ или введите адрес")),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
    );
  });
}

export function formatDistance(m: number) {
  return m < 1000 ? `${Math.round(m)} м` : `${(m / 1000).toFixed(1).replace(".", ",")} км`;
}

export function formatDuration(s: number) {
  const min = Math.max(1, Math.round(s / 60));
  return min < 60 ? `${min} мин` : `${Math.floor(min / 60)} ч ${min % 60} мин`;
}
