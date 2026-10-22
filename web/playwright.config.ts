import { defineConfig, devices } from '@playwright/test';
export default defineConfig({
  testDir:'./e2e', testMatch:'lab.spec.ts', fullyParallel:false, workers:1, timeout:30000,
  use:{baseURL:'http://127.0.0.1:8080', channel:'chrome', trace:'retain-on-failure'},
  projects:[{name:'desktop',use:{...devices['Desktop Chrome']}},{name:'mobile',use:{...devices['Pixel 7'],defaultBrowserType:'chromium'}}],
  webServer:{command:'..\\.venv\\Scripts\\python.exe -m uvicorn tests.web_fixture:app --app-dir .. --host 127.0.0.1 --port 8080', url:'http://127.0.0.1:8080/api/runs',reuseExistingServer:false,timeout:20000}
});
