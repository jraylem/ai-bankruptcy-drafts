import type { IconType } from 'react-icons';
import {
  LuBookOpen,
  LuCalendar,
  LuFileUp,
  LuFolder,
  LuHash,
  LuLandmark,
  LuLink,
  LuListChecks,
  LuMail,
  LuPencil,
  LuSettings,
  LuSparkles,
  LuType,
  LuVariable,
} from 'react-icons/lu';
import type { FieldSource } from '@/types/studio';

export const SOURCE_ICON_COMPONENTS: Record<FieldSource, IconType> = {
  gmail: LuMail,
  court_drive: LuLandmark,
  case_vector: LuFolder,
  law_practice_vector: LuBookOpen,
  constants: LuHash,
  dependent_on_variable: LuVariable,
  system_generated: LuSettings,
  group_dropdown_from_gmail: LuMail,
  group_dropdown_from_court_drive: LuLandmark,
  reco_chips_from_gmail: LuMail,
  reco_chips_from_court_drive: LuLandmark,
  reco_chips_from_case_vector: LuFolder,
  dropdown_from_gmail: LuMail,
  dropdown_from_court_drive: LuLandmark,
  dropdown_from_case_vector: LuFolder,
  dropdown_from_constants: LuHash,
  auto_derived_from_variable: LuLink,
  user_input_plain_text: LuPencil,
  user_input_date: LuCalendar,
  user_input_with_supporting_docs: LuFileUp,
  reco_chips_from_dependent_variables: LuSparkles,
  multi_select_from_case_vector: LuListChecks,
  multi_select_from_gmail: LuListChecks,
  inherit_from_parent: LuLink,
};

export const FALLBACK_SOURCE_ICON: IconType = LuType;
