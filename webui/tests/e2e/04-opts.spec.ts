import { test, expect } from '@playwright/test';

// Runs after 03-new-scan.spec.ts. The empty-state spec (02) wipes
// tbl_scan_instance, the new-scan spec (03) re-adds one scan row.
// /opts doesn't depend on scan data so ordering doesn't affect this
// file, but we keep the numeric prefix convention for consistency.

test.describe('Settings page', () => {
  test('renders Global tab and filters modules', async ({ page }) => {
    await page.goto('/opts');
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
    await expect(page.getByRole('button', { name: /Save Changes/ })).toBeVisible();

    // Filter the left rail to narrow modules. NavLink labels use each
    // module's human-readable meta.name; the filter also matches the
    // `module.sfp_*` key, so 'country' keeps sfp_countryname ("Country
    // Name Extractor") visible.
    const filter = page.getByLabel('Filter settings groups');
    await filter.fill('country');
    await expect(page.getByText('Country Name Extractor')).toBeVisible();
  });

  test('reset to factory default triggers confirm modal', async ({ page }) => {
    await page.goto('/opts');
    // Open actions menu
    await page.getByRole('button', { name: 'Settings actions' }).click();
    await page.getByRole('menuitem', { name: /Reset to Factory Default/ }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(
      page.getByText(/This wipes every API key/),
    ).toBeVisible();
    // Cancel — don't actually reset the fixture DB.
    await page.getByRole('button', { name: 'Cancel' }).click();
    await expect(page.getByRole('dialog')).not.toBeVisible();
  });
});
