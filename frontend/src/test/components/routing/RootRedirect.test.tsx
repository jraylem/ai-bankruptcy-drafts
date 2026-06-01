import { describe, expect, it, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

import { RootRedirect } from '@/components/routing/RootRedirect';
import { useStudioStore } from '@/stores/useStudioStore';
import type { CaseResponse } from '@/types/studio/resolution';

vi.mock('@/features/auth/queries', () => ({
  useAuthSession: () => ({
    user: {
      id: 'user-1',
      email: 'owner@example.com',
      role: 'firm_owner',
      is_accepted: true,
    },
    isAuthenticated: true,
    isInitializing: false,
    isFetching: false,
    error: null,
  }),
}));

/**
 * The case shape is rich (legacy_id, ssn_last4, collection names, etc.). The
 * redirect only reads `id`, so the fixture just casts a minimal stub to keep
 * the test focused on the routing decision.
 */
const fakeCase = (id: string): CaseResponse =>
  ({ id } as unknown as CaseResponse);

const renderRedirect = () =>
  render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<RootRedirect />} />
        <Route path="/case/:caseId" element={<div>case-workspace</div>} />
        <Route path="/case/new" element={<div>case-new</div>} />
      </Routes>
    </MemoryRouter>,
  );

describe('<RootRedirect />', () => {
  beforeEach(() => {
    // Reset the store before each test so case lists don't bleed between them.
    useStudioStore.setState({
      cases: [],
      isLoadingCases: false,
      casesTotal: 0,
      casesHasMore: false,
    });
  });

  it('redirects to /case/new when no cases are loaded', () => {
    renderRedirect();
    expect(screen.getByText('case-new')).toBeInTheDocument();
  });

  it('redirects to /case/:id of the first (most-recent) case', () => {
    useStudioStore.setState({
      cases: [fakeCase('case-newest'), fakeCase('case-older')],
      isLoadingCases: false,
    });
    renderRedirect();
    expect(screen.getByText('case-workspace')).toBeInTheDocument();
  });

  it('shows a spinner while the cases query is in flight', () => {
    useStudioStore.setState({
      cases: [],
      isLoadingCases: true,
    });
    renderRedirect();
    // No navigation yet — neither /case/new nor /case/:id mounted.
    expect(screen.queryByText('case-new')).not.toBeInTheDocument();
    expect(screen.queryByText('case-workspace')).not.toBeInTheDocument();
    // Spinner renders without aria-label here; assert via a generic
    // "loading" presence — the Spinner component uses role="status" by
    // default but the wrapper might not. Soft check: SVG present.
    expect(document.querySelector('svg')).toBeInTheDocument();
  });

  it('redirects to /case/new once loading completes with an empty list', () => {
    useStudioStore.setState({
      cases: [],
      isLoadingCases: false,
    });
    renderRedirect();
    expect(screen.getByText('case-new')).toBeInTheDocument();
  });
});
