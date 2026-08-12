import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // The backend runs on 8000 in dev; the frontend calls /api/* relatively so
    // the same code works in production behind a single origin.
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    // Off deliberately: @tailwindcss/vite does not emit a sourcemap for its
    // transform, which makes rolldown warn on every build and would fail CI
    // on a warning that means nothing.
    sourcemap: false,
  },
});
