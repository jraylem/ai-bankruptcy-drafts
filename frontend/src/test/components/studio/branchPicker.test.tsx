import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { BranchPickerModal } from '@/components/studio/modals/BranchPickerModal';
import type { BundleCompanion } from '@/types/studio/bundling';

const branch: BundleCompanion = {
  kind: 'branch',
  label: 'Certificate of Service',
  question: 'Includes a Notice of Hearing?',
  options: [
    {
      label: 'Yes',
      child_template_id: 'tpl_cos_with_hearing',
      slot_configurations: {},
    },
    {
      label: 'No',
      child_template_id: 'tpl_cos_no_hearing',
      slot_configurations: {},
    },
  ],
};

const fixed: BundleCompanion = {
  kind: 'fixed',
  label: 'Cover Sheet',
  child_template_id: 'tpl_cover',
  slot_configurations: {},
};

describe('<BranchPickerModal />', () => {
  it('returns null when not open', () => {
    const { container } = render(
      <BranchPickerModal
        isOpen={false}
        title="t"
        confirmLabel="Run"
        isRunning={false}
        bundleCompanions={[branch]}
        onClose={() => {}}
        onConfirm={() => {}}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('only renders branch companions, hides fixed companions', () => {
    render(
      <BranchPickerModal
        isOpen={true}
        title="t"
        confirmLabel="Run"
        isRunning={false}
        bundleCompanions={[fixed, branch]}
        onClose={() => {}}
        onConfirm={() => {}}
      />,
    );
    expect(screen.getByText('Certificate of Service')).toBeInTheDocument();
    expect(screen.queryByText('Cover Sheet')).not.toBeInTheDocument();
    expect(
      screen.getByText('Includes a Notice of Hearing?'),
    ).toBeInTheDocument();
  });

  it('seeds the first option for each branch by default', () => {
    render(
      <BranchPickerModal
        isOpen={true}
        title="t"
        confirmLabel="Run"
        isRunning={false}
        bundleCompanions={[branch]}
        onClose={() => {}}
        onConfirm={() => {}}
      />,
    );
    const yesRadio = screen.getByRole('radio', { name: /Yes/ }) as HTMLInputElement;
    expect(yesRadio.checked).toBe(true);
  });

  it('emits the picked label keyed by companion index when confirmed', () => {
    const onConfirm = vi.fn();
    render(
      <BranchPickerModal
        isOpen={true}
        title="t"
        confirmLabel="Run"
        isRunning={false}
        // First entry is fixed, so the branch ends up at index 1.
        bundleCompanions={[fixed, branch]}
        onClose={() => {}}
        onConfirm={onConfirm}
      />,
    );

    fireEvent.click(screen.getByRole('radio', { name: /No/ }));
    fireEvent.click(screen.getByRole('button', { name: /Run/ }));

    expect(onConfirm).toHaveBeenCalledWith({ '1': 'No' });
  });

  it('disables the confirm button while isRunning is true', () => {
    render(
      <BranchPickerModal
        isOpen={true}
        title="t"
        confirmLabel="Run Draft"
        isRunning={true}
        bundleCompanions={[branch]}
        onClose={() => {}}
        onConfirm={() => {}}
      />,
    );
    const button = screen.getByRole('button', { name: /Running…/ });
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });

  it('calls onClose when the close (X) button is clicked', () => {
    const onClose = vi.fn();
    render(
      <BranchPickerModal
        isOpen={true}
        title="t"
        confirmLabel="Run"
        isRunning={false}
        bundleCompanions={[branch]}
        onClose={onClose}
        onConfirm={() => {}}
      />,
    );
    fireEvent.click(screen.getByLabelText('Close'));
    expect(onClose).toHaveBeenCalled();
  });
});
