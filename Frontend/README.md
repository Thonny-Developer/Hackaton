# SeeWay frontend

React + Vite accessibility map based on the supplied wireframe. The map is rendered with Mapbox GL JS.

## Configuration

Set these values in `Frontend/.env`:

```env
VITE_MAPBOX_ACCESS_TOKEN=your_mapbox_public_token
VITE_API_BASE_URL=http://localhost
```

The Mapbox token is a public browser token. Restrict it to the application's allowed URLs in the Mapbox dashboard before deployment. `.env` is ignored by Git; keep real credentials out of commits.

The frontend loads building pins from `GET /api/v1/buildings?limit=200`. Buildings without coordinates are omitted. If the API is unavailable or contains no located buildings, the supplied wireframe's sample places remain visible. The backend building list does not include accessibility details, so API buildings are marked as unverified.

## Run locally

Install Node.js, then run:

```bash
npm install
npm run dev
```

Mapbox GL JS and its stylesheet load from Mapbox's CDN. The API must allow the frontend origin through its `CORS_ORIGINS` setting.
