import { useEffect, useMemo, useState } from "react";
import MapboxMap from "./MapboxMap";

type AccessState = "accessible" | "partial" | "barrier" | "unknown";
type AuthView = "login" | "register" | "recovery" | "profile" | "preferences" | null;
type PrototypeUser = { name: string; email: string };
type Place = {
  id: number;
  name: string;
  type: string;
  address: string;
  state: AccessState;
  summary: string;
  updated: string;
  x: number;
  y: number;
  features: string[];
  route: boolean;
  entrance?: string;
  lat?: number | null;
  lon?: number | null;
};

const places: Place[] = [
  {
    id: 1,
    name: "Городская поликлиника № 3",
    type: "Медицина",
    address: "ул. Советская, 18",
    state: "accessible",
    summary: "Вход без ступеней, работает лифт",
    updated: "сегодня, 09:40",
    x: 36,
    y: 33,
    lat: 51.09085,
    lon: 71.41810,
    features: ["noSteps", "ramp", "elevator", "wide", "toilet", "recent", "verified"],
    route: true,
    entrance: "Вход со стороны ул. Советской",
  },
  {
    id: 2,
    name: "Колледж городского хозяйства",
    type: "Образование",
    address: "пр. Мира, 42",
    state: "partial",
    summary: "Есть пандус, узкая входная дверь",
    updated: "12 мая 2025",
    x: 64,
    y: 24,
    lat: 51.09415,
    lon: 71.42365,
    features: ["ramp", "elevator", "recent", "verified"],
    route: true,
    entrance: "Подтверждённый боковой вход с ул. Школьной",
  },
  {
    id: 3,
    name: "Магазин «У дома»",
    type: "Магазин",
    address: "ул. Лесная, 7",
    state: "unknown",
    summary: "Данные о доступности не проверены",
    updated: "3 февраля 2024",
    x: 52,
    y: 64,
    lat: 51.08690,
    lon: 71.41420,
    features: [],
    route: false,
  },
  {
    id: 4,
    name: "Центральная библиотека",
    type: "Госучреждение",
    address: "пл. Победы, 2",
    state: "barrier",
    summary: "У входа высокий порог, пандус слишком крутой",
    updated: "28 апреля 2025",
    x: 76,
    y: 53,
    lat: 51.08875,
    lon: 71.42670,
    features: ["ramp", "wide", "toilet", "recent", "verified"],
    route: false,
  },
  {
    id: 5,
    name: "Центр социальных услуг",
    type: "Госучреждение",
    address: "ул. Новая, 11",
    state: "accessible",
    summary: "Доступный вход и широкие коридоры",
    updated: "8 мая 2025",
    x: 24,
    y: 71,
    lat: 51.08480,
    lon: 71.41155,
    features: ["noSteps", "ramp", "wide", "toilet", "recent", "verified"],
    route: true,
    entrance: "Главный вход с ул. Новой",
  },
];

const filters = [
  ["noSteps", "Без ступеней"],
  ["ramp", "Есть пандус"],
  ["elevator", "Работающий лифт"],
  ["wide", "Широкие двери и коридоры"],
  ["toilet", "Доступный туалет"],
  ["recent", "Обновлено недавно"],
  ["verified", "Проверенная информация"],
] as const;

const routePrefs = [
  ["noSteps", "Без лестниц"],
  ["elevator", "Нужен работающий лифт"],
  ["wide", "Широкие двери"],
  ["thresholds", "Минимум порогов"],
] as const;

const buildingCategories = [
  ["Образование", "Колледжи и университеты"],
  ["Медицина", "Больницы и поликлиники"],
  ["Магазин", "Магазины и торговые центры"],
  ["Госучреждение", "Государственные учреждения"],
  ["Кафе", "Кафе и рестораны"],
  ["Парк", "Парки и общественные места"],
] as const;

const statusText: Record<AccessState, string> = {
  accessible: "Доступно",
  partial: "Частично доступно",
  barrier: "Есть препятствия",
  unknown: "Не проверено",
};

