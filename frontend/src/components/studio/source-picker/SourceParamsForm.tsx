import React, { useMemo, useState, type ReactElement } from 'react';
import { SelectDropdown, Tooltip } from '@/components/common';
import { useStudioStore } from '@/stores/useStudioStore';
import { useToastStore } from '@/stores/useToastStore';
import { humanizeIdentifier } from '@/utils';
import {
  SOURCES_WITH_CUSTOM_UI,
  defaultParamsFor,
  isParamRequired,
  isParamVisible,
} from '@/utils/studio/sourceConfig';
import { AutoDeriveExampleFormatEditor } from '../field-editors/AutoDeriveExampleFormatEditor';
import { CaseVectorQueriesEditor } from '../field-editors/CaseVectorQueriesEditor';
import { DateFormatField } from '../field-editors/DateFormatField';
import { DependentChipVariablesPicker } from '../field-editors/DependentChipVariablesPicker';
import { DependentVariablesPicker } from '../field-editors/DependentVariablesPicker';
import { MultiSelectEditor } from '../field-editors/MultiSelectEditor';
import { MultiSelectGmailEditor } from '../field-editors/MultiSelectGmailEditor';
import { VariableReferenceInput } from '../field-editors/VariableReferenceInput';
import { InheritFromParentForm } from './InheritFromParentForm';
import type {
  CaseVectorSourceParams,
  Connector,
  ConnectorParam,
  ConstantsSourceParams,
  CourtDriveSourceParams,
  DependentOnVariableSourceParams,
  DropdownCaseVectorSourceParams,
  DropdownEmailSourceParams,
  FieldSource,
  GmailSourceParams,
  MultiSelectFromCaseVectorSourceParams,
  MultiSelectFromGmailSourceParams,
  RecoChipsFromDependentVariablesSourceParams,
  SourceParams,
  SystemGeneratedSourceParams,
  UserInputDateSourceParams,
  VectorSourceParams,
} from '@/types/studio';
import { ATTORNEYS_SHORT_CODE } from '@/types/studio';

interface SourceParamsFormProps {
  source: FieldSource;
  sourceParams: SourceParams | null;
  onChange: (params: SourceParams | null) => void;
  variableName?: string;
}

const DROPDOWN_PARENT_SOURCES: ReadonlySet<FieldSource> = new Set<FieldSource>([
  'dropdown_from_gmail',
  'dropdown_from_court_drive',
  'dropdown_from_case_vector',
]);

const EMAIL_SOURCES_WITH_SCOPING: ReadonlySet<FieldSource> = new Set<FieldSource>([
  'gmail',
  'court_drive',
  'dropdown_from_gmail',
  'dropdown_from_court_drive',
  'group_dropdown_from_gmail',
  'group_dropdown_from_court_drive',
  'reco_chips_from_gmail',
  'reco_chips_from_court_drive',
]);

const QUERY_PARAM_NAMES: ReadonlySet<string> = new Set([
  'subject_query',
  'body_query',
  'text_query',
]);

const lookupParam = (
  connector: Connector | undefined,
  paramName: string
): ConnectorParam | undefined => connector?.params.find((p) => p.name === paramName);

const FORM_DROPDOWN_BUTTON_CLASS =
  'flex w-full items-center justify-between gap-2 rounded-lg border border-border bg-surface px-3 py-2 text-left text-sm text-text-secondary transition-colors hover:border-border focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft';

