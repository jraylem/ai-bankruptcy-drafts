import { describe, expect, it } from 'vitest';
import { createOnboardingSchema } from '@/features/onboarding/schema';

const schema = createOnboardingSchema('owner@example.com');
const baseValues = {
  contactNumber: '',
  firmAddress: 'office@example.com',
  firmName: 'CVH Law Group',
  invitePermissions: [],
  inviteRole: 'member' as const,
  ownerEmail: 'owner@example.com',
  ownerName: 'Brix A.',
  practiceType: 'bankruptcy' as const,
};

describe('onboarding schema', () => {
  it('accepts firm details and a same-domain invited member', () => {
    const result = schema.safeParse({
      ...baseValues,
      inviteEmail: 'admin@example.com',
      inviteRole: 'admin',
    });

    expect(result.success).toBe(true);
  });

  it('accepts empty invite fields so onboarding can continue without members', () => {
    const result = schema.safeParse({
      ...baseValues,
      inviteEmail: '',
    });

    expect(result.success).toBe(true);
  });

  it('rejects missing firm name', () => {
    const result = schema.safeParse({
      ...baseValues,
      firmName: '',
      inviteEmail: '',
    });

    expect(result.success).toBe(false);
  });

  it('rejects invalid invited member email', () => {
    const result = schema.safeParse({
      ...baseValues,
      inviteEmail: 'not-an-email',
    });

    expect(result.success).toBe(false);
  });

  it('rejects invalid firm email address', () => {
    const result = schema.safeParse({
      ...baseValues,
      firmAddress: '123 Main Street, Miami, FL',
      inviteEmail: '',
    });

    expect(result.success).toBe(false);
  });

  it('rejects firm email addresses outside the owner email domain', () => {
    const result = schema.safeParse({
      ...baseValues,
      firmAddress: 'office@otherfirm.com',
      inviteEmail: '',
    });

    expect(result.success).toBe(false);
  });

  it('rejects contact numbers with non-numeric characters', () => {
    const result = schema.safeParse({
      ...baseValues,
      contactNumber: '555-1234',
      inviteEmail: '',
    });

    expect(result.success).toBe(false);
  });

  it('rejects invited member emails outside the owner email domain', () => {
    const result = schema.safeParse({
      ...baseValues,
      inviteEmail: 'member@otherfirm.com',
    });

    expect(result.success).toBe(false);
  });

  it('rejects practice types that are not available yet', () => {
    const result = schema.safeParse({
      ...baseValues,
      practiceType: 'family_law',
      inviteEmail: '',
    });

    expect(result.success).toBe(false);
  });
});
