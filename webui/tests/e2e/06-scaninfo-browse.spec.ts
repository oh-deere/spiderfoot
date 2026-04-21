import { test, expect } from '@playwright/test';

// Runs after 05-scaninfo.spec.ts. Navigates from the scan list to
// the seeded "monthly-recon" FINISHED scan, then exercises Browse
// and Correlations tabs.

async function openFinishedScanInfo(
  page: import('@playwright/test').Page,
): Promise<void> {
  await page.goto('/');
  const anchor = page.getByRole('link', { name: 'monthly-recon' });
  await expect(anchor).toBeVisible();
  await anchor.click();
  await page.waitForURL(/\/scaninfo\?id=.+/, { timeout: 10_000 });
}

test.describe('Scan info page (M4b: Browse + Correlations)', () => {
  test('Browse tab renders the event-type heading or the empty-state', async ({ page }) => {
    await openFinishedScanInfo(page);
    await page.getByRole('tab', { name: 'Browse' }).click();

    // Scope to the Browse tabpanel because the StatusTab uses the same
    // "No events produced yet" alert when scansummary is empty.
    const browsePanel = page.getByRole('tabpanel', { name: 'Browse' });
    // Seeded scan has no events, so the BrowseTab may render the
    // "No events produced yet" empty-state alert instead of the heading.
    const heading = browsePanel.getByRole('heading', {
      name: 'Browse by event type',
    });
    const emptyAlert = browsePanel.getByText(/No events produced yet/);
    await expect(heading.or(emptyAlert)).toBeVisible();
  });

  test('Correlations tab renders either the heading or the empty-state', async ({ page }) => {
    await openFinishedScanInfo(page);
    await page.getByRole('tab', { name: 'Correlations' }).click();
    await expect(
      page.getByRole('heading', { name: 'Triggered correlations' }),
    ).toBeVisible();

    // Seeded scan likely has no correlations; either the empty-state alert
    // OR at least one Table row should be present.
    const emptyAlert = page.getByText(/No correlations triggered/);
    const anyRow = page.getByRole('row').nth(1);
    await expect(emptyAlert.or(anyRow)).toBeVisible();
  });
});
