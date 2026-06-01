import { expect, test } from '@playwright/test';
import { gotoAuthed, seedAuth } from './helpers/auth';
import { stubBackend } from './helpers/api';

test.describe('Studio — unauthenticated', () => {
  test('lands on either /login or /studio without throwing', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await stubBackend(page);
    await page.goto('/studio', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('#root')).toBeAttached();
    expect(errors).toEqual([]);
  });
});

test.describe('Studio — authenticated, empty BE state', () => {
  test.beforeEach(async ({ page }) => {
    await seedAuth(page);
    await stubBackend(page);
  });

  test('reaches /studio without uncaught errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await gotoAuthed(page, '/studio');
    await expect(page).toHaveURL(/\/studio$/);
    await expect(page.locator('#root')).toBeAttached();
    expect(errors).toEqual([]);
  });

  test('opens the upload-template modal when the trigger is present', async ({ page }) => {
    await gotoAuthed(page, '/studio');
    const trigger = page
      .getByRole('button', { name: /upload|new template/i })
      .first();
    if (await trigger.isVisible().catch(() => false)) {
      await trigger.click();
      // Target the modal-specific heading (h2) — there's also a dropzone
      // h3 with the same text that's always visible.
      const modalHeading = page.getByRole('heading', {
        name: /Upload Legal Document/i,
        level: 2,
      });
      await expect(modalHeading).toBeVisible();
      const close = page.getByRole('button', { name: /Close/i }).first();
      await close.click();
      await expect(modalHeading).toBeHidden();
    }
  });
});

test.describe('Studio — authenticated, with seeded template', () => {
  const seededTemplate = {
    id: 'tpl-seed',
    name: 'Seeded Template',
    original_doc_url: null,
    template_doc_url: null,
    template_spec: [
      {
        template_variable: 'debtor_name',
        template_index: 0,
        source: 'case_vector',
        source_params: null,
        template_property_marker: '[[debtor_name]]',
        template_variable_string: '{{debtor_name}}',
        template_identifying_text_match: null,
        description: 'Debtor full legal name',
        instruction: null,
      },
    ],
    agent_config: null,
    created_at: new Date().toISOString(),
    is_active: true,
  };

  test.beforeEach(async ({ page }) => {
    await seedAuth(page);
    await stubBackend(page, { templates: [seededTemplate] });
  });

  test('routes to /studio/template/:id without uncaught errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await gotoAuthed(page, `/studio/template/${seededTemplate.id}`);
    await expect(page).toHaveURL(new RegExp(`/studio/template/${seededTemplate.id}$`));
    await expect(page.locator('#root')).toBeAttached();
    expect(errors).toEqual([]);
  });
});
