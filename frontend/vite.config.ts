import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";
import { resolve } from "path";
import { fileURLToPath, URL } from "url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));

// BUILD_TARGET=standalone produces a self-contained SPA (index.html + hashed
// assets in dist/) for the nginx container. The default build emits a manifest
// into static/vue for Django-template integration.
const standalone = process.env.BUILD_TARGET === "standalone";

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      "@": resolve(__dirname, "./src"),
    },
  },
  build: standalone
    ? {
        outDir: "dist",
        emptyOutDir: true,
      }
    : {
        outDir: "../static/vue",
        manifest: true,
        rollupOptions: {
          input: "./src/main.ts",
        },
      },
});