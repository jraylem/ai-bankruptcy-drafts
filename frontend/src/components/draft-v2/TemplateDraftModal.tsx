import { useEffect, useMemo, useRef, useState, type ReactElement } from 'react';
import { useNavigate } from 'react-router-dom';
import { LuCheck, LuFilePlus, LuSearch, LuX } from 'react-icons/lu';

import { Modal } from '@/components/common';
import { useStudioStore } from '@/stores/useStudioStore';
import { useTemplateDraftStore } from '@/stores/useTemplateDraftStore';
import { useToastStore } from '@/stores/useToastStore';

interface TemplateDraftModalProps {
  isOpen: boolean;
  onClose: () => void;
}

/**
 * V2 template picker — replaces the mock `DraftMotionsModal`.
 *
 * Lists production-ready templates (saved agent_config, active, not
 * child-only) and fires `useTemplateDraftStore.startDraft` on Generate.
 * Auto-closes if the user switches cases while the modal is open.
 */
export const TemplateDraftModal = ({
  isOpen,
  onClose,
}: TemplateDraftModalProps): ReactElement => {
  const navigate = useNavigate();
  const addToast = useToastStore((s) => s.addToast);

  const templates = useStudioStore((s) => s.templates);
  const isLoadingTemplates = useStudioStore((s) => s.isLoadingTemplates);
  const selectedCaseId = useStudioStore((s) => s.selectedCaseId);

  const startDraft = useTemplateDraftStore((s) => s.startDraft);
  const openBranchPicker = useTemplateDraftStore((s) => s.openBranchPicker);

  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [highlightIndex, setHighlightIndex] = useState<number>(0);
  const [isGenerating, setIsGenerating] = useState(false);
  const searchInputRef = useRef<HTMLInputElement | null>(null);

  const productionTemplates = useMemo(
    () =>
      templates
        .filter(
          (t) =>
            t.agent_config !== null &&
            t.is_active &&
            t.bundle_role !== 'child_only',
        )
        .sort((a, b) => a.name.localeCompare(b.name)),
    [templates],
  );

  useEffect(() => {
    if (isOpen) {
      setSelectedTemplateId('');
      setSearchQuery('');
      setHighlightIndex(0);
      // Autofocus the search input so the user can type-to-filter immediately.
      requestAnimationFrame(() => {
        searchInputRef.current?.focus();
      });
    }
  }, [isOpen]);

  const filteredTemplates = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return productionTemplates;
    return productionTemplates.filter((t) => t.name.toLowerCase().includes(q));
  }, [productionTemplates, searchQuery]);

  // Reset highlight whenever the filtered list shrinks/grows so the keyboard
  // cursor never points past the last visible row.
  useEffect(() => {
    setHighlightIndex((i) => Math.min(i, Math.max(filteredTemplates.length - 1, 0)));
  }, [filteredTemplates.length]);

  const handleSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>): void => {
    if (filteredTemplates.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlightIndex((i) => Math.min(i + 1, filteredTemplates.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlightIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const picked = filteredTemplates[highlightIndex] ?? filteredTemplates[0];
      if (picked) setSelectedTemplateId(picked.id);
    } else if (e.key === 'Escape') {
      if (searchQuery) {
        e.preventDefault();
        setSearchQuery('');
      }
    }
  };

  const caseIdAtOpenRef = useRef<string | null>(null);
  useEffect(() => {
    if (isOpen) {
      if (caseIdAtOpenRef.current === null) {
        caseIdAtOpenRef.current = selectedCaseId;
        return;
      }
      if (caseIdAtOpenRef.current !== selectedCaseId) {
        addToast('Closed template picker — you switched cases.', 'info');
        onClose();
      }
    } else {
      caseIdAtOpenRef.current = null;
    }
  }, [isOpen, selectedCaseId, addToast, onClose]);

  const pickedTemplate = useMemo(
    () => productionTemplates.find((t) => t.id === selectedTemplateId) ?? null,
    [productionTemplates, selectedTemplateId],
  );

  const variableCount = pickedTemplate?.template_spec?.length ?? 0;
  const companionCount = pickedTemplate?.bundle_companions?.length ?? 0;

  const isLoading = isLoadingTemplates && templates.length === 0;
  const isEmpty = !isLoading && productionTemplates.length === 0;

  const handleGenerate = async (): Promise<void> => {
    if (!selectedTemplateId || !selectedCaseId || !pickedTemplate || isGenerating) return;

    // Branch-companion pre-flight: if the parent has any branch companions,
    // defer the draft and pop the picker first. Fixed companions don't need
    // picks; they always schedule.
    const branchCount = (pickedTemplate.bundle_companions ?? []).filter(
      (c) => c.kind === 'branch',
    ).length;
    if (pickedTemplate.bundle_role === 'parent' && branchCount > 0) {
      openBranchPicker({
        templateId: selectedTemplateId,
        caseId: selectedCaseId,
        templateName: pickedTemplate.name,
        companions: pickedTemplate.bundle_companions ?? [],
      });
      onClose();
      return;
    }

    // No branches — instant feedback then fire startDraft directly.
    addToast(`Drafting ${pickedTemplate.name}…`, 'info');
    onClose();

    setIsGenerating(true);
    const result = await startDraft(
      {
        template_id: selectedTemplateId,
        case_id: selectedCaseId,
        bundle_picks: null,
      },
      { templateNameHint: pickedTemplate.name },
    );
    setIsGenerating(false);

    if (result.success) return;
    if (result.code === 'DUPLICATE_DRAFT_IN_FLIGHT') {
      addToast(result.error ?? 'A draft is already running for this template.', 'warning');
      return;
    }
    addToast(result.error ?? 'Failed to start draft', 'error');
  };

  const handleOpenStudio = (): void => {
    navigate('/studio');
    onClose();
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="md">
      <div className="flex flex-col" role="dialog" aria-labelledby="template-draft-title">
        <header className="border-b border-border px-6 py-4">
          <h2
            id="template-draft-title"
            className="text-lg font-semibold text-text-secondary"
          >
            Draft pleadings
          </h2>
          <p className="mt-1 text-xs text-muted">
            Run a production-ready template against this case.
          </p>
        </header>

        <div className="px-6 py-5">
          {isLoading && (
            <div className="space-y-2" aria-busy="true">
              <span className="block h-3 w-20 animate-pulse rounded bg-border" />
              <span className="block h-10 w-full animate-pulse rounded-lg bg-border" />
            </div>
          )}

          {isEmpty && (
            <div className="flex flex-col items-center gap-3 py-6 text-center">
              <span
                aria-hidden="true"
                className="grid h-12 w-12 place-items-center rounded-full bg-app-accent-soft text-app-accent-text"
              >
                <LuFilePlus className="h-5 w-5" />
              </span>
              <p className="text-sm font-semibold text-text-secondary">
                No production-ready templates yet
              </p>
              <p className="max-w-xs text-xs text-muted">
                Templates need a saved agent configuration before they can run on a case.
              </p>
              <button
                type="button"
                onClick={handleOpenStudio}
                className="mt-1 inline-flex items-center gap-1.5 rounded-lg border border-app-accent-soft px-3 py-1.5 text-xs font-semibold text-app-accent-text transition-colors hover:bg-app-accent-soft"
              >
                Open Template Studio
              </button>
            </div>
          )}

          {!isLoading && !isEmpty && (
            <div className="space-y-3">
              <div>
                <label
                  htmlFor="template-draft-search"
                  className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-muted"
                >
                  Template
                </label>
                <div className="relative">
                  <LuSearch
                    aria-hidden="true"
                    className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-subtle"
                  />
                  <input
                    id="template-draft-search"
                    ref={searchInputRef}
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyDown={handleSearchKeyDown}
                    placeholder="Search templates…"
                    autoComplete="off"
                    spellCheck={false}
                    className="w-full rounded-lg border border-border bg-surface py-2 pl-8 pr-8 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
                  />
                  {searchQuery && (
                    <button
                      type="button"
                      onClick={() => {
                        setSearchQuery('');
                        searchInputRef.current?.focus();
                      }}
                      aria-label="Clear search"
                      className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-subtle transition-colors hover:bg-surface-muted hover:text-text-secondary"
                    >
                      <LuX className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>

                <ul
                  role="listbox"
                  aria-label="Production-ready templates"
                  className="mt-2 max-h-[260px] overflow-y-auto rounded-lg border border-border bg-surface"
                >
                  {filteredTemplates.length === 0 ? (
                    <li className="px-3 py-3 text-center text-xs text-muted">
                      No templates match “{searchQuery}”.
                    </li>
                  ) : (
                    filteredTemplates.map((t, idx) => {
                      const isPicked = selectedTemplateId === t.id;
                      const isHighlighted = idx === highlightIndex;
                      const companionTotal = t.bundle_companions?.length ?? 0;
                      const subtitle = t.bundle_role === 'parent'
                        ? `Parent · ${companionTotal} ${companionTotal === 1 ? 'companion' : 'companions'}`
                        : 'Standalone';
                      return (
                        <li key={t.id} role="option" aria-selected={isPicked}>
                          <button
                            type="button"
                            onMouseEnter={() => setHighlightIndex(idx)}
                            onClick={() => setSelectedTemplateId(t.id)}
                            className={`flex w-full items-start justify-between gap-3 px-3 py-2 text-left transition-colors ${
                              isPicked
                                ? 'bg-app-accent-soft text-app-accent-text'
                                : isHighlighted
                                  ? 'bg-surface-muted text-text-secondary'
                                  : 'text-text-secondary hover:bg-surface-muted'
                            }`}
                          >
                            <div className="min-w-0 flex-1">
                              <p
                                className={`truncate text-sm ${
                                  isPicked ? 'font-semibold' : 'font-medium'
                                }`}
                              >
                                {t.name}
                              </p>
                              <p className="mt-0.5 truncate text-[11px] text-subtle">
                                {subtitle}
                              </p>
                            </div>
                            {isPicked && (
                              <LuCheck
                                aria-hidden="true"
                                className="mt-1 h-4 w-4 shrink-0 text-app-accent-text"
                              />
                            )}
                          </button>
                        </li>
                      );
                    })
                  )}
                </ul>

                <p className="mt-1 text-[11px] text-subtle">
                  Only templates with a saved agent configuration are shown.
                </p>
              </div>

              {pickedTemplate && (
                <p
                  className="rounded-lg border border-border bg-surface-muted px-3 py-2 text-[11px] text-muted"
                  aria-live="polite"
                >
                  {variableCount} {variableCount === 1 ? 'variable' : 'variables'}
                  <span aria-hidden="true"> · </span>
                  {pickedTemplate.bundle_role === 'parent'
                    ? `Parent · ${companionCount} ${companionCount === 1 ? 'companion' : 'companions'}`
                    : 'Standalone'}
                </p>
              )}
            </div>
          )}
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-border px-6 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-3 py-1.5 text-xs font-semibold text-muted transition-colors hover:bg-surface-muted hover:text-text-secondary"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void handleGenerate()}
            disabled={!selectedTemplateId || !selectedCaseId || isGenerating}
            title={!selectedTemplateId ? 'Select a template to continue.' : undefined}
            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isGenerating ? 'Starting…' : 'Generate draft'}
          </button>
        </footer>
      </div>
    </Modal>
  );
};

export default TemplateDraftModal;
