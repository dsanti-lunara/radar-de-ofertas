import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/**
 * Control Center build (RDR-056, AUT-391, AUT-401).
 *
 * The compiled assets are served locally by `radar-api` from the same origin,
 * so the UI uses relative REST URLs and no CORS surface is opened (AUT-393).
 */
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    host: "127.0.0.1",
    proxy: {
      "/health": "http://127.0.0.1:8000",
      "/review": "http://127.0.0.1:8000",
      "/publications": "http://127.0.0.1:8000",
      "/opportunities": "http://127.0.0.1:8000",
      "/human-actions": "http://127.0.0.1:8000",
      "/integrations": "http://127.0.0.1:8000",
      "/operations": "http://127.0.0.1:8000",
      "/jobs": "http://127.0.0.1:8000",
      "/settings": "http://127.0.0.1:8000",
    },
  },
});
