"""Демо-здание для презентации. Схема каждого этажа 1000×600 px, масштаб 0.05 м/px (50×30 м).

Что видно на демо:
* «Библиотека 105» -> «Компьютерный класс 204»: обычный маршрут идёт по лестнице (ближе),
  маршрут для коляски идёт через лифт в восточном крыле.
* Главный вход с крыльцом (3 ступени), боковой вход с пандусом. Маршрут с улицы для коляски
  выбирает боковой вход.
* «Лаборатория 210»: дверь 70 см, на коляске недоступна, и API честно объясняет почему.
* «Деканат 305»: на полуэтаж ведут 2 ступени, рядом есть подъёмник.
* Отметьте препятствие elevator_broken на узле «Лифт» и маршрут для коляски станет невозможен
  с понятной причиной, а обычный не изменится.
"""

DEMO_NAME = "Колледж Sapa (демо)"

# Привязка к карте: левый верхний угол схемы на местности, схема ориентирована на север.
# Координаты входов не задаются вручную, они вычисляются из этой привязки.
_GEO = {"geo_origin_lat": 51.09115, "geo_origin_lon": 71.41780, "geo_rotation_deg": 0}

_floors = [
    {"key": f"f{lvl}", "level": lvl, "name": f"{lvl} этаж", "meters_per_px": 0.05, "height_m": 3.6, **_GEO}
    for lvl in (1, 2, 3)
]


def _n(key, floor, type_, x, y, name=None, ref=None, **kw):
    return {"key": key, "floor": floor, "type": type_, "x": x, "y": y, "name": name, "ref": ref, **kw}


def _e(a, b, type_="corridor", width=200, **kw):
    return {"from": a, "to": b, "type": type_, "width_cm": width, **kw}


def _typical_floor(lvl: int) -> tuple[list, list]:
    f = f"f{lvl}"
    nodes = [
        _n(f"c{lvl}_w", f, "corridor", 100, 300),
        _n(f"c{lvl}_st", f, "corridor", 300, 300),
        _n(f"c{lvl}_mid", f, "corridor", 500, 300),
        _n(f"c{lvl}_wc", f, "corridor", 700, 300),
        _n(f"c{lvl}_e", f, "corridor", 900, 300),
        _n(f"st{lvl}", f, "stairs", 300, 200, "Лестница"),
        _n(f"el{lvl}", f, "elevator", 960, 300, "Лифт"),
    ]
    edges = [
        _e(f"c{lvl}_w", f"c{lvl}_st"),
        _e(f"c{lvl}_st", f"c{lvl}_mid"),
        _e(f"c{lvl}_mid", f"c{lvl}_wc"),
        _e(f"c{lvl}_wc", f"c{lvl}_e"),
        _e(f"c{lvl}_st", f"st{lvl}", width=150),
        _e(f"c{lvl}_e", f"el{lvl}", "door", width=95),
    ]
    return nodes, edges


def build_demo() -> dict:
    nodes, edges = [], []
    for lvl in (1, 2, 3):
        n, e = _typical_floor(lvl)
        nodes += n
        edges += e

    # 1 этаж: входы, холл, библиотека, туалет
    nodes += [
        _n("ent_main", "f1", "entrance", 500, 590, "Главный вход"),
        _n("lobby", "f1", "corridor", 500, 480, "Холл"),
        _n("ent_side", "f1", "entrance", 990, 480, "Боковой вход (пандус)", is_accessible_entrance=True),
        _n("side_hall", "f1", "corridor", 900, 480),
        _n("r101", "f1", "room", 100, 150, "Аудитория", "101"),
        _n("r105", "f1", "room", 500, 150, "Библиотека", "105"),
        _n("wc1", "f1", "toilet", 700, 420, "Доступный туалет", "WC-1"),
    ]
    edges += [
        _e("ent_main", "lobby", "door", width=140, steps=3, description="Крыльцо без пандуса"),
        _e("lobby", "c1_mid", width=300),
        _e("ent_side", "side_hall", "ramp", width=120, slope_pct=6, length_m=6, description="Пандус 1:16"),
        _e("side_hall", "c1_e", "door", width=100, threshold_cm=1),
        _e("c1_w", "r101", "door", width=90),
        _e("c1_mid", "r105", "door", width=120),
        _e("c1_wc", "wc1", "door", width=100),
    ]

    # 2 этаж: аудитории
    nodes += [
        _n("r201", "f2", "room", 100, 150, "Аудитория", "201"),
        _n("r204", "f2", "room", 500, 150, "Компьютерный класс", "204"),
        _n("r210", "f2", "room", 900, 450, "Лаборатория", "210"),
    ]
    edges += [
        _e("c2_w", "r201", "door", width=90),
        _e("c2_mid", "r204", "door", width=90),
        _e("c2_e", "r210", "door", width=70, description="Узкая дверь лаборатории"),
    ]

    # 3 этаж: актовый зал и деканат на полуэтаже
    nodes += [
        _n("r301", "f3", "room", 500, 150, "Актовый зал", "301"),
        _n("c3_upper", "f3", "corridor", 820, 200, "Полуэтаж"),
        _n("r305", "f3", "room", 820, 100, "Деканат", "305"),
    ]
    edges += [
        _e("c3_mid", "r301", "door", width=160),
        _e("c3_e", "c3_upper", "stairs", width=150, steps=2, length_m=2, description="Две ступени на полуэтаж"),
        _e("c3_e", "c3_upper", "lift", width=100, length_m=2, description="Подъёмник для коляски"),
        _e("c3_upper", "r305", "door", width=90),
    ]

    # Вертикальные связи
    edges += [
        _e("st1", "st2", "stairs", width=140, steps=22),
        _e("st2", "st3", "stairs", width=140, steps=22),
        _e("el1", "el2", "elevator", width=100),
        _e("el2", "el3", "elevator", width=100),
    ]

    return {
        "name": DEMO_NAME,
        "address": "Астана, демо-адрес",
        "description": "Демонстрационное здание: 3 этажа, лифт, лестница, пандус, подъёмник",
        "lat": 51.0910151,
        "lon": 71.418158,
        "graph": {"floors": _floors, "nodes": nodes, "edges": edges},
    }
