import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// В dev API берём через прокси, как в проде через Caddy: запросы идут на /api того же адреса.
// VITE_DEV_API_TARGET — куда проксировать (по умолчанию Caddy из docker compose на :80).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Один .env в корне проекта и для docker compose, и для npm run dev
  envDir: "..",
  server: {
    proxy: {
      "/api": { target: process.env.VITE_DEV_API_TARGET || "http://localhost", changeOrigin: true },
    },
  },
});
