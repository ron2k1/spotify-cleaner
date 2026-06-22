import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// The built SPA lands inside the Python package so `python -m spotify_cleaner.web`
// can serve it as static files on the same origin as the OAuth callback.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  build: {
    outDir: "../src/spotify_cleaner/web/static",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    // In dev the UI runs here and proxies API + the OAuth callback to uvicorn.
    proxy: {
      "/api": { target: "http://127.0.0.1:8888", changeOrigin: true },
      "/callback": { target: "http://127.0.0.1:8888", changeOrigin: true },
    },
  },
});
