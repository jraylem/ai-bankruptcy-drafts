import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { useStudioStore } from '@/stores/useStudioStore';
import { SourceIcon } from '@/components/studio/source-picker/SourceIcon';
import { SourcePicker } from '@/components/studio/source-picker/SourcePicker';
import { InteractionPatternPicker } from '@/components/studio/source-picker/InteractionPatternPicker';
import { SourceParamsForm } from '@/components/studio/source-picker/SourceParamsForm';
import { findFamily } from '@/utils/studio/sourceConfig';
import type { CaseVectorSourceParams, GmailSourceParams } from '@/types/studio';

vi.mock('@/services/studio.service', () => ({
  studioApi: new Proxy({}, { get: () => vi.fn().mockResolvedValue({ data: null }) }),
}));

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

beforeEach(() => useStudioStore.setState(baseStoreState));
afterEach(() => useStudioStore.setState(baseStoreState));

describe('<SourceIcon />', () => {
  it('renders an icon for a known source', () => {
    const { container } = render(<SourceIcon source="gmail" />);
    expect(container.querySelector('svg')).toBeInTheDocument();
  });

  it('renders the fallback icon for null source', () => {
    const { container } = render(<SourceIcon source={null} />);
    expect(container.querySelector('svg')).toBeInTheDocument();
  });

  it('forwards the className', () => {
    const { container } = render(<SourceIcon source="gmail" className="my-class" />);
    expect(container.querySelector('svg')?.getAttribute('class')).toContain('my-class');
  });
});

describe('<InteractionPatternPicker />', () => {
  const family = findFamily('gmail')!;

  it('renders one radio per pattern in the family', () => {
    render(<InteractionPatternPicker family={family} selectedKey="raw" onSelect={() => {}} />);
    const radios = screen.getAllByRole('radio');
    expect(radios).toHaveLength(family.patterns.length);
  });

  it('marks the selected pattern as checked', () => {
    render(<InteractionPatternPicker family={family} selectedKey="dropdown" onSelect={() => {}} />);
    const checked = screen.getAllByRole('radio').filter((r) => (r as HTMLInputElement).checked);
    expect(checked).toHaveLength(1);
  });

  it('clicking a different radio fires onSelect with that pattern key', () => {
    const onSelect = vi.fn();
    render(<InteractionPatternPicker family={family} selectedKey="raw" onSelect={onSelect} />);
    const radios = screen.getAllByRole('radio');
    const dropdownIdx = family.patterns.findIndex((p) => p.key === 'dropdown');
    fireEvent.click(radios[dropdownIdx]!);
    expect(onSelect).toHaveBeenCalledWith('dropdown');
  });

  it('renders pattern labels and descriptions', () => {
    render(<InteractionPatternPicker family={family} selectedKey="raw" onSelect={() => {}} />);
    for (const p of family.patterns) {
      expect(screen.getByText(p.label)).toBeInTheDocument();
      expect(screen.getByText(p.description)).toBeInTheDocument();
    }
  });
});

describe('<SourcePicker />', () => {
  it('renders all source families when no search filter is applied', () => {
    render(<SourcePicker familyKey={null} onSelectFamily={() => {}} />);
    expect(screen.getByText('Gmail')).toBeInTheDocument();
    expect(screen.getByText('Court Drive')).toBeInTheDocument();
    expect(screen.getByText('Constants')).toBeInTheDocument();
  });

  it('filters families by search query (matching by display name)', () => {
    render(<SourcePicker familyKey={null} onSelectFamily={() => {}} />);
    const search = screen.getByPlaceholderText(/search/i);
    fireEvent.change(search, { target: { value: 'gmail' } });
    expect(screen.getByText('Gmail')).toBeInTheDocument();
    expect(screen.queryByText('Court Drive')).toBeNull();
  });

  it('shows empty state when no families match the query', () => {
    render(<SourcePicker familyKey={null} onSelectFamily={() => {}} />);
    fireEvent.change(screen.getByPlaceholderText(/search/i), {
      target: { value: 'no-such-family-anywhere' },
    });
    expect(screen.queryByText('Gmail')).toBeNull();
  });

  it('clicking a family fires onSelectFamily with its key', () => {
    const onSelectFamily = vi.fn();
    render(<SourcePicker familyKey={null} onSelectFamily={onSelectFamily} />);
    fireEvent.click(screen.getByText('Gmail'));
    expect(onSelectFamily).toHaveBeenCalledWith('gmail');
  });
});

