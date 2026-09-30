import path from "node:path";
import preact from "@preact/preset-vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [preact()],
  root: import.meta.dirname,
  base: "/static/",
  // Dependencies may be shared by worktrees; caches must remain checkout-local.
  cacheDir: path.resolve(import.meta.dirname, ".vite"),
  build: {
    outDir: path.resolve(import.meta.dirname, "../moss_transcribe_diarize/app/frontend_assets"),
    emptyOutDir: true,
    target: "es2022",
    // Browsers that take unprefixed backdrop-filter; the es2022-derived CSS target kept only the -webkit- form,
    // which Chrome ignores (no glass on the floating transcript tools).
    cssTarget: ["chrome111", "edge111", "firefox115", "safari18"],
    cssCodeSplit: false,
    sourcemap: true,
    rolldownOptions: {
      input: path.resolve(import.meta.dirname, "src/main.tsx"),
      output: {
        // Map identities belong to the frontend, not the checkout or a symlink target.
        sourcemapPathTransform: (sourcePath, sourcemapPath) => {
          const source = path.resolve(path.dirname(sourcemapPath), sourcePath);
          const portable = source.split(path.sep).join("/");
          const dependency = portable.indexOf("/node_modules/");
          return dependency >= 0
            ? portable.slice(dependency + 1)
            : path.relative(import.meta.dirname, source).split(path.sep).join("/");
        },
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
