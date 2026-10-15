# Sapa

Навигатор доступной среды для колледжа или университета. Он строит маршрут внутри здания с учётом потребностей человека: лифтов, пандусов, ширины проходов, ступеней и временных препятствий вроде сломанного лифта. Если доступного пути нет, сервис честно говорит об этом и объясняет, что мешает.

| Папка | Что там |
|---|---|
| [Frontend/](Frontend/) | React + Vite, карта Mapbox GL |
| [Backend/](Backend/) | REST API на FastAPI: граф здания, маршруты, препятствия ([README](Backend/README.md)) |
| [docs/](docs/) | Контракт API для фронтенда ([API.md](docs/API.md)) и пример графа здания |
| [deploy/](deploy/) | Конфигурация Caddy |

## Запуск одной командой

Нужен только Docker.

```bash
cp .env.example .env
# 1. Замените секреты (JWT_SECRET, POSTGRES_PASSWORD, MINIO_ROOT_PASSWORD): openssl rand -hex 32
# 2. Вставьте публичный токен Mapbox в VITE_MAPBOX_ACCESS_TOKEN
docker compose up -d --build
docker compose exec api python -m app.cli create-admin --email admin@example.com
```

| Адрес | Что там |
|---|---|
| http://localhost/ | Сайт |
| http://localhost/api/docs | Swagger, документация API |
| http://localhost/api/health | Проверка API и БД |

При первом старте создаётся демо-здание «Колледж Sapa (демо)»: 3 этажа, лестница, лифт, пандус и подъёмник. Демо-сценарии описаны в [docs/API.md](docs/API.md#демо-данные).

## Как это устроено

```
браузер ──► web (Caddy :80/:443)
              ├─ /        собранный фронтенд
              └─ /api/*   ──► api (FastAPI)
                               │  внутренняя сеть без выхода наружу
                               ├── db     PostgreSQL
                               ├── redis  лимиты запросов
                               └── minio  схемы этажей
```

* Сайт и API работают на одном домене, поэтому CORS не нужен.
* Наружу открыты только порты 80 и 443. БД, Redis и MinIO доступны только бэкенду.
* Все настройки лежат в одном `.env` в корне. Он не попадает в git, шаблон хранится в [.env.example](.env.example).
* Переменные `VITE_*` встраиваются во фронтенд при сборке. Если их поменять, нужно пересобрать образ: `docker compose up -d --build web`.

## Деплой на VPS

1. Направьте A-запись домена (например, `sapa.example.kz`) на IP сервера и откройте порты 80 и 443.
2. Склонируйте репозиторий и создайте `.env`, как описано выше. Укажите `DOMAIN=sapa.example.kz`.
3. Выполните `docker compose up -d --build`. Caddy сам получит сертификат Let's Encrypt.
4. В кабинете Mapbox ограничьте токен вашим доменом.

Пока домена нет, оставьте `DOMAIN=:80`: сайт откроется по HTTP на IP сервера.

Обновление: `git pull && docker compose up -d --build`. Миграции БД применяются автоматически.

## Разработка

**Фронтенд с горячей перезагрузкой.** Поднимите стек в Docker, а фронт запустите локально:

```bash
docker compose up -d
cd Frontend
echo "VITE_API_BASE_URL=http://localhost" > .env
echo "VITE_MAPBOX_ACCESS_TOKEN=pk...." >> .env
npm install
npm run dev        # http://localhost:5173
```

Vite-сервер ходит в API через Caddy по адресу `http://localhost`. Адрес `http://localhost:5173` уже разрешён в `CORS_ORIGINS`.

**Бэкенд.** Тесты, миграции и запуск без Docker описаны в [Backend/README.md](Backend/README.md).

## Полезные команды

```bash
docker compose ps                     # что запущено
docker compose logs -f api            # логи бэкенда
docker compose up -d --build web      # пересобрать фронт (например, после смены токена Mapbox)
docker compose exec api python -m app.cli seed   # пересоздать демо-здание
docker compose down                   # остановить (данные сохраняются)
docker compose down -v                # остановить и удалить все данные
```
