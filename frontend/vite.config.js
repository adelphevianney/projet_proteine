import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// En développement, /api est relayé vers l'API FastAPI : pas de configuration CORS nécessaire.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: { "/api": process.env.API_URL || "http://localhost:8000" },
  },
});
