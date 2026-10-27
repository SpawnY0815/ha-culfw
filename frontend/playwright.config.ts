import { defineConfig, devices } from "@playwright/test";

// The tests load the checked in bundle, so run `npm run build` first when the
// sources changed. scripts/build_frontend.sh checks that the bundle is current.
export default defineConfig({
  testDir: "test/e2e",
  outputDir: "test-results",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [["list"]],
  use: {
    locale: "en-US",
    timezoneId: "UTC",
    colorScheme: "light",
    trace: "off",
  },
  projects: [
    {
      name: "desktop",
      testMatch: /.*\.spec\.ts/,
      testIgnore: /.*\.touch\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 1100, height: 900 } },
    },
    {
      name: "phone",
      testMatch: /.*\.touch\.spec\.ts/,
      use: { ...devices["Pixel 7"] },
    },
  ],
});
