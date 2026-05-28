import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build output lands inside the Python package so FastAPI can serve it
// directly from `static/app/` without copy steps.
export default defineConfig({
  plugins: [react()],
  base: "/app/",
  build: {
    outDir: "../src/prompture_hub/static/app",
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    port: 1985,
    proxy: {
      "/api": "http://127.0.0.1:1984",
      "/auth": "http://127.0.0.1:1984",
      "/v1": "http://127.0.0.1:1984",
      "/admin": "http://127.0.0.1:1984",
      "/docs": "http://127.0.0.1:1984",
      "/openapi.json": "http://127.0.0.1:1984",
      "/health": "http://127.0.0.1:1984",
    },
  },
});