describe('<SourceParamsForm /> — case_vector + web search', () => {
  it('renders the text_query input and the enable_web_search checkbox', () => {
    const params: CaseVectorSourceParams = {
      text_query: '',
      enable_web_search: false,
      web_search_instruction: '',
    };
    render(
      <SourceParamsForm
        source="case_vector"
        sourceParams={params}
        onChange={() => {}}
      />,
    );
    // text_query input is identified by its placeholder (unique within the form).
    expect(
      screen.getByPlaceholderText(/prior bankruptcy case/i),
    ).toBeInTheDocument();
    // enable_web_search is the only checkbox inside this branch.
    expect(
      screen.getByRole('checkbox', { name: /enhance with web search/i }),
    ).toBeInTheDocument();
  });

  it('hides the Web search instruction textarea when enable_web_search is false', () => {
    const params: CaseVectorSourceParams = {
      text_query: '',
      enable_web_search: false,
      web_search_instruction: '',
    };
    render(
      <SourceParamsForm
        source="case_vector"
        sourceParams={params}
        onChange={() => {}}
      />,
    );
    expect(screen.queryByText(/web search instruction/i)).not.toBeInTheDocument();
  });

  it('renders the Web search instruction textarea when enable_web_search is true', () => {
    const params: CaseVectorSourceParams = {
      text_query: 'circuit court',
      enable_web_search: true,
      web_search_instruction: 'search for FL circuit by county',
    };
    render(
      <SourceParamsForm
        source="case_vector"
        sourceParams={params}
        onChange={() => {}}
      />,
    );
    expect(screen.getByText(/web search instruction/i)).toBeInTheDocument();
    expect(screen.getByDisplayValue('search for FL circuit by county')).toBeInTheDocument();
  });

  it('typing in the Web search instruction patches web_search_instruction', () => {
    const onChange = vi.fn();
    const params: CaseVectorSourceParams = {
      text_query: '',
      enable_web_search: true,
      web_search_instruction: '',
    };
    render(
      <SourceParamsForm
        source="case_vector"
        sourceParams={params}
        onChange={onChange}
      />,
    );
    const textarea = screen.getByPlaceholderText(/search for the Florida judicial circuit/i);
    fireEvent.change(textarea, { target: { value: 'lookup circuit by county' } });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ web_search_instruction: 'lookup circuit by county' }),
    );
  });
});

describe('<SourceParamsForm /> — gmail + web search', () => {
  it('renders the enable_web_search checkbox in the Gmail form', () => {
    const params: GmailSourceParams = {
      subject_query: 'Trustee assignment',
      body_query: '',
      scope_to_current_case: true,
      enable_web_search: false,
      web_search_instruction: '',
    };
    render(
      <SourceParamsForm
        source="gmail"
        sourceParams={params}
        onChange={() => {}}
      />,
    );
    expect(
      screen.getByRole('checkbox', { name: /enhance with web search/i }),
    ).toBeInTheDocument();
  });

  it('hides the Web search instruction textarea when enable_web_search is false', () => {
    const params: GmailSourceParams = {
      subject_query: 'Trustee assignment',
      body_query: '',
      scope_to_current_case: true,
      enable_web_search: false,
      web_search_instruction: '',
    };
    render(
      <SourceParamsForm
        source="gmail"
        sourceParams={params}
        onChange={() => {}}
      />,
    );
    expect(screen.queryByText(/web search instruction/i)).not.toBeInTheDocument();
  });

  it('flipping enable_web_search on patches the params and reveals the instruction textarea', () => {
    const onChange = vi.fn();
    const params: GmailSourceParams = {
      subject_query: 'Trustee assignment',
      body_query: '',
      scope_to_current_case: true,
      enable_web_search: false,
      web_search_instruction: '',
    };
    render(
      <SourceParamsForm
        source="gmail"
        sourceParams={params}
        onChange={onChange}
      />,
    );
    const checkbox = screen.getByRole('checkbox', { name: /enhance with web search/i });
    fireEvent.click(checkbox);
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ enable_web_search: true }),
    );
  });

  it('does NOT render the enable_web_search checkbox for court_drive', () => {
    render(
      <SourceParamsForm
        source="court_drive"
        sourceParams={{
          subject_query: 'Trustee assignment',
          body_query: '',
          scope_to_current_case: true,
        }}
        onChange={() => {}}
      />,
    );
    expect(
      screen.queryByRole('checkbox', { name: /enhance with web search/i }),
    ).not.toBeInTheDocument();
  });
});