function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const paths: Record<string, React.ReactNode> = {
    map: <><path d="m3 6 5-3 8 3 5-3v15l-5 3-8-3-5 3Z"/><path d="M8 3v15M16 6v15"/></>,
    pin: <><path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/></>,
    heart: <path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8l1.1 1.1L12 21l7.7-7.5 1.1-1.1a5.5 5.5 0 0 0 0-7.8Z"/>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.6v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/></>,
    search: <><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>,
    filter: <path d="M4 6h16M7 12h10M10 18h4"/>,
    route: <><circle cx="6" cy="18" r="2"/><circle cx="18" cy="6" r="2"/><path d="M8 18h3a3 3 0 0 0 3-3V9a3 3 0 0 1 3-3"/></>,
    close: <path d="m6 6 12 12M18 6 6 18"/>,
    chevron: <path d="m9 18 6-6-6-6"/>,
    report: <><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.8 2.5 18a2 2 0 0 0 1.8 3h15.4a2 2 0 0 0 1.8-3L13.7 3.8a2 2 0 0 0-3.4 0Z"/></>,
    check: <path d="m5 12 4 4L19 6"/>,
    info: <><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></>,
    building: <><path d="M4 21V4h11v17M15 9h5v12M8 8h3M8 12h3M8 16h3M3 21h18"/></>,
    plus: <path d="M12 5v14M5 12h14"/>,
    minus: <path d="M5 12h14"/>,
    user: <><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></>,
    eye: <><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"/><circle cx="12" cy="12" r="2.5"/></>,
    logout: <><path d="M10 17l5-5-5-5M15 12H3"/><path d="M14 3h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5"/></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function SeeWayLogo({ compact = false }: { compact?: boolean }) {
  return <div className={`seeway-logo ${compact ? "compact" : ""}`}><svg viewBox="0 0 64 64" aria-hidden="true">
    <path className="logo-route" d="M37 25H20C12 25 7 30 7 37s5 12 13 12h12" />
    <path className="logo-route" d="M34 35h12c8 0 12 5 12 12s-5 12-13 12H26" />
    <circle className="logo-dot" cx="27" cy="35" r="2.6" />
    <circle className="logo-dot" cx="38" cy="48" r="2.6" />
    <path className="logo-pin" d="M48 3c-7.4 0-13 5.5-13 13 0 8.5 13 25 13 25s13-16.5 13-25C61 8.5 55.4 3 48 3Z" />
    <circle className="logo-pin-center" cx="48" cy="16" r="5.5" />
  </svg>{!compact && <div><strong>SeeWay</strong><span>ACCESSIBILITY NAVIGATOR</span></div>}</div>;
}

function WelcomeArchitecture() {
  return <svg className="welcome-architecture" viewBox="0 0 660 350" role="img" aria-label="Открытый вход в современное общественное здание и доступный путь">
    <path className="arch-sky" d="M30 298V92c0-22 18-40 40-40h520c22 0 40 18 40 40v206Z" />
    <path className="arch-building-back" d="M75 292V117h196v175M390 292V86h179v206" />
    <path className="arch-building-front" d="M207 292V69h220v223" />
    <path className="arch-door" d="M276 292V135h91v157" />
    <path className="arch-open" d="m322 138 45-3v157h-45Z" />
    <path className="arch-window" d="M102 145h75v57h-75ZM456 121h82v62h-82Z" />
    <path className="arch-path" d="m261 350 48-58h45l56 58Z" />
    <path className="arch-line" d="M34 292h590M89 222h101M445 203h108" />
    <circle className="arch-tree" cx="117" cy="262" r="26" /><path className="arch-trunk" d="M117 288v-38" />
    <circle className="arch-tree" cx="548" cy="250" r="32" /><path className="arch-trunk" d="M548 288v-45" />
  </svg>;
}

function Status({ state }: { state: AccessState }) {
  return <span className={`status status-${state}`}><span className="status-dot" />{statusText[state]}</span>;
}

export default function App() {
  const [apiPlaces, setApiPlaces] = useState<Place[] | null>(null);
  const [apiState, setApiState] = useState<"loading" | "ready" | "offline">("loading");
  const apiBase = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
  useEffect(() => {
    let alive = true;
    fetch(`${apiBase}/api/v1/buildings?limit=200`)
      .then((response) => { if (!response.ok) throw new Error("API unavailable"); return response.json(); })
      .then((page) => {
        if (!alive) return;
        const items = Array.isArray(page) ? page : page.items || [];
        const mapped = items.filter((building: any) => Number.isFinite(building.lat) && Number.isFinite(building.lon)).map((building: any, index: number) => ({
          id: Number(building.id), name: building.name, type: "Здание", address: building.address || "Адрес не указан", state: "unknown" as AccessState,
          summary: "Доступность здания пока не указана", updated: "", x: 0, y: 0, features: [], route: false, lat: building.lat, lon: building.lon,
        }));
        setApiPlaces(mapped); setApiState("ready");
      })
      .catch(() => { if (alive) setApiState("offline"); });
    return () => { alive = false; };
  }, [apiBase]);
  const [welcomeOpen, setWelcomeOpen] = useState(true);
  const [query, setQuery] = useState("");
  const [filterOpen, setFilterOpen] = useState(false);
  const [activeFilters, setActiveFilters] = useState<string[]>([]);
  const [favorites, setFavorites] = useState<number[]>([2]);
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [selected, setSelected] = useState<Place | null>(null);
  const [routePanel, setRoutePanel] = useState(false);
  const [routeShown, setRouteShown] = useState(false);
  const [prefs, setPrefs] = useState<string[]>(["noSteps"]);
  const [savedPrefs, setSavedPrefs] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [reportSent, setReportSent] = useState(false);
  const [reportText, setReportText] = useState("");
  const [sosOpen, setSosOpen] = useState(false);
  const [sosSent, setSosSent] = useState(false);
  const [sosLocation, setSosLocation] = useState("");
  const [sosBuilding, setSosBuilding] = useState("");
  const [sosType, setSosType] = useState("");
  const [sosDetails, setSosDetails] = useState("");
  const [authView, setAuthView] = useState<AuthView>(null);
  const [profileMenu, setProfileMenu] = useState(false);
  const [user, setUser] = useState<PrototypeUser | null>(null);
  const [prototypeAccount, setPrototypeAccount] = useState<{ name: string; email: string; password: string } | null>(null);
  const [accountPrefs, setAccountPrefs] = useState<string[]>(["noSteps"]);
  const [activeCategories, setActiveCategories] = useState<string[]>([]);
  const [layersOpen, setLayersOpen] = useState(false);
  const [mapLayer, setMapLayer] = useState("Схема");
  const [locationActive, setLocationActive] = useState(false);
  const [detailExpanded, setDetailExpanded] = useState(false);

  const sourcePlaces = apiPlaces?.length ? apiPlaces : places;
  const selectedIsFromApi = selected != null && Boolean(apiPlaces?.some((place) => place.id === selected.id));
  const visiblePlaces = useMemo(() => sourcePlaces.filter((place) => {
    const matchesSearch = `${place.name} ${place.type} ${place.address}`.toLowerCase().includes(query.toLowerCase());
    const matchesFilters = activeFilters.every((filter) => place.features.includes(filter));
    const matchesFavorites = !favoritesOnly || favorites.includes(place.id);
    const matchesCategories = activeCategories.length === 0 || activeCategories.includes(place.type);
    return matchesSearch && matchesFilters && matchesFavorites && matchesCategories;
  }), [sourcePlaces, query, activeFilters, favoritesOnly, favorites, activeCategories]);

  const toggleItem = (value: string, values: string[], setter: (v: string[]) => void) => {
    setter(values.includes(value) ? values.filter((item) => item !== value) : [...values, value]);
  };

  const toggleFavorite = (id: number) => {
    setFavorites(favorites.includes(id) ? favorites.filter((item) => item !== id) : [...favorites, id]);
  };

  const openPlace = (place: Place) => {
    setSelected(place);
    setRoutePanel(false);
    setRouteShown(false);
    setDetailExpanded(false);
  };

  const closeDetail = () => {
    setSelected(null);
    setRoutePanel(false);
    setRouteShown(false);
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><SeeWayLogo compact /></div>
        <nav aria-label="Основная навигация">
          <button className={!favoritesOnly && !routePanel ? "nav-item active" : "nav-item"} onClick={() => { setFavoritesOnly(false); closeDetail(); }}><Icon name="pin" /><span>Карта</span></button>
          <button className={routePanel ? "nav-item active" : "nav-item"} onClick={() => { setFavoritesOnly(false); setRoutePanel(true); setSelected(selected || places[0]); }}><Icon name="route" /><span>Маршрут</span></button>
          <button className="nav-item sos-nav-item" onClick={() => { setSosOpen(true); setSosSent(false); }}><span className="sos-nav-icon">SOS</span><span>SOS</span></button>
          <button className={favoritesOnly ? "nav-item active" : "nav-item"} onClick={() => { setFavoritesOnly(true); setRoutePanel(false); setSelected(null); }}><Icon name="heart" /><span>Избранное</span><b>{favorites.length}</b></button>
          <button className="nav-item" onClick={() => user ? setAuthView("profile") : setProfileMenu(true)}><Icon name="user" /><span>Профиль</span></button>
        </nav>
      </aside>

      <main>
        <section className="results-panel map-info-panel" aria-label={routePanel ? "Планирование маршрута" : "Поиск и фильтры"}>
          <div className="panel-brand"><SeeWayLogo /><span className="panel-brand-slogan">Понятный путь для каждого</span></div>
          {routePanel ? (
            <div className="route-planner-panel">
              <div className="panel-title-row"><div><p className="eyebrow">РЕЖИМ МАРШРУТА</p><h1>Построить маршрут</h1></div><button className="plain-icon" onClick={closeDetail} aria-label="Закрыть"><Icon name="close" /></button></div>
              <label className="route-field"><span className="route-point start" /><div><small>ОТКУДА</small><input defaultValue="Моё местоположение" aria-label="Откуда" /></div></label>
              <label className="route-field"><span className="route-point finish" /><div><small>КУДА</small><input value={selected?.name || ""} onChange={(e) => setQuery(e.target.value)} placeholder="Выберите место на карте" aria-label="Куда" /></div></label>
              <h2 className="panel-section-title">Параметры доступности</h2>
              {[["noSteps", "Без лестниц"], ["elevator", "Предпочитать лифты"], ["wide", "Избегать узких проходов"], ["ramp", "Предпочитать пандусы"]].map(([id, label]) => <label className="compact-filter" key={id}><input type="checkbox" checked={prefs.includes(id)} onChange={() => toggleItem(id, prefs, setPrefs)} /><span>{label}</span></label>)}
              <button className="button full route-build-button" onClick={() => setRouteShown(true)} disabled={!selected}>Показать маршрут</button>
              {routeShown && selected && (selected.route && selected.features.includes("verified") ? <div className="route-summary"><div><strong>14 мин</strong><span>920 м</span></div><p>Маршрут без лестниц подтверждён.</p><ul><li>{selected.entrance}</li><li>Непроверенных участков нет</li></ul></div> : <div className="route-alert"><Icon name="info" size={18} /><div><strong>Безбарьерный маршрут не подтверждён</strong><p>Недостаточно проверенных данных. Мы не будем предлагать неподтверждённый путь.</p></div></div>)}
            </div>
          ) : (
            <div className="panel-scroll">
              <label className="search-box map-search"><Icon name="search" size={19} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Поиск здания или адреса" aria-label="Поиск здания или адреса" /></label>
              <div className="panel-action-row">
                <button className={filterOpen ? "panel-action active" : "panel-action"} onClick={() => setFilterOpen(!filterOpen)}><Icon name="filter" size={17} />Фильтры{activeFilters.length > 0 && <b>{activeFilters.length}</b>}</button>
                <button className={favoritesOnly ? "panel-action active" : "panel-action"} onClick={() => setFavoritesOnly(!favoritesOnly)}><Icon name="heart" size={17} />Избранное</button>
              </div>
              <div className="found-row"><span>{favoritesOnly ? "Избранные места" : `На карте: ${visiblePlaces.length}`}</span>{(activeFilters.length > 0 || activeCategories.length > 0) && <button onClick={() => { setActiveFilters([]); setActiveCategories([]); }}>Сбросить</button>}</div>
              {(query || favoritesOnly) && <div className="compact-results">{visiblePlaces.map((place) => <button key={place.id} onClick={() => openPlace(place)}><span className={`result-marker ${place.state}`} /><div><strong>{place.name}</strong><small>{place.address}</small></div><Icon name="chevron" size={15} /></button>)}</div>}
              <section className="panel-section">
                <h2>Категории зданий</h2>
                <div className="category-list">{buildingCategories.map(([id, label]) => <button key={id} className={activeCategories.includes(id) ? "selected" : ""} onClick={() => toggleItem(id, activeCategories, setActiveCategories)}><span className="category-icon"><Icon name="building" size={17} /></span><span>{label}</span><Icon name="chevron" size={15} /></button>)}</div>
              </section>
              {filterOpen && <section className="panel-section accessibility-section">
                <div className="panel-section-head"><h2>Доступность</h2>{activeFilters.length > 0 && <button onClick={() => setActiveFilters([])}>Очистить</button>}</div>
                {filters.slice(0, 5).map(([id, label]) => <label className="compact-filter" key={id}><input type="checkbox" checked={activeFilters.includes(id)} onChange={() => toggleItem(id, activeFilters, setActiveFilters)} /><span>{label === "Широкие двери и коридоры" ? "Широкие проходы" : label}</span></label>)}
              </section>}
              <div className="panel-legend"><h2>Обозначения на карте</h2><div><span><i className="legend-dot accessible" />Подтверждено</span><span><i className="legend-dot partial" />Есть ограничения</span><span><i className="legend-dot barrier" />Есть препятствия</span><span><i className="legend-dot unknown" />Нет данных</span></div><p>Статусы относятся к демонстрационным данным. Проверенные сведения отмечены отдельно.</p></div>
            </div>
          )}
        </section>

        <section className="map-area" aria-label="Интерактивная карта">
          <MapboxMap styleName={mapLayer} locationActive={locationActive} onMapReady={(map) => { (window as any).__seewayMap = map; }} />
          {!import.meta.env.VITE_MAPBOX_ACCESS_TOKEN && <div className="map-notice">Добавьте VITE_MAPBOX_ACCESS_TOKEN в Frontend/.env</div>}
          <div className="map-caption">SeeWay <span>{apiState === "ready" ? "Данные API" : apiState === "loading" ? "Загрузка зданий…" : "Демо-данные · API недоступен"}</span></div>
          <div className="map-top-controls">
            <div className="layer-control"><button onClick={() => setLayersOpen(!layersOpen)}><Icon name="map" size={18} />{mapLayer}</button>{layersOpen && <div><button onClick={() => { setMapLayer("Схема"); setLayersOpen(false); }}>Схема</button><button onClick={() => { setMapLayer("Спутник"); setLayersOpen(false); }}>Спутник</button><button onClick={() => { setMapLayer("Контрастная"); setLayersOpen(false); }}>Контрастная</button></div>}</div>
            <button className={locationActive ? "active" : ""} onClick={() => setLocationActive(!locationActive)} aria-label="Текущее местоположение"><Icon name="pin" size={18} /></button>
            <button onClick={() => user ? setAuthView("preferences") : setAuthView("login")} aria-label="Настройки"><Icon name="settings" size={18} /></button>
          </div>
          {!selected && <button className="route-fab" onClick={() => { setSelected(places[0]); setRoutePanel(true); }}><Icon name="route" />Построить маршрут</button>}

          {selected && !routePanel && (
            <aside className={`detail-panel map-place-card ${detailExpanded ? "expanded" : ""}`} aria-label={`Профиль: ${selected.name}`}>
              <div className="detail-header">
                <div><span className="place-type">{selected.type}</span><h2>{selected.name}</h2><p>{selected.address}</p></div>
                <button className="close-button" onClick={closeDetail} aria-label="Закрыть профиль"><Icon name="close" /></button>
              </div>
              <div className="place-card-status"><Status state={selected.state} /><span>{selected.features.includes("verified") ? "Сведения подтверждены" : selectedIsFromApi ? "Данные API · доступность не указана" : "Демо · не проверено"}</span></div>
              <div className="quick-access-grid">
                <div><small>ПАНДУС</small><strong>{selected.features.includes("ramp") ? (selected.state === "barrier" ? "Крутой уклон" : "Есть") : "Нет данных"}</strong></div>
                <div><small>ЛИФТ</small><strong>{selected.features.includes("elevator") ? "Работает" : "Нет данных"}</strong></div>
                <div><small>ВХОД</small><strong>{selected.entrance || "Не подтверждён"}</strong></div>
                <div><small>ОБНОВЛЕНО</small><strong>{selected.updated}</strong></div>
              </div>
              <div className="detail-actions three-actions"><button className="outline-button" onClick={() => setDetailExpanded(!detailExpanded)}>{detailExpanded ? "Свернуть" : "Подробнее"}</button><button className={`outline-button ${favorites.includes(selected.id) ? "saved-action" : ""}`} onClick={() => toggleFavorite(selected.id)}><Icon name="heart" size={16} />{favorites.includes(selected.id) ? "Сохранено" : "В избранное"}</button><button className="button route-card-button" onClick={() => setRoutePanel(true)}><Icon name="route" size={16} />Построить маршрут</button></div>
              {detailExpanded && (selectedIsFromApi ? <div className="profile-content"><p>В API пока нет паспорта доступности для этого здания. Сведения о пандусах, лифтах и входах не указаны.</p></div> : <div className="profile-content">
                  <Status state={selected.state} />
                  <p className="verification">{selected.features.includes("verified") ? "Проверено организацией · 12 мая 2025" : "Не проверено организацией"}</p>
                  <h3>Паспорт доступности</h3>
                  <div className="access-list">
                    <AccessRow label="Пандус" value={selected.features.includes("ramp") ? (selected.id === 4 ? "Есть, уклон выше нормы" : "Есть, состояние хорошее") : "Нет подтверждённых данных"} known={selected.features.includes("ramp")} date="12.05.2025" />
                    <AccessRow label="Лифт" value={selected.features.includes("elevator") ? "Работает" : "Неизвестно"} known={selected.features.includes("elevator")} date={selected.features.includes("elevator") ? "сегодня, 09:40" : "—"} />
                    <AccessRow label="Двери и коридоры" value={selected.features.includes("wide") ? "Ширина от 90 см" : "Ширина не указана"} known={selected.features.includes("wide")} date="28.04.2025" />
                    <AccessRow label="Ступени у входа" value={selected.features.includes("noSteps") ? "Нет" : "Есть или не проверено"} known={selected.features.includes("noSteps")} date="12.05.2025" />
                    <AccessRow label="Доступный туалет" value={selected.features.includes("toilet") ? "Есть, на 1 этаже" : "Нет данных"} known={selected.features.includes("toilet")} date="28.04.2025" />
                  </div>
                  <div className="reviews-head"><h3>Отзывы и фото</h3><span>2 отзыва · 3 фото</span></div>
                  <div className="photo-row"><div>ФОТО<br />ВХОДА</div><div>ФОТО<br />ПАНДУСА</div><button>+1</button></div>
                  <blockquote>«Вход удобный, но кнопка вызова расположена высоко.»<footer>Анна · 10 мая 2025 · не проверено</footer></blockquote>
                  <div className="recent-report"><div><Icon name="report" size={16} /><strong>Последнее сообщение</strong></div><p>«Доводчик на входной двери работает туго»</p><span>11 мая 2025 · <b>Не проверено</b></span></div>
                  <button className="report-button" onClick={() => { setReportOpen(true); setReportSent(false); }}><Icon name="report" size={18} />Сообщить об изменении</button>
                </div>)}
            </aside>
          )}
        </section>
      </main>

      <div className="account-control">
        <button className="profile-trigger" onClick={() => setProfileMenu(!profileMenu)} aria-expanded={profileMenu} aria-label={user ? "Открыть меню профиля" : "Открыть меню входа"}>
          <span className="profile-avatar">{user ? user.name.slice(0, 1).toUpperCase() : <Icon name="user" size={18} />}</span>
          <span>{user ? user.name : "Войти"}</span>
        </button>
        {profileMenu && (
          <div className="profile-menu">
            {user ? <>
              <div className="profile-menu-user"><strong>{user.name}</strong><span>{user.email}</span></div>
              <button onClick={() => { setAuthView("profile"); setProfileMenu(false); }}><Icon name="user" size={17} />Мой профиль</button>
              <button onClick={() => { setFavoritesOnly(true); setRoutePanel(false); setSelected(null); setAuthView(null); setProfileMenu(false); }}><Icon name="heart" size={17} />Избранное</button>
              <button onClick={() => { setSelected(selected || places[0]); setRoutePanel(true); setAuthView(null); setProfileMenu(false); }}><Icon name="route" size={17} />Мои маршруты</button>
              <button onClick={() => { setAuthView("profile"); setProfileMenu(false); }}><Icon name="report" size={17} />Мои отзывы</button>
              <button onClick={() => { setAuthView("preferences"); setProfileMenu(false); }}><Icon name="settings" size={17} />Настройки доступности</button>
              <button className="logout-menu-item" onClick={() => { setUser(null); setProfileMenu(false); setAuthView(null); }}><Icon name="logout" size={17} />Выйти</button>
            </> : <>
              <p>Войдите, чтобы сохранять маршруты и места.</p>
              <button onClick={() => { setAuthView("login"); setProfileMenu(false); }}><Icon name="user" size={17} />Войти</button>
              <button className="menu-primary" onClick={() => { setAuthView("register"); setProfileMenu(false); }}><Icon name="plus" size={17} />Регистрация</button>
            </>}
          </div>
        )}
      </div>

      {authView && (
        <AuthScreen
          key={authView}
          view={authView}
          user={user}
          prototypeAccount={prototypeAccount}
          preferences={accountPrefs}
          favoritePlaces={places.filter((place) => favorites.includes(place.id))}
          hasSavedRoute={routeShown}
          onClose={() => setAuthView(null)}
          onChangeView={setAuthView}
          onRegister={(newUser, password) => { setUser(newUser); setPrototypeAccount({ name: newUser.name, email: newUser.email, password }); }}
          onLogin={(loggedInUser) => { setUser(loggedInUser); setAuthView(null); setFavoritesOnly(false); }}
          onUpdateUser={setUser}
          onUpdatePreferences={setAccountPrefs}
        />
      )}

      {reportOpen && selected && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) setReportOpen(false); }}>
          <div className="modal" role="dialog" aria-modal="true" aria-labelledby="report-title">
            <div className="modal-head"><div><p className="eyebrow">ОБНОВЛЕНИЕ ДАННЫХ</p><h2 id="report-title">Сообщить об изменении</h2></div><button className="close-button" onClick={() => setReportOpen(false)} aria-label="Закрыть"><Icon name="close" /></button></div>
            {reportSent ? <div className="confirmation"><div className="confirmation-icon"><Icon name="check" size={28} /></div><h3>Сообщение отправлено</h3><p>Спасибо. Оно появится в профиле со статусом «Не проверено». Мы не считаем данные подтверждёнными до проверки.</p><button className="button" onClick={() => setReportOpen(false)}>Готово</button></div> : <>
              <p className="modal-place">{selected.name}<br /><span>{selected.address}</span></p>
              <label className="field-label">Что изменилось?</label>
              <div className="issue-chips"><button onClick={() => setReportText("Не работает лифт")}>Не работает лифт</button><button onClick={() => setReportText("Вход заблокирован")}>Вход заблокирован</button><button onClick={() => setReportText("Пандус слишком крутой")}>Крутой пандус</button></div>
              <textarea value={reportText} onChange={(e) => setReportText(e.target.value)} placeholder="Коротко опишите ситуацию" rows={5} />
              <label className="upload"><input type="file" accept="image/*" /><Icon name="plus" /><span><b>Добавить фото</b><small>Необязательно, JPG или PNG</small></span></label>
              <div className="unverified-note"><Icon name="info" size={18} /><span>Сообщение будет опубликовано как неподтверждённое до проверки.</span></div>
              <button className="button full" disabled={!reportText.trim()} onClick={() => setReportSent(true)}>Отправить сообщение</button>
            </>}
          </div>
        </div>
      )}

      {sosOpen && (
        <div className="modal-backdrop sos-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) setSosOpen(false); }}>
          <div className="modal sos-modal" role="dialog" aria-modal="true" aria-labelledby="sos-title">
            <div className="modal-head">
              <div><p className="eyebrow sos-eyebrow">ЗАПРОС ПОМОЩИ</p><h2 id="sos-title">{sosSent ? "Запрос отправлен" : "Нужна помощь?"}</h2></div>
              <button className="close-button" onClick={() => setSosOpen(false)} aria-label="Закрыть"><Icon name="close" /></button>
            </div>
            {sosSent ? (
              <div className="sos-confirmation">
                <div className="sos-confirmation-icon">SOS</div>
                <h3>Запрос отправлен. Ожидайте подтверждения.</h3>
                <div className="request-status"><span className="request-status-dot" /><div><small>СТАТУС ЗАПРОСА</small><strong>Ожидает ответа</strong></div></div>
                <div className="sos-disclaimer"><Icon name="info" size={19} /><p>Это демонстрационный запрос. Реальная служба помощи или волонтёрская организация к прототипу не подключены.</p></div>
                <button className="button full" onClick={() => setSosOpen(false)}>Закрыть</button>
              </div>
            ) : (
              <>
                <p className="sos-description">Сообщите, где вы находитесь и какая помощь вам нужна.</p>
                <div className="sos-warning"><Icon name="info" size={19} /><span>Это прототип. Если вашей жизни или здоровью угрожает опасность, позвоните по номеру 112.</span></div>
                <label className="field-label" htmlFor="sos-location">Ваше местоположение</label>
                <div className="input-with-icon"><Icon name="pin" size={18} /><input id="sos-location" value={sosLocation} onChange={(e) => setSosLocation(e.target.value)} placeholder="Укажите, где вы находитесь" /></div>
                <label className="field-label" htmlFor="sos-building">Название здания</label>
                <div className="input-with-icon"><Icon name="building" size={18} /><input id="sos-building" value={sosBuilding} onChange={(e) => setSosBuilding(e.target.value)} placeholder="Например, ул. Советская, 18" /></div>
                <fieldset className="assistance-types">
                  <legend>Какая помощь нужна?</legend>
                  {["Помочь войти в здание.", "Помочь выйти из здания.", "Помочь преодолеть препятствие.", "Помочь передвигаться внутри здания."].map((type) => (
                    <label key={type}><input type="radio" name="sos-type" value={type} checked={sosType === type} onChange={(e) => setSosType(e.target.value)} /><span>{type}</span></label>
                  ))}
                </fieldset>
                <label className="field-label" htmlFor="sos-details">Дополнительные сведения</label>
                <textarea id="sos-details" value={sosDetails} onChange={(e) => setSosDetails(e.target.value)} placeholder="Опишите препятствие или уточните, как вам помочь" rows={3} />
                <button className="sos-submit" disabled={!sosLocation.trim() || !sosBuilding.trim() || !sosType} onClick={() => setSosSent(true)}><span className="sos-submit-icon">SOS</span>Отправить SOS</button>
                <p className="prototype-note">Запрос не будет передан в реальные службы — это интерактивный прототип.</p>
              </>
            )}
          </div>
        </div>
      )}

      {welcomeOpen && (
        <section className="welcome-screen" aria-label="Добро пожаловать в SeeWay">
          <div className="welcome-orb orb-one" /><div className="welcome-orb orb-two" />
          <article className="welcome-card">
            <header className="welcome-header"><SeeWayLogo /><button className="glass-icon-button" onClick={() => setWelcomeOpen(false)} aria-label="Закрыть приветствие"><Icon name="close" size={19} /></button></header>
            <div className="welcome-layout">
              <div className="welcome-copy">
                <p className="welcome-kicker">A CLEARER WAY FOR EVERYONE</p>
                <h1>Every place should be within reach.</h1>
                <p className="welcome-description">SeeWay helps you discover accessible buildings, check available facilities, and find routes that match your mobility needs.</p>
                <div className="welcome-features">
                  <div><span><Icon name="pin" /></span><p><strong>Discover places</strong><small>Find buildings and public spaces around you.</small></p></div>
                  <div><span><Icon name="check" /></span><p><strong>Check accessibility</strong><small>See ramps, elevators, entrances, and facilities.</small></p></div>
                  <div><span><Icon name="route" /></span><p><strong>Choose your route</strong><small>Plan journeys with accessibility in mind.</small></p></div>
                </div>
                <button className="welcome-primary" onClick={() => setWelcomeOpen(false)}>Go to map <Icon name="chevron" /></button>
              </div>
              <div className="welcome-visual"><div className="visual-glass-label"><span className="status-dot" />Open paths, welcoming places</div><WelcomeArchitecture /></div>
            </div>
            <footer className="welcome-footer"><span>Different needs. One more accessible world.</span><button onClick={() => setWelcomeOpen(false)}>Continue without introduction</button></footer>
          </article>
        </section>
      )}
    </div>
  );
}

