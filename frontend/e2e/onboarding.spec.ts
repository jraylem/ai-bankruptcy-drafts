import { expect, test, type Page, type Route } from '@playwright/test';
import { seedAuth } from './helpers/auth';

const respondJson = (route: Route, body: unknown, status = 200): Promise<void> =>
  route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });

const stubDashboardBackgroundRequests = async (page: Page): Promise<void> => {
  await page.route('**/api/pleadings/**', (route) => respondJson(route, []));
  await page.route('**/api/reviews/**', (route) => respondJson(route, []));
  await page.route('**/api/threads**', (route) => respondJson(route, []));
  await page.route('**/api/v2/core/cases**', (route) =>
    respondJson(route, {
      cases: [],
      total: 0,
      limit: 20,
      offset: 0,
      has_more: false,
    })
  );
  await page.route('**/api/v2/core/pleading/tasks', (route) => respondJson(route, []));
  await page.route('**/api/v2/core/template', (route) => respondJson(route, []));
  await page.route('**/api/v2/core/pleading/events', (route) =>
    route.fulfill({ status: 200, contentType: 'text/event-stream', body: '' })
  );
  await page.route('**/api/events**', (route) =>
    route.fulfill({ status: 200, contentType: 'text/event-stream', body: '' })
  );
};

const gotoOnboarding = async (page: Page): Promise<void> => {
  await stubDashboardBackgroundRequests(page);
  let onboardingStatus: 'pending' | 'completed' = 'pending';
  await seedAuth(page, { onboardingStatus });
  await page.route('**/api/firms/onboarding-status', (route) =>
    respondJson(route, { onboarding_status: onboardingStatus })
  );
  await page.route('**/api/firms/me', async (route) => {
    if (route.request().method() === 'PATCH') {
      onboardingStatus = 'completed';
      await respondJson(route, {
        id: 'e2e-firm',
        name: 'CVH Law Group',
        owner_email: 'e2e@example.com',
        subscription_status: 'trialing',
        plan_id: null,
        seat_limit: 5,
        onboarding_status: onboardingStatus,
        is_active: true,
        created_at: new Date().toISOString(),
        address: 'firm@example.com',
        firm_type: 'bankruptcy',
        contact_number: null,
      });
      return;
    }

    await respondJson(route, {
      id: 'e2e-firm',
      name: '',
      owner_email: 'e2e@example.com',
      subscription_status: 'trialing',
      plan_id: null,
      seat_limit: 5,
      onboarding_status: onboardingStatus,
      is_active: true,
      created_at: new Date().toISOString(),
      address: '',
      firm_type: null,
      contact_number: null,
    });
  });
  await page.route('**/api/firms/invite', (route) =>
    respondJson(route, {
      id: 'e2e-invitation',
      email: JSON.parse(route.request().postData() || '{}').email,
      role: JSON.parse(route.request().postData() || '{}').role || 'member',
      expires_at: new Date(Date.now() + 48 * 60 * 60 * 1000).toISOString(),
    })
  );
  await page.goto('/onboarding', { waitUntil: 'domcontentloaded' });
  await expect(page).toHaveURL(/\/onboarding$/);
  await expect(page.getByRole('heading', { name: /Configure Legal Workspace/i })).toBeVisible();
};

const goToInvitesStep = async (page: Page): Promise<void> => {
  await page.getByRole('button', { name: /Next/i }).click();
  await expect(page.getByRole('heading', { name: /Invite Members/i })).toBeVisible();
};

const fillFirmDetails = async (page: Page): Promise<void> => {
  await page.getByPlaceholder('Enter law firm name').fill('CVH Law Group');
  await page.getByPlaceholder('name@firmdomain.com').fill('firm@example.com');
};

const goToReviewStep = async (page: Page): Promise<void> => {
  await page.getByRole('button', { name: /Next|Skip/i }).click();
  await expect(page.getByRole('heading', { name: /Review & Confirm/i })).toBeVisible();
};

const addInvite = async (
  page: Page,
  email: string,
  role: 'admin' | 'member' = 'member'
): Promise<void> => {
  await page.getByPlaceholder('name@example.com').fill(email);

  if (role === 'admin') {
    await page.getByRole('button', { name: /^Member$/i }).click();
    await page.getByRole('button', { name: /^Admin$/i }).click();
  }

  await page.getByRole('button', { name: /^Invite$/i }).click();
  await expect(page.getByText(email)).toBeVisible();
};

const confirmSetup = async (page: Page): Promise<void> => {
  await page
    .getByLabel(/I confirm these firm details are ready to use for this workspace/i)
    .check();
  await page.getByRole('button', { name: /Confirm setup/i }).click();
};

test.describe('Onboarding', () => {
  test('happy path: enters firm details, adds members with roles, and redirects', async ({
    page,
  }) => {
    await gotoOnboarding(page);

    await fillFirmDetails(page);
    await goToInvitesStep(page);
    await addInvite(page, 'admin@example.com', 'admin');
    await addInvite(page, 'member@example.com', 'member');
    await goToReviewStep(page);
    await expect(page.getByText('admin@example.com')).toBeVisible();
    await expect(page.getByText('member@example.com')).toBeVisible();
    await expect(page.getByText(/permissions/i)).toHaveCount(0);

    await confirmSetup(page);

    // Post-onboarding redirects to `/`, which RootRedirect resolves to
    // `/case/:latest-id` (when cases exist) or `/case/new` (empty BE).
    // In the e2e test environment there are no seeded cases, so we land
    // on `/case/new` — match either form for resilience.
    await expect(page).toHaveURL(/\/case(\/.*)?$/);
    await expect(page.getByText(/permissions/i)).toHaveCount(0);
  });

  test('happy path: works with no invited members', async ({ page }) => {
    await gotoOnboarding(page);

    await fillFirmDetails(page);
    await goToInvitesStep(page);
    await goToReviewStep(page);
    await confirmSetup(page);

    await expect(page).toHaveURL(/\/case(\/.*)?$/);
  });

  test('unhappy path: missing firm name blocks progress', async ({ page }) => {
    await gotoOnboarding(page);

    await page.getByPlaceholder('Enter law firm name').fill('');
    await page.getByRole('button', { name: /Next/i }).click();

    await expect(page.getByText('Enter your firm name')).toBeVisible();
    await expect(page).toHaveURL(/\/onboarding$/);
    await expect(page.getByRole('heading', { name: /Configure Legal Workspace/i })).toBeVisible();
  });

  test('unhappy path: invalid invite email shows validation error', async ({ page }) => {
    await gotoOnboarding(page);
    await fillFirmDetails(page);
    await goToInvitesStep(page);

    await page.getByPlaceholder('name@example.com').fill('not-an-email');
    await page.getByRole('button', { name: /^Invite$/i }).click();

    await expect(page.getByText('Enter a valid email')).toBeVisible();
  });

  test('unhappy path: duplicate invite email is clearly surfaced', async ({ page }) => {
    await gotoOnboarding(page);
    await fillFirmDetails(page);
    await goToInvitesStep(page);

    await addInvite(page, 'member@example.com');
    await page.getByPlaceholder('name@example.com').fill('member@example.com');
    await page.getByRole('button', { name: /^Invite$/i }).click();

    await expect(page.getByText('This member is already invited')).toBeVisible();
  });
});
