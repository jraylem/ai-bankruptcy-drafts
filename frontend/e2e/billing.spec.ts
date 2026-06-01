import { expect, test } from '@playwright/test';
import { gotoAuthed, seedAuth } from './helpers/auth';
import { stubBackend } from './helpers/api';

// TODO: Re-enable once backend billing/Stripe flow can move the UI beyond Free Tier.
test.describe.skip('Billing — authenticated', () => {
  test.beforeEach(async ({ page }) => {
    await stubBackend(page);
    await seedAuth(page);
  });

  test('opens /billing and shows the pay-as-you-go billing page', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));

    await gotoAuthed(page, '/billing');

    await expect(page).toHaveURL(/\/billing$/);
    await expect(page.getByRole('heading', { name: 'Billing', exact: true })).toBeVisible();
    await expect(page.getByText('Pay as you go')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Chat' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Ingestion' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'AGT Composition' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Pleading Generation' })).toBeVisible();
    await expect(page.getByText('Visa ending in 4242')).toBeVisible();
    await expect(page.getByText('INV-2026-004')).toBeVisible();
    await expect(page.getByText('$312.84').first()).toBeVisible();
    expect(errors).toEqual([]);
  });

  test('account menu Billing item navigates to /billing', async ({ page }) => {
    await gotoAuthed(page, '/');

    await page.getByText('e2e@example.com').click();
    await page.getByRole('button', { name: /^Billing$/ }).click();

    await expect(page).toHaveURL(/\/billing$/);
    await expect(page.getByText('Pay as you go')).toBeVisible();
  });
});
