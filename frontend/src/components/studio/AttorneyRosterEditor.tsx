import { useEffect, useState, type ReactElement } from 'react';
import { DeleteConfirmModal } from '@/components/chat/DeleteConfirmModal';
import { studioApi } from '@/services/studio.service';
import { useToastStore } from '@/stores/useToastStore';
import { useStudioStore } from '@/stores/useStudioStore';
import { ATTORNEYS_SHORT_CODE, type Attorney } from '@/types/studio';

/**
 * Structured editor for the curated attorney roster. Replaces the raw
 * JSON view of the `ATTORNEYS` reference_data row inside the Constants
 * modal — each attorney becomes its own add/edit/delete row, and every
 * mutation flows through the dedicated `/core/attorneys` endpoints so
 * the BE keeps the underlying reference_data row in sync.
 *
 * After any mutation we refresh the parent constants list so the
 * embedding modal's row reflects the new JSON value verbatim.
 */
interface AttorneyRosterEditorProps {
  /** Called after any mutation so the parent (Constants modal) can
   * refresh its referenceData row for ATTORNEYS. */
  onMutated?: () => void;
}

export const AttorneyRosterEditor = ({
  onMutated,
}: AttorneyRosterEditorProps): ReactElement => {
  const addToast = useToastStore((s) => s.addToast);
  const refreshReferenceData = useStudioStore((s) => s.refreshReferenceData);

  const [attorneys, setAttorneys] = useState<Attorney[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [newName, setNewName] = useState<string>('');
  const [isCreating, setIsCreating] = useState<boolean>(false);
  const [editing, setEditing] = useState<Record<string, string>>({});
  const [savingId, setSavingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<Attorney | null>(null);

  const reload = async (): Promise<void> => {
    setIsLoading(true);
    const result = await studioApi.listAttorneys();
    setIsLoading(false);
    if (result.data) {
      setAttorneys(result.data);
    } else if (result.error) {
      addToast(result.error, 'error');
    }
  };

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshParent = async (): Promise<void> => {
    // Keep the Constants modal's referenceData row aligned with the new
    // attorneys list so the JSON snippet shown there isn't stale.
    await refreshReferenceData(ATTORNEYS_SHORT_CODE);
    onMutated?.();
  };

  const handleCreate = async (): Promise<void> => {
    const cleaned = newName.trim();
    if (!cleaned) {
      addToast('Full name is required', 'error');
      return;
    }
    setIsCreating(true);
    const result = await studioApi.createAttorney({ full_name: cleaned });
    setIsCreating(false);
    if (result.data) {
      addToast(`Added ${result.data.full_name}`, 'success');
      setNewName('');
      await reload();
      await refreshParent();
    } else if (result.error) {
      addToast(result.error, 'error');
    }
  };

  const startEdit = (attorney: Attorney): void => {
    setEditing((prev) => ({ ...prev, [attorney.id]: attorney.full_name }));
  };

  const cancelEdit = (id: string): void => {
    setEditing((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  };

  const handleSave = async (id: string): Promise<void> => {
    const draft = editing[id]?.trim();
    if (!draft) {
      addToast('Full name is required', 'error');
      return;
    }
    setSavingId(id);
    const result = await studioApi.updateAttorney(id, { full_name: draft });
    setSavingId(null);
    if (result.data) {
      addToast('Attorney updated', 'success');
      cancelEdit(id);
      await reload();
      await refreshParent();
    } else if (result.error) {
      addToast(result.error, 'error');
    }
  };

  const handleConfirmDelete = async (): Promise<void> => {
    const attorney = deleteConfirm;
    if (!attorney) return;
    setDeleteConfirm(null);
    setDeletingId(attorney.id);
    const result = await studioApi.deleteAttorney(attorney.id);
    setDeletingId(null);
    if (result.error) {
      addToast(result.error, 'error');
      return;
    }
    addToast(`Removed ${attorney.full_name}`, 'success');
    await reload();
    await refreshParent();
  };

  return (
    <>
    <div className="space-y-3">
      <div className="rounded-lg border border-app-accent-soft bg-app-accent-soft/30 p-3">
        <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-app-accent-text">
          Add attorney
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !isCreating) void handleCreate();
            }}
            placeholder="e.g. Chad Van Horn, Esq."
            className="flex-1 rounded-md border border-border bg-surface px-3 py-1.5 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
          />
          <button
            type="button"
            onClick={handleCreate}
            disabled={isCreating || !newName.trim()}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isCreating ? 'Adding…' : 'Add'}
          </button>
        </div>
      </div>

      {isLoading ? (
        <p className="rounded-md border border-dashed border-border bg-surface-muted px-3 py-4 text-center text-xs text-subtle">
          Loading roster…
        </p>
      ) : attorneys.length === 0 ? (
        <p className="rounded-md border border-dashed border-border bg-surface-muted px-3 py-4 text-center text-xs text-subtle">
          No attorneys yet. Add one above to start the roster.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {attorneys.map((attorney) => {
            const draft = editing[attorney.id];
            const isEditing = draft !== undefined;
            const isSaving = savingId === attorney.id;
            const isDeleting = deletingId === attorney.id;
            return (
              <li
                key={attorney.id}
                className="rounded-md border border-border bg-surface px-3 py-2"
              >
                {isEditing ? (
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={draft}
                      onChange={(e) =>
                        setEditing((prev) => ({
                          ...prev,
                          [attorney.id]: e.target.value,
                        }))
                      }
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !isSaving) void handleSave(attorney.id);
                        if (e.key === 'Escape') cancelEdit(attorney.id);
                      }}
                      autoFocus
                      className="flex-1 rounded-md border border-border bg-surface px-2.5 py-1 text-sm text-text-secondary focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
                    />
                    <button
                      type="button"
                      onClick={() => cancelEdit(attorney.id)}
                      className="rounded px-2 py-1 text-xs text-muted hover:bg-surface-muted"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={() => handleSave(attorney.id)}
                      disabled={isSaving}
                      className="rounded bg-indigo-600 px-2 py-1 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                    >
                      {isSaving ? 'Saving…' : 'Save'}
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm text-text-secondary">
                        {attorney.full_name}
                      </p>
                      <p className="truncate font-mono text-[10px] text-subtle">
                        {attorney.id}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      <button
                        type="button"
                        onClick={() => startEdit(attorney)}
                        className="rounded px-2 py-1 text-xs font-semibold text-app-accent-text hover:bg-app-accent-soft"
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => setDeleteConfirm(attorney)}
                        disabled={isDeleting}
                        className="rounded px-2 py-1 text-xs font-semibold text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {isDeleting ? 'Removing…' : 'Remove'}
                      </button>
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
    <DeleteConfirmModal
      isOpen={deleteConfirm !== null}
      title="Remove attorney"
      message={
        deleteConfirm
          ? `Remove "${deleteConfirm.full_name}" from the roster? This cannot be undone.`
          : ''
      }
      confirmText={deletingId ? 'Removing…' : 'Remove'}
      cancelText="Cancel"
      onConfirm={handleConfirmDelete}
      onCancel={() => setDeleteConfirm(null)}
      variant="danger"
    />
    </>
  );
};

export default AttorneyRosterEditor;
