import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [svelte()],
  clearScreen: false,
  server: { port: 1420, strictPort: true },
  build: { target: "es2022", outDir: "dist", emptyOutDir: true },
  // theme.css читает тест контраста палитры: без этого Vitest отдаёт CSS пустым.
  test: { environment: "node", include: ["src/**/*.test.ts"], css: { include: [/theme\.css/] } },
});
