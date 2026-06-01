import type { IconType } from 'react-icons';
import { FiBriefcase, FiFileText, FiHome, FiShield } from 'react-icons/fi';
import { isAvailableOnboardingPracticeType } from './types';
import type { OnboardingPracticeType } from './types';

type BasePracticeOption = {
  description: string;
  icon: IconType;
  label: string;
  value: OnboardingPracticeType;
};

type PracticeOption = BasePracticeOption & {
  isAvailable: boolean;
};

const BASE_ONBOARDING_PRACTICE_OPTIONS: BasePracticeOption[] = [
  {
    description: 'Chapter 7, Chapter 13, motions, claims, and court-drive workflows.',
    icon: FiBriefcase,
    label: 'Bankruptcy',
    value: 'bankruptcy',
  },
  {
    description: 'Matter setup and drafting support for family law teams.',
    icon: FiHome,
    label: 'Family Law',
    value: 'family_law',
  },
  {
    description: 'Case preparation workflows for immigration practices.',
    icon: FiShield,
    label: 'Immigration',
    value: 'immigration',
  },
  {
    description: 'Document workflows for estate planning and probate practices.',
    icon: FiFileText,
    label: 'Estate Planning',
    value: 'estate_planning',
  },
];

export const ONBOARDING_PRACTICE_OPTIONS: PracticeOption[] = BASE_ONBOARDING_PRACTICE_OPTIONS.map(
  (option) => ({
    ...option,
    isAvailable: isAvailableOnboardingPracticeType(option.value),
  })
);

const practiceLabelByValue = new Map(
  ONBOARDING_PRACTICE_OPTIONS.map((option) => [option.value, option.label])
);

export const getPracticeTypeLabel = (practiceType: OnboardingPracticeType): string =>
  practiceLabelByValue.get(practiceType) ?? 'Bankruptcy';
