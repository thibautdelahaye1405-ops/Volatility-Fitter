// Vitest harness (commercial-MVP arc: the frontend finally has tests).
// Standalone config — the app's vite.config.ts carries the Tailwind plugin,
// which tests don't need (components import no CSS; index.css loads in
// main.tsx only). jsdom gives the component tests a DOM; JSX is transformed
// by esbuild's automatic runtime, so no React plugin is required.
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