function AccessRow({ label, value, known, date }: { label: string; value: string; known: boolean; date: string }) {
  return <div className="access-row"><div className={`access-symbol ${known ? "known" : ""}`}>{known ? <Icon name="check" size={17} /> : "?"}</div><div><strong>{label}</strong><span>{value}</span><small>{known ? `Обновлено: ${date}` : "Нет проверенных сведений"}</small></div></div>;
}

function AuthScreen({
  view,
  user,
  prototypeAccount,
  preferences,
  favoritePlaces,
  hasSavedRoute,
  onClose,
  onChangeView,
  onRegister,
  onLogin,
  onUpdateUser,
  onUpdatePreferences,
}: {
  view: Exclude<AuthView, null>;
  user: PrototypeUser | null;
  prototypeAccount: { name: string; email: string; password: string } | null;
  preferences: string[];
  favoritePlaces: Place[];
  hasSavedRoute: boolean;
  onClose: () => void;
  onChangeView: (view: AuthView) => void;
  onRegister: (user: PrototypeUser, password: string) => void;
  onLogin: (user: PrototypeUser) => void;
  onUpdateUser: (user: PrototypeUser) => void;
  onUpdatePreferences: (prefs: string[]) => void;
}) {
  const [name, setName] = useState(user?.name || "");
  const [email, setEmail] = useState(user?.email || "");
  const [password, setPassword] = useState("");
  const [repeatPassword, setRepeatPassword] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [remember, setRemember] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [registrationStep, setRegistrationStep] = useState<"form" | "success" | "preferences">("form");
  const [recoverySent, setRecoverySent] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draftPrefs, setDraftPrefs] = useState(preferences);
  const emailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);

  const validateRegistration = () => {
    const next: Record<string, string> = {};
    if (!name.trim()) next.name = "Укажите имя.";
    if (!email.trim()) next.email = "Укажите электронную почту.";
    else if (!emailValid) next.email = "Введите корректный адрес электронной почты.";
    if (!password) next.password = "Введите пароль.";
    else if (password.length < 8 || !/[A-ZА-Я]/.test(password) || !/[a-zа-я]/.test(password) || !/\d/.test(password)) next.password = "Минимум 8 символов, заглавная и строчная буквы, цифра.";
    if (!repeatPassword) next.repeatPassword = "Повторите пароль.";
    else if (password !== repeatPassword) next.repeatPassword = "Пароли не совпадают.";
    if (!accepted) next.accepted = "Необходимо принять условия использования.";
    setErrors(next);
    if (Object.keys(next).length === 0) {
      onRegister({ name: name.trim(), email: email.trim() }, password);
      setRegistrationStep("success");
    }
  };

  const validateLogin = () => {
    const next: Record<string, string> = {};
    if (!email.trim()) next.email = "Укажите электронную почту.";
    if (!password) next.password = "Введите пароль.";
    if (Object.keys(next).length === 0) {
      const matchesPrototype = prototypeAccount && email.trim().toLowerCase() === prototypeAccount.email.toLowerCase() && password === prototypeAccount.password;
      const matchesDemo = email.trim().toLowerCase() === "demo@dostupno.ru" && password === "Demo1234";
      if (!matchesPrototype && !matchesDemo) next.credentials = "Неверная электронная почта или пароль.";
      else onLogin(matchesPrototype && prototypeAccount ? { name: prototypeAccount.name, email: prototypeAccount.email } : { name: "Анна", email: "demo@dostupno.ru" });
    }
    setErrors(next);
  };

  const sendRecovery = () => {
    if (!email.trim()) setErrors({ email: "Укажите электронную почту." });
    else if (!emailValid) setErrors({ email: "Введите корректный адрес электронной почты." });
    else { setErrors({}); setRecoverySent(true); }
  };

  const togglePref = (id: string) => setDraftPrefs(draftPrefs.includes(id) ? draftPrefs.filter((item) => item !== id) : [...draftPrefs, id]);
  const prefOptions = [
    ["noSteps", "Мне нужен маршрут без лестниц."],
    ["elevator", "Мне необходим работающий лифт."],
    ["wide", "Мне нужны широкие двери."],
    ["ramp", "Мне нужен удобный пандус."],
    ["toilet", "Мне нужен доступный туалет."],
  ];

  return (
    <div className="auth-overlay">
      <div className="auth-shell">
        <div className="auth-brand"><SeeWayLogo /></div>
        <button className="close-button auth-close" onClick={onClose} aria-label="Закрыть"><Icon name="close" /></button>

        {view === "register" && registrationStep === "form" && <div className="auth-content">
          <AuthHeading title="Создать аккаунт" subtitle="Зарегистрируйтесь, чтобы сохранять маршруты и находить доступные места." />
          <div className="prototype-banner"><Icon name="info" size={18} /><span><b>Демонстрационный режим.</b> Реальный аккаунт не создаётся, данные существуют только в этой сессии.</span></div>
          <AuthField id="reg-name" label="Имя" value={name} onChange={setName} error={errors.name} autoComplete="name" />
          <AuthField id="reg-email" label="Электронная почта" value={email} onChange={setEmail} error={errors.email} type="email" autoComplete="email" />
          <PasswordField id="reg-password" label="Пароль" value={password} onChange={setPassword} error={errors.password} visible={showPassword} onToggle={() => setShowPassword(!showPassword)} autoComplete="new-password" />
          <PasswordField id="reg-repeat" label="Повторите пароль" value={repeatPassword} onChange={setRepeatPassword} error={errors.repeatPassword} visible={showPassword} onToggle={() => setShowPassword(!showPassword)} autoComplete="new-password" />
          <label className={`auth-check ${errors.accepted ? "has-error" : ""}`}><input type="checkbox" checked={accepted} onChange={(e) => setAccepted(e.target.checked)} /><span>Я согласен(на) с условиями использования и политикой конфиденциальности.</span></label>
          {errors.accepted && <span className="field-error">{errors.accepted}</span>}
          <button className="button full auth-primary" onClick={validateRegistration}>Зарегистрироваться</button>
          <p className="auth-switch">Уже есть аккаунт? <button onClick={() => onChangeView("login")}>Войти</button></p>
        </div>}

        {view === "register" && registrationStep === "success" && <div className="auth-content auth-result">
          <div className="result-round"><Icon name="check" size={30} /></div>
          <h1>Аккаунт успешно создан!</h1>
          <p>Это демонстрационный аккаунт текущей сессии. Теперь можно настроить необязательные предпочтения или перейти к карте.</p>
          <button className="button full auth-primary" onClick={() => setRegistrationStep("preferences")}>Настроить доступность</button>
          <button className="outline-button full auth-secondary" onClick={onClose}>Пропустить и перейти к карте</button>
        </div>}

        {view === "register" && registrationStep === "preferences" && <PreferencesContent prefs={draftPrefs} options={prefOptions} onToggle={togglePref} onSave={() => { onUpdatePreferences(draftPrefs); onClose(); }} onSkip={onClose} />}

        {view === "login" && <div className="auth-content">
          <AuthHeading title="С возвращением!" subtitle="Войдите, чтобы продолжить пользоваться сервисом." />
          <div className="prototype-banner"><Icon name="info" size={18} /><span>Прототип входа. Для демо: <b>demo@dostupno.ru</b> / <b>Demo1234</b></span></div>
          {errors.credentials && <div className="form-error" role="alert">{errors.credentials}</div>}
          <AuthField id="login-email" label="Электронная почта" value={email} onChange={setEmail} error={errors.email} type="email" autoComplete="email" />
          <PasswordField id="login-password" label="Пароль" value={password} onChange={setPassword} error={errors.password} visible={showPassword} onToggle={() => setShowPassword(!showPassword)} autoComplete="current-password" />
          <div className="auth-row"><label className="auth-check compact"><input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} /><span>Запомнить меня</span></label><button className="auth-link" onClick={() => onChangeView("recovery")}>Забыли пароль?</button></div>
          <button className="button full auth-primary" onClick={validateLogin}>Войти</button>
          <p className="auth-switch">Нет аккаунта? <button onClick={() => onChangeView("register")}>Зарегистрироваться</button></p>
        </div>}

        {view === "recovery" && <div className="auth-content">
          <AuthHeading title="Восстановление пароля" subtitle="Введите электронную почту, указанную при регистрации." />
          {!recoverySent ? <>
            <AuthField id="recovery-email" label="Электронная почта" value={email} onChange={setEmail} error={errors.email} type="email" autoComplete="email" />
            <button className="button full auth-primary" onClick={sendRecovery}>Отправить ссылку для восстановления</button>
            <p className="auth-switch"><button onClick={() => onChangeView("login")}>Вернуться ко входу</button></p>
          </> : <div className="auth-result inline-result"><div className="result-round"><Icon name="check" size={28} /></div><h2>Проверьте почту</h2><p>В рабочем сервисе ссылка для восстановления была бы отправлена на <b>{email}</b>. В этом прототипе письмо не отправляется.</p><button className="button full auth-primary" onClick={() => onChangeView("login")}>Вернуться ко входу</button></div>}
        </div>}

        {view === "preferences" && <PreferencesContent prefs={draftPrefs} options={prefOptions} onToggle={togglePref} onSave={() => { onUpdatePreferences(draftPrefs); onClose(); }} onSkip={onClose} />}

        {view === "profile" && user && <div className="profile-page">
          <AuthHeading title="Мой профиль" subtitle="Личные данные и сохранённая информация." />
          <div className="profile-summary"><div className="large-avatar">{user.name.slice(0, 1).toUpperCase()}</div><div><strong>{user.name}</strong><span>{user.email}</span></div><button className="outline-button" onClick={() => setEditing(!editing)}>{editing ? "Отменить" : "Редактировать"}</button></div>
          {editing && <div className="profile-edit"><AuthField id="profile-name" label="Имя" value={name} onChange={setName} /><AuthField id="profile-email" label="Электронная почта" value={email} onChange={setEmail} type="email" /><button className="button" onClick={() => { if (name.trim() && emailValid) { onUpdateUser({ name: name.trim(), email: email.trim() }); setEditing(false); } }}>Сохранить изменения</button></div>}
          <section className="profile-section"><div className="profile-section-head"><h2>Настройки доступности</h2><button onClick={() => onChangeView("preferences")}>Изменить</button></div><div className="preference-tags">{preferences.length ? preferences.map((id) => <span key={id}>{prefOptions.find(([key]) => key === id)?.[1]}</span>) : <p>Предпочтения пока не настроены.</p>}</div></section>
          <section className="profile-section"><h2>Сохранённые здания</h2>{favoritePlaces.length ? favoritePlaces.map((place) => <div className="profile-list-item" key={place.id}><Icon name="building" /><div><strong>{place.name}</strong><span>{place.address}</span></div></div>) : <p className="profile-empty">Нет сохранённых зданий.</p>}</section>
          <section className="profile-section"><h2>Сохранённые маршруты</h2>{hasSavedRoute ? <div className="profile-list-item"><Icon name="route" /><div><strong>Маршрут до выбранного места</strong><span>Без лестниц · сохранён в этой сессии</span></div></div> : <p className="profile-empty">Сохранённых маршрутов пока нет.</p>}</section>
          <section className="profile-section"><h2>Мои отзывы и сообщения</h2><div className="profile-list-item"><Icon name="report" /><div><strong>Сообщение о доступности</strong><span>11 мая 2025 · Не проверено</span></div></div></section>
        </div>}
      </div>
    </div>
  );
}

