import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev-mode iteration (`npm run dev`) proxies API/WS calls to the already
// running `backend` container (see docker-compose.yml) instead of bundling
// its own backend - the production container serves the built dist/ itself
// via FastAPI's StaticFiles, this proxy only exists for local frontend dev.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
      },
    },
  },
});
