import { useEffect, useState } from 'react';
import { Modal } from '@/components/common/Modal';
import type { TemplateRole } from './types';

interface UploadTemplateModalProps {
  isOpen: boolean;
  file: File | null;
  busy: boolean;
  onConfirm: (templateName: string, role: TemplateRole) => void;
  onClose: () => void;
}

const ROLE_OPTIONS: { value: TemplateRole; label: string; description: string }[] = [
  {
    value: 'single',
    label: 'Standalone filing',
    description: 'Files on its own. The simplest choice.',
  },
  {
    value: 'master',
    label: 'Lead filing',
    description: 'Runs once and drives one or more companion filings.',
  },
  {
    value: 'part_of_packet',
    label: 'Companion filing',
    description: 'Files alongside a lead — repeats once per item.',
  },
];

export const UploadTemplateModal = ({
  isOpen,
  file,
  busy,
  onConfirm,
  onClose,
}: UploadTemplateModalProps) => {
  const [name, setName] = useState('');
  const [role, setRole] = useState<TemplateRole>('single');

  useEffect(() => {
    if (file) {
      setName(file.name.replace(/\.docx$/i, ''));
      setRole('single');
    }
  }, [file]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || busy) return;
    onConfirm(name.trim(), role);
  };

  const handleClose = () => {
    if (busy) return;
    onClose();
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} size="md" closeOnBackdropClick={!busy}>
      <form onSubmit={handleSubmit} className="space-y-5 p-6">
        <header className="space-y-1">
          <h2 className="text-lg font-semibold text-text">
            Upload legal document
          </h2>
          <p className="text-xs text-subtle">
            We'll extract the variables and create a reusable template from this filing.
          </p>
          {file && (
            <p className="pt-1 text-xs text-subtle">
              Source:{' '}
              <span className="font-mono text-text-secondary">{file.name}</span> ·{' '}
              {(file.size / 1024).toFixed(1)} KB
            </p>
          )}
        </header>

        <div className="space-y-1.5">
          <label
            htmlFor="upload-template-name"
            className="text-xs font-semibold uppercase tracking-wider text-text-secondary"
          >
            Template name
          </label>
          <input
            id="upload-template-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={busy}
            autoFocus
            placeholder="e.g. 341(a) Meeting Notice"
            className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent/20 disabled:cursor-not-allowed disabled:opacity-60"
          />
          <p className="text-[11px] text-subtle">
            Shows in the templates rail. Paralegals will pick this name when drafting.
          </p>
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
            Filing role
          </label>
          <div className="space-y-1.5">
            {ROLE_OPTIONS.map((opt) => (
              <label
                key={opt.value}
                className={`flex cursor-pointer items-start gap-2 rounded-md border px-3 py-2 transition-colors ${
                  role === opt.value
                    ? 'border-app-accent bg-app-accent-soft/50'
                    : 'border-border bg-surface hover:bg-surface-muted/50'
                } ${busy ? 'cursor-not-allowed opacity-60' : ''}`}
              >
                <input
                  type="radio"
                  name="role"
                  value={opt.value}
                  checked={role === opt.value}
                  onChange={() => setRole(opt.value)}
                  disabled={busy}
                  className="mt-0.5 accent-app-accent"
                />
                <div className="space-y-0.5">
                  <p className="text-sm font-semibold text-text">{opt.label}</p>
                  <p className="text-[11px] text-subtle">{opt.description}</p>
                </div>
              </label>
            ))}
          </div>
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-border pt-4">
          <button
            type="button"
            onClick={handleClose}
            disabled={busy}
            className="cursor-pointer rounded-md border border-border bg-surface px-4 py-2 text-sm font-medium text-text-secondary hover:bg-surface-muted/50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!name.trim() || busy}
            className="inline-flex cursor-pointer items-center gap-2 rounded-md bg-app-accent px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy && (
              <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/40 border-t-white" />
            )}
            {busy ? 'Creating template…' : 'Upload + create template'}
          </button>
        </footer>
      </form>
    </Modal>
  );
};
