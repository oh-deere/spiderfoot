import { test, expect } from '@playwright/test';

async function openFinishedScanInfo(
  page: import('@playwright/test').Page,
): Promise<void> {
  await page.goto('/');
  const anchor = page.getByRole('link', { name: 'monthly-recon' });
  await expect(anchor).toBeVisible();
  await anchor.click();
  await page.waitForURL(/\/scaninfo\?id=.+/, { timeout: 10_000 });
}

test.describe('Scan info page (M4c: Graph tab)', () => {
  test('Graph tab renders either the empty-state alert or the layout controls', async ({ page }) => {
    await openFinishedScanInfo(page);
    await page.getByRole('tab', { name: 'Graph' }).click();

    // Seeded "monthly-recon" scan has no events -> expect the empty-state
    // Alert. If a future fixture seed adds events, the Force radio should
    // appear instead. Accept both.
    const emptyAlert = page.getByText(/This scan produced no events yet/);
    const forceRadio = page.getByRole('radio', { name: 'Force' });
    await expect(emptyAlert.or(forceRadio)).toBeVisible();
  });
});
