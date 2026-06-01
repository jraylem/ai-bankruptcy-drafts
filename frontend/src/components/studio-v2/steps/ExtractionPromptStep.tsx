import { FiX } from 'react-icons/fi';
import { SOURCE_KINDS, type SourceKind } from '../types';

interface ExtractionPromptStepProps {
  source: SourceKind;
  extractionPrompt: string;
  queryDependencies: string[];
  dependentVariable: string | null;
  availableVariableNames: string[];
  currentVariableName: string;
  onChange: (value: string) => void;
  onChangeDependencies: (deps: string[]) => void;
  onChangeDependentVariable: (name: string | null) => void;
}

const PLACEHOLDERS: Partial<Record<SourceKind, string>> = {
  gmail: 'e.g. the debtor\'s monthly income from the most recent paystub email',
  case_file: 'e.g. creditors with claims over $1,000',
  derived_from_variable:
    'e.g. add 14 days to the parent date — that becomes the deadline',
};

const SUPPORTS_DEPENDENCIES = (source: SourceKind): boolean =>
  source === 'gmail' || source === 'case_file';

export const ExtractionPromptStep = ({
  source,
  extractionPrompt,
  queryDependencies,
  dependentVariable,
  availableVariableNames,
  currentVariableName,
  onChange,
  onChangeDependencies,
  onChangeDependentVariable,
}: ExtractionPromptStepProps) => {
  const sourceMeta = SOURCE_KINDS.find((s) => s.key === source);
  const placeholder = PLACEHOLDERS[source] ?? 'Describe what to find in plain language.';
  const supportsDeps = SUPPORTS_DEPENDENCIES(source);
  const isDerived = source === 'derived_from_variable';

  const parentCandidates = availableVariableNames.filter(
    (name) => name !== currentVariableName,
  );
  const addable = availableVariableNames.filter(
    (name) => name !== currentVariableName && !queryDependencies.includes(name),
  );
  const hasAnyOtherFields =
    addable.length > 0 || queryDependencies.length > 0;

  const handlePick = (name: string): void => {
    if (!name) return;
    if (queryDependencies.includes(name)) return;
    onChangeDependencies([...queryDependencies, name]);
  };

  const handleRemove = (name: string): void => {
    onChangeDependencies(queryDependencies.filter((d) => d !== name));
  };

  const formatDependencyList = (names: string[]): string => {
    if (names.length === 0) return '';
    if (names.length === 1) return names[0];
    if (names.length === 2) return `${names[0]} and ${names[1]}`;
    return `${names.slice(0, -1).join(', ')}, and ${names[names.length - 1]}`;
  };

  return (
    <div className="space-y-5">
      {isDerived && (
        <div className="space-y-2">
          <h3 className="text-base font-semibold text-text-secondary">
            Which field should this be based on?{' '}
            <span className="text-app-danger-text" aria-label="required">*</span>
          </h3>
          {parentCandidates.length === 0 ? (
            <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              No other fields exist in this template yet — add at least one
              other variable before binding this field to "Based on another field".
            </p>
          ) : (
            <select
              value={dependentVariable ?? ''}
              onChange={(e) =>
                onChangeDependentVariable(e.target.value || null)
              }
              className="w-full rounded-lg border border-border bg-surface px-3 py-2.5 text-sm text-text-secondary focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent/20"
            >
              <option value="">— pick a field to base this on —</option>
              {parentCandidates.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          )}
          <p className="text-[11px] text-subtle">
            At draft time, the agent reads the resolved value of this parent
            field and uses your instruction below to compute this one.
          </p>
        </div>
      )}

      <div className="space-y-2">
        <h3 className="text-base font-semibold text-text-secondary">
          {isDerived
            ? 'How should we derive the value from that field?'
            : `What should we look for${sourceMeta ? ` in ${sourceMeta.label.toLowerCase()}` : ''}?`}
        </h3>
        <textarea
          value={extractionPrompt}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          rows={3}
          className="w-full resize-y rounded-lg border border-border bg-surface px-3 py-2.5 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent/20"
        />
        <p className="text-[11px] text-subtle">
          {isDerived
            ? <>Plain-language instruction. e.g. <em>"add 14 days to the parent date"</em> or <em>"return 'are' if the parent value lists multiple items, otherwise 'is'"</em>.</>
            : <>Plain language is fine. Add a cue like <em>"the most recent"</em> if more than one could match.</>}
        </p>
      </div>

      {supportsDeps && hasAnyOtherFields && (
        <div className="space-y-2">
          <h3 className="text-base font-semibold text-text-secondary">
            Does this depend on another field?{' '}
            <span className="font-normal text-subtle">(optional)</span>
          </h3>
          {addable.length > 0 && (
            <select
              value=""
              onChange={(e) => {
                handlePick(e.target.value);
                e.target.value = '';
              }}
              className="w-full rounded-lg border border-border bg-surface px-3 py-2.5 text-sm text-text-secondary focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent/20"
            >
              <option value="">
                {queryDependencies.length === 0
                  ? 'Pick a field this one depends on…'
                  : 'Add another field…'}
              </option>
              {addable.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          )}
          {queryDependencies.length > 0 && (
            <div className="space-y-1.5 pt-1">
              <div className="flex flex-wrap gap-1.5">
                {queryDependencies.map((name) => (
                  <span
                    key={name}
                    className="inline-flex items-center gap-1 rounded-full border border-app-accent/30 bg-app-accent-soft px-2.5 py-1 font-mono text-[12px] text-app-accent-text"
                  >
                    {name}
                    <button
                      type="button"
                      onClick={() => handleRemove(name)}
                      className="cursor-pointer rounded-full p-0.5 hover:bg-app-accent/20"
                      aria-label={`Remove ${name}`}
                    >
                      <FiX className="h-3 w-3" />
                    </button>
                  </span>
                ))}
              </div>
              <p className="text-[11px] italic text-subtle">
                Agent will reference{' '}
                <span className="font-mono not-italic">
                  {formatDependencyList(queryDependencies)}
                </span>{' '}
                during the run.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
