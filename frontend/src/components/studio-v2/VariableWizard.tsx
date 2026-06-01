import { useEffect, useMemo, useState } from 'react';
import { FiChevronLeft, FiChevronRight } from 'react-icons/fi';
import { Modal } from '@/components/common';
import { cn } from '@/utils';
import { StepIndicator } from './StepIndicator';
import { SourceStep } from './steps/SourceStep';
import { ExtractionPromptStep } from './steps/ExtractionPromptStep';
import { UserInputStep } from './steps/UserInputStep';
import { RefinementStep } from './steps/RefinementStep';
import { PreviewStep } from './steps/PreviewStep';
import {
  SOURCE_KINDS,
  defaultWizardParams,
  type AuthorInputKind,
  type StudioVariable,
  type PresentationShape,
  type SourceKind,
  type WizardSourceParams,
} from './types';

const friendlyVarName = (variableName: string): string =>
  variableName.replace(/_/g, ' ');

const generateDefaultLabel = (
  variable: StudioVariable,
  source: SourceKind,
  authorInputKind: AuthorInputKind | null,
): string => {
  const friendly = friendlyVarName(variable.template_variable);
  if (source === 'author_input') {
    if (authorInputKind === 'date') return `Pick the ${friendly}`;
    if (authorInputKind === 'with_docs')
      return `Enter the ${friendly} and attach supporting docs`;
    return `Enter the ${friendly}`;
  }
  return `Pick the ${friendly}`;
};

const requiresLabelFor = (params: WizardSourceParams): boolean => {
  if (params.source === 'author_input') return true;
  const meta = SOURCE_KINDS.find((s) => s.key === params.source);
  return Boolean(meta?.acceptsShape) && params.presentation_shape !== 'raw';
};

interface VariableWizardProps {
  variable: StudioVariable | null;
  allVariableNames: string[];
  onClose: () => void;
  onSave: (variableName: string, params: WizardSourceParams) => void;
}

interface StepDef {
  key: 'source' | 'extraction' | 'user_input' | 'refinement' | 'preview';
  label: string;
  description: string;
}

const ALL_STEPS: StepDef[] = [
  { key: 'source', label: 'Source', description: 'Where from' },
  { key: 'extraction', label: 'Find', description: 'What to look for' },
  { key: 'user_input', label: 'Choose', description: 'How you pick' },
  { key: 'refinement', label: 'Fine-tune', description: 'Optional' },
  { key: 'preview', label: 'Preview', description: 'Confirm' },
];

const computeSteps = (params: WizardSourceParams): StepDef[] => {
  const meta = SOURCE_KINDS.find((s) => s.key === params.source)!;
  return ALL_STEPS.filter((step) => {
    if (step.key === 'extraction') return meta.needsExtractionPrompt;
    if (step.key === 'user_input') {
      return meta.acceptsShape || params.source === 'author_input';
    }
    return true;
  });
};

