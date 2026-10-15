import { useEffect, useRef } from "react";

type Props = { styleName: string; locationActive: boolean; onMapReady?: (map: any) => void };

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

export default function MapboxMap({ styleName, locationActive, onMapReady }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);

  useEffect(() => {
    if (!host.current || !TOKEN) return;
    let cancelled = false;
    loadMapbox().then((mapbox) => {
      if (cancelled || !host.current) return;
      mapbox.accessToken = TOKEN;
      const map = new mapbox.Map({ container: host.current, style: styleName === "Спутник" ? "mapbox://styles/mapbox/satellite-streets-v12" : styleName === "Контрастная" ? "mapbox://styles/mapbox/dark-v11" : "mapbox://styles/mapbox/streets-v12", center: [71.4181, 51.09085], zoom: 14.4, attributionControl: true });
      map.addControl(new mapbox.NavigationControl({ showCompass: false }), "bottom-right");
      mapRef.current = map;
      onMapReady?.(map);
    }).catch((error) => console.error(error));
    return () => { cancelled = true; mapRef.current?.remove(); mapRef.current = null; };
    // Style is updated separately so map state and gestures persist.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [TOKEN]);

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
