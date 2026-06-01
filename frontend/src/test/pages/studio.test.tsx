import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { useStudioStore } from '@/stores/useStudioStore';

vi.mock('@/services/studio.service', () => ({
  studioApi: new Proxy({}, { get: () => vi.fn().mockResolvedValue({ data: null }) }),
}));

vi.mock('lottie-react', () => ({
  default: () => null,
}));

vi.mock('@/components/chat/ChatSidebar', () => ({
  ChatSidebar: () => null,
}));

vi.mock('@/components/studio/TemplatePreview', () => ({
  TemplatePreview: () => null,
}));

import { StudioPage } from '@/pages/studio';

const baseStoreState = {
  selectedCaseId: null,
  selectedTemplateId: null,
  cases: [],
  templates: [],
  connectors: [],
  referenceData: [],
  templateSpec: [],
  agentConfig: null,
  dryRunResult: null,
  dryRunAwaiting: null,
  draftResult: null,
  draftAwaiting: null,
  flowState: 'new' as const,
  isDirty: false,
  actionError: null,
  error: null,
  templateDocUrl: null,
  originalDocUrl: null,
};

const renderRoute = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/studio" element={<StudioPage />} />
        <Route path="/studio/template/:templateId" element={<StudioPage />} />
      </Routes>
    </MemoryRouter>,
  );

beforeEach(() => {
  useStudioStore.setState(baseStoreState);
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});
afterEach(() => useStudioStore.setState(baseStoreState));

describe('<StudioPage /> smoke', () => {
  it('renders without crashing on /studio with empty state', () => {
    const { container } = renderRoute('/studio');
    expect(container.firstChild).not.toBeNull();
  });

  it('renders the page chrome (no template selected) without throwing', () => {
    renderRoute('/studio');
    const matches = screen.queryAllByText(/Studio|Upload|Template/i);
    expect(matches.length).toBeGreaterThan(0);
  });

  it('shows the verified flow-state pill when flowState=verified', () => {
    useStudioStore.setState({
      selectedTemplateId: 't1',
      templateSpec: [
        {
          template_variable: 'foo',
          template_index: 0,
          source: 'case_vector',
          source_params: null,
          template_property_marker: null,
          template_variable_string: null,
          template_identifying_text_match: null,
          description: null,
          instruction: null,
        },
      ],
      flowState: 'verified',
    });
    renderRoute('/studio/template/t1');
    expect(screen.getByText(/Verified/i)).toBeInTheDocument();
  });
});
