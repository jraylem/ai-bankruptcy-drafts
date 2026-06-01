import type { Page, Route } from '@playwright/test';

interface FixtureOverrides {
  cases?: unknown[];
  templates?: unknown[];
  connectors?: unknown[];
  referenceData?: unknown[];
}

const respondJson = (route: Route, body: unknown, status = 200): Promise<void> =>
  route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });

export const stubBackend = async (
  page: Page,
  overrides: FixtureOverrides = {},
): Promise<void> => {
  const cases = overrides.cases ?? [];
  const templates = overrides.templates ?? [];
  const connectors = overrides.connectors ?? [];
  const referenceData = overrides.referenceData ?? [];

  // Playwright evaluates page.route() handlers in REVERSE registration
  // order — the most recently registered route wins. Register the
  // generic catch-all FIRST so the specific handlers below override
  // it for their particular paths.
  await page.route(/^https?:\/\/[^/]+\/api\//, (route) => {
    if (route.request().url().includes('/api/auth/')) {
      return route.fallback();
    }
    if (route.request().resourceType() === 'eventsource') {
      return route.fulfill({ status: 200, contentType: 'text/event-stream', body: '' });
    }
    return respondJson(route, []);
  });

  // Specific GET /cases?limit=...&offset=... — paginated list shape.
  // useStudioStore.loadCases reads `result.data.cases`, so we must
  // return the wrapped shape, not the raw array.
  await page.route(/\/api\/v2\/core\/cases(\?.*)?$/, (route) => {
    if (route.request().method() === 'GET') {
      return respondJson(route, {
        cases,
        total: cases.length,
        limit: 20,
        offset: 0,
        has_more: false,
      });
    }
    // POST → case-create
    return respondJson(route, { case: cases[0] ?? null }, 201);
  });

  await page.route(/\/api\/v2\/core\/cases\/[^?]+$/, (route) =>
    respondJson(route, cases[0] ?? null),
  );

  // Wildcards registered FIRST so the specific paths below override them
  // (Playwright evaluates handlers in reverse registration order — last
  // registered wins).
  await page.route('**/api/v2/core/template/*', (route) => respondJson(route, templates[0] ?? null));
  await page.route('**/api/v2/core/template', (route) => respondJson(route, templates));
  await page.route('**/api/v2/core/template/connectors', (route) =>
    respondJson(route, connectors),
  );
  await page.route('**/api/v2/core/template/reference-data*', (route) =>
    respondJson(route, referenceData),
  );

  await page.route('**/api/v2/core/draft', (route) =>
    respondJson(route, { status: 'completed', resolved_values: [] }),
  );
  await page.route('**/api/v2/core/draft/resume', (route) =>
    respondJson(route, { status: 'completed', resolved_values: [] }),
  );
  await page.route('**/api/v2/core/template/dry-run', (route) =>
    respondJson(route, { status: 'completed', resolved_values: [], can_generate: true }),
  );
  await page.route('**/api/v2/core/template/dry-run/resume', (route) =>
    respondJson(route, { status: 'completed', resolved_values: [], can_generate: true }),
  );

  await page.route('**/api/auth/**', (route) => {
    if (route.request().url().includes('/api/auth/me')) {
      return route.fallback();
    }
    return respondJson(route, { ok: true });
  });
  await page.route('**/api/billing/subscription', (route) =>
    respondJson(route, {
      current_period_end: '2026-06-01T00:00:00+00:00',
      firm_id: 'firm-e2e',
      status: 'active',
      stripe_subscription_id: 'sub_e2e',
    }),
  );
  await page.route('**/api/sessions/**', (route) => respondJson(route, []));
  await page.route('**/api/events/**', (route) =>
    route.fulfill({ status: 200, contentType: 'text/event-stream', body: '' }),
  );
};
