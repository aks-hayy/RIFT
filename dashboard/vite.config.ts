import tailwindcss from "@tailwindcss/vite";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";
import viteReact from "@vitejs/plugin-react";
import { nitro } from "nitro/vite";
import { defineConfig } from "vite";

const controlApi = process.env.RIFT_CONTROL_API ?? "http://127.0.0.1:8777";

export default defineConfig({
  resolve: {
    tsconfigPaths: true,
  },
  server: {
    proxy: {
      "/api/rift": {
        target: controlApi,
        changeOrigin: true,
      },
    },
  },
  plugins: [
    tailwindcss(),
    tanstackStart({ server: { entry: "server" } }),
    nitro({
      devProxy: {
        "/api/rift": { target: controlApi, changeOrigin: true },
      },
      routeRules: {
        "/api/rift/**": { proxy: `${controlApi}/api/rift/**` },
      },
    }),
    viteReact(),
  ],
});
