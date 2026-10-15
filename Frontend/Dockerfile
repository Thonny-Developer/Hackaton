# Сборка фронтенда в статику и раздача её через Caddy (он же проксирует /api на бэкенд)

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .

# Vite встраивает VITE_* в бандл при сборке, поэтому это аргументы сборки, а не runtime-переменные.
# "/" означает, что API на том же домене: запросы идут на /api/v1/... без CORS.
ARG VITE_API_BASE_URL=/
ARG VITE_MAPBOX_ACCESS_TOKEN=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_MAPBOX_ACCESS_TOKEN=$VITE_MAPBOX_ACCESS_TOKEN
RUN npm run build

FROM caddy:2.10-alpine
COPY --from=build /app/dist /srv/frontend
