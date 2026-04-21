import { test, expect } from '@playwright/test';

// Runs after 02-empty-state.spec.ts — the empty-state spec wipes
// tbl_scan_instance, so /newscan still loads (it doesn't depend on
// scan data). This spec also kicks off a new scan, so the fixture
// DB gains one row afterwards; that's fine because Playwright's
// webServer reseeds per run.

test.describe('New scan form', () => {
  test('renders all three selection tabs after load', async ({ page }) => {
    await page.goto('/newscan');
    await expect(page.getByRole('heading', { name: 'New Scan' })).toBeVisible();
    await expect(page.getByRole('tab', { name: /By Use Case/ })).toBeVisible();
    await expect(page.getByRole('tab', { name: /By Required Data/ })).toBeVisible();
    await expect(page.getByRole('tab', { name: /By Module/ })).toBeVisible();
  });

  test('module filter narrows the visible list', async ({ page }) => {
    await page.goto('/newscan');
    await page.getByRole('tab', { name: /By Module/ }).click();
    await expect(page.getByText('sfp_countryname')).toBeVisible();
    await page.getByLabel('Filter modules').fill('country');
    await expect(page.getByText('sfp_countryname')).toBeVisible();
    await expect(page.getByText('sfp_dnsresolve')).not.toBeVisible();
  });

  test('submit kicks off a scan and redirects to scaninfo', async ({ page }) => {
    await page.goto('/newscan');
    await page.getByLabel(/Scan Name/).fill('playwright-newscan-smoke');
    await page.getByLabel(/Scan Target/).fill('spiderfoot.net');
    await page.getByRole('tab', { name: /By Module/ }).click();
    await page.getByLabel('Filter modules').fill('country');
    await page.getByRole('button', { name: 'De-Select All' }).click();
    await page.getByRole('checkbox', { name: 'Toggle sfp_countryname' }).check();

    await page.getByRole('button', { name: 'Run Scan Now' }).click();
    await page.waitForURL(/\/scaninfo\?id=.+/, { timeout: 30_000 });
  });
});
