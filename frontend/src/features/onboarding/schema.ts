import { z } from 'zod';
import {
  isAvailableOnboardingPracticeType,
  ONBOARDING_PRACTICE_TYPES,
  ONBOARDING_ROLES,
} from './types';
import { getEmailDomain, isEmailInAllowedDomain } from '@/utils/emailDomain';

export const createOnboardingSchema = (ownerEmail: string) => {
  const ownerDomain = getEmailDomain(ownerEmail);

  return z
    .object({
      firmName: z.string().trim().min(2, 'Enter your firm name'),
      firmAddress: z.string().trim().email('Enter a valid firm email address'),
      contactNumber: z
        .string()
        .trim()
        .refine((value) => !value || /^\d+$/.test(value), {
          message: 'Contact number must contain numbers only',
        }),
      practiceType: z
        .enum(ONBOARDING_PRACTICE_TYPES)
        .refine(isAvailableOnboardingPracticeType, {
          message: 'Select an available practice type',
        }),
      ownerName: z.string().trim().min(2, 'Enter the account owner name'),
      ownerEmail: z
        .string()
        .email('Authenticated user email is required')
        .refine((email) => email.trim().toLowerCase() === ownerEmail.trim().toLowerCase(), {
          message: 'Owner email must match the authenticated user',
        }),
      inviteEmail: z
        .string()
        .trim()
        .refine((email) => !email || z.string().email().safeParse(email).success, {
          message: 'Enter a valid email',
        }),
      inviteRole: z.enum(ONBOARDING_ROLES),
      invitePermissions: z.array(z.string()),
    })
    .superRefine((values, context) => {
      if (!isEmailInAllowedDomain(values.firmAddress, ownerDomain)) {
        context.addIssue({
          code: 'custom',
          path: ['firmAddress'],
          message: ownerDomain
            ? `Firm email must use @${ownerDomain}`
            : 'Firm email must match the owner email domain',
        });
      }

      if (!values.inviteEmail) return;
      if (isEmailInAllowedDomain(values.inviteEmail, ownerDomain)) return;

      context.addIssue({
        code: 'custom',
        path: ['inviteEmail'],
        message: ownerDomain
          ? `Invite must use @${ownerDomain}`
          : 'Invite must match the owner email domain',
      });
    });
};
export { getEmailDomain };
