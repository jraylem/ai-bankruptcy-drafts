import { describe, it, expect } from 'vitest';
import {
  FALLBACK_SOURCE_ICON,
  SOURCE_ICON_COMPONENTS,
} from '@/utils/studio/sourceIconMap';
import type { FieldSource } from '@/types/studio';

const ALL_SOURCES: FieldSource[] = [
  'gmail', 'court_drive', 'case_vector', 'law_practice_vector',
  'constants', 'dependent_on_variable', 'system_generated',
  'group_dropdown_from_gmail', 'group_dropdown_from_court_drive',
  'reco_chips_from_gmail', 'reco_chips_from_court_drive', 'reco_chips_from_case_vector',
  'dropdown_from_gmail', 'dropdown_from_court_drive', 'dropdown_from_case_vector', 'dropdown_from_constants',
  'auto_derived_from_variable',
  'user_input_with_supporting_docs', 'user_input_plain_text', 'user_input_date',
  'reco_chips_from_dependent_variables', 'multi_select_from_case_vector', 'multi_select_from_gmail',
];

describe('sourceIconMap', () => {
  it('has an icon component for every FieldSource', () => {
    for (const s of ALL_SOURCES) {
      expect(SOURCE_ICON_COMPONENTS[s], `missing icon for ${s}`).toBeDefined();
    }
  });

  it('exposes a fallback icon', () => {
    expect(FALLBACK_SOURCE_ICON).toBeDefined();
    expect(typeof FALLBACK_SOURCE_ICON).toBe('function');
  });

  it('all map values are callable (react-icons functional components)', () => {
    for (const Icon of Object.values(SOURCE_ICON_COMPONENTS)) {
      expect(typeof Icon).toBe('function');
    }
  });

  it('groups source variants under the same family icon', () => {
    expect(SOURCE_ICON_COMPONENTS.gmail).toBe(SOURCE_ICON_COMPONENTS.dropdown_from_gmail);
    expect(SOURCE_ICON_COMPONENTS.gmail).toBe(SOURCE_ICON_COMPONENTS.reco_chips_from_gmail);
    expect(SOURCE_ICON_COMPONENTS.gmail).toBe(SOURCE_ICON_COMPONENTS.group_dropdown_from_gmail);
    expect(SOURCE_ICON_COMPONENTS.court_drive).toBe(SOURCE_ICON_COMPONENTS.dropdown_from_court_drive);
    expect(SOURCE_ICON_COMPONENTS.case_vector).toBe(SOURCE_ICON_COMPONENTS.dropdown_from_case_vector);
    expect(SOURCE_ICON_COMPONENTS.constants).toBe(SOURCE_ICON_COMPONENTS.dropdown_from_constants);
  });
});
