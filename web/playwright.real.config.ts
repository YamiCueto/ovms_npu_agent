import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir:'./e2e',testMatch:'real.spec.ts',workers:1,timeout:600000,
  use:{baseURL:'http://127.0.0.1:8080',channel:'chrome',viewport:{width:1440,height:1000},trace:'retain-on-failure'},
  webServer:{command:'..\\.venv\\Scripts\\python.exe -m uvicorn agent.api.app:app --app-dir .. --host 127.0.0.1 --port 8080',url:'http://127.0.0.1:8080/api/runs',reuseExistingServer:false,timeout:20000}
});