function AuthHeading({ title, subtitle }: { title: string; subtitle: string }) {
  return <div className="auth-heading"><h1>{title}</h1><p>{subtitle}</p></div>;
}

function AuthField({ id, label, value, onChange, error, type = "text", autoComplete }: { id: string; label: string; value: string; onChange: (value: string) => void; error?: string; type?: string; autoComplete?: string }) {
  return <div className={`auth-field ${error ? "has-error" : ""}`}><label htmlFor={id}>{label}</label><input id={id} value={value} onChange={(e) => onChange(e.target.value)} type={type} autoComplete={autoComplete} aria-invalid={!!error} aria-describedby={error ? `${id}-error` : undefined} />{error && <span className="field-error" id={`${id}-error`} role="alert">{error}</span>}</div>;
}

function PasswordField({ id, label, value, onChange, error, visible, onToggle, autoComplete }: { id: string; label: string; value: string; onChange: (value: string) => void; error?: string; visible: boolean; onToggle: () => void; autoComplete?: string }) {
  return <div className={`auth-field ${error ? "has-error" : ""}`}><label htmlFor={id}>{label}</label><div className="password-input"><input id={id} value={value} onChange={(e) => onChange(e.target.value)} type={visible ? "text" : "password"} autoComplete={autoComplete} aria-invalid={!!error} aria-describedby={error ? `${id}-error` : undefined} /><button onClick={onToggle} type="button" aria-label={visible ? "Скрыть пароль" : "Показать пароль"}><Icon name="eye" size={18} /></button></div>{error && <span className="field-error" id={`${id}-error`} role="alert">{error}</span>}</div>;
}

function PreferencesContent({ prefs, options, onToggle, onSave, onSkip }: { prefs: string[]; options: string[][]; onToggle: (id: string) => void; onSave: () => void; onSkip: () => void }) {
  return <div className="auth-content"><AuthHeading title="Настройки доступности" subtitle="Выберите только то, что удобно вам. Эти сведения необязательны, их можно изменить позже." /><div className="privacy-note"><Icon name="info" size={18} /><span>Мы не просим указывать инвалидность или медицинскую информацию.</span></div><div className="auth-preferences">{options.map(([id, label]) => <label key={id}><input type="checkbox" checked={prefs.includes(id)} onChange={() => onToggle(id)} /><span>{label}</span></label>)}</div><button className="button full auth-primary" onClick={onSave}>Сохранить и перейти к карте</button><button className="outline-button full auth-secondary" onClick={onSkip}>Пропустить</button></div>;
}
