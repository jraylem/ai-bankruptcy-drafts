import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { useStudioStore } from '@/stores/useStudioStore';
import { StudioTemplateUploader } from '@/components/studio/StudioTemplateUploader';
import { DOCX_MIME } from '@/utils/studio/templateUpload';

const SUCCESS_HOLD_MS = 600;
const DROP_WAIT_MS = SUCCESS_HOLD_MS + 200;

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
afterEach(() => {
  useStudioStore.setState(baseStoreState);
  vi.useRealTimers();
});

const makeDocxFile = (name: string, sizeBytes = 1024) => {
  const file = new File([new Uint8Array(sizeBytes)], name, { type: DOCX_MIME });
  return file;
};

const dropFile = (zone: HTMLElement, file: File) => {
  fireEvent.drop(zone, {
    dataTransfer: {
      files: [file],
      items: [{ kind: 'file', type: file.type, getAsFile: () => file }],
      types: ['Files'],
    },
  });
};

describe('<StudioTemplateUploader />', () => {
  it('renders the idle copy and the Select DOCX File CTA', () => {
    render(<StudioTemplateUploader onUploadSuccess={() => {}} />);
    expect(screen.getByText(/Upload Legal Document/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Select DOCX File/i })).toBeInTheDocument();
    expect(screen.getByText(/DOCX only/i)).toBeInTheDocument();
  });

  it('drop calls uploadTemplate with the filename-derived name and fires onUploadSuccess on success', async () => {
    const uploadTemplate = vi.fn().mockResolvedValue({ success: true, data: 'tmpl-123' });
    useStudioStore.setState({ ...baseStoreState, uploadTemplate });
    const onUploadSuccess = vi.fn();

    render(<StudioTemplateUploader onUploadSuccess={onUploadSuccess} />);

    const zone = screen.getByLabelText('DOCX dropzone');
    await act(async () => {
      dropFile(zone, makeDocxFile('motion_to_extend.docx'));
    });

    expect(uploadTemplate).toHaveBeenCalledWith('motion to extend', expect.any(File));
    await waitFor(() => {
      expect(onUploadSuccess).toHaveBeenCalledWith('tmpl-123');
    }, { timeout: DROP_WAIT_MS });
  });

  it('shows the type-rejection error when a non-DOCX file is dropped', async () => {
    const uploadTemplate = vi.fn();
    useStudioStore.setState({ ...baseStoreState, uploadTemplate });
    render(<StudioTemplateUploader onUploadSuccess={() => {}} />);
    const zone = screen.getByLabelText('DOCX dropzone');
    const pdfFile = new File(['x'], 'somefile.pdf', { type: 'application/pdf' });

    await act(async () => {
      dropFile(zone, pdfFile);
    });

    await waitFor(() => {
      expect(screen.getByText(/Only DOCX files are supported/i)).toBeInTheDocument();
    });
    expect(uploadTemplate).not.toHaveBeenCalled();
  });

  it('shows the size-rejection error when a too-large DOCX is dropped', async () => {
    const uploadTemplate = vi.fn();
    useStudioStore.setState({ ...baseStoreState, uploadTemplate });
    render(<StudioTemplateUploader onUploadSuccess={() => {}} />);
    const zone = screen.getByLabelText('DOCX dropzone');
    const oversize = makeDocxFile('big.docx', 11 * 1024 * 1024);

    await act(async () => {
      dropFile(zone, oversize);
    });

    await waitFor(() => {
      expect(screen.getByText(/larger than 10 MB/i)).toBeInTheDocument();
    });
    expect(uploadTemplate).not.toHaveBeenCalled();
  });

  it('surfaces server errors on upload failure and stays idle', async () => {
    const uploadTemplate = vi
      .fn()
      .mockResolvedValue({ success: false, error: 'Internal error' });
    useStudioStore.setState({ ...baseStoreState, uploadTemplate });
    const onUploadSuccess = vi.fn();

    render(<StudioTemplateUploader onUploadSuccess={onUploadSuccess} />);
    const zone = screen.getByLabelText('DOCX dropzone');

    await act(async () => {
      dropFile(zone, makeDocxFile('x.docx'));
    });

    await waitFor(() => {
      expect(screen.getByText(/Internal error/i)).toBeInTheDocument();
    });
    expect(onUploadSuccess).not.toHaveBeenCalled();
  });
});
