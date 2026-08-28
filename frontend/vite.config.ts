import path from "node:path";
import preact from "@preact/preset-vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [preact()],
  root: __dirname,
  base: "/static/",
  build: {
    outDir: path.resolve(__dirname, "../ProjectResources/Frontend"),
    emptyOutDir: false,
    target: "es2022",
    cssCodeSplit: false,
    sourcemap: true,
    rollupOptions: {
      input: path.resolve(__dirname, "src/main.tsx"),
      output: {
        codeSplitting: false,
        entryFileNames: "app.js",
        assetFileNames: (info) =>
          info.name?.endsWith(".css") ? "styles.css" : "[name][extname]"
      }
    }
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8090",
      "/static": "http://127.0.0.1:8090",
      "/ws": {
        target: "ws://127.0.0.1:8090",
        ws: true
      }
    }
  }
});
