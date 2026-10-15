# Sapa API: контракт для фронтенда

Живая документация со всеми схемами доступна в Swagger: `/api/docs` (ReDoc: `/api/redoc`, OpenAPI JSON: `/api/openapi.json`). Здесь собрано то, что нужно знать, чтобы быстро подключить карту и маршруты.

## Основное

| | |
|---|---|
| Базовый путь | `/api/v1` |
| Формат | JSON, UTF-8 |
| Проверка живости | `GET /api/health` → `{"status":"ok","db":true}` |
| Язык текстов | `?lang=ru` (по умолчанию), `kk` (можно `kz`), `en` |
| Авторизация | только для изменения данных, см. ниже |

Всё, что читает данные и строит маршруты, открыто без токена. Создавать и менять здания, этажи, узлы, рёбра и препятствия могут только пользователи с ролью `editor` или `admin`.

## Как устроены данные

```
Building (здание)
 └─ Floor (этаж: level, схема, масштаб)
     └─ Node (точка на схеме: аудитория, вход, коридор, лифт...)
Edge (переход между двумя узлами: коридор, дверь, лестница, лифт, пандус...)
Obstacle (временное препятствие на узле или ребре)
```

**Координаты.** `x` и `y` узла задаются в пикселях картинки этажа: `x` вправо, `y` вниз, начало в левом верхнем углу. Размер картинки лежит в `floor.plan_width_px` и `floor.plan_height_px`. Если вы растягиваете схему, умножайте координаты на тот же коэффициент. Масштаб `floor.meters_per_px` нужен бэкенду для расчёта длин.

