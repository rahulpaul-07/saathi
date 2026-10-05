// @ts-check
import { defineConfig } from "@playwright/test";

const PORT = 8765; // keep in sync with tests/e2e/serve.py

export default defineConfig({
  testDir: "tests/e2e",
  testMatch: "*.spec.js",
  workers: 1,
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    launchOptions: {
      // Fake microphone: Chromium feeds a test tone and auto-accepts the permission prompt.
      args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
    },
  },
  webServer: {
    command: "uv run --no-sync python tests/e2e/serve.py",
    url: `http://127.0.0.1:${PORT}/`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
