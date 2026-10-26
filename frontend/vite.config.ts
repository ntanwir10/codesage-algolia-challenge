/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    // Fail instead of moving to 5174, which the example CORS_ORIGINS doesn't allow
    strictPort: true,
    proxy: {
      "/api": { target: "http://127.0.0.1:8001", changeOrigin: true },
      "/ws": { target: "ws://127.0.0.1:8001", ws: true, changeOrigin: true },
      "/health": { target: "http://127.0.0.1:8001", changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
