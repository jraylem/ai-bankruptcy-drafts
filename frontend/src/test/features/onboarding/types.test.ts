import { describe, expect, it } from 'vitest';
import {
  AVAILABLE_ONBOARDING_PRACTICE_TYPES,
  ONBOARDING_PRACTICE_TYPES,
  ONBOARDING_ROLES,
} from '@/features/onboarding/types';

describe('onboarding roles', () => {
  it('only exposes Admin and Member role values from the frontend', () => {
    expect(ONBOARDING_ROLES).toEqual(['admin', 'member']);
  });

  it('exposes Bankruptcy as the only currently available onboarding practice type', () => {
    expect(ONBOARDING_PRACTICE_TYPES).toEqual([
      'bankruptcy',
      'family_law',
      'immigration',
      'estate_planning',
    ]);
    expect(AVAILABLE_ONBOARDING_PRACTICE_TYPES).toEqual(['bankruptcy']);
  });
});
