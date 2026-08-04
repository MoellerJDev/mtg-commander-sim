import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const serverData = path.resolve(
  process.env.MTG_E2E_RUNTIME_DIR ??
    path.join("..", "local", `playwright-${process.pid}`),
);
// Do not borrow the documented manual-development ports. Browser cookies are
// host scoped rather than port scoped, and an open manual table may otherwise
// reconnect to Playwright's disposable server while the suite is running.
const serverPort = Number(process.env.MTG_E2E_SERVER_PORT ?? "18080");
const webPort = Number(process.env.MTG_E2E_WEB_PORT ?? "15173");
const pythonExecutable =
  process.env.MTG_PYTHON_EXECUTABLE ??
  (process.platform === "win32"
    ? path.resolve("..", ".venv", "Scripts", "python.exe")
    : "python");
if (pythonExecutable.includes('"')) {
  throw new Error("MTG_PYTHON_EXECUTABLE cannot contain a double quote");
}
const pythonCommand = `"${pythonExecutable}"`;

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: `http://127.0.0.1:${webPort}`,
    // E2E automation must never take over a contributor's system browser.
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      // The normal launcher opens the system browser for manual play. Tests
      // use Playwright's isolated headless browser and must suppress that side
      // effect explicitly.
      command: `${pythonCommand} -m server --host 127.0.0.1 --port ${serverPort} --no-open --no-build-browser`,
      cwd: "..",
      url: `http://127.0.0.1:${serverPort}/api/v1/health`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        ...process.env,
        MTG_CARD_DB: process.env.MTG_CARD_DB ?? "data/test-ci.sqlite3",
        MTG_SERVER_DATA: serverData,
        MTG_E2E_SERVER_PORT: String(serverPort),
        MTG_E2E_WEB_PORT: String(webPort),
      },
    },
    {
      command: `npm run dev -- --port ${webPort}`,
      url: `http://127.0.0.1:${webPort}`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        ...process.env,
        MTG_E2E_SERVER_PORT: String(serverPort),
        MTG_E2E_WEB_PORT: String(webPort),
      },
    },
  ],
});
