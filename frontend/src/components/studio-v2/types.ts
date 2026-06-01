export type SourceKind =
  | 'gmail'
  | 'case_file'
  | 'attorney'
  | 'constants'
  | 'current_date'
  | 'author_input'
  | 'derived_from_variable'
  | 'value_from_parent_bundle';

export type TemplateRole = 'single' | 'master' | 'part_of_packet';

// ─── Companion bundling (only meaningful when role === 'master') ──────
// Mirrors the v1 BundleCompanion shape from
// bkdrafts-fe/src/types/studio/bundling.ts (FixedBundleCompanion /
// BranchBundleCompanion / BranchOption). Re-defined here in plain
// paralegal-friendly form for the mock.

export type CompanionKind = 'fixed' | 'branch';

// ─── Slot configuration (how the lead fills a child's inherited fields) ──
// Mirrors v1 SlotConfig from bkdrafts-fe/src/types/studio/bundling.ts.
// Every child variable whose source is `value_from_parent_bundle`
// (v1: `inherit_from_parent`) becomes a slot the lead must fill.

export type SlotConfigKind = 'parent_variable' | 'extract_from_draft' | 'literal';

export interface ParentVariableSlotConfig {
  kind: 'parent_variable';
  parent_variable: string;
}

export interface ExtractFromDraftSlotConfig {
  kind: 'extract_from_draft';
  extract_instruction: string;
}

export interface LiteralSlotConfig {
  kind: 'literal';
  literal_value: string;
}

export type SlotConfig =
  | ParentVariableSlotConfig
  | ExtractFromDraftSlotConfig
  | LiteralSlotConfig;

export interface BranchOption {
  id: string;
  option_label: string;
  child_template_id: string | null;
  slot_configurations: Record<string, SlotConfig>;
}

export interface FixedCompanion {
  id: string;
  kind: 'fixed';
  label: string;
  child_template_id: string | null;
  slot_configurations: Record<string, SlotConfig>;
}

export interface BranchCompanion {
  id: string;
  kind: 'branch';
  label: string;
  question: string;
  options: BranchOption[];
}

export type BundleCompanion = FixedCompanion | BranchCompanion;

export interface TemplateConfig {
  role: TemplateRole;
  // Only meaningful when role === 'master'. Mirrors the v1 BundleCompanion
  // list on a parent template — child_only templates just declare themselves
  // as companions and don't store a back-reference (the parent's array is the
  // source of truth for ownership).
  companions: BundleCompanion[];
}

export const defaultTemplateConfig = (): TemplateConfig => ({
  role: 'single',
  companions: [],
});

const randomId = (): string =>
  `cmp-${Math.random().toString(36).slice(2, 8)}`;

export const newFixedCompanion = (): FixedCompanion => ({
  id: randomId(),
  kind: 'fixed',
  label: 'New companion',
  child_template_id: null,
  slot_configurations: {},
});

export const newBranchCompanion = (): BranchCompanion => ({
  id: randomId(),
  kind: 'branch',
  label: 'New companion',
  question: '',
  options: [
    {
      id: randomId(),
      option_label: 'Option 1',
      child_template_id: null,
      slot_configurations: {},
    },
    {
      id: randomId(),
      option_label: 'Option 2',
      child_template_id: null,
      slot_configurations: {},
    },
  ],
});

export const newBranchOption = (): BranchOption => ({
  id: randomId(),
  option_label: 'New option',
  child_template_id: null,
  slot_configurations: {},
});

// Default slot config when a paralegal picks a child but hasn't configured
// a specific slot yet. We start with 'parent_variable' (empty) as the most
// common case — the next-most-likely answer is "use the lead's field of the
// same name."
export const newSlotConfig = (kind: SlotConfigKind = 'parent_variable'): SlotConfig => {
  if (kind === 'parent_variable') return { kind, parent_variable: '' };
  if (kind === 'extract_from_draft') return { kind, extract_instruction: '' };
  return { kind, literal_value: '' };
};

