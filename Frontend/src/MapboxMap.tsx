import { useEffect, useRef } from "react";
import type { LatLon } from "./geo";

export type MapRoute = { geometry: [number, number][]; from: LatLon; to: LatLon };
type Props = {
  styleName: string;
  locationActive: boolean;
  selected?: { lat?: number | null; lon?: number | null } | null;
  route?: MapRoute | null;
  navigationPosition?: LatLon | null;
  onMapReady?: (map: any) => void;
  onMapClick?: (point: LatLon) => void;
};

declare global { interface Window { mapboxgl?: any } }
const TOKEN = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN as string | undefined;
const MAP_SCRIPT = "https://api.mapbox.com/mapbox-gl-js/v3.14.0/mapbox-gl.js";
const ROUTE_SOURCE = "sw-route";

function loadMapbox() {
  if (window.mapboxgl) return Promise.resolve(window.mapboxgl);
  return new Promise<any>((resolve, reject) => {
    let script = document.querySelector<HTMLScriptElement>(`script[src="${MAP_SCRIPT}"]`);
    if (!script) { script = document.createElement("script"); script.src = MAP_SCRIPT; script.async = true; document.head.appendChild(script); }
    script.addEventListener("load", () => window.mapboxgl ? resolve(window.mapboxgl) : reject(new Error("Mapbox GL JS не загрузился")), { once: true });
    script.addEventListener("error", () => reject(new Error("Не удалось загрузить Mapbox GL JS")), { once: true });
  });
}

function styleUrl(styleName: string) {
  if (styleName === "Спутник") return "mapbox://styles/mapbox/satellite-streets-v12";
  if (styleName === "Контрастная") return "mapbox://styles/mapbox/dark-v11";
  return "mapbox://styles/mapbox/streets-v12";
}

function drawRoute(map: any, route: MapRoute | null | undefined) {
  const data = { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: route?.geometry ?? [] } };
  const source = map.getSource(ROUTE_SOURCE);
  if (source) { source.setData(data); return; }
  map.addSource(ROUTE_SOURCE, { type: "geojson", data });
  const layout = { "line-join": "round", "line-cap": "round" };
  map.addLayer({ id: "sw-route-casing", type: "line", source: ROUTE_SOURCE, layout, paint: { "line-color": "#ffffff", "line-width": 9, "line-opacity": 0.9 } });
  map.addLayer({ id: "sw-route-line", type: "line", source: ROUTE_SOURCE, layout, paint: { "line-color": "#2b6cb0", "line-width": 5 } });
}

export default function MapboxMap({ styleName, locationActive, selected, route, navigationPosition, onMapReady, onMapClick }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const routeRef = useRef(route);
  const onMapClickRef = useRef(onMapClick);
  routeRef.current = route;
  onMapClickRef.current = onMapClick;

  useEffect(() => {
    if (!host.current || !TOKEN) return;
    let cancelled = false;
    loadMapbox().then((mapbox) => {
      if (cancelled || !host.current) return;
      mapbox.accessToken = TOKEN;
      const map = new mapbox.Map({ container: host.current, style: styleUrl(styleName), center: [71.4181, 51.09085], zoom: 14.4, attributionControl: true });
      map.addControl(new mapbox.NavigationControl({ showCompass: false }), "bottom-right");
      map.on("style.load", () => drawRoute(map, routeRef.current));
      map.on("click", (e: any) => onMapClickRef.current?.({ lat: e.lngLat.lat, lon: e.lngLat.lng }));
      mapRef.current = map;
      onMapReady?.(map);
    }).catch((error) => console.error(error));
    return () => { cancelled = true; mapRef.current?.remove(); mapRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [TOKEN]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !window.mapboxgl) return;
    map.setStyle(styleUrl(styleName));
  }, [styleName]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !window.mapboxgl) return;
    if (map.isStyleLoaded()) drawRoute(map, route);
    if (!route?.geometry.length) return;
    const bounds = new window.mapboxgl.LngLatBounds();
    route.geometry.forEach((point) => bounds.extend(point));
    map.fitBounds(bounds, { padding: 80, maxZoom: 17 });
  }, [route]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || selected?.lat == null || selected?.lon == null || route) return;
    if (!map.getBounds().contains([selected.lon, selected.lat])) map.flyTo({ center: [selected.lon, selected.lat], zoom: Math.max(map.getZoom(), 15) });
  }, [selected, route]);

  useEffect(() => {
    if (!locationActive || !navigator.geolocation || !mapRef.current) return;
    navigator.geolocation.getCurrentPosition(({ coords }) => mapRef.current?.flyTo({ center: [coords.longitude, coords.latitude], zoom: 16 }));
  }, [locationActive]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !navigationPosition) return;
    map.easeTo({ center: [navigationPosition.lon, navigationPosition.lat], duration: 700, zoom: Math.max(map.getZoom(), 16) });
  }, [navigationPosition]);

  return <div className="mapbox-canvas" ref={host} aria-label="Карта Mapbox" />;
}
