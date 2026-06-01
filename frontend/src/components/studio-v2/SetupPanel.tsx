import { useMemo, useState } from 'react';
import {
  FiAlertCircle,
  FiAlertTriangle,
  FiCheckCircle,
  FiCircle,
  FiLayers,
  FiPlay,
  FiRefreshCw,
  FiTrash2,
  FiX,
} from 'react-icons/fi';
import { cn } from '@/utils';
import { CompanionsModal } from './CompanionsModal';
import { DeleteTemplateModal } from './DeleteTemplateModal';
import { PublishStep } from './PublishStep';
import { SourceIcon } from './SourceIcon';
import { TemplateRolePicker } from './TemplateRolePicker';
import {
  PRESENTATION_SHAPES,
  SOURCE_KINDS,
  type BundleCompanion,
  type StudioTemplate,
  type StudioVariable,
  type TemplateConfig,
  type WizardSourceParams,
} from './types';

interface SetupPanelProps {
  templateName: string;
  templateConfig: TemplateConfig;
  variables: StudioVariable[];
  /** True while `GET /templates/{id}` is in flight to refresh this
   * template's full field list. Drives a skeleton state under the
   * Fields header so paralegals don't see fields blink-fill silently
   * after the lazy fetch completes. */
  isFieldsLoading?: boolean;
  highlightedVariableName: string | null;
  allTemplates: StudioTemplate[];
  currentTemplateId: string;
  publishedAt: string | null;
  hasUnpublishedChanges: boolean;
  bundlingStatus?: 'idle' | 'saving' | 'saved' | 'error';
  roleStatus?: 'idle' | 'saving' | 'saved' | 'error';
  roleLastSavedAt?: number | null;
  roleError?: string | null;
  onDismissRoleError?: () => void;
  onChangeConfig: (patch: Partial<TemplateConfig>) => void;
  onSelectVariable: (variableName: string) => void;
  onHoverVariable: (variableName: string | null) => void;
  onCreateTemplate: (name: string) => string;
  onPublishClick: () => void;
  isPublishing?: boolean;
  publishValidationErrors?: string[];
  onDismissPublishValidationErrors?: () => void;
  onDeleteTemplate?: () => Promise<void>;
  onRegenerateClick?: () => void;
  onTestAgainstCaseClick?: () => void;
}

const summarizeParams = (params: WizardSourceParams | null): string => {
  if (!params) return 'Not set up yet';
  const sourceMeta = SOURCE_KINDS.find((s) => s.key === params.source);
  const shapeMeta = PRESENTATION_SHAPES.find((s) => s.key === params.presentation_shape);
  const parts: string[] = [sourceMeta?.label ?? params.source];
  if (sourceMeta?.acceptsShape && params.presentation_shape !== 'raw') {
    parts.push(shapeMeta?.label ?? params.presentation_shape);
  }
  if (params.source === 'author_input' && params.author_input_kind) {
    parts.push(params.author_input_kind.replace(/_/g, ' '));
  }
  return parts.join(' · ');
};