export const VariableWizard = ({
  variable,
  allVariableNames,
  onClose,
  onSave,
}: VariableWizardProps) => {
  const [params, setParams] = useState<WizardSourceParams>(defaultWizardParams);
  const [stepIndex, setStepIndex] = useState(0);
  // Highest step the user has reached this session. Drives which steps in the
  // top indicator are clickable for jump-back / jump-forward navigation.
  const [maxReachedStep, setMaxReachedStep] = useState(1);

  // Reset only when the SELECTED variable's identity changes — keying off
  // the variable NAME (and a null/non-null toggle for unsaved-vs-saved).
  // We deliberately do NOT depend on the `variable` object reference: the
  // store rebuilds every `StudioVariable` on any field save (and on lazy
  // refetches), and a re-render with the SAME variable selected would
  // otherwise reset the wizard's local state — losing the paralegal's
  // in-progress edits + flashing the doc back to step 1.
  const variableName = variable?.template_variable ?? null;
  useEffect(() => {
    if (!variable) return;
    const base = variable.params ?? defaultWizardParams();
    // Auto-fill the label when this template variable's params are loaded
    // into a user-input shape but the label hasn't been set yet — paralegals
    // can't be left staring at a picker without a question prompt.
    const enrichedLabel =
      requiresLabelFor(base) && !base.label?.trim()
        ? generateDefaultLabel(variable, base.source, base.author_input_kind)
        : base.label;
    const nextParams = { ...base, label: enrichedLabel };
    setParams(nextParams);
    setStepIndex(0);
    // Variables that already have a saved `params` (re-opening a configured
    // field) get FULL step navigation immediately — no point gating
    // jump-to-step behind a "click Next first" wall when every step already
    // has data to render. Fresh variables (no saved params) start gated
    // at step 1 so the paralegal walks the wizard in order.
    const stepsForParams = computeSteps(nextParams);
    setMaxReachedStep(
      variable.params !== null ? stepsForParams.length : 1,
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [variableName]);

  useEffect(() => {
    setMaxReachedStep((prev) => Math.max(prev, stepIndex + 1));
  }, [stepIndex]);

  const steps = useMemo(() => computeSteps(params), [params]);
  const currentStep = steps[stepIndex] ?? steps[steps.length - 1];

  const handlePatch = (patch: Partial<WizardSourceParams>) => {
    setParams((prev) => ({ ...prev, ...patch }));
  };

  const handleSourceChange = (source: SourceKind) => {
    const fresh = defaultWizardParams();
    fresh.source = source;
    if (source === 'author_input') {
      fresh.author_input_kind = 'plain_text';
    }
    if (variable && requiresLabelFor(fresh)) {
      fresh.label = generateDefaultLabel(
        variable,
        fresh.source,
        fresh.author_input_kind,
      );
    }
    setParams(fresh);
    setStepIndex(0);
    // Source change picks new step list — invalidate previously-reached state.
    setMaxReachedStep(1);
  };

  const handleStepJump = (targetIndex: number): void => {
    if (targetIndex < 0 || targetIndex >= steps.length) return;
    if (targetIndex > maxReachedStep - 1) return;
    setStepIndex(targetIndex);
  };

  const handleShapeChange = (shape: PresentationShape) => {
    setParams((prev) => {
      const next: WizardSourceParams = { ...prev, presentation_shape: shape };
      if (variable && requiresLabelFor(next) && !next.label?.trim()) {
        next.label = generateDefaultLabel(
          variable,
          next.source,
          next.author_input_kind,
        );
      }
      return next;
    });
  };

  const handleAuthorKindChange = (kind: AuthorInputKind) => {
    setParams((prev) => {
      const next: WizardSourceParams = { ...prev, author_input_kind: kind };
      if (variable && requiresLabelFor(next) && !next.label?.trim()) {
        next.label = generateDefaultLabel(variable, next.source, kind);
      }
      return next;
    });
  };

  const needsLabel = requiresLabelFor(params);
  const hasValidLabel = (params.label ?? '').trim().length > 0;
  const labelOk = !needsLabel || hasValidLabel;

  const canAdvance = (() => {
    if (currentStep.key === 'extraction') {
      return (params.extraction_prompt ?? '').trim().length > 0;
    }
    if (currentStep.key === 'user_input' && params.source === 'author_input') {
      return params.author_input_kind !== null;
    }
    if (currentStep.key === 'refinement' && !labelOk) {
      return false;
    }
    return true;
  })();

  const handleNext = () => {
    if (stepIndex < steps.length - 1) {
      setStepIndex(stepIndex + 1);
    }
  };

  const handleBack = () => {
    if (stepIndex > 0) {
      setStepIndex(stepIndex - 1);
    }
  };

  const handleSave = () => {
    if (!variable) return;
    if (!labelOk) return;
    onSave(variable.template_variable, params);
    onClose();
  };

  if (!variable) return null;

  return (
    <Modal isOpen onClose={onClose} size="3xl" closeOnBackdropClick={false}>
      <div className="flex max-h-[min(85vh,780px)] flex-col">
        <header className="shrink-0 border-b border-border px-6 py-5 pr-12">
          <p className="text-xs font-semibold uppercase tracking-wider text-app-accent-text">
            Set up this field
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <h2 className="font-mono text-lg font-semibold text-text-secondary">
              {variable.template_variable}
            </h2>
          </div>
          {variable.description && (
            <p className="mt-1 text-sm text-text-secondary">{variable.description}</p>
          )}
          {variable.template_identifying_text_match && (
            <blockquote className="mt-3 rounded-lg border-l-4 border-app-accent-soft bg-app-accent-soft/50 px-3 py-2 text-xs italic text-text-secondary">
              "{variable.template_identifying_text_match}"
            </blockquote>
          )}
        </header>

        <div className="shrink-0 border-b border-border bg-surface-muted/40 px-6 py-4">
          <StepIndicator
            currentStep={stepIndex + 1}
            steps={steps}
            maxReachedStep={maxReachedStep}
            onStepClick={handleStepJump}
          />
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          {currentStep.key === 'source' && (
            <SourceStep
              selectedSource={params.source}
              onSelectSource={handleSourceChange}
            />
          )}
          {currentStep.key === 'extraction' && (
            <ExtractionPromptStep
              source={params.source}
              extractionPrompt={params.extraction_prompt ?? ''}
              queryDependencies={params.query_dependencies}
              dependentVariable={params.dependent_variable}
              availableVariableNames={allVariableNames}
              currentVariableName={variable.template_variable}
              onChange={(value) =>
                handlePatch({ extraction_prompt: value || null })
              }
              onChangeDependencies={(deps) =>
                handlePatch({ query_dependencies: deps })
              }
              onChangeDependentVariable={(name) =>
                handlePatch({ dependent_variable: name })
              }
            />
          )}
          {currentStep.key === 'user_input' && (
            <UserInputStep
              source={params.source}
              presentationShape={params.presentation_shape}
              authorInputKind={params.author_input_kind}
              onChangePresentationShape={handleShapeChange}
              onChangeAuthorInputKind={handleAuthorKindChange}
            />
          )}
          {currentStep.key === 'refinement' && (
            <RefinementStep
              params={params}
              variable={variable}
              onChange={handlePatch}
            />
          )}
          {currentStep.key === 'preview' && (
            <PreviewStep variable={variable} params={params} />
          )}
        </div>

        <footer className="flex shrink-0 items-center justify-between gap-3 border-t border-border bg-surface px-6 py-4">
          <button
            type="button"
            onClick={handleBack}
            disabled={stepIndex === 0}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
              stepIndex === 0
                ? 'cursor-not-allowed text-subtle'
                : 'cursor-pointer text-text-secondary hover:bg-surface-muted',
            )}
          >
            <FiChevronLeft className="h-4 w-4" />
            Back
          </button>
          <p className="text-xs text-subtle">
            Step {stepIndex + 1} of {steps.length}
          </p>
          {stepIndex < steps.length - 1 ? (
            <button
              type="button"
              onClick={handleNext}
              disabled={!canAdvance}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold transition-colors',
                canAdvance
                  ? 'cursor-pointer bg-app-accent text-white hover:opacity-90'
                  : 'cursor-not-allowed bg-surface-muted text-subtle',
              )}
            >
              Next
              <FiChevronRight className="h-4 w-4" />
            </button>
          ) : (
            <button
              type="button"
              onClick={handleSave}
              disabled={!labelOk}
              className={cn(
                'rounded-lg px-4 py-2 text-sm font-semibold transition-opacity',
                labelOk
                  ? 'cursor-pointer bg-app-accent text-white hover:opacity-90'
                  : 'cursor-not-allowed bg-surface-muted text-subtle',
              )}
            >
              Save this field
            </button>
          )}
        </footer>
      </div>
    </Modal>
  );
};
