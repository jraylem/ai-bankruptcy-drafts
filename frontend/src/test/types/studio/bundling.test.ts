import { describe, it, expect } from 'vitest';

import {
  countIncompleteSlots,
  isSlotConfigComplete,
  type BranchBundleCompanion,
  type BundleCompanion,
  type FixedBundleCompanion,
  type SlotConfig,
} from '@/types/studio/bundling';

// ─── isSlotConfigComplete ────────────────────────────────────────────

describe('isSlotConfigComplete', () => {
  it('returns false for undefined', () => {
    expect(isSlotConfigComplete(undefined)).toBe(false);
  });

  it('parent_variable: complete when the picked variable name is non-empty', () => {
    expect(
      isSlotConfigComplete({ kind: 'parent_variable', parent_variable: 'case_number' }),
    ).toBe(true);
  });

  it('parent_variable: incomplete when empty or whitespace', () => {
    expect(isSlotConfigComplete({ kind: 'parent_variable', parent_variable: '' })).toBe(false);
    expect(isSlotConfigComplete({ kind: 'parent_variable', parent_variable: '   ' })).toBe(false);
  });

  it('extract_from_draft: complete when instruction is non-empty', () => {
    expect(
      isSlotConfigComplete({
        kind: 'extract_from_draft',
        extract_instruction: 'Pull the docket title',
      }),
    ).toBe(true);
  });

  it('extract_from_draft: incomplete when blank or whitespace-only', () => {
    expect(
      isSlotConfigComplete({ kind: 'extract_from_draft', extract_instruction: '' }),
    ).toBe(false);
    expect(
      isSlotConfigComplete({ kind: 'extract_from_draft', extract_instruction: '   ' }),
    ).toBe(false);
  });

  it('literal: always complete, even when the literal value is intentionally blank', () => {
    expect(isSlotConfigComplete({ kind: 'literal', literal_value: '' })).toBe(true);
    expect(isSlotConfigComplete({ kind: 'literal', literal_value: 'foo' })).toBe(true);
  });
});

// ─── countIncompleteSlots ───────────────────────────────────────────

const filledParentVar = (name: string): SlotConfig => ({
  kind: 'parent_variable',
  parent_variable: name,
});

const blankParentVar: SlotConfig = {
  kind: 'parent_variable',
  parent_variable: '',
};

const requiredSlotsByChild = (specs: Record<string, string[]>) =>
  (childId: string): string[] => specs[childId] ?? [];

describe('countIncompleteSlots', () => {
  it('returns 0 when there are no companions', () => {
    const n = countIncompleteSlots([], requiredSlotsByChild({}));
    expect(n).toBe(0);
  });

  it('counts empty parent_variable on a fixed companion', () => {
    const fixed: FixedBundleCompanion = {
      kind: 'fixed',
      label: 'Cover Sheet',
      child_template_id: 'child-1',
      slot_configurations: { case_no: blankParentVar },
    };
    const n = countIncompleteSlots(
      [fixed],
      requiredSlotsByChild({ 'child-1': ['case_no'] }),
    );
    expect(n).toBe(1);
  });

  it('passes when every required slot has a non-empty value', () => {
    const fixed: FixedBundleCompanion = {
      kind: 'fixed',
      label: 'Cover Sheet',
      child_template_id: 'child-1',
      slot_configurations: {
        case_no: filledParentVar('case_number'),
        docket_title: {
          kind: 'extract_from_draft',
          extract_instruction: 'pull the title',
        },
      },
    };
    const n = countIncompleteSlots(
      [fixed],
      requiredSlotsByChild({ 'child-1': ['case_no', 'docket_title'] }),
    );
    expect(n).toBe(0);
  });

  it('counts missing keys (slot entirely absent from the config map)', () => {
    const fixed: FixedBundleCompanion = {
      kind: 'fixed',
      label: 'Cover Sheet',
      child_template_id: 'child-1',
      slot_configurations: {
        case_no: filledParentVar('case_number'),
        // docket_title intentionally omitted
      },
    };
    const n = countIncompleteSlots(
      [fixed],
      requiredSlotsByChild({ 'child-1': ['case_no', 'docket_title'] }),
    );
    expect(n).toBe(1);
  });

  it('walks every BranchOption on a branch companion', () => {
    const branch: BranchBundleCompanion = {
      kind: 'branch',
      label: 'Notice of Hearing',
      question: 'Notice of hearing?',
      options: [
        {
          label: 'Yes',
          child_template_id: 'child-yes',
          slot_configurations: {
            case_no: filledParentVar('case_number'),
          },
        },
        {
          label: 'No',
          child_template_id: 'child-no',
          slot_configurations: {
            case_no: filledParentVar('case_number'),
            // docket_title missing for the No branch
          },
        },
      ],
    };
    const n = countIncompleteSlots(
      [branch],
      requiredSlotsByChild({
        'child-yes': ['case_no'],
        'child-no': ['case_no', 'docket_title'],
      }),
    );
    expect(n).toBe(1);
  });

  it('treats `literal` slots as always-complete regardless of value', () => {
    const fixed: FixedBundleCompanion = {
      kind: 'fixed',
      label: 'Cover Sheet',
      child_template_id: 'child-1',
      slot_configurations: {
        court_division: { kind: 'literal', literal_value: '' },
      },
    };
    const n = countIncompleteSlots(
      [fixed],
      requiredSlotsByChild({ 'child-1': ['court_division'] }),
    );
    expect(n).toBe(0);
  });

  it('aggregates across multiple companions', () => {
    const a: FixedBundleCompanion = {
      kind: 'fixed',
      label: 'A',
      child_template_id: 'child-a',
      slot_configurations: { x: blankParentVar },
    };
    const b: BranchBundleCompanion = {
      kind: 'branch',
      label: 'B',
      question: '?',
      options: [
        {
          label: 'Y',
          child_template_id: 'child-b',
          slot_configurations: {
            y: { kind: 'extract_from_draft', extract_instruction: '' },
          },
        },
      ],
    };
    const companions: BundleCompanion[] = [a, b];
    const n = countIncompleteSlots(
      companions,
      requiredSlotsByChild({ 'child-a': ['x'], 'child-b': ['y'] }),
    );
    expect(n).toBe(2);
  });

  it('skips slots the child does not declare as inherit_from_parent', () => {
    // requiredSlotsByChild returns [] → nothing required → 0 incomplete even
    // if slot_configurations is wide open.
    const fixed: FixedBundleCompanion = {
      kind: 'fixed',
      label: 'Cover Sheet',
      child_template_id: 'child-1',
      slot_configurations: { stale_field: blankParentVar },
    };
    const n = countIncompleteSlots([fixed], requiredSlotsByChild({ 'child-1': [] }));
    expect(n).toBe(0);
  });
});
