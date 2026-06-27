import react from "@vitejs/plugin-react";
import path from "path";
import { fileURLToPath } from "url";
import { readFileSync } from "fs";
import { defineConfig } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function loadBuildVersion() {
  try {
    const manifestPath = path.resolve(__dirname, "../app_version.manifest.json");
    const raw = JSON.parse(readFileSync(manifestPath, "utf-8"));
    return {
      __APP_VERSION__: JSON.stringify(raw.app_version || "A23.0.0"),
      __BUILD_LABEL__: JSON.stringify(raw.build_label || "hotfix-pack4"),
      __BUILD_DATE__: JSON.stringify(raw.build_date || ""),
      __BUILD_COMMIT__: JSON.stringify(raw.commit || ""),
    };
  } catch {
    return {
      __APP_VERSION__: JSON.stringify("A23.0.0"),
      __BUILD_LABEL__: JSON.stringify("hotfix-pack4"),
      __BUILD_DATE__: JSON.stringify(""),
      __BUILD_COMMIT__: JSON.stringify(""),
    };
  }
}

export default defineConfig({
  logLevel: "error",
  plugins: [react()],
  define: loadBuildVersion(),
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