**Координаты на карте.** Если этаж привязан к карте (заполнены `geo_origin_lat`, `geo_origin_lon` и `geo_rotation_deg`), у каждого узла, результата поиска и точки маршрута есть поле `geo` в формате `[lon, lat]`. Для Mapbox берите его, а не `x`/`y`. Подробности в разделе [Карта Mapbox](#карта-mapbox).

**Типы узлов** (`node.type`): `room`, `entrance`, `corridor`, `elevator`, `stairs`, `ramp`, `lift` (подъёмник), `toilet`, `other`. Узлы `corridor` служат служебными точками графа. Их удобно не рисовать или рисовать мелко.

**Типы рёбер** (`edge.type`): `corridor`, `door`, `stairs`, `elevator`, `ramp`, `lift`, `outdoor`. Ребро может соединять узлы разных этажей (лестница, лифт). Для доступности важны поля `width_cm` (null значит «неизвестно»), `steps`, `slope_pct` и `threshold_cm`.

**Схема этажа.** `floor.plan_url` содержит относительный URL вида `/api/v1/floors/3/plan?v=ab12...`. Подставьте перед ним адрес API. Файл отдаётся с долгим кэшем: при загрузке новой схемы меняется `v`, поэтому браузер сам скачает свежую версию. Если `plan_url` равен `null`, схема ещё не загружена.

## Эндпоинты для карты

| Метод | Путь | Что делает |
|---|---|---|
| GET | `/buildings?q=&limit=&offset=` | Список зданий (с пагинацией) |
| GET | `/buildings/{id}` | Одно здание |
| GET | `/buildings/{id}/floors` | Этажи здания по возрастанию `level` |
| GET | `/floors/{id}` | Этаж целиком: узлы, рёбра и действующие препятствия. **Основной запрос для отрисовки этажа** |
| GET | `/floors/{id}/geojson` | Тот же этаж в GeoJSON для Mapbox (409, если этаж не привязан к карте) |
| GET | `/floors/{id}/plan` | Картинка схемы (PNG, JPEG, WebP или SVG) |
| GET | `/buildings/{id}/graph` | Весь граф здания одним ответом (все этажи, узлы, рёбра) |
| GET | `/search?q=204&building_id=&limit=` | Поиск помещения по номеру или названию |
| GET | `/profiles?lang=` | Профили доступности для выпадающего списка |
| GET | `/obstacles?building_id=&state=active` | Препятствия (`active`, `inactive` или `all`) |
| GET | `/nodes`, `/edges` | Списки с фильтрами `building_id`, `floor_id`, `type` (для узлов) |

Списки возвращают страницу: `{"items": [...], "total": 42, "limit": 50, "offset": 0}`. Максимальный `limit` равен 200.

В `GET /floors/{id}` приходят и рёбра, у которых на этом этаже только один конец (например, лифт на соседний этаж). По ним удобно рисовать значки переходов.

### Поиск

`GET /api/v1/search?q=204`

```json
[
  {
    "node_id": 64,
    "building_id": 1,
    "building_name": "Колледж Sapa (демо)",
    "floor_id": 2,
    "level": 2,
    "type": "room",
    "name": "Компьютерный класс",
    "ref": "204",
    "x": 500.0,
    "y": 150.0,
    "geo": [71.418158, 51.0910826]
  }
]
```

Сначала идут точные совпадения по номеру, потом номера, которые начинаются с запроса, потом совпадения в названии. Коридоры в выдачу не попадают. `node_id` из ответа сразу подходит для `/route`.

### Профили доступности

`GET /api/v1/profiles?lang=ru`

| id | Название | Главные ограничения |
|---|---|---|
| `default` | Без ограничений | нет |
| `wheelchair` | Кресло-коляска | без ступеней, ширина ≥ 90 см, уклон ≤ 8 %, порог ≤ 1.4 см |
| `walker` | Ходунки | без ступеней, ширина ≥ 70 см, уклон ≤ 10 %, порог ≤ 2 см |
| `stroller` | Детская коляска | без ступеней, ширина ≥ 70 см, уклон ≤ 12 %, порог ≤ 3 см |
| `no_stairs` | Без лестниц | без лестничных маршей, допускается до 2 ступеней |

Все параметры профиля приходят в `params`. Их можно вывести в настройках и дать пользователю поправить через `overrides` (см. ниже).

## Построение маршрута

`POST /api/v1/route?lang=ru`

```json
{
  "from_node": 61,
  "to_node": 64,
  "profile": "wheelchair",
  "overrides": { "min_width_cm": 80 }
}
```

`overrides` можно не передавать. В нём допустимы поля `allow_stairs`, `max_steps`, `min_width_cm`, `max_slope_pct`, `max_threshold_cm`, `allow_elevator` и `speed_mps`. Если передать `null` в числовом поле (например, `"min_width_cm": null`), это ограничение снимается.

### Маршрут найден

Ответ сокращён, полный пример показан в Swagger.

```json
{
  "found": true,
  "building_id": 1,
  "profile": "wheelchair",
  "params": { "allow_stairs": false, "max_steps": 0, "min_width_cm": 90.0, "max_slope_pct": 8.0,
              "max_threshold_cm": 1.4, "allow_elevator": true, "speed_mps": 0.9 },
  "total_distance_m": 64.6,
  "estimated_time_s": 116.0,
  "floors": [1, 2],
  "nodes": [
    { "id": 61, "floor_id": 1, "level": 1, "type": "room", "name": "Библиотека", "ref": "105",
      "x": 500.0, "y": 150.0, "geo": [71.418158, 51.0910826] },
    { "id": 37, "floor_id": 1, "level": 1, "type": "corridor", "name": null, "ref": null,
      "x": 500.0, "y": 300.0, "geo": [71.418158, 51.0910151] }
  ],
  "edges": [
    { "id": 60, "from_node_id": 61, "to_node_id": 37, "type": "door", "length_m": 7.5 }
  ],
  "steps": [
    { "action": "start", "text": "Начните у «Библиотека (105)» (1 этаж)", "floor_id": 1, "level": 1,
      "to_level": null, "distance_m": 0.0, "duration_s": 0.0, "node_ids": [61], "edge_ids": [] },
    { "action": "walk", "text": "Пройдите 8 м", "floor_id": 1, "level": 1, "to_level": null,
      "distance_m": 7.5, "duration_s": 11.0, "node_ids": [61, 37], "edge_ids": [60] },
    { "action": "turn_left", "text": "Поверните налево", "floor_id": 1, "level": 1, "to_level": null,
      "distance_m": 0.0, "duration_s": 0.0, "node_ids": [37], "edge_ids": [] },
    { "action": "walk", "text": "Пройдите 23 м до «Лифт»", "floor_id": 1, "level": 1, "to_level": null,
      "distance_m": 23.0, "duration_s": 29.0, "node_ids": [37, 38, 39, 41], "edge_ids": [39, 40, 42] },
    { "action": "elevator_up", "text": "Поднимитесь на лифте на 2 этаж", "floor_id": 1, "level": 1,
      "to_level": 2, "distance_m": 3.6, "duration_s": 36.0, "node_ids": [41, 48], "edge_ids": [71] },
    { "action": "arrive", "text": "Вы на месте: «Компьютерный класс (204)»", "floor_id": 2, "level": 2,
      "to_level": null, "distance_m": 0.0, "duration_s": 0.0, "node_ids": [64], "edge_ids": [] }
  ],
  "warnings": [],
  "reason": null,
  "geojson": {
    "type": "FeatureCollection",
    "features": [
      { "type": "Feature", "properties": { "kind": "route", "floor_id": 1, "level": 1 },
        "geometry": { "type": "LineString", "coordinates": [[71.418158, 51.0910826], [71.418158, 51.0910151], "..."] } },
      { "type": "Feature", "properties": { "kind": "transition", "floor_id": 1, "level": 1, "to_level": 2, "node_id": 41 },
        "geometry": { "type": "Point", "coordinates": [71.4184873, 51.0910151] } },
      "... линия 2 этажа, точки start и finish"
    ]
  }
}
```

Что с этим делать на фронте:

* **Линия маршрута.** Для Mapbox берите готовый `geojson` из ответа (см. [Карта Mapbox](#карта-mapbox)). Если рисуете поверх картинки, берите `nodes` по порядку, фильтруйте по `floor_id` текущего этажа и соединяйте точки `x`/`y`. Рёбра в `edges` уже развёрнуты по ходу движения.
* **Переключение этажей.** В `floors` перечислены уровни в порядке прохождения. Шаги с `to_level` означают переход на другой этаж: удобное место, чтобы переключить схему.
* **Пошаговая подсказка.** `steps[].text` уже переведён на язык из `lang`. Если хотите свои тексты или иконки, ориентируйтесь на `action`.
* **Подсветка шага.** `node_ids` и `edge_ids` показывают, какой участок линии относится к шагу.
* **Предупреждения.** `warnings` выводите отдельно. Например, ширина прохода неизвестна (`width_unknown`) или проход сужен препятствием (`narrowed`). Маршрут при этом построен.

Возможные `action`: `start`, `walk`, `turn_left`, `turn_right`, `ramp`, `steps`, `elevator_up`, `elevator_down`, `stairs_up`, `stairs_down`, `ramp_up`, `ramp_down`, `lift_up`, `lift_down`, `lift_same`, `arrive`.

### Маршрута нет

Если доступного пути нет, ответ всё равно приходит с кодом **200**, но `found=false`. В `reason` лежат код причины, готовое сообщение и список конкретных мест, которые мешают.

```json
{
  "found": false,
  "reason": {
    "code": "no_accessible_path",
    "message": "Для выбранного профиля доступного пути нет.",
    "details": [
      {
        "kind": "constraint",
        "code": "too_narrow",
        "message": "ширина 70 см, нужно не меньше 90 см (у «Лаборатория (210)»)",
        "edge_id": 64,
        "node_id": null,
        "obstacle_id": null,
        "value": 70.0,
        "limit": 90.0
      }
    ]
  }
}
```

| `reason.code` | Когда |
|---|---|
| `no_accessible_path` | Путь есть, но он не подходит профилю (лестница, узкая дверь, крутой пандус) |
| `blocked_by_obstacles` | Подходящий путь есть, но сейчас он перекрыт (например, сломан лифт) |
| `no_accessible_path_and_obstacles` | И профиль не позволяет, и препятствия мешают |
| `start_blocked`, `goal_blocked` | На начальной или конечной точке стоит препятствие |
| `not_connected` | В схеме нет связи между точками, скорее всего, граф неполный |
| `different_buildings` | Точки в разных зданиях (маршрут строится внутри одного) |

В `details[].kind` бывает `constraint` (не подходит профилю, коды `stairs`, `steps`, `too_narrow`, `too_steep`, `threshold`, `elevator_not_allowed`) или `obstacle` (тогда заполнен `obstacle_id`, а `code` совпадает с типом препятствия). По `edge_id` или `node_id` можно подсветить проблемное место на схеме.

### Маршрут с улицы

`POST /api/v1/route/full?lang=ru`

```json
{
  "from_location": { "lat": 51.0905, "lon": 71.4181 },
  "to_node": 64,
  "profile": "wheelchair"
}
```

Бэкенд выбирает вход в здание, от которого есть подходящий внутренний маршрут. Для колясок подходят только входы с `is_accessible_entrance=true`. Потом бэкенд строит уличный участок до этого входа.

```json
{
  "found": true,
  "entrance": { "id": 58, "floor_id": 1, "level": 1, "type": "entrance", "name": "Боковой вход (пандус)",
                "ref": null, "x": 990.0, "y": 480.0 },
  "outdoor": {
    "provider": "straight_line",
    "accessibility_checked": false,
    "distance_m": 64.6,
    "duration_s": 93.0,
    "geometry": [[71.4181, 51.0905], [71.41862, 51.09098]],
    "steps": []
  },
  "indoor": { "...": "тот же формат, что у POST /route" },
  "total_time_s": 200.0,
  "notices": ["Уличный маршрут не построен, расстояние оценено по прямой"]
}
```

* `outdoor.geometry` задаётся как `[lon, lat]`, такой порядок принят в GeoJSON и Mapbox. Для слоя его достаточно обернуть: `{type: "Feature", geometry: {type: "LineString", coordinates: outdoor.geometry}}`.
* `entrance.geo` содержит координаты выбранного входа, это точка стыка уличной и внутренней частей.
* `outdoor.provider` бывает `ors` (OpenRouteService, учитывает бордюры и уклоны), `2gis` (обычный пеший маршрут) или `straight_line` (ключей внешних API нет или они не ответили).
* Если `accessibility_checked=false`, а профиль не `default`, честно предупредите пользователя: на уличном участке ограничения не проверялись. Тексты для этого уже лежат в `notices`.
* Какие внешние API подключены, показывает `GET /api/v1/integrations/status` → `{"dgis": true, "ors": false}`.

### Подсказки адресов (2GIS)

`GET /api/v1/geo/suggest?q=мега силк&lat=51.09&lon=71.41&lang=ru`

Ключ 2GIS остаётся на сервере, фронт ходит только в наш API. `lat`/`lon` необязательны и поднимают выше то, что рядом (центр карты или пользователь). В ответе только варианты с координатами:

```json
[
  { "id": "70000001026995330", "type": "branch", "name": "Mega Silk Way, торгово-развлекательный центр",
    "address": "Кабанбай батыр проспект, 62", "lat": 51.089347, "lon": 71.405441 }
]
```

* `type`: `building`, `branch` (организация), `street`, `adm_div`, `station` и другие типы 2GIS.
* `address` это вторая строка подсказки. Если адрес совпадает с названием, там полное имя с городом.
* Запрос от 2 символов. Вызывайте с задержкой ~300 мс после ввода, лимит общий с `/search`.
* Без ключа 2GIS ответ `503`, при сбое 2GIS `502`.

### Уличный маршрут между двумя точками (2GIS)

`POST /api/v1/route/outdoor?lang=ru`

```json
{
  "from_location": { "lat": 51.091184, "lon": 71.417607 },
  "to_location": { "lat": 51.089347, "lon": 71.405441 },
  "profile": "no_stairs"
}
```

```json
{
  "route": {
    "provider": "2gis",
    "accessibility_checked": false,
    "distance_m": 1502.0,
    "duration_s": 1202.0,
    "geometry": [[71.417606, 51.091183], "..."],
    "steps": [{ "text": "1.4 км прямо", "distance_m": 1413.0 }, { "text": "Вы на месте!", "distance_m": 0.0 }]
  },
  "notices": ["Уличный участок построен без учёта бордюров и уклонов, будьте внимательны"]
}
```

* `route` в том же формате, что `outdoor` у `/route/full`, `geometry` задаётся как `[lon, lat]`.
* Если профиль запрещает лестницы (`allow_stairs=false`, это все пресеты кроме `default`), 2GIS строит путь без лестниц. Бордюры и уклоны 2GIS не учитывает, поэтому `accessibility_checked` всегда `false`.
* Точки дальше 30 км друг от друга дают `422`. Без ключа 2GIS `503`, если 2GIS не нашёл путь или не ответил, `502` с текстом в `detail`.

## Карта Mapbox

Бэкенд сам переводит пиксели схемы в координаты, фронту остаётся только передать готовые данные в Mapbox GL. Всё работает, когда этаж привязан к карте (на демо-стенде привязаны все этажи).

| Что | Откуда | Как использовать в Mapbox |
|---|---|---|
| Картинка этажа на карте | `floor.plan_url` + `floor.plan_corners` | Источник `image` |
| Узлы и переходы этажа | `GET /floors/{id}/geojson` | Источник `geojson`, слои `circle` и `line` |
| Линия маршрута | `geojson` в ответе `POST /route` (и `indoor.geojson` у `/route/full`) | Источник `geojson`, фильтр по `level` |
| Улица до входа | `outdoor.geometry` у `/route/full` | `LineString` из `[lon, lat]` |
| Пеший маршрут по городу | `route.geometry` у `/route/outdoor` | `LineString` из `[lon, lat]` |
| Точка помещения | `geo` у результатов `/search` и узлов | `flyTo({center: geo})` |

`plan_corners` хранит четыре угла картинки в порядке, который ждёт Mapbox: левый верхний, правый верхний, правый нижний, левый нижний. Если схема не загружена или этаж не привязан, там `null`.

**GeoJSON этажа** состоит из точек узлов (`properties.kind = "node"`, плюс `type`, `name`, `ref`, `is_accessible_entrance`) и линий переходов внутри этажа (`kind = "edge"`, плюс `type`, `width_cm`, `steps`, `slope_pct`). Всё, что сейчас перекрыто препятствием, помечено `blocked: true` и `obstacle_id`. Сломанный лифт тоже помечается на самом узле лифта.

**GeoJSON маршрута** содержит по одной линии на каждый этаж (`kind = "route"`, `level`), точки `start` и `finish`, а также точки `transition` в местах смены этажа (`level`, `to_level`). Показывайте только линию текущего этажа через фильтр по `level`.

```js
const API = "https://api.example.kz";

// Схема этажа поверх карты
map.addSource("plan", { type: "image", url: API + floor.plan_url, coordinates: floor.plan_corners });
map.addLayer({ id: "plan", type: "raster", source: "plan", paint: { "raster-opacity": 0.9 } });

// Узлы и переходы этажа
const floorGeo = await fetch(`${API}/api/v1/floors/${floor.id}/geojson`).then(r => r.json());
map.addSource("floor", { type: "geojson", data: floorGeo });
map.addLayer({ id: "edges", type: "line", source: "floor", filter: ["==", ["get", "kind"], "edge"],
  paint: { "line-color": ["case", ["get", "blocked"], "#d33", "#999"], "line-width": 2 } });
map.addLayer({ id: "nodes", type: "circle", source: "floor",
  filter: ["all", ["==", ["get", "kind"], "node"], ["!=", ["get", "type"], "corridor"]],
  paint: { "circle-radius": 5, "circle-color": ["case", ["get", "blocked"], "#d33", "#1e6fd9"] } });

// Маршрут: показываем только текущий этаж
const route = await fetch(`${API}/api/v1/route?lang=ru`, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ from_node: 61, to_node: 64, profile: "wheelchair" }),
}).then(r => r.json());
if (route.found && route.geojson) {
  map.addSource("route", { type: "geojson", data: route.geojson });
  map.addLayer({ id: "route", type: "line", source: "route",
    filter: ["all", ["==", ["get", "kind"], "route"], ["==", ["get", "level"], floor.level]],
    paint: { "line-color": "#0a7", "line-width": 5 } });
}
// При переключении этажа: map.setFilter("route", [... , ["==", ["get", "level"], newLevel]])
```

Если `geojson` равен `null`, этаж не привязан к карте. Тогда рисуйте маршрут по `x`/`y` поверх картинки, как описано выше.

**Как привязать этаж** (делает редактор, один раз на этаж):

```http
PATCH /api/v1/floors/{id}
Authorization: Bearer <token>
Content-Type: application/json

{ "geo_origin_lat": 51.09115, "geo_origin_lon": 71.41780, "geo_rotation_deg": 0, "meters_per_px": 0.05 }
```

* `geo_origin_lat` и `geo_origin_lon` задают точку на местности, где лежит левый верхний угол картинки схемы.
* `geo_rotation_deg` задаёт поворот схемы по часовой стрелке относительно севера: 0, если верх картинки смотрит на север.
* `meters_per_px` отвечает за масштаб схемы. От него зависят и длины маршрута, и размер картинки на карте.

Удобнее всего подбирать значения в админке: показать полупрозрачную схему поверх Mapbox и двигать и поворачивать её, пока стены не совпадут со зданием на подложке. Координаты входов после этого считаются автоматически. Ручные `lat`/`lon` у узла нужны, только если точка на местности не совпадает со схемой.

## Авторизация

Роли: `admin` и `editor` создаёт админ (через CLI или `POST /users`), `user` регистрируется сам. Посетитель (`user`) хранит профиль, избранное и сообщения, но граф менять не может (403).

### Регистрация и профиль посетителя

| Запрос | Что делает |
|---|---|
| `POST /api/v1/auth/register` `{"name", "email", "password"}` | Создаёт аккаунт `user` и сразу возвращает токен, как `/auth/login`. Пароль от 10 до 128 символов, имя до 100. **409**, если email занят. 5 запросов в минуту с IP |
| `GET /api/v1/auth/me` | Текущий пользователь: `id`, `email`, `name`, `role`, `accessibility_prefs`, `created_at` |
| `PATCH /api/v1/auth/me` `{"name"?, "email"?, "accessibility_prefs"?}` | Меняет только переданные поля. `accessibility_prefs` из `noSteps`, `elevator`, `wide`, `ramp`, `toilet`. **409**, если новый email занят |
| `GET /api/v1/auth/me/favorites` | Избранные здания (как в `GET /buildings`), новые сверху |
| `PUT /api/v1/auth/me/favorites/{building_id}` | Добавить в избранное, **204**. Повторный вызов ничего не меняет |
| `DELETE /api/v1/auth/me/favorites/{building_id}` | Убрать из избранного, **204** |
| `GET /api/v1/auth/me/reports` | Мои сообщения о доступности (страница `items/total`) |

### Сообщения о доступности

`POST /api/v1/reports` `{"building_id", "text"}` (текст от 3 до 2000 символов) можно отправить и без токена. С токеном сообщение привязывается к автору и появляется в `GET /auth/me/reports`. Статус сначала `new`. На маршруты сообщение не влияет, пока редактор не проверит его и не заведёт препятствие. Админы получают письмо о каждом новом сообщении. Не больше 10 сообщений в час с IP.

Редактор видит все сообщения через `GET /api/v1/reports?status=new&building_id=...` и меняет статус через `PATCH /api/v1/reports/{id}` `{"status": "confirmed" | "rejected"}`.

### Вход

1. `POST /api/v1/auth/login` с телом **form-data** (не JSON): `username=<email>&password=<пароль>`.
2. В ответе придёт `{"access_token": "...", "token_type": "bearer", "expires_in": 43200}`.
3. Дальше передавайте заголовок `Authorization: Bearer <access_token>`.
4. `GET /api/v1/auth/me` вернёт текущего пользователя и его роль.

Токен живёт 12 часов. На вход разрешено 5 попыток в минуту с одного IP.

### Забыли пароль

1. `POST /api/v1/auth/forgot-password` с телом `{"email": "user@example.com"}`. Ответ всегда **202** с одинаковым текстом, даже если такого адреса нет: так по API нельзя проверить, кто зарегистрирован. Не больше 3 запросов в минуту с одного IP.
2. Пользователю приходит письмо со ссылкой `https://<сайт>/reset-password?token=...`. Ссылка действует 30 минут.
3. **Фронту нужна страница `/reset-password`.** Она берёт `token` из адреса, показывает поле нового пароля (минимум 10 символов) и отправляет `POST /api/v1/auth/reset-password` с телом `{"token": "...", "password": "..."}`.
4. Ответ **200** означает, что пароль изменён и можно входить. Ответ **400** означает, что ссылка устарела или уже использована: предложите запросить письмо заново.

Ссылка одноразовая: после смены пароля она перестаёт работать.

Когда редактор отмечает препятствие, все админы получают письмо: что случилось, где, до какого времени и кто отметил.

### Что может редактор

| Метод | Путь | |
|---|---|---|
| POST, PATCH, DELETE | `/buildings`, `/buildings/{id}` | Здания (удаление только для `admin`) |
| POST | `/buildings/{id}/floors` | Новый этаж |
| PATCH, DELETE | `/floors/{id}` | Этаж |
| POST, DELETE | `/floors/{id}/plan` | Загрузить (multipart, поле `file`) или удалить схему. До 10 МБ, PNG, JPEG, WebP или SVG |
| POST, PATCH, DELETE | `/nodes`, `/nodes/{id}` | Узлы |
| POST, PATCH, DELETE | `/edges`, `/edges/{id}` | Рёбра. Если не передать `length_m`, длина посчитается по координатам |
| POST, PATCH, DELETE | `/obstacles`, `/obstacles/{id}` | Препятствия |
| POST | `/buildings/import` | Создать здание вместе с графом из одного JSON |
| PUT | `/buildings/{id}/graph` | Заменить граф здания целиком |
| GET, POST | `/integrations/2gis/buildings`, `/integrations/2gis/import` | Найти здание в 2GIS и создать его у нас |
| * | `/users` | Управление пользователями (только `admin`) |

**Препятствие** создаётся на узле **или** на ребре, ровно на одном из двух:

```json
{ "node_id": 41, "type": "elevator_broken", "description": "Ремонт до 20 октября",
  "ends_at": "2026-10-20T18:00:00+05:00" }
```

Типы: `elevator_broken`, `repair`, `blocked`, `narrowed`, `other`. Если указать `reduced_width_cm`, проход не перекрывается, а сужается до этой ширины. Препятствие на любом узле лифта выключает всю шахту, на всех этажах. Снять препятствие можно так: `PATCH /obstacles/{id}` с `{"is_active": false}`. Если указан `ends_at`, оно снимется автоматически.

**Импорт графа одним JSON.** Удобно, если схему реального здания размечают вручную. Узлы и этажи ссылаются друг на друга по локальным ключам `key`, а реальные id бэкенд возвращает в `node_ids`. Полный рабочий пример лежит в [demo_building.json](demo_building.json).

```json
{
  "name": "Корпус А",
  "graph": {
    "floors": [{ "key": "f1", "level": 1, "meters_per_px": 0.05 }],
    "nodes": [
      { "key": "hall", "floor": "f1", "type": "corridor", "x": 100, "y": 300 },
      { "key": "r101", "floor": "f1", "type": "room", "name": "Аудитория", "ref": "101", "x": 100, "y": 150 }
    ],
    "edges": [{ "from": "hall", "to": "r101", "type": "door", "width_cm": 90 }]
  }
}
```

## Ошибки и лимиты

| Код | Когда | Тело |
|---|---|---|
| 401 | Нет токена или он неверный | `{"detail": "Требуется авторизация"}` |
| 403 | Не хватает прав (например, редактор пытается управлять пользователями) | `{"detail": "Недостаточно прав"}` |
| 404 | Объект не найден | `{"detail": "Узел #999 не найден"}` |
| 409 | Дубликат (этаж с таким `level`, здание из 2GIS уже импортировано) | `{"detail": "..."}` |
| 413, 415 | Схема слишком большая или неподходящего формата | `{"detail": "..."}` |
| 422 | Ошибка валидации | `{"detail": [{"loc": [...], "msg": "..."}]}` (у импорта: список строк) |
| 429 | Слишком много запросов | `{"detail": "Слишком много запросов: ..."}` + `Retry-After` |
| 502 | Внешнее API (2GIS, ORS) не ответило | `{"detail": "..."}` |

Лимиты на один IP по умолчанию: 120 запросов в минуту на всё, 30 в минуту на `/route`, 60 на `/search`, 10 на `/route/full` и `/route/outdoor`, 60 на `/geo/suggest`, 5 на вход. Не стройте маршрут на каждое движение мыши: вызывайте `/route` по нажатию кнопки или с задержкой.

CORS разрешён только для адресов из настройки `CORS_ORIGINS` на сервере. Если фронт открывается с нового адреса, попросите бэкенд добавить его. Проще всего раздавать фронт с того же домена, что и API: тогда CORS не нужен вообще.

## Демо-данные

На стенде при старте создаётся «Колледж Sapa (демо)»: 3 этажа, лестница, лифт, пандус и подъёмник. id узлов могут отличаться между стендами, поэтому ищите их через `/search`.

| Сценарий | Что запросить | Что увидите |
|---|---|---|
| Обычный путь и путь на коляске различаются | `/route` 105 → 204 с `default` и `wheelchair` | Пешком по лестнице, на коляске через лифт |
| Честный отказ | `/route` 105 → 210 с `wheelchair` | `too_narrow`: дверь 70 см |
| Подъёмник | `/route` 105 → 305 с `default` и `wheelchair` | Две ступени или подъёмник |
| Сломан лифт | Создать `elevator_broken` на узле «Лифт», потом `/route` 105 → 204 с `wheelchair` | `blocked_by_obstacles` с текстом препятствия |
| С улицы | `/route/full` с координатами `51.0905, 71.4181` к 204 | Для коляски выбирается боковой вход с пандусом |
