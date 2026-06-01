import type { Page } from '@playwright/test';

const futureExp = (): number => Math.floor(Date.now() / 1000) + 60 * 60 * 24;

const base64UrlEncode = (obj: object): string =>
  Buffer.from(JSON.stringify(obj))
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');

const fakeJwt = (): string => {
  const header = base64UrlEncode({ alg: 'HS256', typ: 'JWT' });
  const payload = base64UrlEncode({
    sub: 'e2e-user',
    email: 'e2e@example.com',
    firm_id: 'e2e-firm',
    exp: futureExp(),
    iat: Math.floor(Date.now() / 1000),
  });
  return `${header}.${payload}.signature-not-verified-locally`;
};

interface SeedAuthOptions {
  firmId?: string | null;
  onboardingStatus?: 'pending' | 'completed';
}

const fakeUser = ({
  firmId = 'e2e-firm',
  onboardingStatus = 'completed',
}: SeedAuthOptions = {}): object => ({
  id: 'e2e-user',
  email: 'e2e@example.com',
  first_name: 'E2E',
  firm_id: firmId,
  last_name: 'User',
  onboarding_status: onboardingStatus,
  role: 'firm_owner',
});

export const seedAuth = async (page: Page, options: SeedAuthOptions = {}): Promise<void> => {
  const token = fakeJwt();
  const user = fakeUser(options);
  await page.route('**/api/auth/me', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(user),
    }),
  );
  await page.addInitScript(
    ({ token, user }) => {
      localStorage.setItem('auth_token', JSON.stringify(token));
      localStorage.setItem('user', JSON.stringify(user));
    },
    { token, user },
  );
};

/**
 * Navigate to a path and wait for the auth-init bounce to settle. Without this,
 * a deep link to `/studio` can briefly reroute to `/login` (DashboardLayout
 * redirects unauthenticated users) and then back into the protected layout
 * (AuthLayout redirects authenticated users away from auth pages), settling
 * on the wrong URL. We work around it by visiting `/` first so `initialize()`
 * runs and `isAuthenticated` is true before the test's target navigation.
 *
 * `/` resolves via RootRedirect to `/case/:latest-id` (cases exist) or
 * `/case/new` (empty BE) — either is a valid settled state. We wait for
 * the `/case/*` URL family before continuing.
 */
export const gotoAuthed = async (page: Page, path: string): Promise<void> => {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.waitForURL(/\/case(\/.*)?$/, { timeout: 10_000 });
  if (path !== '/' && !/\/case(\/.*)?$/.test(path)) {
    await page.goto(path, { waitUntil: 'domcontentloaded' });
  }
};
