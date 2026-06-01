import { useState, type ReactElement } from 'react';
import { AttorneyRosterEditor } from '@/components/studio/AttorneyRosterEditor';
import { DeleteConfirmModal } from '@/components/chat/DeleteConfirmModal';
import { useStudioStore } from '@/stores/useStudioStore';
import { useToastStore } from '@/stores/useToastStore';
import { ATTORNEYS_SHORT_CODE, type ReferenceData } from '@/types/studio';

interface ConstantsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface EditDraft {
  value: string;
  description: string;
}

interface NewDraft {
  name: string;
  value: string;
  description: string;
}

type TabKey = 'attorneys' | 'constants';

const EMPTY_NEW: NewDraft = { name: '', value: '', description: '' };

export const ConstantsModal = ({ isOpen, onClose }: ConstantsModalProps): ReactElement | null => {
  const referenceData = useStudioStore((state) => state.referenceData);
  const createReferenceData = useStudioStore((state) => state.createReferenceData);
  const updateReferenceData = useStudioStore((state) => state.updateReferenceData);
  const deleteReferenceData = useStudioStore((state) => state.deleteReferenceData);
  const refreshReferenceData = useStudioStore((state) => state.refreshReferenceData);
  const addToast = useToastStore((state) => state.addToast);

  const [activeTab, setActiveTab] = useState<TabKey>('attorneys');
  const [editing, setEditing] = useState<Record<string, EditDraft>>({});
  const [newDraft, setNewDraft] = useState<NewDraft>(EMPTY_NEW);
  const [isSavingNew, setIsSavingNew] = useState<boolean>(false);
  const [savingShortCode, setSavingShortCode] = useState<string | null>(null);
  const [refreshingShortCode, setRefreshingShortCode] = useState<string | null>(null);
  const [deletingShortCode, setDeletingShortCode] = useState<string | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<ReferenceData | null>(null);

  const handleConfirmDelete = async (): Promise<void> => {
    const ref = deleteConfirm;
    if (!ref) return;
    setDeleteConfirm(null);
    setDeletingShortCode(ref.short_code);
    const result = await deleteReferenceData(ref.short_code);
    setDeletingShortCode(null);
    if (result.success) {
      addToast(`Removed ${ref.display_name}`, 'success');
    } else if (result.error) {
      addToast(result.error, 'error');
    }
  };

  const handleRefresh = async (shortCode: string): Promise<void> => {
    setRefreshingShortCode(shortCode);
    const result = await refreshReferenceData(shortCode);
    setRefreshingShortCode(null);
    if (result.success) {
      addToast('Refreshed from server', 'info');
    } else if (result.error) {
      addToast(result.error, 'error');
    }
  };

  if (!isOpen) return null;

  const startEdit = (ref: ReferenceData): void => {
    setEditing((prev) => ({
      ...prev,
      [ref.short_code]: { value: ref.value, description: ref.description ?? '' },
    }));
  };

  const cancelEdit = (shortCode: string): void => {
    setEditing((prev) => {
      const next = { ...prev };
      delete next[shortCode];
      return next;
    });
  };

  const saveEdit = async (shortCode: string): Promise<void> => {
    const draft = editing[shortCode];
    if (!draft) return;
    setSavingShortCode(shortCode);
    const result = await updateReferenceData(shortCode, {
      value: draft.value,
      description: draft.description || null,
    });
    setSavingShortCode(null);
    if (result.success) {
      addToast('Constant updated', 'success');
      cancelEdit(shortCode);
    } else if (result.error) {
      addToast(result.error, 'error');
    }
  };

  const saveNew = async (): Promise<void> => {
    if (!newDraft.name.trim() || !newDraft.value.trim()) {
      addToast('Name and value are required', 'error');
      return;
    }
    setIsSavingNew(true);
    const result = await createReferenceData({
      name: newDraft.name.trim(),
      value: newDraft.value.trim(),
      description: newDraft.description.trim() || null,
    });
    setIsSavingNew(false);
    if (result.success) {
      addToast('Constant created', 'success');
      setNewDraft(EMPTY_NEW);
    } else if (result.error) {
      addToast(result.error, 'error');
    }
  };

  // Attorney roster is managed via its own dedicated tab + endpoints —
  // hide it from the generic constants list so authors don't accidentally
  // edit the JSON value directly.
  const genericConstants = referenceData.filter(
    (ref) => ref.short_code !== ATTORNEYS_SHORT_CODE,
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl bg-surface shadow-2xl">
        <header className="flex items-center justify-between border-b border-border px-6 py-4">
          <div>
            <h2 className="text-base font-semibold text-text-secondary">Roster & Constants</h2>
            <p className="text-xs text-muted">
              Attorney roll call + reusable template values (firm phone, bar #, etc.).
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-subtle hover:bg-surface-muted hover:text-text-secondary"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </header>

        <nav
          role="tablist"
          aria-label="Roster and constants tabs"
          className="flex shrink-0 gap-1 border-b border-border bg-surface-muted/40 px-3 py-2"
        >
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'attorneys'}
            onClick={() => setActiveTab('attorneys')}
            className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
              activeTab === 'attorneys'
                ? 'bg-surface text-app-accent-text shadow-sm'
                : 'text-muted hover:bg-surface hover:text-text-secondary'
            }`}
          >
            Attorney Roster
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'constants'}
            onClick={() => setActiveTab('constants')}
            className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
              activeTab === 'constants'
                ? 'bg-surface text-app-accent-text shadow-sm'
                : 'text-muted hover:bg-surface hover:text-text-secondary'
            }`}
          >
            Other Constants
            <span className="ml-1.5 rounded-full bg-surface-muted px-1.5 py-0.5 text-[10px] font-semibold text-text-secondary">
              {genericConstants.length}
            </span>
          </button>
        </nav>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          {activeTab === 'attorneys' && (
            <section>
              <header className="mb-3">
                <h3 className="text-sm font-semibold text-text-secondary">Attorney Roster</h3>
                <p className="text-xs text-muted">
                  Curated list of attorneys referenced by{' '}
                  <code className="rounded bg-surface-muted px-1 font-mono text-[10px]">
                    dropdown_from_constants
                  </code>{' '}
                  template fields. Changes here are persisted via{' '}
                  <code className="rounded bg-surface-muted px-1 font-mono text-[10px]">
                    /core/attorneys
                  </code>
                  .
                </p>
              </header>
              <AttorneyRosterEditor />
            </section>
          )}

          {activeTab === 'constants' && (
            <>
              <section className="mb-6 rounded-lg border border-app-accent-soft bg-app-accent-soft/40 p-4">
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-app-accent-text">Add new</h3>
                <div className="grid gap-2 sm:grid-cols-2">
                  <input
                    type="text"
                    placeholder="Name (e.g. Firm Phone)"
                    value={newDraft.name}
                    onChange={(e) => setNewDraft({ ...newDraft, name: e.target.value })}
                    className="rounded border border-border px-3 py-2 text-sm"
                  />
                  <input
                    type="text"
                    placeholder="Value"
                    value={newDraft.value}
                    onChange={(e) => setNewDraft({ ...newDraft, value: e.target.value })}
                    className="rounded border border-border px-3 py-2 text-sm"
                  />
                  <input
                    type="text"
                    placeholder="Description (optional)"
                    value={newDraft.description}
                    onChange={(e) => setNewDraft({ ...newDraft, description: e.target.value })}
                    className="rounded border border-border px-3 py-2 text-sm sm:col-span-2"
                  />
                </div>
                <div className="mt-2 flex justify-end">
                  <button
                    type="button"
                    onClick={saveNew}
                    disabled={isSavingNew}
                    className="rounded-lg bg-indigo-600 px-3 py-2 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                  >
                    {isSavingNew ? 'Creating…' : 'Create'}
                  </button>
                </div>
              </section>

              <section>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">
                  Existing ({genericConstants.length})
                </h3>
                {genericConstants.length === 0 ? (
                  <p className="rounded border border-dashed border-border bg-surface-muted px-4 py-6 text-center text-xs text-subtle">
                    No constants yet.
                  </p>
                ) : (
                  <ul className="space-y-2">
                    {genericConstants.map((ref) => {
                      const draft = editing[ref.short_code];
                      const isSaving = savingShortCode === ref.short_code;
                      return (
                        <li
                          key={ref.short_code}
                          className="rounded-lg border border-border bg-surface px-4 py-3 text-sm"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="font-semibold text-text-secondary">{ref.display_name}</span>
                                <span className="rounded bg-surface-muted px-1.5 py-0.5 font-mono text-[10px] text-muted">
                                  {ref.short_code}
                                </span>
                              </div>
                              {!draft && (
                                <>
                                  <p className="mt-1 break-words text-text-secondary">{ref.value}</p>
                                  {ref.description && (
                                    <p className="mt-0.5 break-words text-xs text-muted">{ref.description}</p>
                                  )}
                                </>
                              )}
                            </div>
                            {!draft && (
                              <div className="flex shrink-0 items-center gap-1">
                                <button
                                  type="button"
                                  onClick={() => handleRefresh(ref.short_code)}
                                  disabled={refreshingShortCode === ref.short_code}
                                  title="Re-fetch this constant from the server (picks up edits from other sessions)"
                                  className="rounded px-2 py-1 text-xs font-semibold text-muted hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                  <svg
                                    className={`h-3.5 w-3.5 ${refreshingShortCode === ref.short_code ? 'animate-spin' : ''}`}
                                    fill="none"
                                    stroke="currentColor"
                                    viewBox="0 0 24 24"
                                  >
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                                  </svg>
                                </button>
                                <button
                                  type="button"
                                  onClick={() => startEdit(ref)}
                                  className="rounded px-2 py-1 text-xs font-semibold text-app-accent-text hover:bg-app-accent-soft"
                                >
                                  Edit
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setDeleteConfirm(ref)}
                                  disabled={deletingShortCode === ref.short_code}
                                  title="Soft-delete this constant"
                                  className="rounded px-2 py-1 text-xs font-semibold text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                  {deletingShortCode === ref.short_code ? 'Removing…' : 'Delete'}
                                </button>
                              </div>
                            )}
                          </div>
                          {draft && (
                            <div className="mt-2 space-y-2">
                              <input
                                type="text"
                                value={draft.value}
                                onChange={(e) =>
                                  setEditing((prev) => ({
                                    ...prev,
                                    [ref.short_code]: { ...draft, value: e.target.value },
                                  }))
                                }
                                placeholder="Value"
                                className="w-full rounded border border-border px-3 py-2 text-sm"
                              />
                              <input
                                type="text"
                                value={draft.description}
                                onChange={(e) =>
                                  setEditing((prev) => ({
                                    ...prev,
                                    [ref.short_code]: { ...draft, description: e.target.value },
                                  }))
                                }
                                placeholder="Description"
                                className="w-full rounded border border-border px-3 py-2 text-sm"
                              />
                              <div className="flex justify-end gap-2">
                                <button
                                  type="button"
                                  onClick={() => cancelEdit(ref.short_code)}
                                  className="rounded px-3 py-1.5 text-xs text-muted hover:bg-surface-muted"
                                >
                                  Cancel
                                </button>
                                <button
                                  type="button"
                                  onClick={() => saveEdit(ref.short_code)}
                                  disabled={isSaving}
                                  className="rounded bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                                >
                                  {isSaving ? 'Saving…' : 'Save'}
                                </button>
                              </div>
                            </div>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </section>
            </>
          )}
        </div>
      </div>

      <DeleteConfirmModal
        isOpen={deleteConfirm !== null}
        title="Delete constant"
        message={
          deleteConfirm
            ? `Remove "${deleteConfirm.display_name}" from the constants? Templates referencing it via dropdown_from_constants will start failing validation. This cannot be undone.`
            : ''
        }
        confirmText={deletingShortCode ? 'Removing…' : 'Delete'}
        cancelText="Cancel"
        onConfirm={handleConfirmDelete}
        onCancel={() => setDeleteConfirm(null)}
        variant="danger"
      />
    </div>
  );
};

export default ConstantsModal;
