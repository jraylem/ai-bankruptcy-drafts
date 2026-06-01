import { useMutation, useQuery } from '@tanstack/react-query';
import { queryClient } from '@/lib/queryClient';
import {
  firmsService,
  type FirmResponse,
  type OnboardingStatus,
  type OnboardingStatusResponse,
} from '@/services/firms.service';
import type { InvitedMember, OnboardingFormValues } from './types';

export const ONBOARDING_STATUS_STALE_TIME_MS = 60 * 1000;

export const onboardingKeys = {
  all: ['onboarding'] as const,
  firm: () => [...onboardingKeys.all, 'firm'] as const,
  status: () => [...onboardingKeys.all, 'status'] as const,
};

class OnboardingApiError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'OnboardingApiError';
  }
}

export const fetchOnboardingStatus = async (): Promise<OnboardingStatus> => {
  const response = await firmsService.getOnboardingStatus();
  if (response.error || !response.data) {
    throw new OnboardingApiError(response.error || 'Unable to load onboarding status');
  }

  return response.data.onboarding_status;
};

export const fetchFirm = async (): Promise<FirmResponse> => {
  const response = await firmsService.getFirm();
  if (response.error || !response.data) {
    throw new OnboardingApiError(response.error || 'Unable to load firm details');
  }

  return response.data;
};

export const useFirmQuery = (enabled = true) =>
  useQuery({
    queryKey: onboardingKeys.firm(),
    queryFn: fetchFirm,
    enabled,
    retry: false,
    staleTime: ONBOARDING_STATUS_STALE_TIME_MS,
  });

export const useOnboardingStatusQuery = (enabled = true) =>
  useQuery({
    queryKey: onboardingKeys.status(),
    queryFn: fetchOnboardingStatus,
    enabled,
    retry: false,
    staleTime: ONBOARDING_STATUS_STALE_TIME_MS,
  });

interface CompleteOnboardingInput {
  values: OnboardingFormValues;
  invites: InvitedMember[];
}

export const useCompleteOnboardingMutation = () =>
  useMutation({
    mutationFn: async ({ values, invites }: CompleteOnboardingInput): Promise<FirmResponse> => {
      const firmResponse = await firmsService.updateFirm({
        name: values.firmName.trim(),
        address: values.firmAddress.trim(),
        firm_type: values.practiceType,
        contact_number: values.contactNumber.trim() || undefined,
      });

      if (firmResponse.error || !firmResponse.data) {
        throw new OnboardingApiError(firmResponse.error || 'Unable to save firm details');
      }

      await Promise.all(
        invites.map(async (member) => {
          const inviteResponse = await firmsService.inviteMember({
            email: member.email,
            role: member.role,
            permissions: member.permissions,
          });

          if (inviteResponse.error) {
            throw new OnboardingApiError(inviteResponse.error);
          }
        })
      );

      return firmResponse.data;
    },
    onSuccess: (firm) => {
      const statusResponse: OnboardingStatusResponse = {
        onboarding_status: firm.onboarding_status,
      };
      queryClient.setQueryData(onboardingKeys.firm(), firm);
      queryClient.setQueryData(onboardingKeys.status(), statusResponse.onboarding_status);
      void queryClient.invalidateQueries({ queryKey: onboardingKeys.status() });
    },
  });
