import React, { useEffect, useMemo, useState, type ReactElement } from 'react';
import { Modal, Tooltip } from '@/components/common';
import { SourcePicker } from '../source-picker/SourcePicker';
import { SourceParamsForm } from '../source-picker/SourceParamsForm';
import { InteractionPatternPicker } from '../source-picker/InteractionPatternPicker';
import { SourceIcon } from '../source-picker/SourceIcon';
import {
  composeSource,
  defaultParamsFor,
  defaultPatternFor,
  familyOf,
  findFamily,
  firstMissingField,
  isSourceParamsValid,
  patternOf,
  type SourceFamilyKey,
} from '@/utils/studio/sourceConfig';
import { useStudioStore } from '@/stores/useStudioStore';
import type {
  FieldSource,
  SourceParams,
  TemplateVariable,
} from '@/types/studio';

interface ConfigureVariableModalProps {
  variable: TemplateVariable | null;
  onClose: () => void;
}

const renderHighlightedMatch = (
  sentence: string,
  marker: string | null,
): React.ReactNode => {
  if (!marker) return <>“{sentence}”</>;
  const idx = sentence.indexOf(marker);
  if (idx === -1) return <>“{sentence}”</>;
  return (
    <>
      “{sentence.slice(0, idx)}
      <mark className="rounded bg-app-accent px-1 font-semibold not-italic text-white">
        {marker}
      </mark>
      {sentence.slice(idx + marker.length)}”
    </>
  );
};

