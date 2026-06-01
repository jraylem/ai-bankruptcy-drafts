import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { useStudioStore } from '@/stores/useStudioStore';
import { CaseSelectionModal } from '@/components/studio/modals/CaseSelectionModal';
import { ConfigureVariableModal } from '@/components/studio/modals/ConfigureVariableModal';
import { ConstantsModal } from '@/components/studio/modals/ConstantsModal';
import { NewCaseModal } from '@/components/studio/modals/NewCaseModal';
import { RegenerateTemplateModal } from '@/components/studio/modals/RegenerateTemplateModal';
import { UploadTemplateModal } from '@/components/studio/modals/UploadTemplateModal';
import type { CaseResponse, TemplateVariable } from '@/types/studio';

vi.mock('@/services/studio.service', () => ({
  studioApi: new Proxy({}, { get: () => vi.fn().mockResolvedValue({ data: null }) }),
}));

vi.mock('lottie-react', () => ({
  default: () => null,
}));

const sampleCase: CaseResponse = {
  id: 'c1',
  case_name: 'Doe, John',
  case_number: '26-10700',
  case_number_original: '26-10700',
  court_district: 'EDPA',
  chapter: 13,
  petition_pdf_url: null,
  case_file_collection: 'cf',
  gmail_collection: 'gm',
  courtdrive_collection: 'cd',
};

const baseVariable = (overrides: Partial<TemplateVariable> = {}): TemplateVariable => ({
  template_variable: 'debtor_name',
  template_index: 0,
  source: 'case_vector',
  source_params: null,
  template_property_marker: '[[debtor_name]]',
  template_variable_string: '{{debtor_name}}',
  template_identifying_text_match: null,
  description: 'Debtor full legal name',
  instruction: null,
  ...overrides,
});

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

describe('<CaseSelectionModal />', () => {
  it('returns null when isOpen=false', () => {
    const { container } = render(
      <CaseSelectionModal
        isOpen={false}
        title="t"
        confirmLabel="Run"
        isRunning={false}
        onClose={() => {}}
        onConfirm={() => {}}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders cases list when isOpen=true', () => {
    useStudioStore.setState({ cases: [sampleCase] });
    render(
      <CaseSelectionModal
        isOpen={true}
        title="Pick a case"
        confirmLabel="Run dry-run"
        isRunning={false}
        onClose={() => {}}
        onConfirm={() => {}}
      />,
    );
    expect(screen.getByText('Pick a case')).toBeInTheDocument();
    expect(screen.getByText('Doe, John')).toBeInTheDocument();
    expect(screen.getByText(/26-10700/)).toBeInTheDocument();
  });

  it('filters cases by query', () => {
    useStudioStore.setState({
      cases: [
        sampleCase,
        { ...sampleCase, id: 'c2', case_name: 'Smith, Jane', case_number: '27-99999' },
      ],
    });
    render(
      <CaseSelectionModal
        isOpen={true}
        title="t"
        confirmLabel="Run"
        isRunning={false}
        onClose={() => {}}
        onConfirm={() => {}}
      />,
    );
    fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: 'Smith' } });
    expect(screen.queryByText('Doe, John')).toBeNull();
    expect(screen.getByText('Smith, Jane')).toBeInTheDocument();
  });
});

describe('<ConstantsModal />', () => {
  it('returns null when isOpen=false', () => {
    const { container } = render(<ConstantsModal isOpen={false} onClose={() => {}} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders constants list when isOpen=true', () => {
    useStudioStore.setState({
      referenceData: [
        {
          id: '1',
          short_code: 'firm_address',
          display_name: 'Firm Address',
          value: '123 Main St',
          category: null,
          description: null,
        },
      ],
    });
    render(<ConstantsModal isOpen={true} onClose={() => {}} />);
    // Modal opens on the Attorney Roster tab by default; switch to the
    // Other Constants tab to see the generic reference_data list.
    fireEvent.click(screen.getByRole('tab', { name: /Other Constants/i }));
    expect(screen.getByText('Firm Address')).toBeInTheDocument();
  });
});

describe('<UploadTemplateModal />', () => {
  it('returns null when isOpen=false', () => {
    const { container } = render(
      <UploadTemplateModal isOpen={false} onClose={() => {}} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders the upload zone when isOpen=true', () => {
    render(<UploadTemplateModal isOpen={true} onClose={() => {}} />);
    expect(screen.getByText(/Upload Legal Document/i)).toBeInTheDocument();
    expect(screen.getByText(/DOCX only/i)).toBeInTheDocument();
  });

  it('Close button calls onClose', () => {
    const onClose = vi.fn();
    render(<UploadTemplateModal isOpen={true} onClose={onClose} />);
    fireEvent.click(screen.getByLabelText(/Close/i));
    expect(onClose).toHaveBeenCalled();
  });
});

describe('<NewCaseModal />', () => {
  it('renders nothing when closed', () => {
    const { container } = render(<NewCaseModal isOpen={false} onClose={() => {}} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders the upload zone when isOpen=true', () => {
    render(<NewCaseModal isOpen={true} onClose={() => {}} />);
    expect(screen.getAllByText(/PDF/i).length).toBeGreaterThan(0);
  });
});

describe('<RegenerateTemplateModal />', () => {
  it('returns null when isOpen=false', () => {
    const { container } = render(
      <RegenerateTemplateModal isOpen={false} onClose={() => {}} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders one row per template variable when open', () => {
    useStudioStore.setState({
      templateSpec: [
        baseVariable({ template_variable: 'a', template_property_marker: '[[a]]' }),
        baseVariable({
          template_variable: 'b',
          template_index: 1,
          template_property_marker: '[[b]]',
        }),
      ],
    });
    const { container } = render(
      <RegenerateTemplateModal isOpen={true} onClose={() => {}} />,
    );
    const codes = Array.from(container.querySelectorAll('code')).map((c) => c.textContent);
    expect(codes).toContain('[[a]]');
    expect(codes).toContain('[[b]]');
  });
});

describe('<ConfigureVariableModal />', () => {
  it('renders nothing when variable=null', () => {
    const { container } = render(
      <ConfigureVariableModal variable={null} onClose={() => {}} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders the variable name in header when variable is provided', () => {
    render(
      <ConfigureVariableModal variable={baseVariable()} onClose={() => {}} />,
    );
    expect(screen.getByText('debtor_name')).toBeInTheDocument();
    expect(screen.getByText(/Debtor full legal name/)).toBeInTheDocument();
  });

  it('renders "Extraction instruction" label (relabeled from "Extraction hint")', () => {
    render(
      <ConfigureVariableModal variable={baseVariable()} onClose={() => {}} />,
    );
    expect(screen.getByText('Extraction instruction')).toBeInTheDocument();
    // Old label should NOT be present anywhere in the DOM
    expect(screen.queryByText('Extraction hint')).not.toBeInTheDocument();
  });

  it('renders "Document output instruction" label (relabeled from "Output instruction")', () => {
    render(
      <ConfigureVariableModal variable={baseVariable()} onClose={() => {}} />,
    );
    expect(screen.getByText('Document output instruction')).toBeInTheDocument();
    // Old label should NOT be present anywhere in the DOM
    expect(screen.queryByText('Output instruction')).not.toBeInTheDocument();
  });
});
