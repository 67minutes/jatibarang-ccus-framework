import { defineConfig, devices } from "@playwright/test";

/**
 * Smoke test config. Drives the app served by the running FastAPI backend
 * (which mounts the built SPA at /). Start the backend on :8000 before running:
 *   uvicorn jatibarang_ccus.api.app:app --app-dir src --port 8000
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:8000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
