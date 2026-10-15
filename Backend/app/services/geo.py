"""Привязка схемы этажа к карте: пиксели схемы <-> долгота/широта.

Этаж задаёт точку на карте, где лежит левый верхний угол схемы (geo_origin_lat/lon),
и поворот схемы по часовой стрелке относительно севера (geo_rotation_deg).
Масштаб берётся из meters_per_px. Для здания (десятки и сотни метров) локальной
плоской аппроксимации хватает с запасом.
"""

import math

EARTH_R = 6_371_008.8


def to_lonlat(x: float, y: float, meters_per_px: float, lat0: float | None, lon0: float | None,
              rotation_deg: float | None) -> list[float] | None:
    """Пиксель схемы -> [lon, lat] (порядок как в GeoJSON и Mapbox). None, если этаж не привязан."""
    if lat0 is None or lon0 is None:
        return None
    # На схеме ось y направлена вниз, на карте север вверх
    east, north = x * meters_per_px, -y * meters_per_px
    th = math.radians(rotation_deg or 0.0)
    e = east * math.cos(th) + north * math.sin(th)
    n = -east * math.sin(th) + north * math.cos(th)
    lat = lat0 + math.degrees(n / EARTH_R)
    lon = lon0 + math.degrees(e / (EARTH_R * math.cos(math.radians(lat0))))
    return [round(lon, 7), round(lat, 7)]


def floor_lonlat(floor, x: float, y: float) -> list[float] | None:
    return to_lonlat(x, y, floor.meters_per_px, floor.geo_origin_lat, floor.geo_origin_lon, floor.geo_rotation_deg)


def plan_corners(floor) -> list[list[float]] | None:
    """Углы картинки схемы в порядке Mapbox image source: левый верхний, правый верхний,
    правый нижний, левый нижний."""
    w, h = floor.plan_width_px, floor.plan_height_px
    if not w or not h:
        return None
    corners = [floor_lonlat(floor, x, y) for x, y in ((0, 0), (w, 0), (w, h), (0, h))]
    return None if corners[0] is None else corners
