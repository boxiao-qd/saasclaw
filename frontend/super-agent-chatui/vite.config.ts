import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig({
  base: "/bx",
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 3000,
    proxy: {
      "/bx/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on("proxyReq", (_proxyReq, _req, res) => {
            // Disable TCP Nagle algorithm so SSE events flush immediately.
            // Without this, small SSE chunks (keepalives, deltas) are buffered
            // by the OS and never reach the browser during dev.
            const socket = (res as unknown as { socket?: { setNoDelay?: (v: boolean) => void } }).socket;
            socket?.setNoDelay?.(true);
          });
        },
      },
    },
  },
});