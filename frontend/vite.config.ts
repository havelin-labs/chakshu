import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// In development the API runs on :8000 (chakshu web); Vite proxies to it.
const api = process.env.CHAKSHU_API_URL ?? "http://localhost:8000"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    proxy: {
      "/api": api,
      "/healthz": api,
      "/readyz": api,
    },
  },
})
