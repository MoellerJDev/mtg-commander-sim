import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiPort = Number(process.env.MTG_E2E_SERVER_PORT ?? "8000");
const webPort = Number(process.env.MTG_E2E_WEB_PORT ?? "5173");

export default defineConfig({
  plugins: [react()],
  server: {
    port: webPort,
    strictPort: true,
    open: false,
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${apiPort}`,
        changeOrigin: false,
        ws: true,
      },
    },
  },
});
