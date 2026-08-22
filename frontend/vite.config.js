import { defineConfig } from "vite";

const backendTarget = process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    watch: {
      usePolling: true,
    },
    proxy: {
      "/api": backendTarget,
      "/healthz": backendTarget,
      "/docs": backendTarget,
      "/openapi.json": backendTarget,
    },
  },
  preview: {
    host: "0.0.0.0",
    port: 4173,
    strictPort: true,
  },
});
