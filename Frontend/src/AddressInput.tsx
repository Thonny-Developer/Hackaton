import { useId, useState } from "react";
import { type LatLon, useAddressSuggestions } from "./geo";

export type AddressOption = {
  key: string;
  title: string;
  subtitle?: string | null;
  kind: "me" | "place" | "2gis";
  lat?: number;
  lon?: number;
  placeId?: number;
};

type Props = {
  label: string;
  point: "start" | "finish";
  value: string;
  placeholder: string;
  onChange: (text: string) => void;
  onPick: (option: AddressOption) => void;
  getNear: () => LatLon;
  /** Варианты до подсказок 2GIS: «Моё местоположение», места из нашей базы */
  localOptions?: (text: string) => AddressOption[];
};

export default function AddressInput({ label, point, value, placeholder, onChange, onPick, getNear, localOptions }: Props) {
  const listId = useId();
  const [open, setOpen] = useState(false);
  // Подсказки нужны только пока человек печатает, а не после выбора варианта
  const [typing, setTyping] = useState(false);
  const [active, setActive] = useState(-1);
  const { items, loading, error } = useAddressSuggestions(value, getNear, open && typing);

  const options: AddressOption[] = [
    ...(localOptions?.(typing ? value : "") ?? []),
    ...(typing ? items.map((it) => ({ key: `2gis-${it.id}`, title: it.name, subtitle: it.address, kind: "2gis" as const, lat: it.lat, lon: it.lon })) : []),
  ];
  const showList = open && (options.length > 0 || (typing && value.trim().length >= 2));

  const pick = (option: AddressOption) => {
    onPick(option);
    setTyping(false);
    setOpen(false);
    setActive(-1);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      if (!options.length) return;
      const step = e.key === "ArrowDown" ? 1 : -1;
      setActive((i) => (i + step + options.length) % options.length);
    } else if (e.key === "Enter" && open && options.length) {
      e.preventDefault();
      pick(options[Math.max(active, 0)]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  return <>
    <label className="route-field">
      <span className={`route-point ${point}`} />
      <div>
        <small>{label}</small>
        <input
          value={value}
          placeholder={placeholder}
          aria-label={label}
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={showList}
          aria-controls={listId}
          aria-activedescendant={showList && active >= 0 ? `${listId}-${active}` : undefined}
          autoComplete="off"
          onChange={(e) => { onChange(e.target.value); setTyping(true); setOpen(true); setActive(-1); }}
          onFocus={(e) => { setOpen(true); e.target.select(); }}
          onBlur={() => setOpen(false)}
          onKeyDown={onKeyDown}
        />
      </div>
    </label>
    {showList && <ul className="suggest-list" id={listId} role="listbox" aria-label={`Варианты: ${label.toLowerCase()}`}>
      {options.map((option, i) => (
        <li
          key={option.key}
          id={`${listId}-${i}`}
          role="option"
          aria-selected={i === active}
          className={`${i === active ? "active" : ""} suggest-${option.kind}`}
          // mousedown, а не click: иначе input теряет фокус и список закрывается раньше выбора
          onMouseDown={(e) => { e.preventDefault(); pick(option); }}
          onMouseEnter={() => setActive(i)}
        >
          <strong>{option.title}</strong>
          {option.subtitle && <small>{option.subtitle}</small>}
        </li>
      ))}
      {typing && loading && !items.length && <li className="suggest-note" aria-live="polite">Ищем адреса…</li>}
      {typing && !loading && error && <li className="suggest-note">{error}</li>}
      {typing && !loading && !error && !options.length && <li className="suggest-note">Ничего не найдено</li>}
    </ul>}
  </>;
}
