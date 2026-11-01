import { defineConfig, devices } from "@playwright/test";
import os from "node:os";
import path from "node:path";

// An isolated stack on its own ports with its own database, and no Algolia, GitHub or API keys,
// so a run never reaches the dev servers (8001, 5173), backend/.env's services or codesage.db
const BACKEND = "http://127.0.0.1:8011";
const FRONTEND = "http://localhost:5183";
const DATABASE = `sqlite:///${path.join(os.tmpdir(), "codesage-e2e.db")}`;
const PYTHON = process.env.E2E_PYTHON ?? "../.venv/bin/python";

export default defineConfig({
  testDir: "e2e",
  testMatch: "**/*.e2e.ts",
  workers: 1, // one shared, seeded database
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? "github" : "list",
  use: { baseURL: FRONTEND, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `${PYTHON} ../frontend/e2e/seed.py && ${PYTHON} -m uvicorn app.main:app --host 127.0.0.1 --port 8011`,
      cwd: "../backend",
      url: `${BACKEND}/health`,
      reuseExistingServer: false,
      // Empty values override backend/.env, which pydantic-settings would read otherwise
      env: {
        PYTHONPATH: ".",
        DATABASE_URL: DATABASE,
        ALGOLIA_APP_ID: "",
        ALGOLIA_ADMIN_API_KEY: "",
        CODESAGE_API_KEY: "",
        GITHUB_TOKEN: "",
        MCP_SERVER_HOST: "127.0.0.1",
        CORS_ORIGINS: FRONTEND,
        ALLOWED_HOSTS: "",
      },
    },
    {
      command: "npx vite --port 5183 --strictPort",
      url: FRONTEND,
      reuseExistingServer: false,
      // Process env beats frontend/.env, so the bundle goes through this proxy without a key
      env: { CODESAGE_BACKEND_URL: BACKEND, VITE_API_BASE_URL: "/api/v1", VITE_CODESAGE_API_KEY: "" },
    },
  ],
});