export const SetupPanel = ({
  templateName,
  templateConfig,
  variables,
  isFieldsLoading = false,
  highlightedVariableName,
  allTemplates,
  currentTemplateId,
  publishedAt,
  hasUnpublishedChanges,
  onChangeConfig,
  onSelectVariable,
  onHoverVariable,
  onCreateTemplate,
  onPublishClick,
  isPublishing = false,
  publishValidationErrors = [],
  onDismissPublishValidationErrors,
  onDeleteTemplate,
  onRegenerateClick,
  onTestAgainstCaseClick,
  bundlingStatus = 'idle',
  roleStatus = 'idle',
  roleLastSavedAt = null,
  roleError = null,
  onDismissRoleError,
}: SetupPanelProps) => {
  const configuredCount = variables.filter((v) => v.params !== null).length;
  const [isCompanionsModalOpen, setIsCompanionsModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);

  const handleCompanionsChange = (companions: BundleCompanion[]): void => {
    onChangeConfig({ companions });
  };

  const handleConfirmDelete = async (): Promise<void> => {
    if (!onDeleteTemplate) return;
    await onDeleteTemplate();
    setIsDeleteModalOpen(false);
  };

  return (
    <aside className="flex w-[360px] shrink-0 flex-col border-l border-border bg-surface">
      <div className="shrink-0 border-b border-border px-4 py-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-app-accent-text">
              Setting up
            </p>
            <p
              className="mt-0.5 truncate text-sm font-semibold text-text-secondary"
              title={templateName}
            >
              {templateName}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            {onRegenerateClick && (
              <button
                type="button"
                onClick={onRegenerateClick}
                className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-app-accent/30 bg-app-accent-soft/40 px-2.5 py-1.5 text-[11px] font-semibold text-app-accent-text transition-colors hover:bg-app-accent-soft"
                title="Re-read this template with the AI"
                aria-label={`Re-read template ${templateName}`}
              >
                <FiRefreshCw className="h-3 w-3" />
                Re-read
              </button>
            )}
            {onDeleteTemplate && (
              <button
                type="button"
                onClick={() => setIsDeleteModalOpen(true)}
                className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-app-danger-text/30 bg-app-danger-text/5 px-2.5 py-1.5 text-[11px] font-semibold text-app-danger-text transition-colors hover:bg-app-danger-text/10"
                title="Delete this template"
                aria-label={`Delete template ${templateName}`}
              >
                <FiTrash2 className="h-3 w-3" />
                Delete
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="space-y-4 px-4 py-4">
          {roleError && (
            <RoleErrorBanner
              error={roleError}
              onDismiss={onDismissRoleError}
            />
          )}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-app-accent-text">
                Step 1 · Filing role
              </p>
              {/* Header chip is for NON-role saves (companion modal,
                  future config). Role saves get the inline pill-morph
                  + status line inside TemplateRolePicker. Showing both
                  for the same action splits attention. */}
              <BundlingStatusIndicator status={bundlingStatus} />
            </div>
            <TemplateRolePicker
              config={templateConfig}
              onChange={onChangeConfig}
              status={roleStatus}
              lastSavedAt={roleLastSavedAt}
            />
            {templateConfig.role === 'master' && (
              <button
                type="button"
                onClick={() => setIsCompanionsModalOpen(true)}
                className="group flex w-full cursor-pointer items-center justify-between gap-2 rounded-lg border border-border bg-surface-muted/40 px-3 py-2.5 text-left transition-colors hover:border-app-accent/40 hover:bg-app-accent-soft/30"
              >
                <span className="inline-flex items-center gap-2">
                  <FiLayers className="h-4 w-4 text-app-accent-text" />
                  <span className="text-xs font-semibold text-text-secondary">
                    Manage companions
                  </span>
                  <span className="rounded-full bg-app-accent-soft px-1.5 py-0.5 text-[10px] font-semibold text-app-accent-text">
                    {templateConfig.companions.length}
                  </span>
                </span>
                <span className="text-[11px] text-subtle group-hover:text-app-accent-text">
                  Open →
                </span>
              </button>
            )}
          </div>

          <div className="border-t border-border" aria-hidden="true" />

          <div className="space-y-2">
            <div className="flex items-end justify-between">
              <div>
                <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-app-accent-text">
                  Step 2 · Fields ({variables.length})
                  {isFieldsLoading && (
                    <span
                      className="inline-block h-3 w-3 animate-spin rounded-full border-[1.5px] border-app-accent/30 border-t-app-accent"
                      aria-label="Loading fields"
                    />
                  )}
                </p>
                <p className="mt-0.5 text-[11px] text-subtle">
                  {isFieldsLoading && variables.length === 0
                    ? 'Loading fields…'
                    : 'Click any field to set it up.'}
                </p>
              </div>
              <span className="rounded-full bg-surface-muted px-1.5 py-0.5 text-[10px] font-semibold text-subtle">
                {configuredCount}/{variables.length} done
              </span>
            </div>

            {isFieldsLoading && variables.length === 0 ? (
              <div className="space-y-1.5" aria-busy="true">
                {[0, 1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className="flex animate-pulse items-center gap-2 rounded-md border border-border/60 bg-surface-muted/40 px-2.5 py-2"
                  >
                    <span className="h-3 w-3 rounded-full bg-surface-muted" />
                    <span className="h-2.5 flex-1 rounded bg-surface-muted" />
                  </div>
                ))}
              </div>
            ) : (
              <VariableTree
                variables={variables}
                highlightedVariableName={highlightedVariableName}
                onSelectVariable={onSelectVariable}
                onHoverVariable={onHoverVariable}
              />
            )}
          </div>

          <div className="border-t border-border" aria-hidden="true" />

          {onTestAgainstCaseClick && (
            <div className="space-y-2">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wider text-app-accent-text">
                  Try it
                </p>
                <p className="mt-0.5 text-[11px] text-subtle">
                  Run a dry-run against a real case to see exactly what the
                  AI extracts. Nothing is saved.
                </p>
              </div>
              <button
                type="button"
                onClick={onTestAgainstCaseClick}
                className="group flex w-full cursor-pointer items-center justify-between gap-2 rounded-lg border border-app-accent/30 bg-app-accent-soft/40 px-3 py-2.5 text-left transition-colors hover:bg-app-accent-soft"
              >
                <span className="inline-flex items-center gap-2">
                  <FiPlay className="h-3.5 w-3.5 text-app-accent-text" />
                  <span className="text-xs font-semibold text-app-accent-text">
                    Test against a case
                  </span>
                </span>
                <span className="text-[11px] text-app-accent-text/70 group-hover:text-app-accent-text">
                  Pick →
                </span>
              </button>
            </div>
          )}

          <div className="border-t border-border" aria-hidden="true" />

          <PublishStep
            publishedAt={publishedAt}
            hasUnpublishedChanges={hasUnpublishedChanges}
            configuredCount={configuredCount}
            totalCount={variables.length}
            isPublishing={isPublishing}
            validationErrors={publishValidationErrors}
            onPublishClick={onPublishClick}
            onDismissValidationErrors={onDismissPublishValidationErrors ?? (() => {})}
          />
        </div>
      </div>

      <CompanionsModal
        isOpen={isCompanionsModalOpen}
        templateName={templateName}
        companions={templateConfig.companions}
        availableChildTemplates={allTemplates}
        currentTemplateId={currentTemplateId}
        leadVariables={variables}
        onChange={handleCompanionsChange}
        onCreateTemplate={onCreateTemplate}
        onClose={() => setIsCompanionsModalOpen(false)}
      />

      {onDeleteTemplate && (
        <DeleteTemplateModal
          isOpen={isDeleteModalOpen}
          templateName={templateName}
          onConfirm={handleConfirmDelete}
          onClose={() => setIsDeleteModalOpen(false)}
        />
      )}
    </aside>
  );
};

// ─── role-save error banner ──────────────────────────────────────────

/**
 * Persistent banner shown at the top of the setup sidebar when the BE
 * rejects a role change. Survives until the paralegal:
 *   - dismisses it via the X button
 *   - switches templates (page-level useEffect resets `roleError`)
 *   - successfully re-saves a different role (handleConfigChange
 *     clears the error at the start of every fresh attempt)
 *
 * Parses the BE's structured error (e.g. "Template <uuid> cannot be
 * set to role=part_of_packet because it contains user-input fields:
 * basis_for_objection, claim_row. Push the user-input variable up to
 * the lead template and inherit its resolved value via a
 * value_from_parent_bundle slot config.") into a paralegal-friendly
 * shape: title, plain-English explanation, monospace field chips,
 * and a concrete next-action sentence.
 */
const RoleErrorBanner = ({
  error,
  onDismiss,
}: {
  error: string;
  onDismiss?: () => void;
}) => {
  const parsed = parseRoleError(error);
  return (
    <div
      role="alert"
      className="rounded-lg border border-app-danger-text/30 bg-app-danger-text/5 px-3 py-3"
    >
      <div className="flex items-start gap-2">
        <FiAlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-app-danger-text" />
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex items-start justify-between gap-2">
            <p className="text-xs font-semibold text-app-danger-text">
              {parsed.title}
            </p>
            {onDismiss && (
              <button
                type="button"
                onClick={onDismiss}
                aria-label="Dismiss"
                className="-mt-0.5 -mr-1 shrink-0 cursor-pointer rounded p-0.5 text-app-danger-text/70 hover:bg-app-danger-text/10 hover:text-app-danger-text"
              >
                <FiX className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <p className="text-[11px] leading-relaxed text-text-secondary">
            {parsed.explanation}
          </p>
          {parsed.fields.length > 0 && (
            <ul className="flex flex-wrap gap-1">
              {parsed.fields.map((f) => (
                <li
                  key={f}
                  className="inline-flex items-center rounded-md bg-surface px-1.5 py-0.5 font-mono text-[10px] font-semibold text-app-danger-text ring-1 ring-app-danger-text/30"
                >
                  {f}
                </li>
              ))}
            </ul>
          )}
          {parsed.nextStep && (
            <p className="text-[11px] leading-relaxed text-muted">
              {parsed.nextStep}
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

interface ParsedRoleError {
  title: string;
  explanation: string;
  fields: string[];
  nextStep: string | null;
}

const ROLE_LABEL: Record<string, string> = {
  single: 'Standalone',
  master: 'Lead',
  part_of_packet: 'Companion',
};

function parseRoleError(raw: string): ParsedRoleError {
  // Try to extract the target role + offending field names from the BE
  // structured message. The regex tolerates either UUID or "template"
  // prefix variants and the trailing fix-up sentence we strip.
  const roleMatch = raw.match(/role=([a-z_]+)/i);
  const fieldsMatch = raw.match(
    /user-input fields?:\s*([a-z0-9_,\s]+?)(?:\.|$)/i,
  );
  const targetRoleKey = roleMatch?.[1] ?? null;
  const targetRole = targetRoleKey ? ROLE_LABEL[targetRoleKey] ?? targetRoleKey : null;
  const fields = fieldsMatch
    ? fieldsMatch[1]
        .split(',')
        .map((s) => s.trim())
        .filter((s) => s.length > 0)
    : [];

  if (targetRole && fields.length > 0) {
    return {
      title: `Can't make this a ${targetRole} filing yet`,
      explanation:
        `${targetRole} filings can't contain fields the paralegal types in at draft time. The ` +
        `${fields.length === 1 ? 'field' : 'fields'} below ${fields.length === 1 ? 'is' : 'are'} configured ` +
        `for user input.`,
      fields,
      nextStep:
        'Fix: move each field above to the Lead template, then have this ' +
        'template read it from the lead via the "From the lead filing" source.',
    };
  }

  // Fallback for unstructured / non-validator errors — surface the raw
  // message but in the banner shell so the paralegal still sees it
  // persistently.
  return {
    title: 'Filing role couldn’t be saved',
    explanation: raw,
    fields: [],
    nextStep: null,
  };
}

// ─── bundling save status indicator ──────────────────────────────────

const BundlingStatusIndicator = ({
  status,
}: {
  status: 'idle' | 'saving' | 'saved' | 'error';
}) => {
  if (status === 'idle') return null;
  if (status === 'saving') {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-medium text-muted">
        <span className="h-2.5 w-2.5 animate-spin rounded-full border border-app-accent/30 border-t-app-accent" />
        Saving…
      </span>
    );
  }
  if (status === 'saved') {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-medium text-app-accent-text">
        <FiCheckCircle className="h-3 w-3" />
        Saved
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-medium text-app-danger-text">
      <FiAlertCircle className="h-3 w-3" />
      Save failed
    </span>
  );
};

// ─── variable tree ───────────────────────────────────────────────────

interface VariableTreeProps {
  variables: StudioVariable[];
  highlightedVariableName: string | null;
  onSelectVariable: (variableName: string) => void;
  onHoverVariable: (variableName: string | null) => void;
}

/**
 * Renders the template's variables as a tree, with
 * `derived_from_variable` rows indented under their parent.
 *
 * A row is a child when:
 *   - its `params.source === 'derived_from_variable'`, AND
 *   - its `params.dependent_variable` references another variable
 *     in this template (orphan derives — parent not in template —
 *     render as top-level so they're not hidden).
 *
 * Tree connectors are pure CSS: each child group sits inside a
 * `border-l` container so a vertical line runs down the left margin,
 * and each child row gets a short horizontal stub via `before:`
 * pointing at it.
 */
const VariableTree = ({
  variables,
  highlightedVariableName,
  onSelectVariable,
  onHoverVariable,
}: VariableTreeProps) => {
  const { roots, childrenByParent } = useMemo(() => {
    const byName = new Map(variables.map((v) => [v.template_variable, v]));
    const childMap = new Map<string, StudioVariable[]>();
    const orphanOrRoot: StudioVariable[] = [];

    for (const v of variables) {
      const parent =
        v.params?.source === 'derived_from_variable'
          ? v.params.dependent_variable ?? null
          : null;
      if (parent && byName.has(parent) && parent !== v.template_variable) {
        const arr = childMap.get(parent) ?? [];
        arr.push(v);
        childMap.set(parent, arr);
      } else {
        orphanOrRoot.push(v);
      }
    }
    return { roots: orphanOrRoot, childrenByParent: childMap };
  }, [variables]);

  return (
    <div className="space-y-1.5">
      {roots.map((variable) => (
        <VariableNode
          key={variable.template_variable}
          variable={variable}
          depth={0}
          childrenByParent={childrenByParent}
          highlightedVariableName={highlightedVariableName}
          onSelectVariable={onSelectVariable}
          onHoverVariable={onHoverVariable}
        />
      ))}
    </div>
  );
};

const VariableNode = ({
  variable,
  depth,
  childrenByParent,
  highlightedVariableName,
  onSelectVariable,
  onHoverVariable,
}: {
  variable: StudioVariable;
  depth: number;
  childrenByParent: Map<string, StudioVariable[]>;
  highlightedVariableName: string | null;
  onSelectVariable: (variableName: string) => void;
  onHoverVariable: (variableName: string | null) => void;
}) => {
  const children = childrenByParent.get(variable.template_variable) ?? [];
  const isConfigured = variable.params !== null;
  const isHighlighted = highlightedVariableName === variable.template_variable;
  const isChild = depth > 0;

  return (
    <div>
      <div
        className={cn(
          'relative',
          isChild &&
            'before:absolute before:left-[-12px] before:top-[18px] before:h-px before:w-3 before:bg-app-accent/30',
        )}
      >
        <button
          type="button"
          onClick={() => onSelectVariable(variable.template_variable)}
          onMouseEnter={() => onHoverVariable(variable.template_variable)}
          onMouseLeave={() => onHoverVariable(null)}
          className={cn(
            'group flex w-full cursor-pointer items-start gap-2 rounded-md border bg-surface px-2.5 py-2 text-left transition-all',
            isHighlighted && 'border-app-accent shadow-sm',
            !isHighlighted &&
              (isConfigured
                ? 'border-app-accent/30 hover:border-app-accent'
                : 'border-border hover:border-app-accent/40 hover:bg-surface-muted'),
          )}
        >
          <span
            className={cn(
              'mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded',
              isConfigured
                ? 'bg-app-accent text-white'
                : 'bg-surface-muted text-subtle',
            )}
          >
            {isConfigured && variable.params ? (
              <SourceIcon source={variable.params.source} className="h-3 w-3" />
            ) : (
              <FiCircle className="h-3 w-3" />
            )}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1">
              <p className="truncate font-mono text-[11px] font-semibold text-text-secondary">
                {variable.template_variable}
              </p>
              {isConfigured && (
                <span className="inline-flex items-center gap-0.5 rounded-full bg-app-accent-soft px-1 py-0.5 text-[8px] font-semibold uppercase tracking-wider text-app-accent-text">
                  <FiCheckCircle className="h-2 w-2" />
                  Set up
                </span>
              )}
            </div>
            <p
              className={cn(
                'mt-0.5 truncate text-[10px] font-semibold uppercase tracking-wider',
                isConfigured ? 'text-app-accent-text' : 'text-subtle',
              )}
            >
              {summarizeParams(variable.params)}
            </p>
          </div>
        </button>
      </div>
      {children.length > 0 && (
        <div className="mt-1.5 space-y-1.5 border-l border-app-accent/30 pl-3 ml-3">
          {children.map((child) => (
            <VariableNode
              key={child.template_variable}
              variable={child}
              depth={depth + 1}
              childrenByParent={childrenByParent}
              highlightedVariableName={highlightedVariableName}
              onSelectVariable={onSelectVariable}
              onHoverVariable={onHoverVariable}
            />
          ))}
        </div>
      )}
    </div>
  );
};