interface TemplateRoleMeta {
  key: TemplateRole;
  label: string;
  description: string;
  example: string;
}

export const TEMPLATE_ROLES: TemplateRoleMeta[] = [
  {
    key: 'single',
    label: 'Standalone filing',
    description:
      'Files on its own. The simplest and most common choice.',
    example: 'e.g. a one-off motion to extend the automatic stay.',
  },
  {
    key: 'master',
    label: 'Lead filing',
    description:
      'Runs once, then drives one or more companion filings.',
    example:
      'e.g. a 341(a) meeting notice that drives one creditor letter per claim.',
  },
  {
    key: 'part_of_packet',
    label: 'Companion filing',
    description:
      'Files alongside a lead — repeats once per item the lead decides.',
    example: 'e.g. a creditor letter filed alongside a 341(a) notice.',
  },
];

export type PresentationShape = 'raw' | 'dropdown' | 'chip' | 'multi_select';

export type AuthorInputKind = 'plain_text' | 'date' | 'with_docs';

export interface WizardSourceParams {
  source: SourceKind;
  extraction_prompt: string | null;
  presentation_shape: PresentationShape;
  output_expectation: string | null;
  label: string | null;
  example_format: string | null;
  min_picks: number;
  max_picks: number;
  author_input_kind: AuthorInputKind | null;
  constants_short_code: string | null;
  date_format: string;
  dependent_variable: string | null;
  parent_bundle_fallback: string | null;
  attorney_id: string | null;
  // Other fields whose resolved values this query relies on (gmail / case_file).
  // The agent waits for these to resolve first, then has their values
  // available when processing extraction_prompt.
  query_dependencies: string[];
  // Optional post-resolution web-search enhancement. When set, the
  // resolved value (regardless of source) is run through Claude's
  // web search and reshaped per this instruction. Slow + costly —
  // leave null/empty to skip. Soft-fails to the unenhanced value.
  web_enhance_instruction: string | null;
}

export interface StudioVariable {
  template_variable: string;
  description: string;
  template_property_marker: string | null;
  template_identifying_text_match: string | null;
  params: WizardSourceParams | null;
}

export interface StudioTemplate {
  id: string;
  name: string;
  config: TemplateConfig;
  variables: StudioVariable[];
  updatedRelative: string;
  // Phase 3 publish state. `publishedAt` is null until first
  // /publish; `hasUnpublishedChanges` is computed BE-side as
  // `updated_at > published_at` so the working draft drifting
  // from the published snapshot is visible everywhere
  // (PublishStep status pill, TemplatesRail pill, etc.).
  publishedAt: string | null;
  hasUnpublishedChanges: boolean;
  // Field counts populated by the list endpoint so the rail's
  // status pill works without lazy-loading every template's full
  // spec. `variables` is empty on list-fetched templates and full
  // on single-row-fetched templates; these counts are authoritative
  // either way.
  totalFields: number;
  configuredFields: number;
}

export const defaultWizardParams = (): WizardSourceParams => ({
  source: 'gmail',
  extraction_prompt: null,
  presentation_shape: 'raw',
  output_expectation: null,
  label: null,
  example_format: null,
  min_picks: 1,
  max_picks: 5,
  author_input_kind: null,
  constants_short_code: null,
  date_format: '%B %-d, %Y',
  dependent_variable: null,
  parent_bundle_fallback: null,
  attorney_id: null,
  query_dependencies: [],
  web_enhance_instruction: null,
});

interface SourceMeta {
  key: SourceKind;
  label: string;
  description: string;
  example: string;
  iconKey: SourceKind;
  acceptsShape: boolean;
  needsExtractionPrompt: boolean;
  // Restrict which presentation shapes are valid for this source. When
  // undefined, all shapes are allowed (the default for email/case-file).
  allowedShapes?: PresentationShape[];
}

