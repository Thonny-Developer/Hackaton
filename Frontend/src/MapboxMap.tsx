import { useEffect, useRef } from "react";
import type { LatLon } from "./geo";

export type MapRoute = { geometry: [number, number][]; from: LatLon; to: LatLon };
type Props = {
  styleName: string;
  locationActive: boolean;
  selected?: { lat?: number | null; lon?: number | null } | null;
  route?: MapRoute | null;
  userLocation?: LatLon | null;
  onUserLocationChange?: (location: LatLon) => void;
  navigationPosition?: LatLon | null;
  onMapReady?: (map: any) => void;
  onMapClick?: (point: LatLon) => void;
};

declare global { interface Window { mapboxgl?: any } }
const TOKEN = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN as string | undefined;
const MAP_SCRIPT = "https://api.mapbox.com/mapbox-gl-js/v3.14.0/mapbox-gl.js";
const ROUTE_SOURCE = "sw-route";
const USER_LOCATION_SOURCE = "sw-user-location";

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

function drawUserLocation(map: any, location: LatLon | null | undefined) {
  const data = {
    type: "FeatureCollection",
    features: location ? [{ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [location.lon, location.lat] } }] : [],
  };
  const source = map.getSource(USER_LOCATION_SOURCE);
  if (source) source.setData(data);
  else map.addSource(USER_LOCATION_SOURCE, { type: "geojson", data });
  if (!map.getLayer("sw-user-location-halo")) {
    map.addLayer({ id: "sw-user-location-halo", type: "circle", source: USER_LOCATION_SOURCE, paint: { "circle-radius": 13, "circle-color": "#3b82f6", "circle-opacity": 0.2 } });
  }
  if (!map.getLayer("sw-user-location-dot")) {
    map.addLayer({ id: "sw-user-location-dot", type: "circle", source: USER_LOCATION_SOURCE, paint: { "circle-radius": 7, "circle-color": "#2563eb", "circle-stroke-color": "#ffffff", "circle-stroke-width": 3 } });
  }
}

export default function MapboxMap({ styleName, locationActive, selected, route, userLocation, onUserLocationChange, navigationPosition, onMapReady, onMapClick }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const routeRef = useRef(route);
  const userLocationRef = useRef(userLocation);
  const navigationPositionRef = useRef(navigationPosition);
  const onUserLocationChangeRef = useRef(onUserLocationChange);
  const onMapClickRef = useRef(onMapClick);
  routeRef.current = route;
  userLocationRef.current = userLocation;
  navigationPositionRef.current = navigationPosition;
  onUserLocationChangeRef.current = onUserLocationChange;
  onMapClickRef.current = onMapClick;

  useEffect(() => {
    if (!host.current || !TOKEN) return;
    let cancelled = false;
    loadMapbox().then((mapbox) => {
      if (cancelled || !host.current) return;
      mapbox.accessToken = TOKEN;
      const map = new mapbox.Map({ container: host.current, style: styleUrl(styleName), center: [71.4181, 51.09085], zoom: 14.4, attributionControl: true });
      map.addControl(new mapbox.NavigationControl({ showCompass: false }), "bottom-right");
      map.on("style.load", () => {
        drawRoute(map, routeRef.current);
        drawUserLocation(map, navigationPositionRef.current ?? userLocationRef.current);
      });
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
    if (map?.isStyleLoaded()) drawUserLocation(map, navigationPosition ?? userLocation);
  }, [navigationPosition, userLocation]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || selected?.lat == null || selected?.lon == null || route) return;
    if (!map.getBounds().contains([selected.lon, selected.lat])) map.flyTo({ center: [selected.lon, selected.lat], zoom: Math.max(map.getZoom(), 15) });
  }, [selected, route]);

  useEffect(() => {
    if (!locationActive || !navigator.geolocation || !mapRef.current) return;
    navigator.geolocation.getCurrentPosition(({ coords }) => {
      const location = { lat: coords.latitude, lon: coords.longitude };
      onUserLocationChangeRef.current?.(location);
      mapRef.current?.flyTo({ center: [location.lon, location.lat], zoom: 16 });
    });
  }, [locationActive]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !navigationPosition) return;
    map.easeTo({ center: [navigationPosition.lon, navigationPosition.lat], duration: 700, zoom: Math.max(map.getZoom(), 16) });
  }, [navigationPosition]);

  return <div className="mapbox-canvas" ref={host} aria-label="Карта Mapbox" />;
}
