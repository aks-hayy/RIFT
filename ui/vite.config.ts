import tailwindcss from "@tailwindcss/vite";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import tsconfigPaths from "vite-tsconfig-paths";

const controllerTarget = process.env.RIFT_CONTROL_API ?? "http://127.0.0.1:8777";

export default defineConfig({
  plugins: [tanstackStart(), react(), tailwindcss(), tsconfigPaths()],
  server: {
    proxy: {
      "/api/rift": {
        target: controllerTarget,
        changeOrigin: true,
      },
    },
  },
});