export const SOURCE_KINDS: SourceMeta[] = [
  {
    key: 'gmail',
    label: 'Email Inbox',
    description: 'Search the firm\'s email inbox for the right message.',
    example: 'e.g. "the debtor\'s most recent paystub email"',
    iconKey: 'gmail',
    acceptsShape: true,
    needsExtractionPrompt: true,
  },
  {
    key: 'case_file',
    label: 'Case Documents',
    description: 'Search the petition and other files uploaded for this case.',
    example: 'e.g. "creditors with claims over $1,000"',
    iconKey: 'case_file',
    acceptsShape: true,
    needsExtractionPrompt: true,
  },
  {
    key: 'attorney',
    label: 'Attorney',
    description: 'Pick from the firm\'s attorney roster.',
    example: 'e.g. the bankruptcy attorney signing this filing',
    iconKey: 'attorney',
    acceptsShape: true,
    needsExtractionPrompt: false,
    allowedShapes: ['raw', 'dropdown', 'multi_select'],
  },
  {
    key: 'constants',
    label: 'Firm Constant',
    description: 'A single saved firm value — looked up by name, never picked at draft time.',
    example: 'e.g. firm address, default disclaimer, fee schedule',
    iconKey: 'constants',
    acceptsShape: false,
    needsExtractionPrompt: false,
  },
  {
    key: 'current_date',
    label: 'Today\'s Date',
    description: 'Insert today\'s date in any format you choose.',
    example: 'e.g. "April 1, 2026" or "04/01/2026"',
    iconKey: 'current_date',
    acceptsShape: false,
    needsExtractionPrompt: false,
  },
  {
    key: 'author_input',
    label: 'Type It Yourself',
    description: 'You\'ll type or pick the value when drafting the document.',
    example: 'Text · Date picker · Text with file upload',
    iconKey: 'author_input',
    acceptsShape: false,
    needsExtractionPrompt: false,
  },
  {
    key: 'derived_from_variable',
    label: 'Based on Another Field',
    description: 'Calculate this value from another field using a short instruction.',
    example: 'e.g. "say \'are\' if there are multiple creditors, otherwise \'is\'"',
    iconKey: 'derived_from_variable',
    acceptsShape: false,
    needsExtractionPrompt: true,
  },
  {
    key: 'value_from_parent_bundle',
    label: 'From the Lead Filing',
    description:
      'Reuse a value already filled in by the lead filing this template is a companion to.',
    example: 'For companion filings in a 341(a) packet, creditor letter sets, etc.',
    iconKey: 'value_from_parent_bundle',
    acceptsShape: false,
    needsExtractionPrompt: false,
  },
];

interface ShapeMeta {
  key: PresentationShape;
  label: string;
  description: string;
  preview: string;
}

export const PRESENTATION_SHAPES: ShapeMeta[] = [
  {
    key: 'raw',
    label: 'Auto-fill (no pick)',
    description: 'The agent extracts a single value and fills it in automatically.',
    preview: 'value → "John Smith"',
  },
  {
    key: 'dropdown',
    label: 'Pick one from a list',
    description: 'The agent shows several candidates — you pick one.',
    preview: '○ Option A   ◉ Option B   ○ Option C',
  },
  {
    key: 'chip',
    label: 'Smart suggestions',
    description: 'The agent shows 1–3 quick suggestions — pick one or edit.',
    preview: '[ Suggestion 1 ]  [ Suggestion 2 ]  [ Edit… ]',
  },
  {
    key: 'multi_select',
    label: 'Pick several from a list',
    description: 'The agent shows several candidates — you pick more than one.',
    preview: '☑ Option A   ☐ Option B   ☑ Option C   ☑ Option D',
  },
];

interface AuthorInputMeta {
  key: AuthorInputKind;
  label: string;
  description: string;
}

export const AUTHOR_INPUT_KINDS: AuthorInputMeta[] = [
  {
    key: 'plain_text',
    label: 'Text',
    description: 'Type the value into a text box.',
  },
  {
    key: 'date',
    label: 'Date picker',
    description: 'Pick a date from a calendar.',
  },
  {
    key: 'with_docs',
    label: 'Text + file upload',
    description: 'Type a value and attach one or more supporting files.',
  },
];
