import { test, expect } from '@playwright/test';

test.describe('Scan list', () => {
  test('renders all seeded scans with correct statuses', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Scans' })).toBeVisible();

    await expect(page.getByText('monthly-recon')).toBeVisible();
    await expect(page.getByText('ongoing-1')).toBeVisible();
    await expect(page.getByText('failed-1')).toBeVisible();
    await expect(page.getByText('finished-2')).toBeVisible();
    await expect(page.getByText('finished-3')).toBeVisible();

    // Status column cells: one per row, so three rows carry "FINISHED".
    const finishedBadges = page.getByRole('cell', { name: 'FINISHED', exact: true });
    await expect(finishedBadges).toHaveCount(3);
  });

  test('filter narrows to finished scans only', async ({ page }) => {
    await page.goto('/');
    await page.getByText('Finished', { exact: true }).click();

    await expect(page.getByText('monthly-recon')).toBeVisible();
    await expect(page.getByText('finished-2')).toBeVisible();
    await expect(page.getByText('finished-3')).toBeVisible();
    await expect(page.getByText('ongoing-1')).not.toBeVisible();
    await expect(page.getByText('failed-1')).not.toBeVisible();
  });

  test('delete flow removes a scan after confirmation', async ({ page }) => {
    await page.goto('/');
    const rowName = 'failed-1';
    const rowLink = page.getByRole('link', { name: rowName });
    await expect(rowLink).toBeVisible();

    await page
      .getByRole('button', { name: new RegExp(`Actions for ${rowName}`) })
      .click();
    await page.getByRole('menuitem', { name: 'Delete' }).click();

    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: 'Delete' }).click();

    // Wait for the modal to close before asserting the row is gone (otherwise
    // the <strong>failed-1</strong> inside the dialog creates a strict-mode
    // ambiguity with the row's anchor).
    await expect(dialog).not.toBeVisible();
    await expect(rowLink).not.toBeVisible();
  });
});
