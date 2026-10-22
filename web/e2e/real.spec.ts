import { test, expect } from '@playwright/test';
import fs from 'node:fs';
test('real OVMS: three modes, tools, SSE and dashboard',async({page,request})=>{
  const status=await (await request.get('/api/status')).json();
  test.skip(!status.connected||!status.model_available,'OVMS/model not available');
  await page.goto('/');
  await page.getByRole('button',{name:/Chat/}).click();
  for(const mode of ['normal','rapido','automatico']){
    await page.getByRole('button',{name:'Reiniciar conversación'}).click();
    await page.locator('select').selectOption(mode);
    await page.getByLabel('Consulta',{exact:true}).fill('Multiplica 875 por 43 usando multiplicar.');
    await page.getByRole('button',{name:'Enviar consulta'}).click();
    await expect(page.getByRole('status')).toContainText('Procesando');
    await expect(page.getByRole('status')).toHaveCount(0,{timeout:220000});
    await expect(page.locator('.message').last()).toContainText(/37[.,]?625/);
    await page.getByRole('button',{name:/Inspector/}).click();
    await expect(page.locator('.timeline')).toContainText('tool_completed');
    await expect(page.locator('.timeline')).toContainText('run_completed');
    await page.getByRole('button',{name:/Chat/}).click();
  }
  await page.getByRole('button',{name:/Dashboard/}).click();
  await expect(page.locator('.bar-column')).toHaveCount(3);
  await page.screenshot({path:'test-results/real-dashboard.png',fullPage:true});
  const traces=await (await request.get('/api/runs')).json();
  fs.writeFileSync('test-results/real-traces.json',JSON.stringify({status,traces},null,2));
});