export const SourceParamsForm = ({
  source,
  sourceParams,
  onChange,
  variableName,
}: SourceParamsFormProps): ReactElement => {
  const connectors = useStudioStore((state) => state.connectors);
  const templateSpec = useStudioStore((state) => state.templateSpec);
  const referenceData = useStudioStore((state) => state.referenceData);

  const activeConnector = useMemo(
    () => connectors.find((c) => c.source === source),
    [connectors, source]
  );

  const autoDeriveChildren = useMemo(() => {
    if (!variableName) return [];
    return templateSpec.filter(
      (v) =>
        v.source === 'auto_derived_from_variable' &&
        v.source_params !== null &&
        'dependent_variable' in v.source_params &&
        (v.source_params as { dependent_variable: string }).dependent_variable === variableName
    );
  }, [templateSpec, variableName]);

  const isDropdownParentWithChildren =
    DROPDOWN_PARENT_SOURCES.has(source) && autoDeriveChildren.length > 1;

  const patchParams = (partial: Partial<SourceParams>): void => {
    const base = sourceParams ?? defaultParamsFor(source) ?? {};
    onChange({ ...base, ...partial } as SourceParams);
  };

  const paramHint = (paramName: string): { label: string; hint: string; required: boolean } => {
    const param = lookupParam(activeConnector, paramName);
    return {
      label: param ? humanizeIdentifier(param.name) : humanizeIdentifier(paramName),
      hint: param?.description ?? '',
      required: param?.required ?? false,
    };
  };

  const hasCustomUI = SOURCES_WITH_CUSTOM_UI.has(source);
  const isDatePicker = source === 'user_input_date';

  return (
    <div className="space-y-4">
      {source === 'inherit_from_parent' && (
        <InheritFromParentForm
          variableName={variableName ?? ''}
          sourceParams={sourceParams}
          onChange={onChange}
        />
      )}

      {isDatePicker && (
        <DateFormatField
          params={sourceParams as UserInputDateSourceParams | null}
          onChange={(next) => onChange(next)}
        />
      )}

      {(source === 'gmail' || source === 'court_drive') && (() => {
        const params = sourceParams as GmailSourceParams | CourtDriveSourceParams | null;
        const subjectValue = params?.subject_query ?? '';
        const bodyValue = params?.body_query ?? '';
        const hasSubject = subjectValue.trim().length > 0;
        const hasBody = bodyValue.trim().length > 0;
        const hasError = !hasSubject && !hasBody;
        const subjectMeta = paramHint('subject_query');
        const bodyMeta = paramHint('body_query');
        const gmailParams = source === 'gmail' ? (params as GmailSourceParams | null) : null;
        const enableWebSearch = gmailParams?.enable_web_search ?? false;
        const webSearchInstructionValue = gmailParams?.web_search_instruction ?? '';
        return (
          <div className="space-y-3">
            <div
              role={hasError ? 'alert' : undefined}
              className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-xs ${
                hasError
                  ? 'border-app-warning-soft bg-app-warning-soft text-app-warning-text'
                  : 'border-app-accent-soft bg-app-accent-soft/60 text-app-accent-text'
              }`}
            >
              <svg
                className="mt-0.5 h-3.5 w-3.5 shrink-0"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                {hasError ? (
                  <>
                    <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                    <line x1="12" y1="9" x2="12" y2="13" />
                    <line x1="12" y1="17" x2="12.01" y2="17" />
                  </>
                ) : (
                  <>
                    <circle cx="12" cy="12" r="10" />
                    <line x1="12" y1="16" x2="12" y2="12" />
                    <line x1="12" y1="8" x2="12.01" y2="8" />
                  </>
                )}
              </svg>
              <span>
                <span className="font-semibold">At least one query is required.</span>{' '}
                Provide a Subject query, a Body query, or both so the agent knows where to look.
              </span>
            </div>
            <FormField label={subjectMeta.label} hint={subjectMeta.hint} required={hasError}>
              <VariableReferenceInput
                value={subjectValue}
                onChange={(v) => patchParams({ subject_query: v })}
                placeholder="e.g. Notice of Filing — type {{ to reference a variable"
                ariaLabel="Subject query"
                referencerSource={source}
              />
            </FormField>
            <FormField label={bodyMeta.label} hint={bodyMeta.hint} required={hasError}>
              <VariableReferenceInput
                value={bodyValue}
                onChange={(v) => patchParams({ body_query: v })}
                placeholder="e.g. {{prior_case_number}} — type {{ to reference a variable"
                ariaLabel="Body query"
                referencerSource={source}
              />
            </FormField>
            {source === 'gmail' && (
              <WebSearchEnhancementFields
                enableWebSearch={enableWebSearch}
                webSearchInstruction={webSearchInstructionValue}
                onChange={patchParams}
              />
            )}
          </div>
        );
      })()}

      {source === 'case_vector' && (() => {
        const params = sourceParams as CaseVectorSourceParams | null;
        const textValue = params?.text_query ?? '';
        const enableWebSearch = params?.enable_web_search ?? false;
        const webSearchInstructionValue = params?.web_search_instruction ?? '';
        return (
          <div className="space-y-3">
            <div className="rounded-lg border border-app-accent-soft bg-app-accent-soft/40 px-3 py-2 text-xs text-app-accent-text">
              <p className="font-semibold">Text query (optional)</p>
              <p className="mt-0.5">
                Leave blank to auto-derive the query from the variable name (today's
                behavior). Set it for explicit control — e.g. when the variable name
                doesn't match what's in the case file. Supports {`{{variable}}`} references.
              </p>
            </div>
            <FormField
              label="Text query"
              hint="Optional. The text used to retrieve relevant case-file chunks."
            >
              <VariableReferenceInput
                value={textValue}
                onChange={(v) => patchParams({ text_query: v })}
                placeholder="e.g. prior bankruptcy case filed within last 8 years"
                ariaLabel="Text query"
                multiline
                referencerSource={source}
              />
            </FormField>
            <WebSearchEnhancementFields
              enableWebSearch={enableWebSearch}
              webSearchInstruction={webSearchInstructionValue}
              onChange={patchParams}
            />
          </div>
        );
      })()}

      {source === 'law_practice_vector' && (() => {
        const meta = paramHint('text_query');
        return (
          <FormField label={meta.label} hint={meta.hint} required={meta.required}>
            <textarea
              rows={3}
              value={(sourceParams as VectorSourceParams | null)?.text_query ?? ''}
              onChange={(e) => patchParams({ text_query: e.target.value })}
              placeholder="e.g. trustee appointment date"
              className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
            />
          </FormField>
        );
      })()}

      {source === 'constants' && (() => {
        const meta = paramHint('short_code');
        return (
          <FormField label={meta.label} hint={meta.hint} required={meta.required}>
            <ConstantsPicker
              selected={(sourceParams as ConstantsSourceParams | null)?.short_code ?? ''}
              onSelect={(shortCode) => patchParams({ short_code: shortCode })}
            />
          </FormField>
        );
      })()}

      {source === 'dependent_on_variable' && (() => {
        const params = (sourceParams as DependentOnVariableSourceParams | null) ?? null;
        const paramsRecord = (params ?? {}) as Record<string, unknown>;
        return (
          <>
            {(activeConnector?.params ?? []).map((p) => {
              if (!isParamVisible(p, paramsRecord)) return null;
              const meta = paramHint(p.name);
              const isRequired = isParamRequired(p, paramsRecord);
              if (p.name === 'dependent_variable') {
                return (
                  <FormField key={p.name} label={meta.label} hint={meta.hint} required={isRequired}>
                    <ParentVariablePicker
                      selected={params?.dependent_variable ?? ''}
                      onSelect={(name) => patchParams({ dependent_variable: name })}
                    />
                  </FormField>
                );
              }
              return (
                <FormField key={p.name} label={meta.label} hint={meta.hint} required={isRequired}>
                  <ConnectorOptionInput
                    param={p}
                    value={(paramsRecord[p.name] as string | null | undefined) ?? ''}
                    onChange={(v) => patchParams({ [p.name]: v } as never)}
                  />
                </FormField>
              );
            })}
          </>
        );
      })()}

      {source === 'system_generated' && (() => {
        const params = (sourceParams as SystemGeneratedSourceParams | null) ?? null;
        const paramsRecord = (params ?? {}) as Record<string, unknown>;
        return (
          <>
            {(activeConnector?.params ?? []).map((p) => {
              if (!isParamVisible(p, paramsRecord)) return null;
              const meta = paramHint(p.name);
              const isRequired = isParamRequired(p, paramsRecord);
              return (
                <FormField key={p.name} label={meta.label} hint={meta.hint} required={isRequired}>
                  <ConnectorOptionInput
                    param={p}
                    value={(paramsRecord[p.name] as string | null | undefined) ?? ''}
                    onChange={(v) => patchParams({ [p.name]: v } as never)}
                  />
                </FormField>
              );
            })}
          </>
        );
      })()}

      {source === 'multi_select_from_case_vector' && (() => {
        const params =
          (sourceParams as MultiSelectFromCaseVectorSourceParams | null) ??
          ({
            label: '',
            instruction: '',
            text_query: '',
            example_formats: [],
            min_picks: 1,
            max_picks: null,
            list_joiner: ', ',
            oxford: true,
          } as MultiSelectFromCaseVectorSourceParams);
        return (
          <div className="space-y-3">
            <div className="rounded-lg border border-app-accent-soft bg-app-accent-soft/40 px-3 py-2 text-xs text-app-accent-text">
              <p className="font-semibold">Multi-select from Case Documents</p>
              <p className="mt-0.5">
                Pre-fetched at draft time. The BE searches case PDFs with
                <code className="mx-1 rounded bg-surface px-1">text_query</code>,
                extracts up to 20 distinct options matching
                <code className="mx-1 rounded bg-surface px-1">example_formats</code>,
                and presents a multi-select card UI. The picked options are
                Oxford-comma-joined into one prose string ready to drop
                directly into a docx slot.
              </p>
            </div>
            <MultiSelectEditor
              value={params}
              onChange={(next: MultiSelectFromCaseVectorSourceParams) => onChange(next)}
            />
          </div>
        );
      })()}

      {source === 'multi_select_from_gmail' && (() => {
        const params =
          (sourceParams as MultiSelectFromGmailSourceParams | null) ??
          ({
            label: '',
            instruction: '',
            subject_query: '',
            body_query: '',
            scope_to_current_case: true,
            example_formats: [],
            min_picks: 1,
            max_picks: null,
            list_joiner: ', ',
            oxford: true,
          } as MultiSelectFromGmailSourceParams);
        return (
          <div className="space-y-3">
            <div className="rounded-lg border border-app-accent-soft bg-app-accent-soft/40 px-3 py-2 text-xs text-app-accent-text">
              <p className="font-semibold">Multi-select from Gmail</p>
              <p className="mt-0.5">
                Pre-fetched at draft time. The BE searches Gmail with
                <code className="mx-1 rounded bg-surface px-1">subject_query</code>{' '}/
                <code className="mx-1 rounded bg-surface px-1">body_query</code>,
                extracts up to 20 distinct options matching
                <code className="mx-1 rounded bg-surface px-1">example_formats</code>,
                and presents a multi-select card UI. Use this when options live
                in case email correspondence (e.g. creditors from Proof of
                Claim filings).
              </p>
            </div>
            <MultiSelectGmailEditor
              value={params}
              onChange={(next: MultiSelectFromGmailSourceParams) => onChange(next)}
            />
          </div>
        );
      })()}

      {source === 'reco_chips_from_dependent_variables' && (() => {
        const params = (sourceParams as RecoChipsFromDependentVariablesSourceParams | null) ?? null;
        const labelValue = params?.label ?? '';
        const exampleValue = params?.example_sentence ?? '';
        const depsValue = params?.dependent_variables ?? [];
        const caseVectorQueriesValue = params?.case_vector_queries ?? [];
        const dependentChipVariablesValue = params?.dependent_chip_variables ?? [];
        const instructionValue = params?.instruction ?? '';
        return (
          <div className="space-y-3">
            <div className="rounded-lg border border-app-accent-soft bg-app-accent-soft/40 px-3 py-2 text-xs text-app-accent-text">
              <p className="font-semibold">Compose chips from multiple context sources</p>
              <p className="mt-0.5">
                The chip generator composes context from up to three sources — already-resolved
                variables, inline case-vector retrievals, and sibling chip-from-deps fields —
                then produces 3 suggestions. The user picks one or types their own; heal pass
                tone-matches against the example sentence. At least ONE source must be filled.
              </p>
            </div>
            <FormField label="Label" hint="Header shown above the chips at draft time" required>
              <input
                type="text"
                value={labelValue}
                onChange={(e) => patchParams({ label: e.target.value } as never)}
                placeholder="e.g. Change in Circumstances"
                className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
              />
            </FormField>
            <FormField
              label="Example sentence"
              hint="Tone / structure target — also used as the heal target after the user picks/types"
              required
            >
              <textarea
                rows={3}
                value={exampleValue}
                onChange={(e) => patchParams({ example_sentence: e.target.value } as never)}
                placeholder="The Debtor will now be able to afford their plan due to a substantial change in circumstances..."
                className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
              />
            </FormField>
            <FormField
              label="Dependent variables"
              hint="Resolved values composed as context for chip generation. Pick from LLM_DRAFT and SYSTEM_GENERATED stages only."
            >
              <DependentVariablesPicker
                value={depsValue}
                onChange={(next) => patchParams({ dependent_variables: next } as never)}
                referencerSource={source}
              />
            </FormField>
            <FormField
              label="Case-vector retrievals"
              hint="Optional. Inline case-file similarity queries (e.g. Schedule I/J) folded into the chip prompt at generation time. text_query supports {{variable}} substitution."
            >
              <CaseVectorQueriesEditor
                value={caseVectorQueriesValue}
                onChange={(next) => patchParams({ case_vector_queries: next } as never)}
              />
            </FormField>
            <FormField
              label="Dependent chip variables"
              hint="Optional. Names of OTHER reco-chips-from-deps fields whose generated chip arrays seed this generator's context for tonal alignment."
            >
              <DependentChipVariablesPicker
                value={dependentChipVariablesValue}
                onChange={(next) => patchParams({ dependent_chip_variables: next } as never)}
                selfVariableName={variableName}
              />
            </FormField>
            <FormField
              label="Instruction"
              hint="Optional. Extra prompt guidance for the chip-generation LLM."
            >
              <textarea
                rows={2}
                value={instructionValue}
                onChange={(e) => patchParams({ instruction: e.target.value } as never)}
                placeholder="Synthesize 3 plausible reasons grounded in the dependent variables above."
                className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
              />
            </FormField>
          </div>
        );
      })()}

      {!hasCustomUI &&
        source !== 'reco_chips_from_dependent_variables' &&
        source !== 'multi_select_from_case_vector' &&
        source !== 'multi_select_from_gmail' &&
        !isDatePicker && (() => {
        const paramsRecord = (sourceParams ?? {}) as Record<string, unknown>;
        const params = activeConnector?.params ?? [];
        if (params.length === 0) {
          return (
            <div className="rounded-lg border border-dashed border-border bg-surface-muted px-3 py-3 text-xs text-muted">
              This source has no parameters to configure.
            </div>
          );
        }

        const renderParam = (p: ConnectorParam): React.ReactNode => {
          if (!isParamVisible(p, paramsRecord)) return null;
          const meta = paramHint(p.name);
          const isRequired = isParamRequired(p, paramsRecord);
          if (p.name === 'dependent_variable' || p.name === 'right_partner_variable') {
            return (
              <FormField key={p.name} label={meta.label} hint={meta.hint} required={isRequired}>
                <ParentVariablePicker
                  selected={(paramsRecord[p.name] as string | null | undefined) ?? ''}
                  onSelect={(name) => patchParams({ [p.name]: name } as never)}
                />
              </FormField>
            );
          }
          if (p.name === 'reference_short_code' && source === 'dropdown_from_constants') {
            const selected = (paramsRecord[p.name] as string | null | undefined) ?? '';
            const options = referenceData.map((ref) => ({
              label: `${ref.display_name} (${ref.short_code})`,
              value: ref.short_code,
            }));
            return (
              <FormField key={p.name} label={meta.label} hint={meta.hint} required={isRequired}>
                <SelectDropdown
                  value={selected}
                  onChange={(next) => patchParams({ [p.name]: next } as never)}
                  options={options}
                  placeholder="Select a reference constant…"
                  buttonClassName={FORM_DROPDOWN_BUTTON_CLASS}
                />
              </FormField>
            );
          }
          if (p.name === 'example_format' && isDropdownParentWithChildren) {
            const dropdownParams = (sourceParams ?? {}) as
              | DropdownEmailSourceParams
              | DropdownCaseVectorSourceParams
              | Record<string, never>;
            return (
              <FormField key={p.name} label={meta.label} hint={meta.hint} required={isRequired}>
                <AutoDeriveExampleFormatEditor
                  children={autoDeriveChildren}
                  value={(dropdownParams as { example_format?: string }).example_format ?? ''}
                  onChange={(composed) => patchParams({ example_format: composed } as never)}
                />
              </FormField>
            );
          }
          if (QUERY_PARAM_NAMES.has(p.name)) {
            return (
              <FormField key={p.name} label={meta.label} hint={meta.hint} required={isRequired}>
                <VariableReferenceInput
                  value={(paramsRecord[p.name] as string | null | undefined) ?? ''}
                  onChange={(v) => patchParams({ [p.name]: v } as never)}
                  placeholder="Type {{ to reference another variable"
                  ariaLabel={meta.label}
                  multiline={p.name === 'text_query'}
                  referencerSource={source}
                />
              </FormField>
            );
          }
          if (
            p.name === 'example_format' &&
            DROPDOWN_PARENT_SOURCES.has(source) &&
            autoDeriveChildren.length === 1
          ) {
            const currentFormat =
              (paramsRecord[p.name] as string | null | undefined) ?? '';
            const child = autoDeriveChildren[0]!;
            const marker = child.template_property_marker ?? '';
            const missing = !!marker && !currentFormat.includes(marker);
            return (
              <FormField key={p.name} label={meta.label} hint={meta.hint} required={isRequired}>
                <div className="space-y-2">
                  <ConnectorOptionInput
                    param={p}
                    value={currentFormat}
                    onChange={(v) => patchParams({ [p.name]: v } as never)}
                  />
                  {marker && (
                    <div
                      className={`rounded-lg border px-3 py-2 text-xs ${
                        missing
                          ? 'border-app-warning-soft bg-app-warning-soft/40 text-app-warning-text'
                          : 'border-app-accent-soft bg-app-accent-soft/40 text-app-accent-text'
                      }`}
                    >
                      <p className="font-semibold">
                        {missing
                          ? 'Missing required token'
                          : 'Required token present'}
                      </p>
                      <p className="mt-0.5">
                        Child{' '}
                        <span className="font-mono">{child.template_variable}</span>{' '}
                        uses <span className="font-mono">{marker}</span> as its sample
                        value (pulled from the original docx). Include this sample in
                        the format so the dropdown extractor produces options shaped
                        to include the data the child will derive at runtime.
                      </p>
                      <p className="mt-2 font-semibold">Example shapes:</p>
                      <ul className="mt-0.5 list-disc space-y-0.5 pl-5">
                        <li>
                          <span className="font-mono">{marker} - &lt;description&gt;</span>
                        </li>
                        <li>
                          <span className="font-mono">&lt;description&gt; - {marker}</span>
                        </li>
                        <li>
                          <span className="font-mono">{marker}</span> (sample alone)
                        </li>
                      </ul>
                    </div>
                  )}
                </div>
              </FormField>
            );
          }
          return (
            <FormField key={p.name} label={meta.label} hint={meta.hint} required={isRequired}>
              <ConnectorOptionInput
                param={p}
                value={(paramsRecord[p.name] as string | null | undefined) ?? ''}
                onChange={(v) => patchParams({ [p.name]: v } as never)}
              />
            </FormField>
          );
        };

        // Split visible params by required-ness so the form opens with only the
        // mandatory fields and tucks optional ones behind an "Advanced" disclosure.
        // Hidden-by-`visible_when` params get filtered inside renderParam (returns null).
        //
        // Two carve-outs:
        //   - `scope_to_current_case` has its own dedicated checkbox UI below
        //     (see the `EMAIL_SOURCES_WITH_SCOPING` block) — skip it in the
        //     generic renderer or it'd render as a stray "true" text input.
        //   - For email-derived sources, `subject_query` / `body_query` are
        //     the PRIMARY way to find emails; force them into the top section
        //     even though the connector marks them as optional.
        const isEmailSource = EMAIL_SOURCES_WITH_SCOPING.has(source);
        const visibleParams = params.filter(
          (p) =>
            isParamVisible(p, paramsRecord) &&
            !(isEmailSource && p.name === 'scope_to_current_case'),
        );
        const isAlwaysPrimary = (p: ConnectorParam): boolean =>
          isEmailSource &&
          (p.name === 'subject_query' || p.name === 'body_query');
        const requiredParams = visibleParams.filter(
          (p) => isParamRequired(p, paramsRecord) || isAlwaysPrimary(p),
        );
        const optionalParams = visibleParams.filter(
          (p) => !isParamRequired(p, paramsRecord) && !isAlwaysPrimary(p),
        );

        return (
          <>
            {requiredParams.length > 0 && (
              <div className="space-y-4">{requiredParams.map(renderParam)}</div>
            )}
            {optionalParams.length > 0 && (
              <details className="group rounded-xl border border-border bg-surface-muted/40">
                <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-semibold text-text-secondary [&::-webkit-details-marker]:hidden">
                  <svg
                    className="h-3.5 w-3.5 text-muted transition-transform group-open:rotate-90"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={2}
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                  </svg>
                  <span>Advanced</span>
                  <span className="rounded-full bg-surface px-1.5 py-0.5 text-[10px] font-semibold text-muted">
                    {optionalParams.length} optional
                  </span>
                </summary>
                <div className="space-y-4 border-t border-border px-4 py-4">
                  {optionalParams.map(renderParam)}
                </div>
              </details>
            )}
            {requiredParams.length === 0 && optionalParams.length === 0 && (
              <div className="rounded-lg border border-dashed border-border bg-surface-muted px-3 py-3 text-xs text-muted">
                This source has no parameters to configure.
              </div>
            )}
          </>
        );
      })()}

      {EMAIL_SOURCES_WITH_SCOPING.has(source) && (() => {
        const params = (sourceParams ?? {}) as Record<string, unknown>;
        const checked = (params.scope_to_current_case as boolean | undefined) ?? true;
        return (
          <div className="rounded-lg border border-border bg-surface-muted/40 px-3 py-2.5">
            <label className="flex cursor-pointer items-start gap-2">
              <input
                type="checkbox"
                checked={checked}
                onChange={(e) =>
                  patchParams({ scope_to_current_case: e.target.checked } as never)
                }
                className="mt-0.5 h-4 w-4 shrink-0 rounded border-border text-app-accent focus:ring-app-accent-soft"
              />
              <div className="text-xs">
                <p className="font-semibold text-text-secondary">
                  Scope to current case number
                </p>
                <p className="mt-0.5 text-muted">
                  Adds the case's number variants as an AND clause. Uncheck for
                  cross-case templates that need to reach into another case's email
                  thread (typically combined with{' '}
                  <span className="font-mono">{`{{prior_case_number}}`}</span>{' '}
                  in the query).
                </p>
              </div>
            </label>
          </div>
        );
      })()}
    </div>
  );
};

interface ParentVariablePickerProps {
  selected: string;
  onSelect: (name: string) => void;
}

const ParentVariablePicker = ({ selected, onSelect }: ParentVariablePickerProps): ReactElement => {
  const templateSpec = useStudioStore((state) => state.templateSpec);
  const options = useMemo(
    () =>
      templateSpec
        .filter((v) => v.source !== 'dependent_on_variable')
        .map((v) => ({ label: v.template_variable, value: v.template_variable })),
    [templateSpec]
  );

  return (
    <SelectDropdown
      value={selected}
      onChange={onSelect}
      options={options}
      placeholder="Select parent variable…"
      buttonClassName={FORM_DROPDOWN_BUTTON_CLASS}
    />
  );
};

interface FormFieldProps {
  label: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
}

interface WebSearchEnhancementFieldsProps {
  enableWebSearch: boolean;
  webSearchInstruction: string;
  onChange: (next: { enable_web_search?: boolean; web_search_instruction?: string }) => void;
}

const WebSearchEnhancementFields = ({
  enableWebSearch,
  webSearchInstruction,
  onChange,
}: WebSearchEnhancementFieldsProps): ReactElement => (
  <>
    <FormField
      label="Enhance with web search"
      hint="When on, Claude looks up small pieces of stable external context the petition doesn't carry (e.g. resolves a Florida county to its judicial circuit number) and reshapes the result to match the template's marker. Requires the upstream retrieval to first pull a non-empty value as an anchor. Adds 1–3s and external lookup cost."
    >
      <label className="flex items-center gap-2 text-sm text-app-text">
        <input
          type="checkbox"
          checked={enableWebSearch}
          onChange={(e) => onChange({ enable_web_search: e.target.checked })}
          aria-label="Enhance with web search"
        />
        <span>Enable web-search enhancement for this variable</span>
      </label>
    </FormField>
    {enableWebSearch && (
      <div className="pt-1">
        <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-text-secondary">
          Web search instruction
        </label>
        <p className="mb-1 text-[11px] leading-snug text-subtle">
          Per-field directive for the web-search agent only. Use this to steer the search step (e.g. &quot;search for circuit number by county; ignore federal court info&quot;). For docx-output formatting, use &quot;Document output instruction&quot; on the variable instead.
        </p>
        <textarea
          rows={2}
          value={webSearchInstruction}
          onChange={(e) => onChange({ web_search_instruction: e.target.value })}
          placeholder="Optional — e.g. 'search for the Florida judicial circuit number for the county extracted above'"
          aria-label="Web search instruction"
          className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
        />
      </div>
    )}
  </>
);

const FormField = ({ label, hint, required, children }: FormFieldProps): ReactElement => (
  <div>
    <label className="mb-1 flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-muted">
      <span>{label}</span>
      {required && <span className="text-red-500">*</span>}
      {hint && (
        <Tooltip label={hint} side="top" delayMs={150} className="ml-0.5">
          <span
            tabIndex={0}
            aria-label={`About ${label}`}
            className="grid h-3.5 w-3.5 cursor-help place-items-center rounded-full text-subtle hover:text-text-secondary focus:outline-none focus-visible:ring-2 focus-visible:ring-app-accent-soft"
          >
            <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </span>
        </Tooltip>
      )}
    </label>
    {children}
  </div>
);

interface ConstantsPickerProps {
  selected: string;
  onSelect: (shortCode: string) => void;
}

const ConstantsPicker = ({ selected, onSelect }: ConstantsPickerProps): ReactElement => {
  const referenceData = useStudioStore((state) => state.referenceData);
  const createReferenceData = useStudioStore((state) => state.createReferenceData);
  const addToast = useToastStore((state) => state.addToast);

  const [isAdding, setIsAdding] = useState<boolean>(false);
  const [name, setName] = useState<string>('');
  const [value, setValue] = useState<string>('');
  const [description, setDescription] = useState<string>('');
  const [isSaving, setIsSaving] = useState<boolean>(false);

  const openAdd = (): void => {
    setName('');
    setValue('');
    setDescription('');
    setIsAdding(true);
  };

  const cancelAdd = (): void => {
    setIsAdding(false);
  };

  const saveNew = async (): Promise<void> => {
    if (!name.trim() || !value.trim()) {
      addToast('Name and value are required', 'error');
      return;
    }
    setIsSaving(true);
    const result = await createReferenceData({
      name: name.trim(),
      value: value.trim(),
      description: description.trim() || null,
    });
    setIsSaving(false);
    if (!result.success || !result.data) {
      addToast(result.error ?? 'Failed to create constant', 'error');
      return;
    }
    addToast('Constant created', 'success');
    onSelect(result.data.short_code);
    setIsAdding(false);
  };

  const options = useMemo(
    () =>
      referenceData
        .filter((ref) => ref.short_code !== ATTORNEYS_SHORT_CODE)
        .map((ref) => ({
          label: `${ref.display_name} — ${ref.value}`,
          value: ref.short_code,
        })),
    [referenceData]
  );

  return (
    <div>
      <div className="flex items-start gap-2">
        <div className="flex-1">
          <SelectDropdown
            value={selected}
            onChange={onSelect}
            options={options}
            placeholder="Select a constant…"
            buttonClassName={FORM_DROPDOWN_BUTTON_CLASS}
          />
        </div>
        <button
          type="button"
          onClick={openAdd}
          className="shrink-0 rounded-lg border border-app-accent-soft bg-surface px-3 py-2 text-sm font-semibold text-app-accent-text hover:bg-app-accent-soft"
          title="Add a new constant"
        >
          + Add
        </button>
      </div>

      {isAdding && (
        <div className="mt-2 space-y-2 rounded-lg border border-app-accent-soft bg-app-accent-soft/40 p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-app-accent-text">Add new constant</p>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Name (e.g. Firm Phone)"
            className="w-full rounded border border-border bg-surface px-3 py-2 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
          />
          <input
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Value"
            className="w-full rounded border border-border bg-surface px-3 py-2 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
          />
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Description (optional)"
            className="w-full rounded border border-border bg-surface px-3 py-2 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
          />
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={cancelAdd}
              className="rounded px-3 py-1.5 text-xs text-muted hover:bg-surface"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={saveNew}
              disabled={isSaving}
              className="rounded bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {isSaving ? 'Creating…' : 'Create'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

interface ConnectorOptionInputProps {
  param: ConnectorParam;
  value: string;
  onChange: (value: string) => void;
}

const CUSTOM_SENTINEL = '__custom__';

const ConnectorOptionInput = ({ param, value, onChange }: ConnectorOptionInputProps): ReactElement => {
  const options = param.options ?? [];
  const allowCustom = param.allow_custom ?? false;
  const isKnownOption = options.some((o) => o.value === value);
  const isCustomSelected = !isKnownOption && !!value;

  if (options.length === 0) {
    return (
      <input
        type={param.type === 'number' ? 'number' : 'text'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
      />
    );
  }

  const selectValue = !value ? '' : isKnownOption ? value : CUSTOM_SENTINEL;

  const dropdownOptions = [
    ...options.map((o) => ({
      label: o.preview ? `${o.label} — ${o.preview}` : o.label,
      value: o.value,
    })),
    ...(allowCustom ? [{ label: 'Custom…', value: CUSTOM_SENTINEL }] : []),
  ];

  return (
    <div className="space-y-1.5">
      <SelectDropdown
        value={selectValue}
        onChange={(next) => {
          if (next === CUSTOM_SENTINEL) {
            onChange('');
            return;
          }
          onChange(next);
        }}
        options={dropdownOptions}
        placeholder="Select…"
        buttonClassName={FORM_DROPDOWN_BUTTON_CLASS}
      />
      {allowCustom && isCustomSelected && (
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Enter custom value"
          className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
        />
      )}
    </div>
  );
};

export default SourceParamsForm;
