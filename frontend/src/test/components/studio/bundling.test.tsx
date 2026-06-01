import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { TemplateBundleSettings } from '@/components/studio/TemplateBundleSettings';
import { BundleCompanionsEditor } from '@/components/studio/BundleCompanionsEditor';
import { InheritFromParentForm } from '@/components/studio/source-picker/InheritFromParentForm';
import { useStudioStore } from '@/stores/useStudioStore';
import type { DraftTemplateListItem } from '@/types/studio';

vi.mock('@/services/studio.service', () => ({
  studioApi: new Proxy({}, { get: () => vi.fn().mockResolvedValue({ data: null }) }),
}));

const baseStore = {
  selectedCaseId: null,
  selectedTemplateId: 't1',
  cases: [],
  templates: [] as DraftTemplateListItem[],
  connectors: [],
  referenceData: [],
  templateSpec: [],
  agentConfig: null,
  bundleRole: 'standalone' as const,
  bundleCompanions: [],
  isBundlingDirty: false,
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

beforeEach(() => {
  useStudioStore.setState(baseStore);
});

describe('<TemplateBundleSettings />', () => {
  it('renders the three role options with the current selection from the store', () => {
    render(<TemplateBundleSettings />);
    // Header lives on the CollapsibleSection wrapper at the page level —
    // this component only renders the role picker + per-role body.
    const radios = screen.getAllByRole('radio');
    expect(radios).toHaveLength(3);
    expect((radios[0] as HTMLInputElement).value).toBe('standalone');
    expect((radios[0] as HTMLInputElement).checked).toBe(true);
    expect((radios[1] as HTMLInputElement).value).toBe('parent');
    expect((radios[1] as HTMLInputElement).checked).toBe(false);
    expect((radios[2] as HTMLInputElement).value).toBe('child_only');
    expect((radios[2] as HTMLInputElement).checked).toBe(false);
  });

  it('marks the template bundling-dirty when the role changes', () => {
    render(<TemplateBundleSettings />);
    expect(useStudioStore.getState().isBundlingDirty).toBe(false);
    const childOnlyRadio = screen
      .getAllByRole('radio')
      .find((r) => (r as HTMLInputElement).value === 'child_only')!;
    fireEvent.click(childOnlyRadio);
    expect(useStudioStore.getState().bundleRole).toBe('child_only');
    expect(useStudioStore.getState().isBundlingDirty).toBe(true);
  });

  it('renders no extra body for child_only role (radio description suffices; picker handles the rest)', () => {
    useStudioStore.setState({ bundleRole: 'child_only' });
    render(<TemplateBundleSettings />);
    // Companions editor must NOT render for child_only — only for parent.
    expect(screen.queryByText('Bundle Companions')).not.toBeInTheDocument();
    // Linked-from-parents body was redundant with the radio + picker UX,
    // so it was stripped. If you re-add an info card here, update this test.
    expect(screen.queryByText(/Linked from parents/i)).not.toBeInTheDocument();
  });

  it('renders the companions editor when role is parent', () => {
    useStudioStore.setState({ bundleRole: 'parent' });
    render(<TemplateBundleSettings />);
    expect(screen.getByText('Bundle Companions')).toBeInTheDocument();
  });
});

describe('<BundleCompanionsEditor />', () => {
  const childTemplate: DraftTemplateListItem = {
    id: 'tpl_cos',
    name: 'COS',
    original_doc_url: null,
    template_doc_url: null,
    template_spec: [
      {
        template_variable: 'case_number',
        template_index: 0,
        source: 'inherit_from_parent',
        source_params: null,
        template_property_marker: null,
        template_variable_string: '[[case_number]]',
        template_identifying_text_match: null,
        description: null,
        instruction: null,
      },
    ],
    agent_config: null,
    bundle_role: 'child_only',
    bundle_companions: null,
    created_at: '2026-05-07T00:00:00Z',
    is_active: true,
  };

  it('warns when no child-only templates exist in the catalog', () => {
    useStudioStore.setState({ templates: [] });
    render(<BundleCompanionsEditor />);
    expect(
      screen.getByText(/No child-only templates available/i),
    ).toBeInTheDocument();
  });

  it('shows the empty state when child templates exist but no companions yet', () => {
    useStudioStore.setState({ templates: [childTemplate] });
    render(<BundleCompanionsEditor />);
    expect(screen.getByText(/No companions yet/i)).toBeInTheDocument();
  });

  it('appends a fixed companion when the + Fixed companion button is clicked', () => {
    useStudioStore.setState({ templates: [childTemplate] });
    render(<BundleCompanionsEditor />);
    fireEvent.click(screen.getByText('+ Fixed companion'));
    expect(useStudioStore.getState().bundleCompanions).toHaveLength(1);
    expect(useStudioStore.getState().bundleCompanions[0]?.kind).toBe('fixed');
    expect(useStudioStore.getState().isBundlingDirty).toBe(true);
  });

  it('appends a branch companion with two default options when + Branch companion is clicked', () => {
    useStudioStore.setState({ templates: [childTemplate] });
    render(<BundleCompanionsEditor />);
    fireEvent.click(screen.getByText('+ Branch companion'));
    const companions = useStudioStore.getState().bundleCompanions;
    expect(companions).toHaveLength(1);
    expect(companions[0]?.kind).toBe('branch');
    if (companions[0]?.kind === 'branch') {
      expect(companions[0].options).toHaveLength(2);
    }
  });
});

describe('<InheritFromParentForm />', () => {
  it('renders the slot marker headline + slot name', () => {
    render(
      <InheritFromParentForm
        variableName="case_number"
        sourceParams={null}
        onChange={() => {}}
      />,
    );
    expect(screen.getByText('This variable is a slot')).toBeInTheDocument();
    expect(screen.getByText('case_number')).toBeInTheDocument();
  });

  it('emits a fallback_value patch when the input changes', () => {
    const onChange = vi.fn();
    render(
      <InheritFromParentForm
        variableName="docket_title"
        sourceParams={{ fallback_value: null }}
        onChange={onChange}
      />,
    );
    const input = screen.getByPlaceholderText(/no parent attached/i);
    fireEvent.change(input, { target: { value: '[no parent]' } });
    expect(onChange).toHaveBeenCalledWith({ fallback_value: '[no parent]' });
  });

  it('clears fallback_value to null when the input is emptied', () => {
    const onChange = vi.fn();
    render(
      <InheritFromParentForm
        variableName="case_number"
        sourceParams={{ fallback_value: 'x' }}
        onChange={onChange}
      />,
    );
    const input = screen.getByPlaceholderText(/no parent attached/i);
    fireEvent.change(input, { target: { value: '' } });
    expect(onChange).toHaveBeenCalledWith({ fallback_value: null });
  });
});
