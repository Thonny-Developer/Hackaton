import { useEffect, useRef } from "react";

type MapPlace = { id: number; name: string; type: string; address: string; state: string; lon?: number | null; lat?: number | null };
type Props = { places: MapPlace[]; selected: MapPlace | null; onSelect: (place: any) => void; styleName: string; locationActive: boolean; onMapReady?: (map: any) => void };

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

export default function MapboxMap({ places, selected, onSelect, styleName, locationActive, onMapReady }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const markers = useRef<Map<number, any>>(new Map());
  const onSelectRef = useRef(onSelect);
  const didInitialFit = useRef(false);
  onSelectRef.current = onSelect;

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
    return () => { cancelled = true; markers.current.forEach((marker) => marker.remove()); markers.current.clear(); mapRef.current?.remove(); mapRef.current = null; };
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
