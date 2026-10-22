import { test, expect } from '@playwright/test';

test('chat modes, live events, metrics, history and reset', async ({page})=>{
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'Dashboard',exact:true})).toBeVisible();
  await page.getByRole('button',{name:/Chat/}).click();
  for(const mode of ['normal','rapido','automatico']){
    await page.locator('select').selectOption(mode);
    await page.getByLabel('Consulta',{exact:true}).fill('Multiplica 875 por 43');
    await page.getByRole('button',{name:'Enviar consulta'}).click();
    await expect(page.getByRole('status')).toContainText('Procesando');
    await expect(page.getByRole('button',{name:'Modelo ocupado'})).toBeDisabled();
    await expect(page.locator('.message').last()).toContainText('37625');
    await expect(page.getByRole('status')).toHaveCount(0);
  }
  await page.getByRole('button',{name:/Inspector/}).click();
  await expect(page.locator('.timeline')).toContainText('tool_started');
  await expect(page.locator('.timeline')).toContainText('tool_completed');
  await expect(page.locator('.timeline')).toContainText('finish_reason: tool_calls');
  await page.getByRole('button',{name:/Dashboard/}).click();
  await expect(page.locator('.metrics')).toContainText('20');
  await page.locator('.bar-column').last().click();
  await expect(page.getByRole('heading',{name:'Línea de tiempo'})).toBeVisible();
  await page.getByRole('button',{name:/Chat/}).click();
  await page.getByRole('button',{name:'Reiniciar conversación'}).click();
  await expect(page.locator('.message')).toHaveCount(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
});

test('failures, MCP lifecycle and benchmark export',async({page})=>{
  await page.goto('/');
  await page.getByRole('button',{name:/Chat/}).click();
  for(const query of ['vacia','truncada','timeout']){
    await page.getByLabel('Consulta',{exact:true}).fill(query);
    await page.getByRole('button',{name:'Enviar consulta'}).click();
    await expect(page.locator('.message').last()).toHaveClass(/failure/);
    await expect(page.getByRole('status')).toHaveCount(0);
  }
  await page.getByRole('button',{name:/MCP/}).click();
  await page.getByRole('button',{name:'Conectar',exact:true}).click();
  await expect(page.locator('.tool-grid')).toContainText('mcp_ws_leer_archivo');
  await page.getByRole('button',{name:'Desconectar',exact:true}).click();
  await expect(page.locator('.tool-grid')).not.toContainText('mcp_ws_leer_archivo');
  await page.getByRole('button',{name:/Benchmark/}).click();
  await page.getByRole('spinbutton').fill('1');
  await page.getByRole('button',{name:'Ejecutar comparación'}).click();
  await expect(page.getByRole('heading',{name:'Comparación finalizada'})).toBeVisible({timeout:15000});
  await expect(page.locator('table').first().locator('tbody tr')).toHaveCount(6);
  const download = page.waitForEvent('download');
  await page.getByRole('link',{name:'↓ CSV'}).click();
  expect((await download).suggestedFilename()).toBe('benchmark.csv');
  await page.screenshot({path:'test-results/lab-'+test.info().project.name+'.png',fullPage:true});
});

test('live inspector and reconnect after page reload',async({page})=>{
  await page.goto('/');
  await page.getByRole('button',{name:/Chat/}).click();
  await page.getByLabel('Consulta',{exact:true}).fill('Multiplica 875 por 43, consulta lenta');
  await page.getByRole('button',{name:'Enviar consulta'}).click();
  await page.getByRole('button',{name:/Inspector/}).click();
  await expect(page.locator('.timeline')).toContainText('hop_started');
  await expect(page.locator('.timeline')).not.toContainText('run_completed');
  await page.reload();
  await page.getByRole('button',{name:/Chat/}).click();
  await expect(page.locator('.message').last()).toContainText('37625');
  await expect(page.locator('.message')).toHaveCount(2);
});
