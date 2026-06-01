import { cn } from '@/utils';
import { MOCK_ATTORNEYS, MOCK_FIRM_CONSTANTS } from '../mockData';
import type { StudioVariable, WizardSourceParams } from '../types';

interface RefinementStepProps {
  params: WizardSourceParams;
  variable: StudioVariable;
  onChange: (patch: Partial<WizardSourceParams>) => void;
}

const Field = ({
  label,
  hint,
  required,
  error,
  children,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  error?: string | null;
  children: React.ReactNode;
}) => (
  <div className="space-y-1.5">
    <label className="text-xs font-semibold uppercase tracking-wider text-subtle">
      {label}
      {required && (
        <span className="ml-1 text-app-danger-text" aria-label="required">
          *
        </span>
      )}
    </label>
    {children}
    {error ? (
      <p className="text-[11px] font-medium text-app-danger-text">{error}</p>
    ) : (
      hint && <p className="text-[11px] text-subtle">{hint}</p>
    )}
  </div>
);

const textInputClass =
  'w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent/20';

export const RefinementStep = ({
  params,
  variable,
  onChange,
}: RefinementStepProps) => {
  const isUserPick =
    params.source !== 'author_input' &&
    params.source !== 'current_date' &&
    params.source !== 'derived_from_variable' &&
    params.source !== 'value_from_parent_bundle' &&
    params.presentation_shape !== 'raw';

  const isAuthorInput = params.source === 'author_input';
  const labelRequired = isUserPick || isAuthorInput;
  const labelEmpty = !(params.label ?? '').trim();
  const labelError = labelRequired && labelEmpty
    ? 'Required — paralegals need a prompt above the input.'
    : null;
  const labelHint = isAuthorInput
    ? "The prompt you'll see above the input when drafting."
    : "The label you'll see above the choices when drafting.";

  const showOutputExpectation =
    params.source === 'gmail' ||
    params.source === 'case_file' ||
    params.source === 'derived_from_variable' ||
    params.source === 'author_input';

  // Web enhancement applies to sources where the resolved value
  // comes from an upstream extraction or transform — exactly the
  // same set as `showOutputExpectation`. Deterministic sources
  // (constants / current_date / attorney / value_from_parent_bundle)
  // skip the affordance.
  const showWebEnhance = showOutputExpectation;
  const webEnhanceEnabled = params.web_enhance_instruction !== null;

  // Date format is never user-configurable. Every date-shaped value in the
  // firm flows through the BE's date-healing layer and ends up in the
  // canonical `%B %-d, %Y` format. No format input anywhere in the wizard.

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold text-text-secondary">
          Fine-tune the result (optional)
        </h3>
        <p className="mt-1 text-sm text-subtle">
          Adjust labels and formatting. The defaults work for most fields — feel free to skip.
        </p>
      </div>

      <div className="space-y-4 rounded-lg border border-border bg-surface-muted/40 p-4">
        {labelRequired && (
          <Field
            label="Question shown to you"
            required
            hint={labelHint}
            error={labelError}
          >
            <input
              type="text"
              value={params.label ?? ''}
              onChange={(e) => onChange({ label: e.target.value || null })}
              placeholder={
                isAuthorInput
                  ? `Enter the ${variable.template_variable.replace(/_/g, ' ')}`
                  : `Pick the ${variable.template_variable.replace(/_/g, ' ')}`
              }
              className={cn(
                textInputClass,
                labelError && 'border-app-danger-text focus:border-app-danger-text focus:ring-app-danger-text/20',
              )}
            />
          </Field>
        )}

        {isUserPick && (
          <>
            <Field
              label="Example of one choice"
              hint="Write one sample option here — the agent will shape every choice in the list to look like it."
            >
              <input
                type="text"
                value={params.example_format ?? ''}
                onChange={(e) => onChange({ example_format: e.target.value || null })}
                placeholder="e.g. Acme Bank — $1,200"
                className={textInputClass}
              />
            </Field>
            {params.presentation_shape === 'multi_select' && (
              <div className="grid grid-cols-2 gap-3">
                <Field label="Minimum picks">
                  <input
                    type="number"
                    min={1}
                    max={20}
                    value={params.min_picks}
                    onChange={(e) =>
                      onChange({ min_picks: Math.max(1, parseInt(e.target.value, 10) || 1) })
                    }
                    className={textInputClass}
                  />
                </Field>
                <Field label="Maximum picks">
                  <input
                    type="number"
                    min={1}
                    max={20}
                    value={params.max_picks}
                    onChange={(e) =>
                      onChange({ max_picks: Math.max(1, parseInt(e.target.value, 10) || 5) })
                    }
                    className={textInputClass}
                  />
                </Field>
              </div>
            )}
          </>
        )}

        {showOutputExpectation && (
          <Field
            label="How should the final value look?"
            hint="Any formatting rules for what gets inserted into the document."
          >
            <textarea
              value={params.output_expectation ?? ''}
              onChange={(e) =>
                onChange({ output_expectation: e.target.value || null })
              }
              placeholder="e.g. all lowercase, no trailing period"
              rows={2}
              className={`${textInputClass} resize-none`}
            />
          </Field>
        )}

        {showWebEnhance && (
          <Field
            label="Double-check this online?"
            hint="The AI runs a web search to look up missing public details and update the value. Slower and a bit costly — flip on only when public information fills in a gap."
          >
            <label className="flex cursor-pointer items-start gap-2 text-sm text-text-secondary">
              <input
                type="checkbox"
                checked={webEnhanceEnabled}
                onChange={(e) =>
                  onChange({
                    web_enhance_instruction: e.target.checked ? '' : null,
                  })
                }
                className="mt-0.5 h-4 w-4 cursor-pointer accent-app-accent"
              />
              <span>
                Look this value up online before writing it into the document.
              </span>
            </label>
            {webEnhanceEnabled && (
              <div className="mt-3 space-y-1">
                <p className="text-xs font-medium text-text-secondary">
                  What should the AI look up?
                </p>
                <textarea
                  value={params.web_enhance_instruction ?? ''}
                  onChange={(e) =>
                    onChange({ web_enhance_instruction: e.target.value })
                  }
                  placeholder="e.g. Confirm this is the 17th Judicial Circuit for Broward County, FL"
                  rows={3}
                  className={`${textInputClass} resize-none`}
                />
                <p className="text-[11px] italic text-subtle">
                  If the search comes up empty or unclear, the AI keeps the
                  value as-is.
                </p>
              </div>
            )}
          </Field>
        )}

        {params.source === 'constants' && (
          <Field
            label="Which firm constant to use"
            hint="Pick the saved firm value this field should resolve to."
          >
            <select
              value={params.constants_short_code ?? ''}
              onChange={(e) =>
                onChange({ constants_short_code: e.target.value || null })
              }
              className={textInputClass}
            >
              <option value="">— select a constant —</option>
              {MOCK_FIRM_CONSTANTS.map((c) => (
                <option key={c.short_code} value={c.short_code}>
                  {c.display_name}
                </option>
              ))}
            </select>
            {params.constants_short_code && (
              <div className="mt-2 rounded-md border border-border bg-surface px-3 py-2 text-[11px] text-text-secondary">
                {(() => {
                  const c = MOCK_FIRM_CONSTANTS.find(
                    (k) => k.short_code === params.constants_short_code,
                  );
                  if (!c) return null;
                  return (
                    <>
                      <p className="font-mono text-[10px] text-subtle">
                        {c.short_code}
                      </p>
                      <p className="mt-0.5 italic">"{c.value}"</p>
                      {c.description && (
                        <p className="mt-1 text-subtle">{c.description}</p>
                      )}
                    </>
                  );
                })()}
              </div>
            )}
          </Field>
        )}

        {params.source === 'attorney' && params.presentation_shape === 'raw' && (
          <Field
            label="Which attorney"
            hint="The same attorney will be used every time this template runs."
          >
            <select
              value={params.attorney_id ?? ''}
              onChange={(e) =>
                onChange({ attorney_id: e.target.value || null })
              }
              className={textInputClass}
            >
              <option value="">— select an attorney —</option>
              {MOCK_ATTORNEYS.map((att) => (
                <option key={att.id} value={att.id}>
                  {att.display_name} · {att.bar_number}
                </option>
              ))}
            </select>
          </Field>
        )}

        {/* derived_from_variable's "which field to base this on" picker
            lives in the Find step (ExtractionPromptStep), alongside the
            extraction prompt — both are REQUIRED to make the derive
            agent work, so they belong together. Don't duplicate the
            picker here. */}

        {params.source === 'value_from_parent_bundle' && (
          <Field
            label="Fallback value"
            hint="Used if the lead filing hasn't filled this in yet."
          >
            <input
              type="text"
              value={params.parent_bundle_fallback ?? ''}
              onChange={(e) =>
                onChange({ parent_bundle_fallback: e.target.value || null })
              }
              placeholder="e.g. TBD"
              className={textInputClass}
            />
          </Field>
        )}

        {!labelRequired &&
          !showOutputExpectation &&
          params.source !== 'constants' &&
          params.source !== 'attorney' &&
          params.source !== 'derived_from_variable' &&
          params.source !== 'value_from_parent_bundle' && (
            <p className="text-xs italic text-subtle">
              Nothing to adjust here — click Next to see the preview.
            </p>
          )}
      </div>
    </div>
  );
};
