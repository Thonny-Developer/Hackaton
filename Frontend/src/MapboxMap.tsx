import { useEffect, useRef } from "react";
import type { LatLon } from "./geo";

type MapPlace = { id: number; name: string; type: string; address: string; state: string; lon?: number | null; lat?: number | null };
export type MapRoute = { geometry: [number, number][]; from: LatLon; to: LatLon };
type Props = { places: MapPlace[]; selected: MapPlace | null; onSelect: (place: any) => void; styleName: string; locationActive: boolean; route?: MapRoute | null; onMapReady?: (map: any) => void };

declare global { interface Window { mapboxgl?: any } }
const TOKEN = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN as string | undefined;
const MAP_SCRIPT = "https://api.mapbox.com/mapbox-gl-js/v3.14.0/mapbox-gl.js";

function loadMapbox() {
  if (window.mapboxgl) return Promise.resolve(window.mapboxgl);
  return new Promise<any>((resolve, reject) => {
    let script = document.querySelector<HTMLScriptElement>(`script[src="${MAP_SCRIPT}"]`);
    if (!script) { script = document.createElement("script"); script.src = MAP_SCRIPT; script.async = true; document.head.appendChild(script); }
    script.addEventListener("load", () => window.mapboxgl ? resolve(window.mapboxgl) : reject(new Error("Mapbox GL JS не загрузился")), { once: true });
    script.addEventListener("error", () => reject(new Error("Не удалось загрузить Mapbox GL JS")), { once: true });
  });
}

const ROUTE_SOURCE = "sw-route";

/** Источник и слои маршрута. После setStyle они пропадают, поэтому вызывается и на каждый style.load. */
function drawRoute(map: any, route: MapRoute | null | undefined) {
  const data = { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: route?.geometry ?? [] } };
  const source = map.getSource(ROUTE_SOURCE);
  if (source) { source.setData(data); return; }
  map.addSource(ROUTE_SOURCE, { type: "geojson", data });
  const layout = { "line-join": "round", "line-cap": "round" };
  map.addLayer({ id: "sw-route-casing", type: "line", source: ROUTE_SOURCE, layout, paint: { "line-color": "#ffffff", "line-width": 9, "line-opacity": 0.9 } });
  map.addLayer({ id: "sw-route-line", type: "line", source: ROUTE_SOURCE, layout, paint: { "line-color": "#2b6cb0", "line-width": 5 } });
}

function routeMarker(kind: "start" | "finish", label: string) {
  const el = document.createElement("div");
  el.className = `mapbox-route-marker ${kind}`;
  el.setAttribute("role", "img");
  el.setAttribute("aria-label", label);
  return el;
}

export default function MapboxMap({ places, selected, onSelect, styleName, locationActive, route, onMapReady }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const markers = useRef<Map<number, any>>(new Map());
  const onSelectRef = useRef(onSelect);
  const didInitialFit = useRef(false);
  const routeRef = useRef(route);
  const routeMarkers = useRef<any[]>([]);
  onSelectRef.current = onSelect;
  routeRef.current = route;

  useEffect(() => {
    if (!host.current || !TOKEN) return;
    let cancelled = false;
    loadMapbox().then((mapbox) => {
      if (cancelled || !host.current) return;
      mapbox.accessToken = TOKEN;
      const map = new mapbox.Map({ container: host.current, style: styleName === "Спутник" ? "mapbox://styles/mapbox/satellite-streets-v12" : styleName === "Контрастная" ? "mapbox://styles/mapbox/dark-v11" : "mapbox://styles/mapbox/streets-v12", center: [71.4181, 51.09085], zoom: 14.4, attributionControl: true });
      map.addControl(new mapbox.NavigationControl({ showCompass: false }), "bottom-right");
      map.on("style.load", () => drawRoute(map, routeRef.current));
      mapRef.current = map;
      onMapReady?.(map);
    }).catch((error) => console.error(error));
    return () => { cancelled = true; markers.current.forEach((marker) => marker.remove()); markers.current.clear(); routeMarkers.current.forEach((marker) => marker.remove()); routeMarkers.current = []; mapRef.current?.remove(); mapRef.current = null; };
    // Style is updated separately so map state and gestures persist.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [TOKEN]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !window.mapboxgl) return;
    const active = new Set(places.map((place) => place.id));
    markers.current.forEach((marker, id) => { if (!active.has(id)) { marker.remove(); markers.current.delete(id); } });
    places.forEach((place) => {
      if (place.lat == null || place.lon == null) return;
      let marker = markers.current.get(place.id);
      if (!marker) {
        const el = document.createElement("button");
        el.type = "button"; el.className = `mapbox-place-marker marker-${place.state}`; el.setAttribute("aria-label", place.name); el.innerHTML = "<span></span>";
        el.addEventListener("click", () => onSelectRef.current(place));
        marker = new window.mapboxgl.Marker({ element: el, anchor: "bottom" }).setLngLat([place.lon, place.lat]).addTo(map);
        markers.current.set(place.id, marker);
      } else marker.setLngLat([place.lon, place.lat]);
      marker.getElement().classList.toggle("active", selected?.id === place.id);
      marker.getElement().setAttribute("aria-label", `${place.name}, ${place.address}`);
    });
    if (!didInitialFit.current) {
      const points = places.filter((place) => place.lat != null && place.lon != null);
      if (points.length) {
        const bounds = new window.mapboxgl.LngLatBounds();
        points.forEach((place) => bounds.extend([place.lon, place.lat]));
        map.fitBounds(bounds, { padding: 90, maxZoom: 15, duration: 0 });
        didInitialFit.current = true;
      }
    }
  }, [places, selected]);

  // Выбранное место за краем экрана (например, адрес из подсказок) показываем на карте
  useEffect(() => {
    const map = mapRef.current;
    if (!map || selected?.lat == null || selected?.lon == null || routeRef.current) return;
    if (!map.getBounds().contains([selected.lon, selected.lat])) map.flyTo({ center: [selected.lon, selected.lat], zoom: Math.max(map.getZoom(), 15) });
  }, [selected]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !window.mapboxgl) return;
    if (map.isStyleLoaded()) drawRoute(map, route);
    routeMarkers.current.forEach((marker) => marker.remove());
    routeMarkers.current = [];
    if (!route?.geometry.length) return;
    routeMarkers.current = [
      new window.mapboxgl.Marker({ element: routeMarker("start", "Начало маршрута") }).setLngLat([route.from.lon, route.from.lat]).addTo(map),
      new window.mapboxgl.Marker({ element: routeMarker("finish", "Конец маршрута") }).setLngLat([route.to.lon, route.to.lat]).addTo(map),
    ];
    const bounds = new window.mapboxgl.LngLatBounds();
    route.geometry.forEach((point) => bounds.extend(point));
    map.fitBounds(bounds, { padding: 80, maxZoom: 17 });
  }, [route]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !window.mapboxgl) return;
    const style = styleName === "Спутник" ? "mapbox://styles/mapbox/satellite-streets-v12" : styleName === "Контрастная" ? "mapbox://styles/mapbox/dark-v11" : "mapbox://styles/mapbox/streets-v12";
    map.setStyle(style);
  }, [styleName]);

  useEffect(() => {
    if (!locationActive || !navigator.geolocation || !mapRef.current) return;
    navigator.geolocation.getCurrentPosition(({ coords }) => mapRef.current?.flyTo({ center: [coords.longitude, coords.latitude], zoom: 16 }));
  }, [locationActive]);

  return <div className="mapbox-canvas" ref={host} aria-label="Карта Mapbox" />;
}