export const ConfigureVariableModal = ({
  variable,
  onClose,
}: ConfigureVariableModalProps): ReactElement => {
  const updateVariable = useStudioStore((state) => state.updateVariable);
  const connectors = useStudioStore((state) => state.connectors);

  const [source, setSource] = useState<FieldSource | null>(null);
  const [sourceParams, setSourceParams] = useState<SourceParams | null>(null);
  const [instruction, setInstruction] = useState<string>('');
  const [outputInstruction, setOutputInstruction] = useState<string>('');
  const [familyKey, setFamilyKey] = useState<SourceFamilyKey | null>(null);
  const [patternKey, setPatternKey] = useState<string | null>(null);

  useEffect(() => {
    if (variable) {
      setSource(variable.source);
      setSourceParams(variable.source_params);
      setInstruction(variable.instruction ?? '');
      setOutputInstruction(variable.output_instruction ?? '');
      setFamilyKey(familyOf(variable.source));
      setPatternKey(patternOf(variable.source));
    }
  }, [variable]);

  const activeConnector = useMemo(
    () => connectors.find((c) => c.source === source),
    [connectors, source]
  );

  const activeFamily = useMemo(() => findFamily(familyKey), [familyKey]);

  const activePattern = useMemo(
    () => (activeFamily && patternKey
      ? activeFamily.patterns.find((p) => p.key === patternKey) ?? null
      : null),
    [activeFamily, patternKey],
  );

  const headerName = activePattern?.label ?? activeConnector?.display_name ?? '';
  const headerDescription = activePattern?.description ?? activeConnector?.description ?? '';

  const handleSelectFamily = (nextFamilyKey: SourceFamilyKey): void => {
    if (nextFamilyKey === familyKey) return;
    const family = findFamily(nextFamilyKey);
    if (!family) return;
    const defaultPattern = defaultPatternFor(family);
    setFamilyKey(nextFamilyKey);
    setPatternKey(defaultPattern.key);
    setSource(defaultPattern.source);
    const defaults = defaultParamsFor(defaultPattern.source);
    setSourceParams(defaults ? seedSmartDefaults(defaults, variable) : defaults);
  };

  const handleSelectPattern = (nextPatternKey: string): void => {
    if (nextPatternKey === patternKey || !familyKey) return;
    const nextSource = composeSource(familyKey, nextPatternKey);
    if (!nextSource) return;
    setPatternKey(nextPatternKey);
    setSource(nextSource);
    const defaults = defaultParamsFor(nextSource);
    setSourceParams(defaults ? seedSmartDefaults(defaults, variable) : defaults);
  };

  const handleSave = (): void => {
    if (!variable) return;
    if (!isSourceParamsValid(source, sourceParams, activeConnector)) return;
    updateVariable(variable.template_variable, {
      source,
      source_params: sourceParams,
      instruction: instruction.trim() ? instruction.trim() : null,
      output_instruction: outputInstruction.trim() ? outputInstruction.trim() : null,
    });
    onClose();
  };

  const missingField = firstMissingField(source, sourceParams, activeConnector);
  const canSave = missingField === null;
  const isReadOnly = variable?.read_only === true;
  const dependentVariableName =
    isReadOnly && variable?.source_params && 'dependent_variable' in variable.source_params
      ? variable.source_params.dependent_variable
      : null;

  return (
    <Modal isOpen={variable !== null} onClose={onClose} size="3xl">
      {variable && (
        <div className="flex max-h-[min(82vh,760px)] flex-col">
          <header className="shrink-0 border-b border-border px-6 py-5 pr-12">
            <p className="text-xs font-semibold uppercase tracking-wider text-app-accent-text">
              Configure Variable
            </p>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <h2 className="font-mono text-lg font-semibold text-text-secondary">
                {variable.template_variable}
              </h2>
              {variable.kind && (
                <Tooltip
                  side="top"
                  delayMs={150}
                  label={
                    variable.kind === 'virtual'
                      ? 'Virtual — has no [[placeholder]] in the docx. Powers auto_derive children but never renders directly.'
                      : 'Physical — fills a [[placeholder]] in the rendered docx.'
                  }
                >
                  <span
                    className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
                      variable.kind === 'virtual'
                        ? 'bg-app-warning-soft text-app-warning-text'
                        : 'bg-app-accent-soft text-app-accent-text'
                    }`}
                  >
                    {variable.kind}
                  </span>
                </Tooltip>
              )}
            </div>
            {variable.description && (
              <p className="mt-1 text-sm text-text-secondary">{variable.description}</p>
            )}
            {variable.template_identifying_text_match && (
              <blockquote className="mt-3 rounded-lg border-l-4 border-app-accent-soft bg-app-accent-soft/50 px-3 py-2 text-xs italic text-text-secondary">
                {renderHighlightedMatch(
                  variable.template_identifying_text_match,
                  variable.template_property_marker,
                )}
              </blockquote>
            )}
          </header>

          {isReadOnly && (
            <div className="shrink-0 border-b border-amber-200 bg-amber-50/70 px-6 py-3">
              <div className="flex items-start gap-2.5">
                <svg
                  aria-hidden="true"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="mt-0.5 h-4 w-4 shrink-0 text-amber-700"
                >
                  <rect x="4" y="11" width="16" height="10" rx="2" />
                  <path d="M8 11V7a4 4 0 1 1 8 0v4" />
                </svg>
                <p className="text-xs leading-relaxed text-amber-900">
                  <span className="font-semibold">Read-only.</span> This variable
                  is auto-derived
                  {dependentVariableName ? (
                    <>
                      {' '}from{' '}
                      <code className="rounded bg-amber-100 px-1 py-0.5 font-mono text-[11px]">
                        {dependentVariableName}
                      </code>
                    </>
                  ) : null}{' '}
                  by the template agent. To change the derivation, regenerate the
                  template.
                </p>
              </div>
            </div>
          )}

          <div className="flex min-h-0 flex-1 flex-col md:flex-row">
            <aside
              className={`flex max-h-[40vh] min-h-0 shrink-0 flex-col border-b border-border md:max-h-none md:w-[320px] md:border-b-0 md:border-r ${
                isReadOnly ? 'pointer-events-none opacity-60' : ''
              }`}
              aria-disabled={isReadOnly}
            >
              <SourcePicker
                familyKey={familyKey}
                onSelectFamily={handleSelectFamily}
              />
            </aside>

            <section
              className={`min-h-0 flex-1 overflow-y-auto ${
                isReadOnly ? 'pointer-events-none opacity-60' : ''
              }`}
              aria-disabled={isReadOnly}
            >
              {source ? (
                <fieldset disabled={isReadOnly} className="contents">
                  <div className="space-y-5 px-6 py-5">
                    {activeConnector && (
                      <div className="-mx-2 flex items-start gap-3 rounded-lg bg-surface-muted px-3 py-2.5">
                        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-surface text-app-accent-text shadow-sm ring-1 ring-gray-200">
                          <SourceIcon source={activeConnector.source} className="h-4 w-4" />
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5">
                            <p className="text-sm font-semibold text-text-secondary">
                              {headerName}
                            </p>
                            <Tooltip
                              side="top"
                              delayMs={150}
                              label={headerDescription}
                            >
                              <span
                                tabIndex={0}
                                aria-label={`About ${headerName}`}
                                className="grid h-3.5 w-3.5 cursor-help place-items-center rounded-full text-subtle hover:text-text-secondary focus:outline-none focus-visible:ring-2 focus-visible:ring-app-accent-soft"
                              >
                                <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                </svg>
                              </span>
                            </Tooltip>
                          </div>
                          <p className="mt-0.5 truncate text-xs text-muted">
                            {headerDescription.split('. ')[0]}
                            {headerDescription.includes('. ') ? '.' : ''}
                          </p>
                        </div>
                      </div>
                    )}

                    {activeFamily && activeFamily.patterns.length > 1 && patternKey && (
                      <InteractionPatternPicker
                        family={activeFamily}
                        selectedKey={patternKey}
                        onSelect={handleSelectPattern}
                      />
                    )}

                    <SourceParamsForm
                      source={source}
                      sourceParams={sourceParams}
                      onChange={setSourceParams}
                      variableName={variable.template_variable}
                    />

                    <div className="border-t border-dashed border-border pt-4">
                      <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-text-secondary">
                        Extraction instruction
                      </label>
                      <p className="mb-1 text-[11px] leading-snug text-subtle">
                        For the EXTRACTION agents (DraftAgent / vision / chips / dropdown / multi-select extractors). What to pull from the raw source data. Web-search-enhance does NOT read this — use "Web search instruction" on the source params for that.
                      </p>
                      <textarea
                        rows={2}
                        value={instruction}
                        onChange={(e) => setInstruction(e.target.value)}
                        placeholder="Optional — e.g. 'extract Document Number from email body', 'use SOFA Q9 not Q3', 'extract county only — circuit number is looked up via web search'"
                        className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
                      />
                    </div>

                    <div className="pt-2">
                      <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-text-secondary">
                        Document output instruction
                      </label>
                      <p className="mb-1 text-[11px] leading-snug text-subtle">
                        Rules for the FINAL DOCX OUTPUT shape. Surfaced as authoritative to whichever agent is responsible for final shaping — the heal pass for chip / dropdown / multi-select / plain-text picks, and the web-search-enhance agent for case_vector + web search.
                      </p>
                      <textarea
                        rows={2}
                        value={outputInstruction}
                        onChange={(e) => setOutputInstruction(e.target.value)}
                        placeholder="Optional — e.g. 'PAST TENSE ONLY', 'Predicate-only — drop The Debtor subject (already in docx)', 'Use ordinal form for circuit numbers'"
                        className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
                      />
                    </div>
                  </div>
                </fieldset>
              ) : (
                <EmptyState />
              )}
            </section>
          </div>

          <footer className="flex shrink-0 items-center justify-between gap-2 border-t border-border bg-surface-muted px-6 py-4">
            <div className="hidden min-w-0 items-center gap-2 text-xs text-text-secondary sm:flex">
              {isReadOnly ? (
                <span>Read-only — close to dismiss.</span>
              ) : canSave ? (
                <>
                  <svg
                    className="h-3.5 w-3.5 shrink-0 text-app-success-text"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={2.5}
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                  <span>Ready to save.</span>
                </>
              ) : !source ? (
                <span>Pick a source to get started.</span>
              ) : (
                <>
                  <span
                    aria-hidden="true"
                    className="grid h-4 w-4 shrink-0 place-items-center rounded-full bg-app-warning-soft text-[10px] font-bold text-app-warning-text"
                  >
                    !
                  </span>
                  <span className="truncate">
                    <span className="font-semibold text-text-secondary">{missingField}</span>{' '}
                    is required to save.
                  </span>
                </>
              )}
            </div>
            <div className="ml-auto flex items-center gap-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg border border-border bg-surface px-4 py-2 text-sm text-text-secondary hover:bg-surface-muted"
              >
                {isReadOnly ? 'Close' : 'Cancel'}
              </button>
              {!isReadOnly && (
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={!canSave}
                  className="rounded-lg bg-gradient-to-r from-indigo-600 to-purple-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:from-indigo-700 hover:to-purple-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Save Variable
                </button>
              )}
            </div>
          </footer>
        </div>
      )}
    </Modal>
  );
};

const seedSmartDefaults = (
  params: SourceParams,
  variable: TemplateVariable | null
): SourceParams => {
  if (!variable) return params;
  const seeded = { ...params } as Record<string, unknown>;

  if ('label' in seeded && (!seeded.label || (typeof seeded.label === 'string' && seeded.label.trim() === ''))) {
    const description = variable.description?.trim();
    if (description) seeded.label = description;
  }

  if (
    'example_format' in seeded &&
    (!seeded.example_format ||
      (typeof seeded.example_format === 'string' && seeded.example_format.trim() === ''))
  ) {
    const sample = variable.template_property_marker?.trim();
    if (sample) seeded.example_format = sample;
  }

  return seeded as SourceParams;
};

const EmptyState = (): ReactElement => (
  <div className="flex h-full min-h-[260px] flex-col items-center justify-center px-8 py-10 text-center">
    <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-app-accent-soft text-app-accent-text">
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.8}
        className="h-6 w-6"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2m-6 9 2 2 4-4"
        />
      </svg>
    </div>
    <p className="text-sm font-semibold text-text-secondary">Pick a source to configure</p>
    <p className="mt-1 max-w-xs text-xs leading-relaxed text-text-secondary">
      Choose where this variable’s value should come from. You can search or
      browse by category on the left.
    </p>
  </div>
);

export default ConfigureVariableModal;
